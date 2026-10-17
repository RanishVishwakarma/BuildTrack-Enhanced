import { useState } from "react";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
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
import { formatDate } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { closeCorrectiveAction, getCorrectiveActions, updateCorrectiveAction } from "../services/hubService.js";

// Corrective actions assigned to me, plus (for supervisors) those on my
// projects. The assignee updates progress; someone else verifies closure.
export function ActionsTab() {
  const { user } = useAuth();
  const actions = useAsyncData(getCorrectiveActions, [], { initialData: [] });
  const [dialog, setDialog] = useState(null);
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const { run, pending } = useAction();
  usePageRefresh(actions.reload);
  const me = String(user?.id);

  async function save() {
    const { kind, action } = dialog;
    const result = kind === "update"
      ? await run("save", () => updateCorrectiveAction(action._id, value, note), { success: "Updated." })
      : await run("save", () => closeCorrectiveAction(action._id, value, note), { success: value === "verified_closed" ? "Closed." : "Reopened." });
    if (result) {
      setDialog(null);
      actions.reload();
    }
  }

  if (actions.loading && !actions.data?.length) return <LoadingState />;
  if (actions.error) return <ErrorState message={getApiErrorMessage(actions.error)} onRetry={actions.reload} />;

  return (
    <>
      <DataTable
        columns={[
          { key: "title", header: "Action", render: (a) => <span className="font-semibold">{a.title}</span> },
          { key: "status", header: "Status", render: (a) => <StatusBadge status={a.status} /> },
          { key: "due_date", header: "Due", render: (a) => <span className={new Date(a.due_date) < new Date() && !["verified_closed", "cancelled"].includes(a.status) ? "font-semibold text-danger" : ""}>{formatDate(a.due_date)}</span> },
          { key: "who", header: "Assigned", render: (a) => (a.assignee_id === me ? "You" : "Team member") },
          {
            key: "actions", header: "", render: (a) => (
              <div className="flex gap-2">
                {a.assignee_id === me && hasPermission(user, "safety_actions.update.own") && !["verified_closed", "cancelled"].includes(a.status) ? (
                  <Button onClick={() => { setDialog({ kind: "update", action: a }); setValue(a.status === "assigned" ? "acknowledged" : "done_pending_verification"); setNote(""); }} size="sm" variant="secondary">Update</Button>
                ) : null}
                {a.assignee_id !== me && hasPermission(user, "safety_actions.close") && a.status === "done_pending_verification" ? (
                  <Button onClick={() => { setDialog({ kind: "close", action: a }); setValue("verified_closed"); setNote(""); }} size="sm">Verify</Button>
                ) : null}
              </div>
            ),
          },
        ]}
        emptyDescription="Corrective actions from safety reports appear here."
        emptyTitle="No corrective actions"
        getRowId={(a) => a._id}
        rows={actions.data || []}
      />
      <Modal
        footer={<><Button onClick={() => setDialog(null)} variant="secondary">Cancel</Button><Button disabled={pending === "save" || note.trim().length < (dialog?.kind === "close" ? 5 : 3)} onClick={save}>Save</Button></>}
        onClose={() => setDialog(null)}
        open={Boolean(dialog)}
        size="sm"
        title={dialog?.kind === "close" ? "Verify corrective action" : "Update corrective action"}
      >
        <div className="space-y-3">
          <Select label="Status" onChange={(e) => setValue(e.target.value)} value={value}>
            {dialog?.kind === "close" ? (
              <><option value="verified_closed">Verified: close it</option><option value="reopened">Not done: reopen</option></>
            ) : (
              <><option value="acknowledged">Acknowledged</option><option value="in_progress">In progress</option><option value="done_pending_verification">Done: ready for verification</option></>
            )}
          </Select>
          <Textarea label={dialog?.kind === "close" ? "What you checked" : "Note"} onChange={(e) => setNote(e.target.value)} value={note} />
        </div>
      </Modal>
    </>
  );
}
