import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { formatDateTime, formatNumber, getId } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { getInventory, getLowStockItems } from "../services/inventoryService.js";
import { useChartTheme } from "../../../lib/chartTheme.js";

// Read-only stock monitor (Angular StockMonitoringComponent): what needs
// reordering, using GET /inventory and GET /inventory/low-stock.
export function StockMonitoringPage() {
  const chart = useChartTheme();
  const { data, loading, error, reload } = useAsyncData(async () => {
    const [items, lowStock] = await Promise.all([getInventory(), getLowStockItems()]);
    return { items, lowStock };
  }, []);

  if (loading) return <LoadingState label="Loading stock levels..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  const items = data.items;
  const attention = items
    .filter((item) => item.status !== "in_stock")
    .sort((a, b) => Number(a.quantity) - Number(b.quantity));
  const chartData = items
    .slice()
    .sort((a, b) => Number(a.quantity) / Math.max(1, a.reorder_level) - Number(b.quantity) / Math.max(1, b.reorder_level))
    .slice(0, 12)
    .map((item) => ({ name: item.material_name, "On hand": Number(item.quantity), "Reorder level": Number(item.reorder_level) }));

  return (
    <>
      <PageHeader
        title="Stock Monitoring"
        description="Materials at or below their reorder level, refreshed from live inventory."
        onRefresh={reload}
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Tracked materials" value={items.length} />
        <StatCard label="In stock" value={items.filter((item) => item.status === "in_stock").length} />
        <StatCard label="Low stock" value={items.filter((item) => item.status === "low_stock").length} helper={`Backend low-stock query: ${data.lowStock.length}`} />
        <StatCard label="Out of stock" value={items.filter((item) => item.status === "out_of_stock").length} />
      </section>
      <section className="card mb-6">
        <h2 className="text-lg font-semibold">Lowest stock relative to reorder level</h2>
        {chartData.length ? (
          <div className="mt-4 h-[320px]">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={chartData} margin={{ left: 0, right: 8 }}>
                <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis {...chart.axis} dataKey="name" interval={0} tick={{ ...chart.axis.tick, fontSize: 11 }} angle={-25} textAnchor="end" height={70} />
                <YAxis {...chart.axis} allowDecimals={false} />
                <Tooltip {...chart.tooltip} />
                <Legend wrapperStyle={chart.legend} />
                <Bar dataKey="On hand" fill={chart.colors.chart1} />
                <Bar dataKey="Reorder level" fill={chart.colors.chart2} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <p className="mt-4 text-sm text-muted">No inventory items to chart.</p>}
      </section>
      <section className="card">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Needs attention</h2>
          <Link className="text-sm font-semibold text-primary" to="/procurement/request">Raise a material request</Link>
        </div>
        <DataTable
          columns={[
            { key: "material_name", header: "Material", render: (row) => <span className="font-semibold">{row.material_name}</span> },
            { key: "quantity", header: "On hand", render: (row) => `${formatNumber(row.quantity)} ${row.unit}` },
            { key: "reorder_level", header: "Reorder level", render: (row) => formatNumber(row.reorder_level) },
            { key: "shortfall", header: "Shortfall", render: (row) => formatNumber(Math.max(0, Number(row.reorder_level) - Number(row.quantity))) },
            { key: "location", header: "Location" },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "updated_at", header: "Updated", render: (row) => formatDateTime(row.updated_at) },
          ]}
          emptyDescription="Every material is above its reorder level."
          emptyTitle="All stock levels healthy"
          getRowId={getId}
          rows={attention}
        />
      </section>
    </>
  );
}
