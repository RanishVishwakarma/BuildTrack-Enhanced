import { AlertTriangle, BookOpen, Brain, CheckCircle2, Database, GitBranch, Loader2, PenLine, RefreshCw, Search, Send, ShieldCheck, Square, Wrench, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { Button } from "../../../components/ui/Button.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { cn } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { getAgentStatus, rebuildAgentIndex, streamAgentChat } from "../services/aiService.js";
import { AnswerText } from "./AskAiTab.jsx";

const EXAMPLES = [
  "Will any project be delayed because of a late material order?",
  "What do the safety reports say about scaffolding?",
  "Which tasks are overdue, and what should the site engineer do first?",
];

// One line of the live timeline per agent event (backend app/modules/agent/graph.py).
function describe(step) {
  switch (step.type) {
    case "index":
      return { icon: Database, text: step.label };
    case "memory":
      return { icon: Brain, text: "Recalled related earlier answers", detail: step.items?.join(" · ") };
    case "route":
      return { icon: GitBranch, text: `Supervisor routed to ${step.agents.join(" + ")}${step.fallback ? " (keyword fallback)" : ""}`, detail: step.reason };
    case "tool":
      return {
        icon: step.tool === "search_site_records" ? Search : Wrench,
        text: `${step.agent}: ${step.label}`,
        detail: [step.thought, step.input && Object.keys(step.input).length ? JSON.stringify(step.input) : ""].filter(Boolean).join(" — "),
      };
    case "result":
      return { icon: step.ok ? CheckCircle2 : XCircle, tone: step.ok ? "success" : "danger", text: `${step.agent}: ${step.ok ? "got results" : "tool refused or failed"}${step.sources ? ` · ${step.sources} record(s)` : ""}` };
    case "error":
      return { icon: AlertTriangle, tone: "warning", text: `${step.agent}: invalid step rejected, asked again`, detail: step.message };
    case "fallback":
      return { icon: Wrench, tone: "warning", text: `${step.agent}: chose no tool, so ran ${step.label.toLowerCase()} to ground the answer` };
    case "finish":
      return { icon: CheckCircle2, text: `${step.agent} finished`, detail: step.thought };
    case "draft":
      return { icon: PenLine, text: step.attempt > 1 ? `Writer redrafted the answer (attempt ${step.attempt})` : "Writer drafted the answer" };
    case "check":
      if (step.ok) return { icon: ShieldCheck, tone: "success", text: "Checker: every figure matches the records" };
      return {
        icon: AlertTriangle,
        tone: "warning",
        text: step.retry ? "Checker: figures not found in records, sent back to the writer" : "Checker: figures could not be confirmed and are flagged",
        detail: step.missing?.join(", "),
      };
    default:
      return { icon: BookOpen, text: step.type };
  }
}

const TONES = { success: "text-success", warning: "text-warning", danger: "text-danger" };

function Timeline({ steps, running }) {
  return (
    <ol className="space-y-2" aria-label="Agent steps">
      {steps.map((step, index) => {
        const { icon: Icon, text, detail, tone } = describe(step);
        return (
          <li className="flex gap-2 text-sm" key={index}>
            <Icon aria-hidden="true" className={cn("mt-0.5 h-4 w-4 shrink-0", TONES[tone] || "text-muted")} />
            <div className="min-w-0">
              <p className="text-foreground">{text}</p>
              {detail ? <p className="break-words text-xs text-muted">{detail}</p> : null}
            </div>
          </li>
        );
      })}
      {running ? (
        <li className="flex items-center gap-2 text-sm text-muted" role="status">
          <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> Working…
        </li>
      ) : null}
    </ol>
  );
}

function Run({ run }) {
  return (
    <article className="card space-y-4 p-4">
      <p className="text-sm font-semibold text-foreground">{run.question}</p>
      <details className="rounded-md border border-border p-3" open={!run.final}>
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted">
          Agent steps ({run.steps.length}){run.seconds ? ` · ${run.seconds}s` : ""}
        </summary>
        <div className="mt-3"><Timeline running={!run.final && !run.error} steps={run.steps} /></div>
      </details>
      {run.error ? <p className="text-sm text-danger" role="alert">{run.error}</p> : null}
      {run.final ? (
        <div className="space-y-3">
          <AnswerText text={run.final.answer} />
          <p className={cn("inline-flex items-center gap-1 text-xs", run.final.verified ? "text-success" : "text-warning")}>
            {run.final.verified ? <ShieldCheck aria-hidden="true" className="h-3.5 w-3.5" /> : <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" />}
            {run.final.verified ? "Verified against your records" : "Some figures could not be verified"}
          </p>
          {run.final.sources?.length ? (
            <details className="text-xs text-muted">
              <summary className="cursor-pointer">Sources ({run.final.sources.length})</summary>
              <ul className="mt-1 space-y-0.5">{run.final.sources.map((s) => <li key={`${s.type}-${s.id}`}>{s.type.replace(/_/g, " ")}: {s.label}</li>)}</ul>
            </details>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export function AgentTab() {
  const status = useAsyncData(getAgentStatus, []);
  const { run: act, isPending } = useAction();
  const [runs, setRuns] = useState([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const conversationId = useRef(null);
  const abort = useRef(null);
  const info = status.data;
  const ready = Boolean(info?.reachable && info?.model_available);

  useEffect(() => () => abort.current?.abort(), []);

  function update(fn) {
    setRuns((current) => [...current.slice(0, -1), fn(current[current.length - 1])]);
  }

  async function ask(text) {
    const question = String(text ?? input).trim();
    if (!question || running) return;
    setInput("");
    setRunning(true);
    const started = Date.now();
    setRuns((current) => [...current, { question, steps: [], final: null, error: "" }]);
    abort.current = new AbortController();
    try {
      await streamAgentChat(question, conversationId.current, (event) => {
        if (event.type === "step") update((r) => ({ ...r, steps: [...r.steps, event.step] }));
        if (event.type === "final") update((r) => ({ ...r, final: event, seconds: Math.round((Date.now() - started) / 1000) }));
        if (event.type === "error") update((r) => ({ ...r, error: event.message }));
        if (event.type === "saved") conversationId.current = event.conversation_id;
      }, abort.current.signal);
    } catch (error) {
      if (error.name !== "AbortError") update((r) => ({ ...r, error: error.message || "Agent mode failed." }));
      else update((r) => ({ ...r, error: "Stopped." }));
    } finally {
      setRunning(false);
      status.reload();
    }
  }

  async function reindex() {
    const result = await act("index", rebuildAgentIndex, { error: "Unable to rebuild the search index." });
    if (result) {
      toast.success(`Search index rebuilt: ${result.chunks} passages.`);
      status.reload();
    }
  }

  function startOver() {
    conversationId.current = null;
    setRuns([]);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
      <section className="space-y-4">
        {!runs.length ? (
          <div className="card p-5">
            <p className="text-sm font-semibold text-foreground">Multi-agent mode</p>
            <p className="mt-1 text-sm text-muted">
              A supervisor sends your question to specialist agents. They choose tools, search site records and
              work in parallel; a checker confirms every figure against your records before you see the answer.
              It runs on a free model on this computer and can only read what you are allowed to see.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {EXAMPLES.map((q) => (
                <button className="rounded-full border border-border px-3 py-1.5 text-xs text-foreground hover:bg-subtle disabled:opacity-50" disabled={!ready || running} key={q} onClick={() => ask(q)} type="button">
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : runs.map((r, index) => <Run key={index} run={r} />)}
        <form className="card flex items-end gap-2 p-3" onSubmit={(event) => { event.preventDefault(); ask(); }}>
          <label className="sr-only" htmlFor="agent-question">Your question</label>
          <textarea
            className="max-h-40 min-h-[44px] flex-1 resize-y rounded-md border border-input bg-surface px-3 py-2 text-sm"
            disabled={!ready}
            id="agent-question"
            maxLength={2000}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); ask(); } }}
            placeholder={ready ? "e.g. Will Tower A be delayed because of the cement order?" : "Agent mode is not ready"}
            rows={1}
            value={input}
          />
          {running ? (
            <Button aria-label="Stop" onClick={() => abort.current?.abort()} type="button" variant="secondary"><Square className="h-4 w-4" /></Button>
          ) : (
            <Button aria-label="Ask the agents" disabled={!ready || !input.trim()} type="submit"><Send className="h-4 w-4" /></Button>
          )}
        </form>
        {runs.length ? <Button disabled={running} onClick={startOver} size="sm" variant="secondary">New conversation</Button> : null}
      </section>

      <aside className="card h-fit space-y-3 p-4 text-sm" aria-label="Agent mode status">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Setup</p>
        {status.loading && !info ? <p className="text-muted">Checking…</p> : null}
        {status.error ? <p className="text-danger">{getApiErrorMessage(status.error)}</p> : null}
        {info ? (
          <>
            <dl className="space-y-1">
              <div className="flex justify-between gap-2"><dt className="text-muted">Model</dt><dd className="font-medium">{info.model}</dd></div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Ollama</dt>
                <dd className={info.reachable ? "text-success" : "text-danger"}>{info.reachable ? (info.model_available ? "Ready" : "Model missing") : "Not running"}</dd>
              </div>
              <div className="flex justify-between gap-2"><dt className="text-muted">Search</dt><dd className="font-medium">{info.embedder}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted">Indexed passages</dt><dd className="font-medium">{info.chunks}</dd></div>
            </dl>
            {!info.reachable ? <p className="text-xs text-warning">Start Ollama on this computer to use agent mode.</p> : null}
            {info.reachable && !info.model_available ? <p className="text-xs text-warning">Run <code>ollama pull {info.model}</code>.</p> : null}
            {info.embedder !== info.embed_model ? (
              <p className="text-xs text-muted">Using local keyword vectors. For meaning-based search run <code>ollama pull {info.embed_model}</code>, then rebuild.</p>
            ) : null}
            {info.can_index ? (
              <Button disabled={isPending("index") || running} onClick={reindex} size="sm" variant="secondary">
                <RefreshCw className="h-4 w-4" /> {isPending("index") ? "Rebuilding…" : "Rebuild search index"}
              </Button>
            ) : null}
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Your agents</p>
              <ul className="space-y-1">
                {info.specialists.map((s) => (
                  <li key={s.name}>
                    <span className="font-medium">{s.label}</span>
                    <span className="text-xs text-muted"> · {s.tools.length} tools</span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        ) : null}
      </aside>
    </div>
  );
}
