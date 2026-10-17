import { Link } from "react-router-dom";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { formatDateTime } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { getProcurementDashboard } from "../services/procurementService.js";

export function ProcurementDashboardTab({ canOpen }) {
  const { data, loading, error, reload } = useAsyncData(getProcurementDashboard, []);
  usePageRefresh(reload);
  if (loading) return <LoadingState label="Loading procurement dashboard..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  const cards = [
    { label: "Pending requests", value: data?.pending_requests ?? 0, to: "/procurement/approvals" },
    { label: "Active purchase orders", value: data?.active_purchase_orders ?? 0, to: "/procurement/purchase-orders" },
    { label: "Pending deliveries", value: data?.pending_deliveries ?? 0, to: "/procurement/deliveries" },
    { label: "Pending payments", value: data?.pending_payments ?? 0, to: "/procurement/payments" },
  ];
  const activity = data?.recent_activity || [];

  return (
    <>
      <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) =>
          canOpen(card.to) ? (
            <Link className="block rounded-lg transition hover:-translate-y-0.5 hover:shadow-md" key={card.label} to={card.to}>
              <StatCard helper="Open list" label={card.label} value={card.value} />
            </Link>
          ) : (
            <StatCard key={card.label} label={card.label} value={card.value} />
          ),
        )}
      </section>
      <section className="card mt-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Recent procurement activity</h2>
            <p className="text-sm text-muted">Latest audit events recorded by the backend.</p>
          </div>
        </div>
        {activity.length ? (
          <ul className="grid gap-3 md:grid-cols-2">
            {activity.map((item, index) => (
              <li className="rounded-md border border-border p-4" key={item.id || item._id || index}>
                <p className="font-semibold">{item.title || `${item.entity} ${item.action}`}</p>
                <p className="mt-1 text-sm text-muted">{item.description}</p>
                <p className="mt-2 text-xs text-muted">
                  {item.user_name || "System"} · {formatDateTime(item.timestamp || item.created_at)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">No procurement activity has been logged yet.</p>
        )}
      </section>
    </>
  );
}
