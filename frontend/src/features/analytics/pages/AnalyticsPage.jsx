import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { formatCurrency, formatDate, formatStatus, getId, normalizeList, projectName, toDateInput } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { getInvoices, getMaterialRequests, getPayments, getPurchaseOrders } from "../../procurement/services/procurementService.js";
import { getMilestoneRecords, getProjects, projectStatusLabel } from "../../projects/services/projectService.js";
import { getResources } from "../../resources/services/resourceService.js";
import { getWorkforceSummary } from "../../workforce/services/workforceService.js";
import { useChartTheme } from "../../../lib/chartTheme.js";

const statusColors = (colors) => ({ Completed: colors.chart2, "In Progress": colors.chart1, "On Hold": colors.warning, "Not Started": colors.chart4 });

const META = {
  progress: { title: "Progress Analytics", description: "Delivery progress, milestones and schedule risk across projects." },
  budget: { title: "Budget Analytics", description: "Project budgets against spend committed through purchase orders." },
  resource: { title: "Resource Analytics", description: "Equipment availability and workforce composition." },
  procurement: { title: "Procurement Analytics", description: "Request pipeline, purchase order value and invoice settlement." },
};

const countBy = (items, keyOf) =>
  Object.entries(items.reduce((acc, item) => {
    const key = keyOf(item) || "Unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {})).map(([name, value]) => ({ name, value }));

function ChartCard({ title, children, empty }) {
  return (
    <section className="card">
      <h2 className="text-lg font-semibold">{title}</h2>
      {empty ? <p className="mt-4 text-sm text-muted">{empty}</p> : <div className="mt-4 h-[300px]"><ResponsiveContainer height="100%" width="100%">{children}</ResponsiveContainer></div>}
    </section>
  );
}

function StatusPie({ data, colors }) {
  const chart = useChartTheme();
  return (
    <PieChart>
      <Pie data={data} dataKey="value" label nameKey="name" outerRadius={100}>
        {data.map((entry, index) => <Cell fill={colors?.[entry.name] || chart.series[index % chart.series.length]} key={entry.name} />)}
      </Pie>
      <Tooltip {...chart.tooltip} />
      <Legend wrapperStyle={chart.legend} />
    </PieChart>
  );
}

async function loadProjects() {
  return normalizeList(await getProjects()).items;
}

function ProgressAnalytics({ projects, milestoneRecords }) {
  const chart = useChartTheme();
  const today = toDateInput();
  const projectIds = new Set(projects.map(getId));
  const milestones = [
    ...milestoneRecords.filter((milestone) => projectIds.has(milestone.project_id || milestone.projectId)),
    ...projects.flatMap((project) => project.milestones || []),
  ];
  const atRisk = projects.filter((project) => {
    const label = projectStatusLabel(project.status);
    return label === "On Hold" || (label !== "Completed" && project.end_date && toDateInput(project.end_date) < today);
  });
  const avg = projects.length ? Math.round(projects.reduce((sum, project) => sum + Number(project.progress || 0), 0) / projects.length) : 0;
  const byProgress = projects.slice().sort((a, b) => Number(b.progress || 0) - Number(a.progress || 0)).slice(0, 12).map((project) => ({ name: projectName(project), Progress: Number(project.progress || 0) }));
  const statuses = countBy(projects, (project) => projectStatusLabel(project.status));

  return (
    <>
      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Average progress" value={`${avg}%`} />
        <StatCard label="Completed projects" value={statuses.find((item) => item.name === "Completed")?.value || 0} />
        <StatCard label="At risk" value={atRisk.length} helper="On hold, or past end date and not completed" />
        <StatCard label="Milestones completed" value={`${milestones.filter((m) => String(m.status).toLowerCase() === "completed").length} / ${milestones.length}`} />
      </section>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard empty={!byProgress.length && "No projects yet."} title="Progress by project">
          <BarChart data={byProgress} layout="vertical" margin={{ left: 24 }}>
            <XAxis {...chart.axis} domain={[0, 100]} type="number" unit="%" />
            <YAxis {...chart.axis} dataKey="name" type="category" width={140} tick={{ ...chart.axis.tick, fontSize: 11 }} />
            <Tooltip {...chart.tooltip} formatter={(value) => `${value}%`} />
            <Bar dataKey="Progress" fill={chart.colors.chart1} />
          </BarChart>
        </ChartCard>
        <ChartCard empty={!statuses.length && "No projects yet."} title="Projects by status"><StatusPie colors={statusColors(chart.colors)} data={statuses} /></ChartCard>
      </div>
      <section className="card mt-6">
        <h2 className="mb-4 text-lg font-semibold">Projects at risk</h2>
        <DataTable
          columns={[
            { key: "name", header: "Project", render: (row) => projectName(row) },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={projectStatusLabel(row.status)} /> },
            { key: "progress", header: "Progress", render: (row) => `${Number(row.progress || 0)}%` },
            { key: "end_date", header: "Planned end", render: (row) => formatDate(row.end_date) },
          ]}
          emptyDescription="No project is on hold or past its planned end date."
          emptyTitle="No projects at risk"
          getRowId={getId}
          rows={atRisk}
        />
      </section>
    </>
  );
}

function BudgetAnalytics({ projects, orders }) {
  const chart = useChartTheme();
  const spendFor = (project) => {
    const id = getId(project);
    const name = projectName(project).toLowerCase();
    return (orders || []).filter((po) => po.project_id === id || (!po.project_id && String(po.project || "").toLowerCase() === name)).reduce((sum, po) => sum + Number(po.total_cost || 0), 0);
  };
  const rows = projects.map((project) => ({ project, budget: Number(project.budget || 0), spend: spendFor(project) }));
  const budget = rows.reduce((sum, row) => sum + row.budget, 0);
  const spend = rows.reduce((sum, row) => sum + row.spend, 0);
  const byCategory = Object.entries(rows.reduce((acc, row) => ({ ...acc, [row.project.category || "Uncategorised"]: (acc[row.project.category || "Uncategorised"] || 0) + row.budget }), {})).map(([name, value]) => ({ name, value }));
  const budgetRows = rows.slice().sort((a, b) => b.budget - a.budget).slice(0, 10).map((row) => ({ name: projectName(row.project), Budget: row.budget, "Committed spend": row.spend }));

  return (
    <>
      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total budget" value={formatCurrency(budget)} />
        <StatCard label="Committed spend" value={orders ? formatCurrency(spend) : "Unavailable"} helper="Purchase order totals" />
        <StatCard label="Budget committed" value={orders && budget ? `${Math.round((spend / budget) * 100)}%` : "Unavailable"} />
        <StatCard label="Over-committed projects" value={orders ? rows.filter((row) => row.budget && row.spend > row.budget).length : "Unavailable"} />
      </section>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard empty={!budgetRows.length && "No projects yet."} title="Budget vs committed spend">
          <BarChart data={budgetRows}>
            <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis {...chart.axis} dataKey="name" interval={0} tick={{ ...chart.axis.tick, fontSize: 11 }} angle={-20} textAnchor="end" height={70} />
            <YAxis {...chart.axis} tickFormatter={(value) => `${Math.round(value / 100000)}L`} />
            <Tooltip {...chart.tooltip} formatter={(value) => formatCurrency(value)} />
            <Legend wrapperStyle={chart.legend} />
            <Bar dataKey="Budget" fill={chart.colors.chart1} />
            <Bar dataKey="Committed spend" fill={chart.colors.chart2} />
          </BarChart>
        </ChartCard>
        <ChartCard empty={!byCategory.some((item) => item.value) && "No budgets recorded."} title="Budget by category">
          <PieChart>
            <Pie data={byCategory} dataKey="value" label={({ name }) => name} nameKey="name" outerRadius={100}>
              {byCategory.map((entry, index) => <Cell fill={chart.series[index % chart.series.length]} key={entry.name} />)}
            </Pie>
            <Tooltip {...chart.tooltip} formatter={(value) => formatCurrency(value)} />
          </PieChart>
        </ChartCard>
      </div>
      {!orders ? <p className="mt-4 text-sm text-muted">Purchase orders are not available to your role, so spend figures are omitted.</p> : null}
    </>
  );
}

function ResourceAnalytics({ resources, workforce }) {
  const chart = useChartTheme();
  const byStatus = countBy(resources, (resource) => formatStatus(resource.status));
  const byType = countBy(resources, (resource) => formatStatus(resource.resource_type));
  const categories = (workforce?.category_distribution || []).map((item) => ({ name: formatStatus(item._id || "Other"), Workers: item.count }));
  const inUse = resources.filter((resource) => resource.status === "in_use").length;
  const active = resources.filter((resource) => resource.status !== "retired").length;

  return (
    <>
      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Resources" value={resources.length} />
        <StatCard label="Equipment utilization" value={active ? `${Math.round((inUse / active) * 100)}%` : "0%"} helper="In use ÷ non-retired" />
        <StatCard label="Workers" value={workforce?.total_workers ?? "Unavailable"} />
        <StatCard label="Workers available" value={workforce?.available_workers ?? "Unavailable"} helper={workforce ? `${workforce.assigned_workers ?? 0} assigned` : undefined} />
      </section>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <ChartCard empty={!byStatus.length && "No resources yet."} title="Resources by status"><StatusPie data={byStatus} /></ChartCard>
        <ChartCard empty={!byType.length && "No resources yet."} title="Resources by type">
          <BarChart data={byType}>
            <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis {...chart.axis} dataKey="name" />
            <YAxis {...chart.axis} allowDecimals={false} />
            <Tooltip {...chart.tooltip} />
            <Bar dataKey="value" fill={chart.colors.chart1} name="Resources" />
          </BarChart>
        </ChartCard>
        <ChartCard empty={!categories.length && "Workforce summary unavailable."} title="Workforce by category">
          <BarChart data={categories}>
            <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis {...chart.axis} dataKey="name" tick={{ ...chart.axis.tick, fontSize: 10 }} />
            <YAxis {...chart.axis} allowDecimals={false} />
            <Tooltip {...chart.tooltip} />
            <Bar dataKey="Workers" fill={chart.colors.chart2} />
          </BarChart>
        </ChartCard>
      </div>
    </>
  );
}

function ProcurementAnalytics({ requests, orders, invoices, payments }) {
  const chart = useChartTheme();
  const poValue = orders.reduce((sum, po) => sum + Number(po.total_cost || 0), 0);
  const invoiced = invoices.reduce((sum, invoice) => sum + Number(invoice.amount || 0) + Number(invoice.gst || 0), 0);
  const paid = payments.filter((payment) => payment.status === "paid").reduce((sum, payment) => sum + Number(payment.amount || 0), 0);
  const requestStatus = countBy(requests, (request) => formatStatus(request.status));
  const poStatus = Object.entries(orders.reduce((acc, po) => {
    const key = formatStatus(po.status);
    acc[key] = acc[key] || { name: key, Orders: 0, Value: 0 };
    acc[key].Orders += 1;
    acc[key].Value += Number(po.total_cost || 0);
    return acc;
  }, {})).map(([, value]) => value);

  return (
    <>
      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Material requests" value={requests.length} helper={`${requests.filter((request) => request.status === "pending").length} awaiting approval`} />
        <StatCard label="Purchase order value" value={formatCurrency(poValue)} helper={`${orders.length} orders`} />
        <StatCard label="Invoiced" value={formatCurrency(invoiced)} helper={`${invoices.length} invoices`} />
        <StatCard label="Paid" value={formatCurrency(paid)} helper={invoiced ? `${Math.round((paid / invoiced) * 100)}% of invoiced` : undefined} />
      </section>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard empty={!requestStatus.length && "No material requests yet."} title="Material requests by status"><StatusPie data={requestStatus} /></ChartCard>
        <ChartCard empty={!poStatus.length && "No purchase orders yet."} title="Purchase orders by status">
          <BarChart data={poStatus}>
            <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis {...chart.axis} dataKey="name" />
            <YAxis {...chart.axis} allowDecimals={false} yAxisId="count" />
            <YAxis {...chart.axis} orientation="right" tickFormatter={(value) => `${Math.round(value / 1000)}k`} yAxisId="value" />
            <Tooltip {...chart.tooltip} formatter={(value, name) => (name === "Value" ? formatCurrency(value) : value)} />
            <Legend wrapperStyle={chart.legend} />
            <Bar dataKey="Orders" fill={chart.colors.chart1} yAxisId="count" />
            <Bar dataKey="Value" fill={chart.colors.chart2} yAxisId="value" />
          </BarChart>
        </ChartCard>
      </div>
    </>
  );
}

const LOADERS = {
  progress: async () => {
    const [projects, milestoneRecords] = await Promise.all([loadProjects(), getMilestoneRecords().catch(() => [])]);
    return { projects, milestoneRecords };
  },
  budget: async () => {
    const [projects, orders] = await Promise.all([loadProjects(), getPurchaseOrders({ limit: 1000 }).then((page) => page.items).catch(() => null)]);
    return { projects, orders };
  },
  resource: async () => {
    const [resources, workforce] = await Promise.all([getResources(), getWorkforceSummary().catch(() => null)]);
    return { resources, workforce };
  },
  procurement: async () => {
    const [requests, orders, invoices, payments] = await Promise.all([
      getMaterialRequests({ limit: 1000 }),
      getPurchaseOrders({ limit: 1000 }),
      getInvoices({ limit: 1000 }),
      getPayments({ limit: 1000 }),
    ]);
    return { requests: requests.items, orders: orders.items, invoices: invoices.items, payments: payments.items };
  },
};

const VIEWS = { progress: ProgressAnalytics, budget: BudgetAnalytics, resource: ResourceAnalytics, procurement: ProcurementAnalytics };

export function AnalyticsPage({ type }) {
  const { data, loading, error, reload } = useAsyncData(LOADERS[type], [type]);
  const View = VIEWS[type];
  const meta = META[type];

  return (
    <>
      <PageHeader
        eyebrow="Analytics"
        title={meta.title}
        description={meta.description}
        onRefresh={reload}
      />
      {loading ? <LoadingState label="Loading analytics..." /> : null}
      {!loading && error ? <ErrorState message={getApiErrorMessage(error)} onRetry={reload} /> : null}
      {!loading && !error && data ? <View {...data} /> : null}
    </>
  );
}
