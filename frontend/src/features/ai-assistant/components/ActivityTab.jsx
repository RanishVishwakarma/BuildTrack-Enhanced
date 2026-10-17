import { EmptyState } from "../../../components/common/EmptyState.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { formatDateTime, formatStatus } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { getActivity, getAlerts } from "../services/aiService.js";

// Your recent AI, recommendation, report and alert events, plus all alerts
// raised for you (open, acknowledged or resolved).
export function ActivityTab() {
  const data = useAsyncData(async () => {
    const [events, alerts] = await Promise.all([getActivity(), getAlerts("all")]);
    return { events, alerts };
  }, [], { initialData: { events: [], alerts: [] } });
  usePageRefresh(data.reload);

  if (data.loading && !data.data.events.length && !data.data.alerts.length) return <LoadingState />;
  if (data.error) return <ErrorState message={getApiErrorMessage(data.error)} onRetry={data.reload} />;
  const { events, alerts } = data.data;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="card">
        <h3 className="mb-3 text-sm font-semibold text-foreground">Alerts raised for you</h3>
        {!alerts.length ? <EmptyState title="No alerts" description="Monitoring has not raised any alerts for you." /> : (
          <ul className="divide-y divide-border/70">
            {alerts.map((alert) => (
              <li className="flex items-start gap-3 py-2.5" key={alert._id}>
                <StatusBadge status={alert.severity} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-foreground">{alert.title}</p>
                  <p className="text-xs text-muted">{alert.message}</p>
                  <p className="text-[11px] text-muted">
                    Raised {formatDateTime(alert.created_at)}
                    {alert.acknowledged_at ? ` · acknowledged ${formatDateTime(alert.acknowledged_at)}${alert.acknowledged_via ? ` via ${alert.acknowledged_via}` : ""}` : ""}
                    {alert.escalation_level ? " · escalated" : ""}
                  </p>
                </div>
                <StatusBadge status={alert.status} />
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card">
        <h3 className="mb-3 text-sm font-semibold text-foreground">Your recent activity</h3>
        {!events.length ? <EmptyState title="No activity yet" description="Questions, approvals, reports and reviews you make will be listed here." /> : (
          <ol className="space-y-2">
            {events.map((event) => (
              <li className="flex items-baseline gap-3 text-sm" key={event._id}>
                <span className="w-36 shrink-0 text-xs text-muted">{formatDateTime(event.timestamp)}</span>
                <span className="text-foreground">{formatStatus(event.event_type.replace(/\./g, " "))}</span>
                {event.outcome && event.outcome !== "success" ? <StatusBadge status={event.outcome} /> : null}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
