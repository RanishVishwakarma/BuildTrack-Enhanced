"""RAG store for the agents (Chroma).

Two kinds of entries share one collection:

* site records - safety reports, improvement suggestions, saved reports and
  project descriptions, chunked and embedded so agents can search them;
* memory - each user's past agent questions and answers (long-term memory).

Every entry carries `kind`, `project_id` and `owner_id`. Searches are
filtered in Chroma by what the user may read (permission per kind, their
projects, their own entries) and the hits are checked again in Python, so
retrieval can never surface a record the user could not open in the app.
Anonymous safety reports are indexed without the reporter.
"""

import hashlib
import math
import re
from dataclasses import dataclass

import httpx
from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.modules.intelligence.data import Scope

# kind -> permissions that allow reading it (None = owner only)
KIND_PERMISSIONS: dict[str, tuple[str, ...] | None] = {
    "safety_report": ("safety_reports.read.assigned",),
    "suggestion": ("suggestions.review.assigned",),
    "report": ("reports.read.assigned", "reports.generate"),
    "project": ("projects.read.all", "projects.read.assigned"),
    "memory": None,
}
CHUNK_CHARS = 900


class HashingEmbeddings(Embeddings):
    """Local fallback when no Ollama embedding model is pulled: signed hashed
    word and bigram counts. Lexical rather than semantic, but deterministic,
    offline and good enough to find records that share the question's words."""

    name = "hashing-512"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        vec = [0.0] * self.dim
        for gram in words + [f"{a} {b}" for a, b in zip(words, words[1:])]:
            digest = hashlib.blake2b(gram.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            vec[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def choose_embeddings() -> Embeddings:
    """Ollama's embedding model when it is pulled, else the local fallback."""
    try:
        tags = httpx.get(f"{settings.ollama_url.rstrip('/')}/api/tags", timeout=3).json()
        names = {m.get("name") for m in tags.get("models", [])}
    except Exception:
        names = set()
    model = settings.agent_embed_model
    if model in names or f"{model}:latest" in names:
        from langchain_ollama import OllamaEmbeddings

        embeddings = OllamaEmbeddings(model=model, base_url=settings.ollama_url)
        embeddings.name = model  # type: ignore[attr-defined]
        return embeddings
    return HashingEmbeddings()


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on paragraph/sentence boundaries into pieces of about `size`."""
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if len(text) <= size:
        return [text] if text else []
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?\n])\s+", text):
        if current and len(current) + len(sentence) > size:
            parts.append(current.strip())
            current = ""
        current += sentence + " "
    if current.strip():
        parts.append(current.strip())
    return parts


@dataclass
class Hit:
    text: str
    kind: str
    label: str
    record_id: str
    project_id: str
    score: float

    def source(self) -> dict:
        return {"type": self.kind, "id": self.record_id, "label": self.label}


class KnowledgeStore:
    def __init__(self, client=None, embeddings: Embeddings | None = None, name: str | None = None):
        import chromadb

        self.embeddings = embeddings or choose_embeddings()
        self.embedder = getattr(self.embeddings, "name", type(self.embeddings).__name__)
        if client is None:
            settings.agent_store_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(settings.agent_store_dir))
        # One collection per embedder: vectors of different models never mix.
        safe = re.sub(r"[^a-zA-Z0-9]+", "-", self.embedder).strip("-")
        self.collection = client.get_or_create_collection(
            name or f"buildtrack-{safe}", embedding_function=None, configuration={"hnsw": {"space": "cosine"}}
        )

    # ----------------------------------------------------------- writing
    def _upsert(self, entry_id: str, text: str, kind: str, label: str, record_id: str, project_id: str = "", owner_id: str = "") -> int:
        pieces = chunks(text)
        if not pieces:
            return 0
        self.collection.delete(where={"entry": entry_id})
        ids = [f"{entry_id}#{i}" for i in range(len(pieces))]
        meta = {"entry": entry_id, "kind": kind, "label": label[:200], "record_id": record_id, "project_id": project_id or "", "owner_id": owner_id or ""}
        self.collection.upsert(ids=ids, documents=pieces, embeddings=self.embeddings.embed_documents(pieces), metadatas=[meta] * len(pieces))
        return len(pieces)

    async def index_records(self, db) -> dict:
        """(Re)index site records. Safe to run any time; entries are replaced."""
        counts = {"safety_report": 0, "suggestion": 0, "report": 0, "project": 0}
        async for r in db.safety_reports.find({}):
            text = (f"Safety report ({r.get('report_type', '')}, severity {r.get('severity', '')}, status {r.get('status', '')}): "
                    f"{r.get('title', '')}. Location: {r.get('location') or 'not given'}. {r.get('description', '')} "
                    f"Immediate action: {r.get('immediate_action_taken') or 'none recorded'}.")  # never the reporter
            counts["safety_report"] += self._upsert(f"safety:{r['_id']}", text, "safety_report", r.get("title") or "Safety report", str(r["_id"]), str(r.get("project_id") or ""))
        async for r in db.suggestions.find({}):
            text = (f"Improvement suggestion ({r.get('category', '')}, status {r.get('status', '')}): {r.get('title', '')}. "
                    f"Problem: {r.get('problem', '')} Proposed solution: {r.get('proposed_solution', '')} Expected benefit: {r.get('expected_benefit') or ''}")
            counts["suggestion"] += self._upsert(f"suggestion:{r['_id']}", text, "suggestion", r.get("title") or "Suggestion", str(r["_id"]),
                                                 str(r.get("project_id") or ""), str(r.get("submitted_by") or ""))
        async for r in db.generated_reports.find({}):
            report = r.get("report") or {}
            lines = [str(report.get("title") or r.get("type") or "Report"), str(r.get("ai_summary") or "")]
            for section in report.get("sections") or []:
                items = section.get("items") or section.get("rows") or []
                rendered = [", ".join(map(str, i)) if isinstance(i, list) else (f"{i.get('label')}: {i.get('value')}" if isinstance(i, dict) else str(i)) for i in items[:20]]
                lines.append(f"{section.get('title', '')}: " + "; ".join(rendered))
            created = r.get("created_at")
            label = f"{report.get('title') or r.get('type')} ({created:%d %b %Y})" if hasattr(created, "strftime") else str(report.get("title") or "Report")
            counts["report"] += self._upsert(f"report:{r['_id']}", "\n".join(lines), "report", label, str(r["_id"]), str(r.get("project_id") or ""))
        async for p in db.projects.find({}):
            text = f"Project {p.get('name', '')}: {p.get('description') or ''} Location: {p.get('location') or ''}. Status: {p.get('status') or ''}."
            counts["project"] += self._upsert(f"project:{p['_id']}", text, "project", p.get("name") or "Project", str(p["_id"]), str(p["_id"]))
        return counts

    def remember(self, user_id: str, question: str, answer: str, run_id: str) -> None:
        """Long-term memory: the user's question and the verified answer."""
        self._upsert(f"memory:{run_id}", f"Earlier question: {question}\nAnswer given: {answer[:1500]}", "memory", question[:120], run_id, owner_id=str(user_id))

    # ----------------------------------------------------------- reading
    def readable_kinds(self, scope: Scope) -> list[str]:
        return [kind for kind, perms in KIND_PERMISSIONS.items() if perms and scope.can(*perms)]

    def _allowed(self, scope: Scope, meta: dict) -> bool:
        if meta.get("owner_id") and meta["owner_id"] == str(scope.user["_id"]):
            return True
        if meta.get("kind") not in self.readable_kinds(scope):
            return False
        project_id = meta.get("project_id") or ""
        return scope.project_ids is None or (bool(project_id) and project_id in scope.project_ids)

    def _where(self, scope: Scope, kinds: list[str] | None) -> dict:
        own = {"owner_id": str(scope.user["_id"])}
        readable = [k for k in self.readable_kinds(scope) if not kinds or k in kinds]
        if not readable:
            return own
        shared: dict = {"kind": {"$in": readable}}
        if scope.project_ids is not None:
            shared = {"$and": [shared, {"project_id": {"$in": sorted(scope.project_ids) or ["-"]}}]}
        if kinds and "memory" not in kinds:
            # Own entries of the requested kinds only (e.g. own suggestions).
            own = {"$and": [own, {"kind": {"$in": kinds}}]}
        return {"$or": [shared, own]}

    def search(self, scope: Scope, query: str, k: int = 4, kinds: list[str] | None = None) -> list[Hit]:
        if not query.strip() or self.collection.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[self.embeddings.embed_query(query)], n_results=min(k * 3, 30), where=self._where(scope, kinds),
        )
        hits, seen = [], set()
        for text, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
            if not self._allowed(scope, meta) or (kinds and meta.get("kind") not in kinds):
                continue  # defence in depth: the filter above should already exclude it
            if meta["entry"] in seen:
                continue
            seen.add(meta["entry"])
            hits.append(Hit(text, meta["kind"], meta["label"], meta["record_id"], meta.get("project_id", ""), round(1 - float(distance), 3)))
            if len(hits) == k:
                break
        return hits

    def recall(self, scope: Scope, query: str, k: int = 2) -> list[Hit]:
        return [h for h in self.search(scope, query, k=k, kinds=["memory"]) if h.score >= 0.35]

    def stats(self) -> dict:
        return {"embedder": self.embedder, "chunks": self.collection.count()}
