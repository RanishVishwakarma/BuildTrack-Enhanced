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
import { hasPermission } from "../../../lib/roles.js";
import { formatDateTime, formatStatus } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getRisks, reviewRisk, runRisks } from "../services/insightsService.js";

const LEVEL_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

export function RisksTab({ projectId }) {
  const { user } = useAuth();
  const [showCleared, setShowCleared] = useState(false);
  const risks = useAsyncData(() => getRisks(projectId, showCleared), [projectId, showCleared], { initialData: [] });
  const [reviewing, setReviewing] = useState(null);
  const [review, setReview] = useState({ status: "acknowledged", note: "" });
  const { run, pending } = useAction();
  usePageRefresh(risks.reload);
  const rows = [...(risks.data || [])].sort((a, b) => (LEVEL_ORDER[a.level] ?? 9) - (LEVEL_ORDER[b.level] ?? 9));

  async function saveReview() {
    const result = await run("review", () => reviewRisk(reviewing._id, review.status, review.note), { success: "Review saved." });
    if (result) {
      setReviewing(null);
      risks.reload();
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button disabled={pending === "run"} onClick={() => run("run", () => runRisks(projectId), { success: "Risk assessment updated.", onSuccess: risks.reload })}>
          {pending === "run" ? "Assessing..." : "Run assessment now"}
        </Button>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input checked={showCleared} onChange={(event) => setShowCleared(event.target.checked)} type="checkbox" /> Include cleared
        </label>
        <p className="text-xs text-muted">Rule-based: each level comes from stated thresholds on your records. No probabilities are estimated.</p>
      </div>
      {risks.loading && !rows.length ? <LoadingState label="Loading risk assessments..." /> : null}
      {risks.error ? <ErrorState message={getApiErrorMessage(risks.error)} onRetry={risks.reload} /> : null}
      {!risks.loading && !risks.error && !rows.length ? <EmptyState title="No active risks" description="Run the assessment to check your projects, or none of the rules currently apply." /> : null}
      <ul className="space-y-3">
        {rows.map((risk) => (
          <li className="card" key={risk._id}>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={risk.level} />
              <h3 className="flex-1 text-sm font-semibold text-foreground">{risk.project_name}: {formatStatus(risk.category)} ({formatStatus(risk.rule)})</h3>
              <StatusBadge status={risk.status === "cleared" ? "cleared" : risk.review_status} />
            </div>
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-foreground">{risk.factors?.map((factor) => <li key={factor}>{factor}</li>)}</ul>
            <p className="mt-2 text-sm text-muted"><span className="font-semibold text-foreground">Recommended:</span> {risk.recommended_action}</p>
            <p className="mt-1 text-xs text-muted">
              First detected {formatDateTime(risk.detected_at)} · last seen {formatDateTime(risk.last_detected_at)}
              {risk.sources?.length ? ` · Records: ${risk.sources.map((s) => s.label).join(", ")}` : ""}
            </p>
            {hasPermission(user, "risks.review") && risk.status !== "cleared" ? (
              <Button className="mt-3" onClick={() => { setReviewing(risk); setReview({ status: "acknowledged", note: "" }); }} size="sm" variant="secondary">Review</Button>
            ) : null}
          </li>
        ))}
      </ul>
      <Modal
        footer={<><Button onClick={() => setReviewing(null)} variant="secondary">Cancel</Button><Button disabled={pending === "review" || (review.status === "dismissed" && review.note.trim().length < 3)} onClick={saveReview}>Save</Button></>}
        onClose={() => setReviewing(null)}
        open={Boolean(reviewing)}
        size="sm"
        title="Review risk"
      >
        <div className="space-y-3">
          <Select label="Status" onChange={(event) => setReview({ ...review, status: event.target.value })} value={review.status}>
            <option value="acknowledged">Acknowledged: being handled</option>
            <option value="resolved">Resolved</option>
            <option value="dismissed">Dismissed (reason required)</option>
            <option value="open">Re-open</option>
          </Select>
          <Textarea label="Note" onChange={(event) => setReview({ ...review, note: event.target.value })} value={review.note} />
        </div>
      </Modal>
    </div>
  );
}
