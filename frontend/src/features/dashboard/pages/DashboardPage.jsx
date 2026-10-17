import { useMemo } from "react";
import { Link, Navigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getRoute } from "../../../app/routeConfig.js";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { ROLE, hasAnyRole, canOpenRoute } from "../../../lib/roles.js";
import { formatCurrency, formatDate, formatStatus, getId, projectName, toDateInput } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { projectStatusLabel } from "../../projects/services/projectService.js";
import { getDashboardData } from "../services/dashboardService.js";
import { useChartTheme } from "../../../lib/chartTheme.js";

const STATUS_LABELS = ["Completed", "In Progress", "On Hold", "Not Started"];
const statusColors = (colors) => ({ Completed: colors.chart2, "In Progress": colors.chart1, "On Hold": colors.warning, "Not Started": colors.chart4 });
const SOURCE_NAMES = { projects: "projects", metrics: "dashboard metrics", workforce: "workforce summary", procurement: "procurement summary", milestones: "milestones" };

function MetricCard({ to, canOpen, ...props }) {
  if (to && canOpen(to)) {
    return (
      <Link className="block rounded-lg transition hover:-translate-y-0.5 hover:shadow-md" to={to}>
        <StatCard {...props} />
      </Link>
    );
  }
  return <StatCard {...props} />;
}

