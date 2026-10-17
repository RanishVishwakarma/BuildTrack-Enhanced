import { useState } from "react";
import { EmptyState } from "../../../components/common/EmptyState.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { hasPermission } from "../../../lib/roles.js";
import { formatDate, formatDateTime, formatStatus, getId, projectName as nameOfProject } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { decideRecommendation, generateRecommendations, getRecommendations, retryRecommendation, verifyRecommendation } from "../services/aiService.js";

const FILTERS = [["", "All"], ["proposed", "Awaiting approval"], ["approved", "Approved"], ["executed", "Executed"], ["execution_failed", "Failed"], ["verified", "Verified"], ["rejected", "Rejected"]];

function describeAction(action) {
  if (!action) return "";
  const p = action.params || {};
  if (action.type === "create_material_request") return `On approval: raise a material request for ${p.quantity} ${p.unit || ""} ${p.material_name} (it still needs procurement approval).`;
  if (action.type === "reserve_stock") return `On approval: reserve ${p.quantity} of the item for the project.`;
  if (action.type === "notify_user") return "On approval: send an in-app notification.";
  return `Manual action: ${p.instruction || "carried out by the responsible person."} Approving records the decision only.`;
}

export function ActionCenterTab() {
  const { user } = useAuth();
  const [filter, setFilter] = useState("");
  const recs = useAsyncData(() => getRecommendations(filter), [filter], { initialData: [] });
  const { projects } = useProjectOptions();
  const [dialog, setDialog] = useState(null);
  const [note, setNote] = useState("");
  const [effective, setEffective] = useState("true");
  const { run, pending, isPending } = useAction();
  usePageRefresh(recs.reload);
  const canApprove = hasPermission(user, "ai.recommendation.approve");
  const canReview = hasPermission(user, "ai.recommendation.review");
  const projectName = (id) => {
    const project = projects.find((p) => getId(p) === id);
    return project ? nameOfProject(project) : "";
  };

  async function submitDialog() {
    const { kind, rec } = dialog;
    const action =
      kind === "verify" ? () => verifyRecommendation(rec._id, effective === "true", note)
        : () => decideRecommendation(rec._id, kind, note);
    const result = await run(kind, action, { success: kind === "approve" ? "Approved." : kind === "reject" ? "Rejected." : "Outcome recorded." });
    if (result) {
      setDialog(null);
      setNote("");
      recs.reload();
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-56"><Select aria-label="Filter by status" onChange={(event) => setFilter(event.target.value)} value={filter}>{FILTERS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></div>
        {canReview ? (
          <Button disabled={isPending("generate")} onClick={() => run("generate", generateRecommendations, { success: (r) => `${r.created} new recommendation(s).`, onSuccess: recs.reload })} variant="secondary">
            {isPending("generate") ? "Checking..." : "Check for new recommendations"}
          </Button>
        ) : null}
      </div>
      {recs.loading && !recs.data?.length ? <LoadingState /> : null}
      {recs.error ? <ErrorState message={getApiErrorMessage(recs.error)} onRetry={recs.reload} /> : null}
      {!recs.loading && !recs.error && !recs.data?.length ? <EmptyState title="No recommendations" description="Recommendations appear here when shortages, late deliveries or other issues are detected, or when someone proposes one." /> : null}
      <ul className="space-y-3">
        {(recs.data || []).map((rec) => {
          const mine = rec.created_by === String(user?.id);
          return (
            <li className="card" key={rec._id}>
              <div className="flex flex-wrap items-start gap-2">
                <h3 className="flex-1 text-sm font-semibold text-foreground">{rec.title}</h3>
                <StatusBadge status={rec.priority} />
                <StatusBadge status={rec.status} />
              </div>
              <p className="mt-1 text-xs text-muted">
                {projectName(rec.project_id) ? `${projectName(rec.project_id)} · ` : ""}Proposed by {rec.created_by === "system" ? "BuildTrack monitoring" : mine ? "you" : "a team member"} · {formatDateTime(rec.created_at)}
                {rec.deadline ? ` · Needed by ${formatDate(rec.deadline)}` : ""}
              </p>
              <p className="mt-2 text-sm text-foreground">{rec.rationale}</p>
              <p className="mt-1 text-xs text-muted">{describeAction(rec.action)}</p>
              {rec.execution_result ? <p className="mt-1 text-xs text-success">Done: {Object.entries(rec.execution_result).map(([k, v]) => `${formatStatus(k)} ${v}`).join(", ")}</p> : null}
              {rec.execution_error ? <p className="mt-1 text-xs text-danger">Execution failed: {rec.execution_error}</p> : null}
              {rec.verification_note ? <p className="mt-1 text-xs text-muted">Verified {rec.verified_effective ? "effective" : "not effective"}: {rec.verification_note}</p> : null}
              {rec.sources?.length ? <p className="mt-1 text-xs text-muted">Evidence: {rec.sources.map((s) => s.label).join(", ")}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {rec.status === "proposed" && canApprove && !mine ? (
                  <>
                    <Button onClick={() => setDialog({ kind: "approve", rec })} size="sm">Approve</Button>
                    <Button onClick={() => setDialog({ kind: "reject", rec })} size="sm" variant="secondary">Reject</Button>
                  </>
                ) : null}
                {rec.status === "proposed" && mine ? <span className="text-xs text-muted">Awaiting approval by someone else.</span> : null}
                {rec.status === "execution_failed" && canApprove ? <Button disabled={pending === rec._id} onClick={() => run(rec._id, () => retryRecommendation(rec._id), { success: "Retried.", onSuccess: recs.reload })} size="sm" variant="secondary">Retry</Button> : null}
                {(rec.status === "executed" || (rec.status === "approved" && rec.action?.type === "manual")) && canReview ? (
                  <Button onClick={() => setDialog({ kind: "verify", rec })} size="sm" variant="secondary">Record outcome</Button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>

      <Modal
        footer={
          <>
            <Button onClick={() => setDialog(null)} variant="secondary">Cancel</Button>
            <Button disabled={Boolean(pending) || (dialog?.kind !== "approve" && note.trim().length < 5)} onClick={submitDialog} variant={dialog?.kind === "reject" ? "danger" : "primary"}>
              {dialog?.kind === "approve" ? "Approve" : dialog?.kind === "reject" ? "Reject" : "Save outcome"}
            </Button>
          </>
        }
        onClose={() => setDialog(null)}
        open={Boolean(dialog)}
        size="sm"
        title={dialog?.kind === "approve" ? "Approve recommendation" : dialog?.kind === "reject" ? "Reject recommendation" : "Record verified outcome"}
        description={dialog ? describeAction(dialog.rec.action) : undefined}
      >
        <div className="space-y-3">
          {dialog?.kind === "verify" ? (
            <Select label="Was it effective?" onChange={(event) => setEffective(event.target.value)} value={effective}>
              <option value="true">Yes, the issue was resolved</option>
              <option value="false">No, it did not resolve the issue</option>
            </Select>
          ) : null}
          <Textarea label={dialog?.kind === "approve" ? "Note (optional)" : dialog?.kind === "reject" ? "Reason (required)" : "What was observed (required)"} onChange={(event) => setNote(event.target.value)} value={note} />
        </div>
      </Modal>
    </div>
  );
}
