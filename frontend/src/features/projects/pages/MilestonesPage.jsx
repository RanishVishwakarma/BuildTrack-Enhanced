import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { can } from "../../../lib/roles.js";
import { formatDate, getId, normalizeList, projectName, toDateInput } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { MilestoneFormModal } from "../components/MilestoneFormModal.jsx";
import { MILESTONE_STATUSES, deleteMilestoneRecord, getMilestoneRecords, getProjects, recordProjectId } from "../services/projectService.js";

// Angular MilestonesComponent: milestones across every project, from the
// project_milestones collection.
export function MilestonesPage() {
  const { user } = useAuth();
  const { run } = useAction();
  const { data, loading, error, reload } = useAsyncData(async () => {
    const [projects, milestones] = await Promise.all([getProjects(), getMilestoneRecords()]);
    return { projects: normalizeList(projects).items, milestones };
  }, []);
  const [filters, setFilters] = useState({ project: "", status: "" });
  const [form, setForm] = useState({ open: false, milestone: null });
  const today = toDateInput();

  const rows = useMemo(() => {
    if (!data) return [];
    const byId = new Map(data.projects.map((project) => [getId(project), project]));
    // Only milestones of projects the user can see (clients get their own projects).
    return data.milestones
      .map((milestone) => ({ ...milestone, project: byId.get(recordProjectId(milestone)) }))
      .filter((milestone) => milestone.project)
      .filter((milestone) => (!filters.project || recordProjectId(milestone) === filters.project) && (!filters.status || milestone.status === filters.status))
      .sort((a, b) => String(a.due_date || a.dueDate).localeCompare(String(b.due_date || b.dueDate)));
  }, [data, filters]);
  const isOverdue = (milestone) => milestone.status !== "Completed" && toDateInput(milestone.due_date || milestone.dueDate) < today;

  async function remove(milestone) {
    if (!confirmAction(`Delete milestone "${milestone.title}"?`)) return;
    await run("delete", () => deleteMilestoneRecord(getId(milestone)), { success: "Milestone deleted.", error: "Unable to delete milestone.", onSuccess: reload });
  }

  if (loading) return <LoadingState label="Loading milestones..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  return (
    <>
      <PageHeader
        onRefresh={reload}
        title="Milestones"
        description="Key delivery checkpoints across all projects."
        action={
          <div className="flex flex-wrap gap-2">
            {can.manage(user) ? <Button onClick={() => setForm({ open: true, milestone: null })}><Plus className="h-4 w-4" /> Add milestone</Button> : null}
          </div>
        }
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Milestones" value={rows.length} />
        <StatCard label="In progress" value={rows.filter((milestone) => milestone.status === "In Progress").length} />
        <StatCard label="Completed" value={rows.filter((milestone) => milestone.status === "Completed").length} />
        <StatCard label="Overdue" value={rows.filter(isOverdue).length} helper="Past due and not completed" />
      </section>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:max-w-2xl">
        <Select aria-label="Filter by project" className="h-10" value={filters.project} onChange={(event) => setFilters({ ...filters, project: event.target.value })}>
          <option value="">All projects</option>
          {data.projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
        <Select aria-label="Filter by status" className="h-10" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">All statuses</option>
          {MILESTONE_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
        </Select>
      </div>
      <DataTable
        columns={[
          { key: "title", header: "Milestone", render: (row) => <span className="font-semibold">{row.title}</span> },
          { key: "project", header: "Project", render: (row) => <Link className="text-primary" to={`/projects/${getId(row.project)}`}>{projectName(row.project)}</Link> },
          { key: "due", header: "Due", render: (row) => <span className={isOverdue(row) ? "font-semibold text-danger" : undefined}>{formatDate(row.due_date || row.dueDate)}</span> },
          { key: "progress", header: "Progress", render: (row) => `${Number(row.progress || 0)}%` },
          { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
          ...(can.manage(user)
            ? [{
                key: "actions",
                header: "Actions",
                render: (row) => (
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => setForm({ open: true, milestone: row })} size="sm" variant="secondary">Edit</Button>
                    {can.adminOnly(user) ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
                  </div>
                ),
              }]
            : []),
        ]}
        emptyDescription="Add milestones to projects to track delivery checkpoints."
        emptyTitle="No milestones"
        getRowId={getId}
        rows={rows}
      />
      <MilestoneFormModal
        milestone={form.milestone}
        onClose={() => setForm({ open: false, milestone: null })}
        onSaved={() => { setForm({ open: false, milestone: null }); reload(); }}
        open={form.open}
        projects={data.projects}
      />
    </>
  );
}
