import { Bot, Loader2, MessageSquarePlus, Send, Trash2, User, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { Button } from "../../../components/ui/Button.jsx";
import { confirmAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { cn, formatDateTime } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { deleteConversation, getConversation, getConversations, getSuggestedQuestions, sendChat } from "../services/aiService.js";

// Renders assistant text: paragraphs and "-" / "1." lists, no HTML.
function AnswerText({ text }) {
  const blocks = String(text || "").split(/\n{2,}/);
  return (
    <div className="space-y-2 text-sm leading-relaxed text-foreground">
      {blocks.map((block, index) => {
        const lines = block.split("\n");
        if (lines.every((line) => /^\s*([-*•]|\d+[.)])\s+/.test(line))) {
          return <ul className="list-disc space-y-1 pl-5" key={index}>{lines.map((line, i) => <li key={i}>{line.replace(/^\s*([-*•]|\d+[.)])\s+/, "").replace(/\*\*/g, "")}</li>)}</ul>;
        }
        return <p className="whitespace-pre-line" key={index}>{block.replace(/\*\*/g, "")}</p>;
      })}
    </div>
  );
}

function Message({ message }) {
  if (message.role === "system") return <p className="rounded-md bg-subtle px-3 py-2 text-xs text-muted">{message.text}</p>;
  const mine = message.role === "user";
  return (
    <div className={cn("flex gap-3", mine && "flex-row-reverse")}>
      <span className={cn("mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full", mine ? "bg-primary text-primary-foreground" : "bg-subtle text-foreground")} aria-hidden="true">
        {mine ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </span>
      <div className={cn("max-w-[85%] rounded-lg border px-4 py-3", mine ? "border-primary/20 bg-primary/5" : "border-border bg-surface")}>
        {message.tools?.length ? (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {message.tools.map((tool, index) => (
              <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]", tool.ok ? "border-border text-muted" : "border-danger/30 text-danger")} key={index}>
                <Wrench aria-hidden="true" className="h-3 w-3" /> {tool.label}{tool.ok ? "" : " (not permitted)"}
              </span>
            ))}
          </div>
        ) : null}
        {mine ? <p className="whitespace-pre-line text-sm text-foreground">{message.text}</p> : null}
        {!mine && message.text ? <AnswerText text={message.text} /> : null}
        {!mine && message.error ? <p className="text-sm text-danger" role="alert">{message.error}</p> : null}
        {message.sources?.length ? (
          <details className="mt-3 text-xs text-muted">
            <summary className="cursor-pointer">Sources ({message.sources.length})</summary>
            <ul className="mt-1 space-y-0.5">{message.sources.map((s) => <li key={`${s.type}-${s.id}`}>{s.type.replace(/_/g, " ")}: {s.label}</li>)}</ul>
          </details>
        ) : null}
        {message.at ? <p className="mt-2 text-[11px] text-muted">{formatDateTime(message.at)}{message.engine ? ` · ${message.engine}` : ""}</p> : null}
      </div>
    </div>
  );
}

