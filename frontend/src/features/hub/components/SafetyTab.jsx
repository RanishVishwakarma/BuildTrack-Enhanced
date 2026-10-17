import { ShieldAlert, Sparkles, UserSearch } from "lucide-react";
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
import { getProjectMembers } from "../../settings/services/accessService.js";
import { createCorrectiveAction, getSafetyReport, getSafetyReports, revealReporter, reviewSafetyReport, safetyAiAssist, submitSafetyReport } from "../services/hubService.js";

const TYPES = [["hazard", "Hazard"], ["near_miss", "Near miss"], ["incident", "Incident"], ["inspection", "Safety inspection"], ["improvement", "Safety improvement"]];
const NEXT = { open: ["under_review"], under_review: ["action_required", "resolved"], action_required: ["resolved"], resolved: ["closed", "action_required"], closed: [] };
const EMPTY = { report_type: "hazard", severity: "medium", title: "", description: "", project_id: "", location: "", anonymous: false, immediate_action_taken: "" };

export function SafetyTab() {
  const { user } = useAuth();
  const isReviewer = hasPermission(user, "safety_reports.read.assigned");
  const reports = useAsyncData(() => getSafetyReports(!isReviewer), [isReviewer], { initialData: [] });
  const { projects } = useProjectOptions();
  const [form, setForm] = useState(null);
  const [detail, setDetail] = useState(null);
  const [reviewForm, setReviewForm] = useState({ status: "", note: "" });
  const [actionForm, setActionForm] = useState({ title: "", description: "", assignee_id: "", due_date: "" });
  const members = useAsyncData(() => (detail?.project_id && hasPermission(user, "safety_actions.assign") ? getProjectMembers(detail.project_id) : []), [detail?.project_id], { initialData: [] });
  const [revealed, setRevealed] = useState(null);
  const { run, pending, isPending } = useAction();
  usePageRefresh(reports.reload);

  async function open(id) {
    try {
      const report = await getSafetyReport(id);
      setDetail(report);
      setRevealed(null);
      setReviewForm({ status: NEXT[report.status]?.[0] || "", note: "" });
    } catch (error) {
      toast.error(getApiErrorMessage(error));
    }
  }

  async function submit(event) {
    event.preventDefault();
    const result = await run("submit", () => submitSafetyReport({ ...form, project_id: form.project_id || undefined, location: form.location || undefined, immediate_action_taken: form.immediate_action_taken || undefined }));
    if (result) {
      toast.success(result.escalated_to_count ? `Report submitted and escalated to ${result.escalated_to_count} responsible person(s).` : "Report submitted. Thank you for keeping the site safe.");
      setForm(null);
      reports.reload();
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        {hasPermission(user, "safety_reports.create") ? <Button onClick={() => setForm(EMPTY)} variant="danger"><ShieldAlert className="h-4 w-4" /> Report a safety issue</Button> : null}
      </div>
      {reports.loading && !reports.data?.length ? <LoadingState /> : null}
      {reports.error ? <ErrorState message={getApiErrorMessage(reports.error)} onRetry={reports.reload} /> : null}
      {!reports.loading && !reports.error ? (
        <DataTable
          columns={[
            { key: "title", header: "Report", render: (r) => <button className="font-semibold underline-offset-2 hover:underline" onClick={() => open(r._id)} type="button">{r.title}</button> },
            { key: "type", header: "Type", render: (r) => formatStatus(r.report_type) },
            { key: "severity", header: "Severity", render: (r) => <StatusBadge status={r.severity} /> },
            { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
            { key: "created_at", header: "Reported", render: (r) => formatDateTime(r.created_at) },
          ]}
          emptyDescription="Hazards, near misses and incidents you report appear here."
          emptyTitle="No safety reports"
          getRowId={(r) => r._id}
          rows={reports.data || []}
        />
      ) : null}

      <Modal
        description="Urgent reports alert the responsible managers immediately. For an emergency, call emergency services first."
        footer={<><Button onClick={() => setForm(null)} variant="secondary">Cancel</Button><Button disabled={pending === "submit"} form="safety-form" type="submit" variant="danger">Submit report</Button></>}
        onClose={() => setForm(null)}
        open={Boolean(form)}
        size="lg"
        title="Report a safety issue"
      >
        {form ? (
          <form className="grid gap-3 sm:grid-cols-2" id="safety-form" onSubmit={submit}>
            <Select label="Type" onChange={(e) => setForm({ ...form, report_type: e.target.value })} value={form.report_type}>{TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
            <Select label="Severity" onChange={(e) => setForm({ ...form, severity: e.target.value })} value={form.severity}>
              <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent: needs immediate action</option>
            </Select>
            <div className="sm:col-span-2"><Input label="Short title" maxLength={150} minLength={3} onChange={(e) => setForm({ ...form, title: e.target.value })} required value={form.title} /></div>
            <div className="sm:col-span-2"><Textarea label="What did you see or what happened?" maxLength={4000} minLength={10} onChange={(e) => setForm({ ...form, description: e.target.value })} required rows={4} value={form.description} /></div>
            <Select label="Project" onChange={(e) => setForm({ ...form, project_id: e.target.value })} value={form.project_id}>
              <option value="">Not project-specific</option>
              {projects.map((p) => <option key={getId(p)} value={getId(p)}>{projectName(p)}</option>)}
            </Select>
            <Input label="Location on site" maxLength={200} onChange={(e) => setForm({ ...form, location: e.target.value })} value={form.location} />
            <div className="sm:col-span-2"><Input label="Immediate action taken (optional)" maxLength={2000} onChange={(e) => setForm({ ...form, immediate_action_taken: e.target.value })} value={form.immediate_action_taken} /></div>
            <label className="flex items-start gap-2 text-sm sm:col-span-2">
              <input checked={form.anonymous} className="mt-1" onChange={(e) => setForm({ ...form, anonymous: e.target.checked })} type="checkbox" />
              <span>Submit anonymously. Your name is hidden from reviewers; it is only revealed with special authorization and a recorded reason.</span>
            </label>
          </form>
        ) : null}
      </Modal>

      <Modal onClose={() => setDetail(null)} open={Boolean(detail)} size="lg" title={detail?.title || "Safety report"}>
        {detail ? (
          <div className="space-y-4">
            <DetailList items={[
              ["Type", formatStatus(detail.report_type)], ["Severity", <StatusBadge key="sev" status={detail.severity} />], ["Status", <StatusBadge key="st" status={detail.status} />],
              ["Reported", formatDateTime(detail.created_at)], ["Location", detail.location], ["Reporter", detail.reporter || (detail.is_mine ? "You" : "Named")],
              ["Description", detail.description], ["Immediate action", detail.immediate_action_taken],
              ...(detail.escalated_at ? [["Escalated", formatDateTime(detail.escalated_at)]] : []),
            ]} />
            {revealed ? <p className="rounded bg-warning/10 p-2 text-sm text-warning">Reporter: {revealed.name} ({revealed.email}). This access was recorded.</p> : null}
            {detail.ai_assist ? (
              <section className="rounded-lg border border-info/30 bg-info/5 p-3 text-sm">
                <p>{detail.ai_assist.summary}</p>
                <p className="mt-1 text-xs">Suggested type: {formatStatus(detail.ai_assist.suggested_type)} · Possible hazards: {detail.ai_assist.possible_hazard_categories.join(", ")}</p>
                {detail.ai_assist.questions_for_reviewer?.length ? <ul className="mt-1 list-disc pl-5 text-xs">{detail.ai_assist.questions_for_reviewer.map((q) => <li key={q}>{q}</li>)}</ul> : null}
                <p className="mt-1 text-xs text-muted">{detail.ai_assist.label}</p>
              </section>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {hasPermission(user, "safety_reports.review") ? (
                <Button disabled={isPending("assist")} onClick={() => run("assist", () => safetyAiAssist(detail._id)).then((r) => r && setDetail({ ...detail, ai_assist: r }))} size="sm" variant="ghost"><Sparkles className="h-4 w-4" /> AI triage aid</Button>
              ) : null}
              {hasPermission(user, "safety_reports.identity.reveal") && detail.reporter === "Anonymous" ? (
                <Button onClick={() => {
                  const reason = window.prompt("Why do you need to identify the reporter? This is recorded.");
                  if (reason && reason.trim().length >= 10) run("reveal", () => revealReporter(detail._id, reason.trim())).then((r) => r && setRevealed(r));
                  else if (reason) toast.error("Give a reason of at least 10 characters.");
                }} size="sm" variant="ghost"><UserSearch className="h-4 w-4" /> Reveal reporter</Button>
              ) : null}
            </div>

            {hasPermission(user, "safety_reports.review") && NEXT[detail.status]?.length ? (
              <section className="grid gap-2 border-t border-border pt-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
                <Select label="Move to" onChange={(e) => setReviewForm({ ...reviewForm, status: e.target.value })} value={reviewForm.status}>{NEXT[detail.status].map((s) => <option key={s} value={s}>{formatStatus(s)}</option>)}</Select>
                <Input label="Review note" onChange={(e) => setReviewForm({ ...reviewForm, note: e.target.value })} value={reviewForm.note} />
                <Button disabled={pending === "review" || reviewForm.note.trim().length < 3} onClick={() => run("review", () => reviewSafetyReport(detail._id, { status: reviewForm.status, note: reviewForm.note }), { success: "Updated.", onSuccess: () => { open(detail._id); reports.reload(); } })}>Save</Button>
              </section>
            ) : null}

            <section className="border-t border-border pt-3">
              <h4 className="text-sm font-semibold">Corrective actions</h4>
              {detail.corrective_actions?.length ? (
                <ul className="mt-2 space-y-1 text-sm">{detail.corrective_actions.map((a) => <li className="flex items-center gap-2" key={a._id}><StatusBadge status={a.status} /> {a.title} · due {formatDate(a.due_date)}</li>)}</ul>
              ) : <p className="mt-1 text-xs text-muted">None yet.</p>}
              {hasPermission(user, "safety_actions.assign") && detail.status !== "closed" ? (
                <form className="mt-3 grid gap-2 sm:grid-cols-2" onSubmit={async (e) => {
                  e.preventDefault();
                  const r = await run("action", () => createCorrectiveAction(detail._id, { ...actionForm, due_date: new Date(actionForm.due_date).toISOString() }), { success: "Corrective action assigned." });
                  if (r) { setActionForm({ title: "", description: "", assignee_id: "", due_date: "" }); open(detail._id); }
                }}>
                  <Input label="Action" minLength={3} onChange={(e) => setActionForm({ ...actionForm, title: e.target.value })} required value={actionForm.title} />
                  <Select label="Assign to" onChange={(e) => setActionForm({ ...actionForm, assignee_id: e.target.value })} required value={actionForm.assignee_id}>
                    <option value="">{detail.project_id ? "Choose a project member" : "Report has no project"}</option>
                    {(members.data || []).map((m) => <option key={m.user_id} value={m.user_id}>{m.name || m.email} ({formatStatus(m.role)})</option>)}
                  </Select>
                  <Input label="Due date" onChange={(e) => setActionForm({ ...actionForm, due_date: e.target.value })} required type="date" value={actionForm.due_date} />
                  <Input label="Details" minLength={5} onChange={(e) => setActionForm({ ...actionForm, description: e.target.value })} required value={actionForm.description} />
                  <div className="sm:col-span-2"><Button disabled={pending === "action"} size="sm" type="submit">Assign action</Button></div>
                </form>
              ) : null}
            </section>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
