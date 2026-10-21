import { useMemo, useState } from "react";
import { DetailList } from "../../../components/common/DetailList.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { formatDate, formatDateTime, getId } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getTasksForWorker } from "../services/taskService.js";

// Read-only, like Angular MyTasksComponent: PUT /tasks/{id} is restricted to
// admin/manager, so workers cannot change task status from here.
export function MyTasksPage() {
  const { user } = useAuth();
  const projects = useProjectOptions();
  const [status, setStatus] = useState("");
  const [details, setDetails] = useState(null);
  const tasks = useAsyncData(() => getTasksForWorker(user.workerId), [user?.workerId], { initialData: [], enabled: Boolean(user?.workerId) });

  const rows = useMemo(
    () => (tasks.data || []).filter((task) => !status || task.status === status).sort((a, b) => String(a.due_date || "").localeCompare(String(b.due_date || ""))),
    [tasks.data, status],
  );

  if (!user?.workerId) {
    return (
      <>
        <PageHeader title="My Tasks" />
        <ErrorState message="Your login is not linked to a worker profile, so tasks cannot be loaded. Ask your project manager to link it on the Workers page." />
      </>
    );
  }

  const today = new Date().toISOString().slice(0, 10);
  return (
    <>
      <PageHeader
        title="My Tasks"
        description="Tasks assigned to you by project managers."
        onRefresh={tasks.reload}
      />
      <div className="mb-4 max-w-xs">
        <Select aria-label="Filter by status" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">All tasks</option>
          <option value="pending">Pending</option>
          <option value="completed">Completed</option>
        </Select>
      </div>
      {tasks.loading ? <LoadingState label="Loading tasks..." /> : null}
      {!tasks.loading && tasks.error ? <ErrorState message={getApiErrorMessage(tasks.error)} onRetry={tasks.reload} /> : null}
      {!tasks.loading && !tasks.error ? (
        <DataTable
          columns={[
            { key: "title", header: "Task", render: (row) => <button className="text-left font-semibold text-primary" onClick={() => setDetails(row)} type="button">{row.title}</button> },
            { key: "project", header: "Project", render: (row) => projects.nameOf(row.project_id) },
            {
              key: "due_date",
              header: "Due",
              render: (row) => (
                <span className={row.status !== "completed" && row.due_date && row.due_date.slice(0, 10) < today ? "font-semibold text-danger" : undefined}>
                  {formatDate(row.due_date)}
                </span>
              ),
            },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
          ]}
          emptyDescription="You have no tasks assigned right now."
          emptyTitle="No tasks"
          getRowId={getId}
          rows={rows}
        />
      ) : null}
      <Modal onClose={() => setDetails(null)} open={Boolean(details)} title={details?.title || "Task"}>
        {details ? (
          <DetailList
            items={[
              ["Project", projects.nameOf(details.project_id)],
              ["Status", <StatusBadge key="s" status={details.status} />],
              ["Due", formatDate(details.due_date)],
              ["Description", details.description],
              ["Assigned", formatDateTime(details.created_at)],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
