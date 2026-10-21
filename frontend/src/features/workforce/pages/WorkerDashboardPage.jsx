import { Link } from "react-router-dom";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { formatDate, formatDateTime, getId, normalizeList } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getNotifications } from "../../notifications/services/notificationService.js";
import { getTasksForWorker } from "../../tasks/services/taskService.js";
import { getAttendance, getWorkerAllocations } from "../services/workforceService.js";

// Angular WorkerDashboardComponent: the worker's own tasks, recent
// attendance, project allocations and notifications.
export function WorkerDashboardPage() {
  const { user } = useAuth();
  const projects = useProjectOptions();
  const { data, loading, error, reload } = useAsyncData(
    async () => {
      const since = new Date(Date.now() - 30 * 86400000).toISOString();
      const [tasks, attendance, allocations, notifications] = await Promise.all([
        getTasksForWorker(user.workerId),
        getAttendance({ workerId: user.workerId, startDate: since }),
        getWorkerAllocations(user.workerId),
        getNotifications({ limit: 5 }),
      ]);
      return { tasks, attendance: normalizeList(attendance).items, allocations: normalizeList(allocations).items, notifications };
    },
    [user?.workerId],
    { enabled: Boolean(user?.workerId) },
  );

  if (!user?.workerId) {
    return (
      <>
        <PageHeader title="My Dashboard" />
        <ErrorState message="Your login is not linked to a worker profile. Ask your project manager to link it on the Workers page." />
      </>
    );
  }
  if (loading) return <LoadingState label="Loading your dashboard..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  const pendingTasks = data.tasks.filter((task) => task.status !== "completed");
  const recorded = data.attendance.length;
  const present = data.attendance.filter((record) => record.status === "present").length;
  const activeAllocations = data.allocations.filter((allocation) => allocation.status === "ACTIVE");

  return (
    <>
      <PageHeader title={`Welcome, ${user.name}`} description="Your tasks, attendance and project assignments." />
      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <Link to="/my-tasks"><StatCard label="Open tasks" value={pendingTasks.length} helper="View all tasks" /></Link>
        <StatCard label="Completed tasks" value={data.tasks.length - pendingTasks.length} />
        <Link to="/attendance"><StatCard label="Attendance (30 days)" value={recorded ? `${Math.round((present / recorded) * 100)}%` : "No records"} helper={`${present} present of ${recorded} recorded`} /></Link>
        <StatCard label="Active projects" value={activeAllocations.length} />
      </section>
      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="card">
          <h2 className="mb-3 text-lg font-semibold">Upcoming tasks</h2>
          {pendingTasks.length ? (
            <ul className="divide-y divide-border">
              {pendingTasks.slice(0, 6).map((task) => (
                <li className="flex items-center justify-between gap-3 py-2" key={getId(task)}>
                  <div>
                    <p className="font-semibold">{task.title}</p>
                    <p className="text-sm text-muted">{projects.nameOf(task.project_id)} · due {formatDate(task.due_date)}</p>
                  </div>
                  <StatusBadge status={task.status} />
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No open tasks.</p>}
        </div>
        <div className="card">
          <h2 className="mb-3 text-lg font-semibold">My project assignments</h2>
          {data.allocations.length ? (
            <ul className="divide-y divide-border">
              {data.allocations.map((allocation) => (
                <li className="flex items-center justify-between gap-3 py-2" key={getId(allocation)}>
                  <div>
                    <p className="font-semibold">{projects.nameOf(allocation.project_id)}</p>
                    <p className="text-sm text-muted">{allocation.role || "Role not set"} · from {formatDate(allocation.start_date)}</p>
                  </div>
                  <StatusBadge status={allocation.status} />
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">You are not allocated to any project.</p>}
        </div>
        <div className="card">
          <h2 className="mb-3 text-lg font-semibold">Recent attendance</h2>
          {recorded ? (
            <ul className="divide-y divide-border">
              {data.attendance.slice().sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 7).map((record) => (
                <li className="flex items-center justify-between py-2" key={getId(record)}>
                  <span>{formatDate(record.date)}</span>
                  <StatusBadge status={record.status} />
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No attendance recorded in the last 30 days.</p>}
        </div>
        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Notifications</h2>
            <Link className="text-sm font-semibold text-primary" to="/notifications">View all</Link>
          </div>
          {data.notifications.length ? (
            <ul className="divide-y divide-border">
              {data.notifications.map((item) => (
                <li className="py-2" key={getId(item)}>
                  <p className={item.is_read ? "text-sm" : "text-sm font-semibold"}>{item.title}</p>
                  <p className="text-xs text-muted">{formatDateTime(item.created_at)}</p>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No notifications.</p>}
        </div>
      </section>
    </>
  );
}