export function AskAiTab({ status }) {
  const conversations = useAsyncData(getConversations, [], { initialData: [] });
  const suggestions = useAsyncData(getSuggestedQuestions, [], { initialData: [] });
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);
  // Chat works with the free engines too (quick answers or a local model);
  // only "Claude selected but not enabled" leaves it unavailable.
  const configured = Boolean(status?.chat_available ?? status?.configured);
  const localModel = status?.local_model;

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  async function open(id) {
    try {
      const conversation = await getConversation(id);
      setConversationId(id);
      setMessages(conversation.messages || []);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Unable to open the conversation."));
    }
  }

  function startNew() {
    setConversationId(null);
    setMessages([]);
  }

  async function remove(id) {
    if (!confirmAction("Delete this conversation?")) return;
    try {
      await deleteConversation(id);
      if (id === conversationId) startNew();
      conversations.reload();
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Unable to delete."));
    }
  }

  async function ask(text) {
    const message = String(text ?? input).trim();
    if (!message || sending) return;
    setInput("");
    setSending(true);
    setMessages((current) => [...current, { role: "user", text: message, at: new Date().toISOString() }]);
    try {
      const result = await sendChat(message, conversationId);
      setConversationId(result.conversation_id);
      setMessages((current) => [
        ...current,
        ...(result.notice ? [{ role: "system", text: result.notice }] : []),
        { role: "assistant", text: result.answer, error: result.error, tools: result.tools, sources: result.sources, engine: result.engine, at: new Date().toISOString() },
      ]);
      conversations.reload();
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", text: "", error: getApiErrorMessage(error, "The assistant could not answer."), at: new Date().toISOString() }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <aside className="card flex max-h-[70vh] flex-col gap-2 p-3">
        <Button onClick={startNew} size="sm" variant="secondary"><MessageSquarePlus className="h-4 w-4" /> New conversation</Button>
        <ul className="-mx-1 flex-1 space-y-1 overflow-y-auto">
          {(conversations.data || []).map((c) => (
            <li className="group flex items-center gap-1" key={c.id}>
              <button className={cn("min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-left text-sm", c.id === conversationId ? "bg-subtle font-semibold text-foreground" : "text-muted hover:bg-subtle")} onClick={() => open(c.id)} type="button">
                {c.title || "Conversation"}
              </button>
              <button aria-label={`Delete ${c.title}`} className="rounded p-1 text-muted opacity-0 hover:text-danger group-hover:opacity-100 focus:opacity-100" onClick={() => remove(c.id)} type="button">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
          {!conversations.data?.length ? <li className="px-2 text-xs text-muted">No conversations yet.</li> : null}
        </ul>
      </aside>

      <section className="card flex min-h-[60vh] flex-col p-0">
        {!configured ? (
          <p className="m-4 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning" role="status">
            The assistant is not available: Claude is selected on the server but not enabled. Set AI_PROVIDER=quick or ollama for free answers. The Overview, reports and insights still work.
          </p>
        ) : null}
        {configured && status?.chat_engine ? (
          <p className="mx-4 mt-3 text-xs text-muted" role="status">
            Answering with: <span className="font-semibold text-foreground">{status.chat_engine}</span>
            {status.chat_provider === "quick" ? " · free, answers common questions from your records" : ""}
            {status.chat_provider === "ollama" ? ` · free, runs on this computer (${localModel?.name || "local model"})` : ""}
            {status.chat_provider === "ollama" && localModel && !localModel.reachable ? " · Ollama is not running, so quick answers are used" : ""}
            {status.chat_provider === "ollama" && localModel?.reachable && !localModel.model_available ? ` · model not downloaded: run "ollama pull ${localModel.name}"` : ""}
          </p>
        ) : null}
        <div className="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
          {!messages.length ? (
            <div className="py-6 text-center">
              <Bot aria-hidden="true" className="mx-auto h-8 w-8 text-muted" />
              <p className="mt-2 text-sm font-semibold text-foreground">Ask about your projects</p>
              <p className="mx-auto mt-1 max-w-md text-xs text-muted">Answers use only the records you are allowed to see. The assistant cannot approve, order or change anything.</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {(suggestions.data || []).map((question) => (
                  <button className="rounded-full border border-border px-3 py-1.5 text-xs text-foreground hover:bg-subtle disabled:opacity-50" disabled={!configured || sending} key={question} onClick={() => ask(question)} type="button">
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : messages.map((message, index) => <Message key={index} message={message} />)}
          {sending ? <p className="flex items-center gap-2 text-sm text-muted" role="status"><Loader2 className="h-4 w-4 animate-spin" /> Checking your records...</p> : null}
          <div ref={endRef} />
        </div>
        <form className="flex items-end gap-2 border-t border-border p-3" onSubmit={(event) => { event.preventDefault(); ask(); }}>
          <label className="sr-only" htmlFor="ai-question">Ask the assistant</label>
          <textarea
            className="max-h-40 min-h-[44px] flex-1 resize-y rounded-md border border-input bg-surface px-3 py-2 text-sm"
            disabled={!configured}
            id="ai-question"
            maxLength={4000}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); ask(); } }}
            placeholder={configured ? "e.g. What needs attention at my site today?" : "Assistant not configured"}
            rows={1}
            value={input}
          />
          <Button aria-label="Send" disabled={!configured || sending || !input.trim()} type="submit"><Send className="h-4 w-4" /></Button>
        </form>
      </section>
    </div>
  );
}
