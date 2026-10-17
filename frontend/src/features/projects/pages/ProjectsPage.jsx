import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { SearchInput } from "../../../components/common/SearchInput.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { ROLE, can, hasAnyRole } from "../../../lib/roles.js";
import { formatCurrency, formatDate, getId, matchesSearch, normalizeList, projectName, toDateInput } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getWorkerAllocations } from "../../workforce/services/workforceService.js";
import { ProjectFormModal } from "../components/ProjectFormModal.jsx";
import { PROJECT_STATUSES, deleteProject, getProjects, projectStatusLabel } from "../services/projectService.js";

const managerOf = (project) => (project.project_manager_id && project.project_manager_id !== "unassigned" ? project.project_manager_id : "Unassigned");

export function ProjectsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isWorker = hasAnyRole(user, [ROLE.WORKER]);
  const { run } = useAction();
  const [filters, setFilters] = useState({ query: "", status: "", minProgress: "", startedBefore: "" });
  const [form, setForm] = useState({ open: false, project: null });

  // Workers see only projects they are allocated to (Angular "My Projects").
  const { data, loading, error, reload } = useAsyncData(
    async () => {
      const projects = normalizeList(await getProjects()).items;
      if (!isWorker) return projects;
      if (!user?.workerId) return [];
      const allocations = normalizeList(await getWorkerAllocations(user.workerId)).items;
      const ids = new Set(allocations.map((allocation) => allocation.project_id));
      return projects.filter((project) => ids.has(getId(project)));
    },
    [isWorker, user?.workerId],
    { initialData: [] },
  );
  const projects = data;

  const filtered = useMemo(
    () =>
      projects.filter(
        (project) =>
          matchesSearch([projectName(project), project.location, project.client, managerOf(project), project.category], filters.query) &&
          (!filters.status || projectStatusLabel(project.status) === filters.status) &&
          (!filters.minProgress || Number(project.progress || 0) >= Number(filters.minProgress)) &&
          (!filters.startedBefore || (project.start_date && toDateInput(project.start_date) <= filters.startedBefore)),
      ),
    [projects, filters],
  );

  async function remove(project) {
    if (!confirmAction(`Delete project ${projectName(project)}? This cannot be undone.`)) return;
    await run("delete", () => deleteProject(getId(project)), { success: "Project deleted.", error: "Unable to delete project.", onSuccess: reload });
  }

  const countBy = (label) => projects.filter((project) => projectStatusLabel(project.status) === label).length;
  const hasFilters = Object.values(filters).some(Boolean);

  return (
    <>
      <PageHeader
        onRefresh={reload}
        title={isWorker ? "My Projects" : "Projects"}
        description={isWorker ? "Projects you are allocated to." : "All construction projects, their progress, budget and team."}
        action={
          <div className="flex flex-wrap gap-2">
            {can.manage(user) ? <Button onClick={() => setForm({ open: true, project: null })}><Plus className="h-4 w-4" /> New project</Button> : null}
          </div>
        }
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total projects" value={projects.length} />
        <StatCard label="In progress" value={countBy("In Progress")} />
        <StatCard label="On hold" value={countBy("On Hold")} />
        <StatCard label="Completed" value={countBy("Completed")} />
      </section>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="lg:col-span-2"><SearchInput aria-label="Search projects" placeholder="Search name, client, location, manager..." value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} /></div>
        <Select aria-label="Filter by status" className="h-10" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">All statuses</option>
          {PROJECT_STATUSES.map((item) => <option key={item.value} value={item.label}>{item.label}</option>)}
        </Select>
        <Select aria-label="Minimum progress" className="h-10" value={filters.minProgress} onChange={(event) => setFilters({ ...filters, minProgress: event.target.value })}>
          <option value="">Any progress</option>
          {[25, 50, 75, 100].map((value) => <option key={value} value={value}>{value}% or more</option>)}
        </Select>
        <div className="flex gap-2">
          <Input aria-label="Started on or before" className="h-10" title="Started on or before" type="date" value={filters.startedBefore} onChange={(event) => setFilters({ ...filters, startedBefore: event.target.value })} />
          {hasFilters ? <Button onClick={() => setFilters({ query: "", status: "", minProgress: "", startedBefore: "" })} variant="ghost">Reset</Button> : null}
        </div>
      </div>
      {loading ? <LoadingState label="Loading projects..." /> : null}
      {!loading && error ? <ErrorState message={getApiErrorMessage(error)} onRetry={reload} /> : null}
      {!loading && !error ? (
        <DataTable
          columns={[
            { key: "name", header: "Project", render: (row) => <Link className="font-semibold text-primary" to={`/projects/${getId(row)}`}>{projectName(row)}</Link> },
            { key: "category", header: "Category" },
            { key: "manager", header: "Manager", render: managerOf },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={projectStatusLabel(row.status)} /> },
            {
              key: "progress",
              header: "Progress",
              render: (row) => (
                <div className="flex min-w-[120px] items-center gap-2">
                  <div className="h-2 flex-1 rounded-full bg-secondary"><div className="h-2 rounded-full bg-primary" style={{ width: `${Math.min(100, Number(row.progress || 0))}%` }} /></div>
                  <span className="text-xs font-semibold">{Number(row.progress || 0)}%</span>
                </div>
              ),
            },
            { key: "budget", header: "Budget", render: (row) => formatCurrency(row.budget) },
            { key: "start_date", header: "Start", render: (row) => formatDate(row.start_date) },
            {
              key: "actions",
              header: "Actions",
              render: (row) => (
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => navigate(`/projects/${getId(row)}`)} size="sm" variant="secondary">Open</Button>
                  {can.manage(user) ? <Button onClick={() => setForm({ open: true, project: row })} size="sm" variant="secondary">Edit</Button> : null}
                  {can.adminOnly(user) ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
                </div>
              ),
            },
          ]}
          emptyDescription={hasFilters ? "No projects match the current filters." : isWorker ? "You are not allocated to any project yet." : "Create a project to get started."}
          emptyTitle={hasFilters ? "No matching projects" : "No projects"}
          getRowId={getId}
          rows={filtered}
        />
      ) : null}
      <ProjectFormModal onClose={() => setForm({ open: false, project: null })} onSaved={() => { setForm({ open: false, project: null }); reload(); }} open={form.open} project={form.project} />
    </>
  );
}
