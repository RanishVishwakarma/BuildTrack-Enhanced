import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { can } from "../../../lib/roles.js";
import { addDays, downloadCsv, formatCurrency, formatDate, formatDateTime, formatStatus, getId, normalizeList, projectName, toDateInput } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { downloadBlob } from "../../../services/fileDownload.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getPurchaseOrders } from "../../procurement/services/procurementService.js";
import { PROJECT_STATUSES, getProjects, projectStatusLabel } from "../../projects/services/projectService.js";
import { getProcurementSummary, getSavedReports, exportReport } from "../services/reportService.js";
import { useChartTheme } from "../../../lib/chartTheme.js";

const PRESETS = [
  { key: "overall", label: "Overall", days: null },
  { key: "today", label: "Today", days: 0 },
  { key: "7", label: "7 days ago", days: 7 },
  { key: "30", label: "30 days ago", days: 30 },
];

// Committed spend per project = purchase orders raised for it (matched by
// project_id, or by project name for older POs).
function spendFor(project, orders) {
  const id = getId(project);
  const name = projectName(project).toLowerCase();
  return orders.filter((po) => po.project_id === id || (!po.project_id && String(po.project || "").toLowerCase() === name)).reduce((sum, po) => sum + Number(po.total_cost || 0), 0);
}

