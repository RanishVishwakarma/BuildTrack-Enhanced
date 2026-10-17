import { Link } from "react-router-dom";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { formatCurrency, formatDate, getId, normalizeList, projectName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { PROJECT_STATUSES, getProjects, projectStatusLabel } from "../services/projectService.js";

// Angular ProjectStatusDashboardComponent: projects grouped into status columns.
export function ProjectStatusDashboardPage() {
  const { data, loading, error, reload } = useAsyncData(async () => normalizeList(await getProjects()).items, [], { initialData: [] });

  if (loading) return <LoadingState label="Loading projects..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  const columns = PROJECT_STATUSES.map((status) => ({ ...status, projects: data.filter((project) => projectStatusLabel(project.status) === status.label) }));

  return (
    <>
      <PageHeader
        title="Project Status Dashboard"
        description="Every project grouped by its current status."
        onRefresh={reload}
      />
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        {columns.map((column) => (
          <section className="rounded-lg border border-border bg-subtle p-3" key={column.value}>
            <h2 className="mb-3 flex items-center justify-between px-1 text-sm font-semibold">
              {column.label}
              <span className="rounded-full bg-surface px-2 py-0.5 text-xs text-muted">{column.projects.length}</span>
            </h2>
            <div className="space-y-3">
              {column.projects.map((project) => (
                <Link className="block rounded-md border border-border bg-surface p-3 shadow-sm hover:border-primary" key={getId(project)} to={`/projects/${getId(project)}`}>
                  <p className="font-semibold">{projectName(project)}</p>
                  <p className="mt-1 text-xs text-muted">{project.location || project.category}</p>
                  <div className="mt-3 h-1.5 rounded-full bg-secondary"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${Math.min(100, Number(project.progress || 0))}%` }} /></div>
                  <div className="mt-2 flex justify-between text-xs text-muted">
                    <span>{Number(project.progress || 0)}%</span>
                    <span>{formatCurrency(project.budget)}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted">Due {formatDate(project.end_date)}</p>
                </Link>
              ))}
              {!column.projects.length ? <p className="px-1 text-sm text-muted">No projects.</p> : null}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
