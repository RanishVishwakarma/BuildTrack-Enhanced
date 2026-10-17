import { formatStatus } from "../../lib/utils.js";
import { Badge } from "../ui/Badge.jsx";

const GREEN = ["complete", "completed", "active", "approved", "paid", "passed", "accepted", "verified", "in_stock", "available", "present", "delivered", "received", "read", "po_accepted", "executed", "implemented", "resolved", "verified_closed", "success", "completed", "cleared", "acknowledged"];
const AMBER = ["pending", "hold", "on_hold", "low", "low_stock", "partial", "partially_delivered", "draft", "leave", "maintenance", "planning", "unread", "invoice_pending", "payment_pending", "medium", "proposed", "open", "submitted", "under_review", "more_information_required", "approved_for_trial", "in_implementation", "impact_verification", "action_required", "assigned", "in_progress", "done_pending_verification", "pending_review", "needs_more_evidence", "queued", "partial", "skipped"];
const RED = ["rejected", "failed", "cancelled", "out_of_stock", "inactive", "absent", "unavailable", "vendor_rejected", "high", "retired", "critical", "urgent", "execution_failed", "blocked", "dismissed"];

export function StatusBadge({ status }) {
  const normalized = String(status ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  const tone = GREEN.includes(normalized) ? "green" : AMBER.includes(normalized) ? "amber" : RED.includes(normalized) ? "red" : normalized ? "blue" : "slate";
  return <Badge tone={tone}>{formatStatus(status)}</Badge>;
}
