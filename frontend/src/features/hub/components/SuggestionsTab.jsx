import { Lightbulb, Plus, Sparkles } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { DetailList } from "../../../components/common/DetailList.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { hasPermission } from "../../../lib/roles.js";
import { formatDate, formatDateTime, formatStatus, getId, projectName } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import {
  OUTCOME_METRICS, SUGGESTION_CATEGORIES, addSuggestionOutcome, analyzeSuggestion, assistSuggestion, createSuggestion,
  getSuggestion, getSuggestions, transitionSuggestion,
} from "../services/hubService.js";

const EMPTY = { title: "", problem: "", proposed_solution: "", category: "productivity", project_id: "", expected_benefit: "" };
const categoryLabel = (value) => SUGGESTION_CATEGORIES.find(([key]) => key === value)?.[1] || formatStatus(value);
const NEEDS_NOTE = ["rejected", "more_information_required"];

export function SuggestionsTab() {
  const { user } = useAuth();
  const isReviewer = hasPermission(user, "suggestions.review.assigned");
  const [mine, setMine] = useState(!isReviewer);
  const list = useAsyncData(() => getSuggestions({ mine }), [mine], { initialData: [] });
  const { projects } = useProjectOptions();
  const [form, setForm] = useState(null);
  const [assist, setAssist] = useState(null);
  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState({ metric: "time_saved_hours", value: "", unit: "", measured_on: "", method: "" });
  const { run, pending, isPending } = useAction();
  usePageRefresh(list.reload);

  async function openDetail(id) {
    try {
      setDetail(await getSuggestion(id));
      setNote("");
    } catch (error) {
      toast.error(getApiErrorMessage(error));
    }
  }

  async function submit(event) {
    event.preventDefault();
    const result = await run("create", () => createSuggestion({ ...form, project_id: form.project_id || undefined, expected_benefit: form.expected_benefit || undefined }), { success: "Suggestion submitted. Thank you!" });
    if (result) {
      setForm(null);
      setAssist(null);
      list.reload();
    }
  }

  async function move(status) {
    const result = await run(status, () => transitionSuggestion(detail._id, status, note), { success: `Moved to ${formatStatus(status)}.` });
    if (result) {
      await openDetail(detail._id);
      list.reload();
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {isReviewer ? (
          <label className="flex items-center gap-2 text-sm text-muted"><input checked={mine} onChange={(event) => setMine(event.target.checked)} type="checkbox" /> Only my suggestions</label>
        ) : <span />}
        {hasPermission(user, "suggestions.create") ? <Button onClick={() => setForm(EMPTY)}><Plus className="h-4 w-4" /> New suggestion</Button> : null}
      </div>
      {list.loading && !list.data?.length ? <LoadingState /> : null}
      {list.error ? <ErrorState message={getApiErrorMessage(list.error)} onRetry={list.reload} /> : null}
      {!list.loading && !list.error ? (
        <DataTable
          columns={[
            { key: "title", header: "Suggestion", render: (row) => <button className="font-semibold underline-offset-2 hover:underline" onClick={() => openDetail(row._id)} type="button">{row.title}</button> },
            { key: "category", header: "Category", render: (row) => categoryLabel(row.category) },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "updated_at", header: "Updated", render: (row) => formatDate(row.updated_at) },
          ]}
          emptyDescription="Ideas for safer, faster or cheaper work are welcome from everyone."
          emptyTitle="No suggestions yet"
          getRowId={(row) => row._id}
          rows={list.data || []}
        />
      ) : null}

      <Modal
        footer={<><Button onClick={() => { setForm(null); setAssist(null); }} variant="secondary">Cancel</Button><Button disabled={pending === "create"} form="suggestion-form" type="submit">Submit</Button></>}
        onClose={() => { setForm(null); setAssist(null); }}
        open={Boolean(form)}
        size="lg"
        title="New improvement suggestion"
      >
        {form ? (
          <form className="grid gap-3 sm:grid-cols-2" id="suggestion-form" onSubmit={submit}>
            <div className="sm:col-span-2"><Input label="Title" maxLength={150} minLength={3} onChange={(e) => setForm({ ...form, title: e.target.value })} required value={form.title} /></div>
            <Select label="Category" onChange={(e) => setForm({ ...form, category: e.target.value })} value={form.category}>{SUGGESTION_CATEGORIES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select>
            <Select label="Project (optional)" onChange={(e) => setForm({ ...form, project_id: e.target.value })} value={form.project_id}>
              <option value="">Company-wide</option>
              {projects.map((p) => <option key={getId(p)} value={getId(p)}>{projectName(p)}</option>)}
            </Select>
            <div className="sm:col-span-2"><Textarea label="What is the problem?" maxLength={3000} minLength={10} onChange={(e) => setForm({ ...form, problem: e.target.value })} required rows={3} value={form.problem} /></div>
            <div className="sm:col-span-2"><Textarea label="What do you propose?" maxLength={3000} minLength={10} onChange={(e) => setForm({ ...form, proposed_solution: e.target.value })} required rows={3} value={form.proposed_solution} /></div>
            <div className="sm:col-span-2"><Input label="Expected benefit (your estimate, optional)" maxLength={1000} onChange={(e) => setForm({ ...form, expected_benefit: e.target.value })} value={form.expected_benefit} /></div>
            <div className="sm:col-span-2">
              <Button disabled={isPending("assist") || form.title.length < 3 || form.problem.length < 3} onClick={() => run("assist", () => assistSuggestion({ title: form.title, problem: form.problem, proposed_solution: form.proposed_solution })).then((r) => r && setAssist(r))} size="sm" type="button" variant="secondary">
                <Sparkles className="h-4 w-4" /> {isPending("assist") ? "Checking..." : "Check for related ideas and missing details"}
              </Button>
            </div>
            {assist ? (
              <div className="space-y-2 rounded-lg border border-border bg-subtle p-3 text-sm sm:col-span-2">
                {assist.related?.length ? <p><span className="font-semibold">Similar ideas:</span> {assist.related.map((r) => `${r.title} (${formatStatus(r.status)})`).join("; ")}</p> : <p className="text-muted">No similar ideas found.</p>}
                {assist.ai ? (
                  <>
                    <p>
                      <span className="font-semibold">Suggested category:</span> {categoryLabel(assist.ai.suggested_category)}{" "}
                      {assist.ai.suggested_category !== form.category ? <button className="text-xs font-semibold underline" onClick={() => setForm({ ...form, category: assist.ai.suggested_category })} type="button">Use it</button> : null}
                    </p>
                    {assist.ai.missing_information?.length ? <p><span className="font-semibold">A reviewer may also want:</span> {assist.ai.missing_information.join("; ")}</p> : null}
                    {assist.ai.clearer_wording ? <p><span className="font-semibold">Clearer wording (optional):</span> {assist.ai.clearer_wording}</p> : null}
                    <p className="text-xs text-muted">{assist.ai.label} Your own words are what get submitted.</p>
                  </>
                ) : assist.ai_error ? <p className="text-xs text-muted">AI help unavailable: {assist.ai_error}</p> : null}
              </div>
            ) : null}
          </form>
        ) : null}
      </Modal>

      <Modal onClose={() => setDetail(null)} open={Boolean(detail)} size="lg" title={detail?.title || "Suggestion"}>
        {detail ? (
          <div className="space-y-4">
            <DetailList items={[
              ["Status", <StatusBadge key="s" status={detail.status} />], ["Category", categoryLabel(detail.category)],
              ["Problem", detail.problem], ["Proposal", detail.proposed_solution],
              ["Expected benefit (estimate)", detail.expected_benefit], ["Submitted", formatDateTime(detail.created_at)],
              ...(detail.rejection_reason ? [["Rejection reason", detail.rejection_reason]] : []),
            ]} />
            {detail.measured_outcomes?.length ? (
              <section>
                <h4 className="text-sm font-semibold">Measured outcomes</h4>
                <ul className="mt-1 list-disc pl-5 text-sm">{detail.measured_outcomes.map((o, i) => <li key={i}>{OUTCOME_METRICS.find(([k]) => k === o.metric)?.[1]}: {o.value} {o.unit} (measured {o.measured_on}; {o.method})</li>)}</ul>
              </section>
            ) : null}
            {detail.ai_review_analysis ? (
              <section className="rounded-lg border border-info/30 bg-info/5 p-3 text-sm">
                <p className="whitespace-pre-line">{detail.ai_review_analysis.text}</p>
                <p className="mt-1 text-xs text-muted">{detail.ai_review_analysis.label}</p>
              </section>
            ) : null}
            {detail.related?.length ? <p className="text-sm"><span className="font-semibold">Related:</span> {detail.related.map((r) => r.title).join("; ")}</p> : null}
            {detail.history?.length ? (
              <details className="text-xs text-muted"><summary className="cursor-pointer">History</summary>
                <ul className="mt-1 space-y-0.5">{detail.history.map((h, i) => <li key={i}>{formatDateTime(h.at)}: {h.status ? formatStatus(h.status) : "edited"}{h.note ? ` (${h.note})` : ""}</li>)}</ul>
              </details>
            ) : null}
            {detail.allowed_transitions?.length ? (
              <section className="space-y-2 border-t border-border pt-3">
                <Textarea label="Note (required to reject or ask for more information)" onChange={(e) => setNote(e.target.value)} value={note} />
                <div className="flex flex-wrap gap-2">
                  {detail.allowed_transitions.map((status) => (
                    <Button disabled={Boolean(pending) || (NEEDS_NOTE.includes(status) && !note.trim())} key={status} onClick={() => move(status)} size="sm" variant={status === "rejected" ? "danger" : "secondary"}>
                      {status === "submitted" ? "Resubmit" : formatStatus(status)}
                    </Button>
                  ))}
                </div>
              </section>
            ) : null}
            {hasPermission(user, "suggestions.implement") && ["in_implementation", "impact_verification"].includes(detail.status) ? (
              <form className="grid gap-2 border-t border-border pt-3 sm:grid-cols-2" onSubmit={async (e) => {
                e.preventDefault();
                const r = await run("outcome", () => addSuggestionOutcome(detail._id, { ...outcome, value: Number(outcome.value) }), { success: "Outcome recorded." });
                if (r) { setDetail({ ...detail, ...r }); setOutcome({ metric: "time_saved_hours", value: "", unit: "", measured_on: "", method: "" }); }
              }}>
                <p className="text-sm font-semibold sm:col-span-2">Record a measured outcome</p>
                <Select label="Metric" onChange={(e) => setOutcome({ ...outcome, metric: e.target.value })} value={outcome.metric}>{OUTCOME_METRICS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
                <Input label="Value" onChange={(e) => setOutcome({ ...outcome, value: e.target.value })} required step="any" type="number" value={outcome.value} />
                <Input label="Unit" onChange={(e) => setOutcome({ ...outcome, unit: e.target.value })} required value={outcome.unit} />
                <Input label="Measured on" onChange={(e) => setOutcome({ ...outcome, measured_on: e.target.value })} required type="date" value={outcome.measured_on} />
                <div className="sm:col-span-2"><Input label="How it was measured" minLength={5} onChange={(e) => setOutcome({ ...outcome, method: e.target.value })} required value={outcome.method} /></div>
                <div className="sm:col-span-2"><Button disabled={pending === "outcome"} size="sm" type="submit">Save outcome</Button></div>
              </form>
            ) : null}
            {isReviewer ? (
              <Button disabled={isPending("analysis")} onClick={() => run("analysis", () => analyzeSuggestion(detail._id)).then((r) => r && setDetail({ ...detail, ai_review_analysis: r }))} size="sm" variant="ghost">
                <Lightbulb className="h-4 w-4" /> {isPending("analysis") ? "Analysing..." : "AI impact analysis for reviewers"}
              </Button>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
