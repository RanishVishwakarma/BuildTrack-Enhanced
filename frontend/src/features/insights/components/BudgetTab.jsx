import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { formatCurrency } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { getBudget } from "../services/insightsService.js";

function FlagList({ title, items, render }) {
  if (!items?.length) return null;
  return (
    <section className="card">
      <h3 className="text-sm font-semibold text-foreground">{title} ({items.length})</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{items.map((item, i) => <li key={i}>{render(item)}</li>)}</ul>
    </section>
  );
}

export function BudgetTab({ projectId }) {
  const budget = useAsyncData(() => getBudget(projectId), [projectId]);
  usePageRefresh(budget.reload);
  if (budget.loading && !budget.data) return <LoadingState label="Calculating budgets..." />;
  if (budget.error) return <ErrorState message={getApiErrorMessage(budget.error)} onRetry={budget.reload} />;
  const data = budget.data;

  return (
    <div className="space-y-5">
      <p className="text-xs text-muted">{data.method}</p>
      <DataTable
        columns={[
          { key: "project", header: "Project", render: (p) => <span className="font-semibold">{p.project}</span> },
          { key: "approved_budget", header: "Budget", render: (p) => formatCurrency(p.approved_budget) },
          { key: "paid", header: "Paid", render: (p) => formatCurrency(p.paid) },
          { key: "invoiced_unpaid", header: "Invoiced, unpaid", render: (p) => formatCurrency(p.invoiced_unpaid) },
          { key: "open_commitments", header: "Open commitments", render: (p) => formatCurrency(p.open_commitments) },
          { key: "known_cost", header: "Known cost", render: (p) => <span className="font-semibold">{formatCurrency(p.known_cost)}</span> },
          { key: "pct", header: "% of budget", render: (p) => (p.known_cost_percent_of_budget === null ? "No budget" : <span className="inline-flex items-center gap-2">{p.known_cost_percent_of_budget}%{p.over_budget ? <StatusBadge status="high" /> : null}</span>) },
          { key: "trend", header: "Trend projection", render: (p) => (p.trend_projection === null ? <span className="text-xs text-muted">Not enough data</span> : <span title={p.trend_basis}>{formatCurrency(p.trend_projection)}</span>) },
        ]}
        emptyTitle="No projects"
        getRowId={(p) => p.project_id}
        rows={data.projects}
      />
      <FlagList items={data.duplicate_invoice_flags} render={(f) => f.reason} title="Possible duplicate invoices" />
      <FlagList items={data.price_change_flags} render={(f) => `${f.po_number} ${f.material}: Rs ${f.unit_price} vs median Rs ${f.median_of_other_orders} of ${f.based_on_orders} other orders (${f.change_percent > 0 ? "+" : ""}${f.change_percent}%)`} title="Unusual price changes" />
      <FlagList items={data.quantity_reconciliation_flags} render={(f) => `${f.po_number} (${f.project}): ${f.flags.join("; ")}`} title="Ordered / received / invoiced mismatches" />
      <ul className="list-disc pl-5 text-xs text-muted">{data.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
    </div>
  );
}