export function DashboardPage() {
  const { user } = useAuth();
  const chart = useChartTheme();
  const isWorker = hasAnyRole(user, [ROLE.WORKER]);
  const isClient = hasAnyRole(user, [ROLE.CLIENT]);
  const { data, loading, error, reload } = useAsyncData(getDashboardData, [], { enabled: !isWorker });
  const canOpen = (path) => canOpenRoute(user, getRoute(path));

  const derived = useMemo(() => {
    const projects = data?.projects || [];
    const statusCounts = STATUS_LABELS.map((label) => ({ name: label, value: projects.filter((project) => projectStatusLabel(project.status) === label).length }));
    // Projects started per month over the last 6 months, by current status (from start_date).
    const months = Array.from({ length: 6 }, (_, index) => {
      const date = new Date();
      date.setDate(1);
      date.setMonth(date.getMonth() - (5 - index));
      return date;
    });
    const startedByMonth = months.map((month) => {
      const key = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}`;
      const row = { month: month.toLocaleDateString("en-IN", { month: "short", year: "2-digit" }) };
      for (const label of STATUS_LABELS) {
        row[label] = projects.filter((project) => project.start_date && String(project.start_date).slice(0, 7) === key && projectStatusLabel(project.status) === label).length;
      }
      return row;
    });
    const today = toDateInput();
    // Milestone records (project_milestones, as Angular used) plus milestones
    // embedded on project documents.
    const byId = new Map(projects.map((project) => [getId(project), project]));
    const upcoming = [
      ...(data?.milestones || []).map((milestone) => ({ ...milestone, due_date: milestone.due_date || milestone.dueDate, project: byId.get(milestone.project_id || milestone.projectId) })),
      ...projects.flatMap((project) => (project.milestones || []).map((milestone) => ({ ...milestone, project }))),
    ]
      .filter((milestone) => milestone.project && String(milestone.status).toLowerCase() !== "completed" && milestone.due_date && toDateInput(milestone.due_date) >= today)
      .sort((a, b) => String(a.due_date).localeCompare(String(b.due_date)))
      .slice(0, 5);
    return {
      projects,
      statusCounts,
      startedByMonth,
      upcoming,
      active: statusCounts.find((item) => item.name === "In Progress").value,
      budget: projects.reduce((sum, project) => sum + Number(project.budget || 0), 0),
      avgProgress: projects.length ? Math.round(projects.reduce((sum, project) => sum + Number(project.progress || 0), 0) / projects.length) : 0,
    };
  }, [data]);

  if (isWorker) return <Navigate replace to="/worker-dashboard" />;
  if (loading) return <LoadingState label="Loading dashboard..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  const { metrics, workforce, procurement, failed } = data;
  const categories = (workforce?.category_distribution || []).map((item) => ({ name: formatStatus(item._id || item.category || "Other"), count: item.count }));

  return (
    <>
      <PageHeader
        title={isClient ? "My Projects Overview" : "Dashboard"}
        description={`Welcome back, ${user?.name || "there"}. Live figures from projects, workforce, inventory and procurement.`}
        onRefresh={reload}
      />
      {failed.length ? (
        <div className="mb-4 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning" role="status">
          Some data could not be loaded ({failed.map((key) => SOURCE_NAMES[key]).join(", ")}). Those figures are shown as unavailable.
        </div>
      ) : null}

      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard canOpen={canOpen} label={isClient ? "My projects" : "Total projects"} to="/projects" value={derived.projects.length} helper={`${derived.active} in progress`} />
        <MetricCard canOpen={canOpen} label="Average progress" to="/projects/status-dashboard" value={`${derived.avgProgress}%`} helper="Across visible projects" />
        <MetricCard canOpen={canOpen} label="Total budget" to="/analytics/budget" value={formatCurrency(derived.budget)} helper="Sum of project budgets" />
        {isClient ? (
          <MetricCard canOpen={canOpen} label="Completed" value={derived.statusCounts.find((item) => item.name === "Completed").value} />
        ) : (
          <MetricCard
            canOpen={canOpen}
            helper={workforce ? `${workforce.available_workers ?? 0} available · ${workforce.assigned_workers ?? 0} assigned` : "Unavailable"}
            label="Workers"
            to="/workers"
            value={workforce?.total_workers ?? "Unavailable"}
          />
        )}
      </section>

      {!isClient ? (
        <section className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard canOpen={canOpen} helper="Awaiting project manager approval" label="Pending material requests" to="/procurement/approvals" value={procurement?.pending_requests ?? "Unavailable"} />
          <MetricCard canOpen={canOpen} helper={procurement ? `${procurement.pending_deliveries ?? 0} deliveries pending` : undefined} label="Active purchase orders" to="/procurement/purchase-orders" value={procurement?.active_purchase_orders ?? "Unavailable"} />
          <MetricCard canOpen={canOpen} helper={metrics ? `Stock value ${formatCurrency(metrics.total_inventory_value)}` : undefined} label="Low stock items" to="/inventory/stock-monitoring" value={metrics?.low_stock_items ?? "Unavailable"} />
          <MetricCard canOpen={canOpen} helper={metrics ? `of ${metrics.total_resources} resources` : undefined} label="Available resources" to="/resources" value={metrics?.available_resources ?? "Unavailable"} />
        </section>
      ) : null}

      <section className="mt-6 grid gap-5 lg:grid-cols-2">
        <div className="card">
          <h2 className="text-lg font-semibold">Project status</h2>
          {derived.projects.length ? (
            <div className="h-[280px]">
              <ResponsiveContainer height="100%" width="100%">
                <PieChart>
                  <Pie data={derived.statusCounts.filter((item) => item.value)} dataKey="value" innerRadius={60} label nameKey="name" outerRadius={100}>
                    {derived.statusCounts.filter((item) => item.value).map((entry) => <Cell fill={statusColors(chart.colors)[entry.name]} key={entry.name} />)}
                  </Pie>
                  <Tooltip {...chart.tooltip} />
                  <Legend wrapperStyle={chart.legend} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : <p className="mt-6 text-sm text-muted">No projects to chart yet.</p>}
        </div>
        <div className="card">
          <h2 className="text-lg font-semibold">Projects started (last 6 months)</h2>
          <div className="h-[280px]">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={derived.startedByMonth}>
                <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis {...chart.axis} dataKey="month" />
                <YAxis {...chart.axis} allowDecimals={false} />
                <Tooltip {...chart.tooltip} />
                <Legend wrapperStyle={chart.legend} />
                {Object.entries(statusColors(chart.colors)).map(([label, color]) => <Bar dataKey={label} fill={color} key={label} stackId="status" />)}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-5 lg:grid-cols-[1.2fr_1fr]">
        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Recent projects</h2>
            <Link className="text-sm font-semibold text-primary" to="/projects">View all</Link>
          </div>
          {derived.projects.length ? (
            <ul className="divide-y divide-border">
              {derived.projects
                .slice()
                .sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")))
                .slice(0, 6)
                .map((project) => (
                  <li key={getId(project)}>
                    <Link className="flex items-center justify-between gap-3 py-3 hover:text-primary" to={`/projects/${getId(project)}`}>
                      <div className="min-w-0">
                        <p className="truncate font-semibold">{projectName(project)}</p>
                        <p className="text-sm text-muted">{Number(project.progress || 0)}% complete · {formatCurrency(project.budget)}</p>
                      </div>
                      <StatusBadge status={projectStatusLabel(project.status)} />
                    </Link>
                  </li>
                ))}
            </ul>
          ) : <p className="text-sm text-muted">No projects returned by the backend.</p>}
        </div>
        <div className="space-y-5">
          <div className="card">
            <h2 className="mb-3 text-lg font-semibold">Upcoming milestones</h2>
            {derived.upcoming.length ? (
              <ul className="space-y-3">
                {derived.upcoming.map((milestone, index) => (
                  <li className="flex items-start justify-between gap-3" key={`${getId(milestone.project)}-${index}`}>
                    <div>
                      <p className="font-semibold">{milestone.title}</p>
                      <p className="text-sm text-muted">{projectName(milestone.project)}</p>
                    </div>
                    <span className="whitespace-nowrap text-sm text-muted">{formatDate(milestone.due_date)}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No upcoming milestones.</p>}
          </div>
          {!isClient && categories.length ? (
            <div className="card">
              <h2 className="text-lg font-semibold">Workforce by category</h2>
              <div className="h-[220px]">
                <ResponsiveContainer height="100%" width="100%">
                  <BarChart data={categories} layout="vertical" margin={{ left: 24 }}>
                    <XAxis {...chart.axis} allowDecimals={false} type="number" />
                    <YAxis {...chart.axis} dataKey="name" type="category" width={110} />
                    <Tooltip {...chart.tooltip} />
                    <Bar dataKey="count" fill={chart.colors.chart1} name="Workers" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </>
  );
}
