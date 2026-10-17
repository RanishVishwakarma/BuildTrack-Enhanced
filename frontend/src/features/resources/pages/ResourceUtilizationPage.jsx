import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { formatStatus } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { RESOURCE_STATUSES, getResources } from "../services/resourceService.js";
import { useChartTheme } from "../../../lib/chartTheme.js";

const statusColors = (colors) => ({ available: colors.chart2, in_use: colors.chart1, maintenance: colors.warning, retired: colors.chart4 });

// Utilisation computed from the live /resources list: share of resources in
// use, broken down by type and by project.
export function ResourceUtilizationPage() {
  const chart = useChartTheme();
  const { data, loading, error, reload } = useAsyncData(getResources, [], { initialData: [] });
  const projects = useProjectOptions();

  if (loading) return <LoadingState label="Loading utilization..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  const resources = data || [];
  const inUse = resources.filter((resource) => resource.status === "in_use").length;
  const active = resources.filter((resource) => resource.status !== "retired").length;
  const utilization = active ? Math.round((inUse / active) * 100) : 0;

  const byStatus = RESOURCE_STATUSES.map((status) => ({ name: formatStatus(status), status, value: resources.filter((resource) => resource.status === status).length })).filter((item) => item.value);
  const types = [...new Set(resources.map((resource) => resource.resource_type || "other"))];
  const byType = types.map((type) => {
    const ofType = resources.filter((resource) => (resource.resource_type || "other") === type);
    return {
      name: formatStatus(type),
      "In use": ofType.filter((resource) => resource.status === "in_use").length,
      Available: ofType.filter((resource) => resource.status === "available").length,
      Maintenance: ofType.filter((resource) => resource.status === "maintenance").length,
    };
  });
  const byProject = Object.entries(
    resources.filter((resource) => resource.assigned_project).reduce((acc, resource) => ({ ...acc, [resource.assigned_project]: (acc[resource.assigned_project] || 0) + 1 }), {}),
  ).map(([projectId, count]) => ({ projectId, project: projects.nameOf(projectId), count }));

  return (
    <>
      <PageHeader
        title="Resource Utilization"
        description="How much of the equipment pool is deployed, by type and by project."
        onRefresh={reload}
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Utilization" value={`${utilization}%`} helper="In use ÷ non-retired resources" />
        <StatCard label="In use" value={inUse} />
        <StatCard label="Idle (available)" value={resources.filter((resource) => resource.status === "available").length} />
        <StatCard label="Under maintenance" value={resources.filter((resource) => resource.status === "maintenance").length} />
      </section>
      {resources.length ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="card">
            <h2 className="text-lg font-semibold">Resources by status</h2>
            <div className="h-[300px]">
              <ResponsiveContainer height="100%" width="100%">
                <PieChart>
                  <Pie data={byStatus} dataKey="value" label nameKey="name" outerRadius={100}>
                    {byStatus.map((entry) => <Cell fill={statusColors(chart.colors)[entry.status] || chart.colors.chart4} key={entry.status} />)}
                  </Pie>
                  <Tooltip {...chart.tooltip} />
                  <Legend wrapperStyle={chart.legend} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </section>
          <section className="card">
            <h2 className="text-lg font-semibold">Utilization by type</h2>
            <div className="h-[300px]">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={byType}>
                  <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis {...chart.axis} dataKey="name" />
                  <YAxis {...chart.axis} allowDecimals={false} />
                  <Tooltip {...chart.tooltip} />
                  <Legend wrapperStyle={chart.legend} />
                  <Bar dataKey="In use" fill={chart.colors.chart1} stackId="a" />
                  <Bar dataKey="Available" fill={chart.colors.chart2} stackId="a" />
                  <Bar dataKey="Maintenance" fill={chart.colors.warning} stackId="a" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
          <section className="card lg:col-span-2">
            <h2 className="mb-4 text-lg font-semibold">Resources deployed per project</h2>
            <DataTable
              columns={[{ key: "project", header: "Project" }, { key: "count", header: "Resources assigned" }]}
              emptyDescription="No resources are currently assigned to a project."
              emptyTitle="Nothing deployed"
              getRowId={(row) => row.projectId}
              rows={byProject}
            />
          </section>
        </div>
      ) : (
        <div className="card text-sm text-muted">No resources exist yet, so utilization cannot be calculated.</div>
      )}
    </>
  );
}