export function ReportsPage() {
  const { user } = useAuth();
  const chart = useChartTheme();
  const { run, isPending } = useAction();
  const [filters, setFilters] = useState({ asOf: "", status: "", project: "" });
  const { data, loading, error, reload } = useAsyncData(async () => {
    const [projects, orders, saved, legacy] = await Promise.allSettled([getProjects(), getPurchaseOrders({ limit: 1000 }), getSavedReports(), getProcurementSummary()]);
    if (projects.status === "rejected") throw projects.reason;
    return {
      projects: normalizeList(projects.value).items,
      orders: orders.status === "fulfilled" ? orders.value.items : null,
      saved: saved.status === "fulfilled" ? saved.value : [],
      legacy: legacy.status === "fulfilled" ? legacy.value : null,
    };
  }, []);

  const report = useMemo(() => {
    if (!data) return null;
    const asOf = filters.asOf;
    const orders = (data.orders || []).filter((po) => !asOf || (po.created_at && toDateInput(po.created_at) <= asOf));
    const projects = data.projects
      .filter((project) => !asOf || (project.start_date && toDateInput(project.start_date) <= asOf))
      .filter((project) => !filters.status || projectStatusLabel(project.status) === filters.status)
      .filter((project) => !filters.project || getId(project) === filters.project)
      .map((project) => ({ project, label: projectStatusLabel(project.status), spend: spendFor(project, orders) }));
    const count = (label) => projects.filter((row) => row.label === label).length;
    return {
      rows: projects,
      total: projects.length,
      completed: count("Completed"),
      inProgress: count("In Progress"),
      onHoldOrPlanned: count("On Hold") + count("Not Started"),
      budget: projects.reduce((sum, row) => sum + Number(row.project.budget || 0), 0),
      spend: projects.reduce((sum, row) => sum + row.spend, 0),
      avgProgress: projects.length ? Math.round(projects.reduce((sum, row) => sum + Number(row.project.progress || 0), 0) / projects.length) : 0,
    };
  }, [data, filters]);

  if (loading) return <LoadingState label="Loading reports..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  const activePreset = PRESETS.find((preset) => (preset.days === null ? !filters.asOf : filters.asOf === addDays(-preset.days)))?.key;
  const periodLabel = filters.asOf ? `as of ${formatDate(filters.asOf)}` : "overall";
  const chartRows = report.rows
    .slice()
    .sort((a, b) => Number(b.project.budget || 0) - Number(a.project.budget || 0))
    .slice(0, 10)
    .map((row) => ({ name: projectName(row.project), Budget: Number(row.project.budget || 0), "Committed spend": row.spend }));

  function exportCsv() {
    downloadCsv(`buildtrack-report-${filters.asOf || "overall"}.csv`, [
      ["BuildTrack project report", periodLabel],
      [],
      ["Metric", "Value"],
      ["Projects", report.total],
      ["Completed", report.completed],
      ["In progress", report.inProgress],
      ["On hold / not started", report.onHoldOrPlanned],
      ["Average progress (current)", `${report.avgProgress}%`],
      ["Total budget (Rs)", report.budget],
      ["Committed spend from purchase orders (Rs)", report.spend],
      [],
      ["Project", "Status", "Progress", "Budget (Rs)", "Committed spend (Rs)", "Start date", "End date"],
      ...report.rows.map((row) => [projectName(row.project), row.label, `${Number(row.project.progress || 0)}%`, row.project.budget ?? 0, row.spend, toDateInput(row.project.start_date), row.project.end_date ? toDateInput(row.project.end_date) : ""]),
    ]);
  }

  const exportBackend = (format) =>
    run(format, async () => downloadBlob(await exportReport(format), format === "pdf" ? "procurement-summary.pdf" : "procurement-summary.xlsx"), { error: "Export failed." });

  return (
    <>
      <PageHeader
        onRefresh={reload}
        title="Reports"
        description="Project portfolio report built from live project and purchase order records."
        action={
          <div className="flex flex-wrap gap-2">
            <Button disabled={!report.rows.length} onClick={exportCsv}><Download className="h-4 w-4" /> Export CSV</Button>
          </div>
        }
      />

      <section className="card mb-6">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Report period">
            {PRESETS.map((preset) => (
              <Button
                aria-pressed={activePreset === preset.key}
                key={preset.key}
                onClick={() => setFilters({ ...filters, asOf: preset.days === null ? "" : addDays(-preset.days) })}
                size="sm"
                variant={activePreset === preset.key ? "primary" : "secondary"}
              >
                {preset.label}
              </Button>
            ))}
          </div>
          <div className="w-44"><Input aria-label="Report as of date" label="As of" max={toDateInput()} type="date" value={filters.asOf} onChange={(event) => setFilters({ ...filters, asOf: event.target.value })} /></div>
          <div className="w-48">
            <Select label="Status" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
              <option value="">All statuses</option>
              {PROJECT_STATUSES.map((item) => <option key={item.value} value={item.label}>{item.label}</option>)}
            </Select>
          </div>
          <div className="w-56">
            <Select label="Project" value={filters.project} onChange={(event) => setFilters({ ...filters, project: event.target.value })}>
              <option value="">All projects</option>
              {data.projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
            </Select>
          </div>
        </div>
        <p className="mt-3 text-xs text-muted">
          A date limits the report to projects started and purchase orders raised on or before it. Status and progress are current values; the backend keeps no status history.
        </p>
      </section>

      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Projects" value={report.total} helper={periodLabel} />
        <StatCard label="Completed" value={report.completed} />
        <StatCard label="In progress" value={report.inProgress} />
        <StatCard label="On hold / not started" value={report.onHoldOrPlanned} />
      </section>
      <section className="mt-5 grid gap-5 sm:grid-cols-3">
        <StatCard label="Total budget" value={formatCurrency(report.budget)} />
        <StatCard label="Committed spend" value={data.orders ? formatCurrency(report.spend) : "Unavailable"} helper={data.orders ? "Sum of purchase order totals" : "Purchase orders could not be loaded for your role"} />
        <StatCard label="Average progress" value={`${report.avgProgress}%`} />
      </section>

      <section className="card mt-6">
        <h2 className="text-lg font-semibold">Budget vs committed spend (top 10 by budget)</h2>
        {chartRows.length ? (
          <div className="mt-4 h-[320px]">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={chartRows}>
                <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis {...chart.axis} dataKey="name" interval={0} tick={{ ...chart.axis.tick, fontSize: 11 }} angle={-20} textAnchor="end" height={70} />
                <YAxis {...chart.axis} tickFormatter={(value) => `${Math.round(value / 100000)}L`} />
                <Tooltip {...chart.tooltip} formatter={(value) => formatCurrency(value)} />
                <Legend wrapperStyle={chart.legend} />
                <Bar dataKey="Budget" fill={chart.colors.chart1} />
                <Bar dataKey="Committed spend" fill={chart.colors.chart2} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <p className="mt-4 text-sm text-muted">No projects match the selected filters.</p>}
      </section>

      <section className="card mt-6">
        <h2 className="mb-4 text-lg font-semibold">Project breakdown</h2>
        <DataTable
          columns={[
            { key: "name", header: "Project", render: (row) => <Link className="font-semibold text-primary" to={`/projects/${getId(row.project)}`}>{projectName(row.project)}</Link> },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.label} /> },
            { key: "progress", header: "Progress", render: (row) => `${Number(row.project.progress || 0)}%` },
            { key: "budget", header: "Budget", render: (row) => formatCurrency(row.project.budget) },
            { key: "spend", header: "Committed spend", render: (row) => formatCurrency(row.spend) },
            { key: "start", header: "Start", render: (row) => formatDate(row.project.start_date) },
            { key: "end", header: "End", render: (row) => formatDate(row.project.end_date) },
          ]}
          emptyDescription="Adjust the filters to include more projects."
          emptyTitle="No projects in this report"
          getRowId={(row) => getId(row.project)}
          rows={report.rows}
        />
      </section>

      <section className="mt-6 grid gap-5 lg:grid-cols-2">
        <div className="card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Legacy procurement summary</h2>
            {can.manage(user) ? (
              <div className="flex gap-2">
                <Button disabled={isPending("pdf")} onClick={() => exportBackend("pdf")} size="sm" variant="secondary"><FileText className="h-4 w-4" /> PDF</Button>
                <Button disabled={isPending("excel")} onClick={() => exportBackend("excel")} size="sm" variant="secondary"><FileSpreadsheet className="h-4 w-4" /> Excel</Button>
              </div>
            ) : null}
          </div>
          <p className="mb-3 text-xs text-muted">From GET /reports/procurement, which summarises the older procurements collection (not the material request workflow).</p>
          {data.legacy ? (
            <dl className="grid gap-2 text-sm">
              {Object.entries(data.legacy).map(([key, value]) => (
                <div className="flex items-center justify-between gap-3 border-b border-border pb-2" key={key}>
                  <dt className="text-muted">{formatStatus(key)}</dt>
                  <dd className="text-right font-semibold">
                    {value && typeof value === "object" ? Object.entries(value).map(([k, v]) => `${formatStatus(k)}: ${v}`).join(", ") || "None" : String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : <p className="text-sm text-muted">Summary unavailable.</p>}
        </div>
        <div className="card">
          <h2 className="mb-3 text-lg font-semibold">Saved report records</h2>
          <DataTable
            columns={[
              { key: "title", header: "Title" },
              { key: "report_type", header: "Type", render: (row) => formatStatus(row.report_type) },
              { key: "generated_by", header: "By" },
              { key: "created_at", header: "Created", render: (row) => formatDateTime(row.created_at) },
            ]}
            emptyDescription="No report records have been saved in the backend."
            emptyTitle="No saved reports"
            getRowId={getId}
            rows={data.saved}
          />
        </div>
      </section>
    </>
  );
}
