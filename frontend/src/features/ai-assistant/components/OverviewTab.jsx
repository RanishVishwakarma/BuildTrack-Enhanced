import { AlertTriangle, CheckCircle2, Clock, PackageX, ShieldAlert, Truck } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState } from "../../../components/common/EmptyState.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { hasPermission } from "../../../lib/roles.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { runRisks } from "../../insights/services/insightsService.js";
import { acknowledgeAlert, getOverview } from "../services/aiService.js";

const ICONS = { alerts: ShieldAlert, deadlines: Clock, shortages: PackageX, procurement: Truck, blockers: AlertTriangle, risks: AlertTriangle };

// "What needs attention" computed from records by the backend; no AI call.
export function OverviewTab() {
  const { user } = useAuth();
  const overview = useAsyncData(getOverview, []);
  const { run, isPending } = useAction();
  usePageRefresh(overview.reload);

  if (overview.loading && !overview.data) return <LoadingState label="Checking your sites..." />;
  if (overview.error) return <ErrorState message={getApiErrorMessage(overview.error)} onRetry={overview.reload} />;
  const sections = overview.data?.sections || [];
  const total = sections.reduce((sum, section) => sum + section.items.length, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">{total ? `${total} item(s) need attention, calculated from your records.` : "Nothing needs attention right now."}</p>
        {hasPermission(user, "risks.read.assigned") ? (
          <Button disabled={isPending("risks")} onClick={() => run("risks", () => runRisks(), { success: "Risk assessment updated.", onSuccess: overview.reload })} size="sm" variant="secondary">
            {isPending("risks") ? "Assessing..." : "Re-run risk assessment"}
          </Button>
        ) : null}
      </div>
      {!total ? <EmptyState title="All clear" description="No overdue work, shortages, late deliveries or open alerts in your scope." /> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {sections.filter((section) => section.items.length).map((section) => {
          const Icon = ICONS[section.key] || AlertTriangle;
          return (
            <section className="card" key={section.key}>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <Icon aria-hidden="true" className="h-4 w-4 text-muted" /> {section.title}
                <span className="ml-auto text-xs font-normal text-muted">{section.items.length}</span>
              </h3>
              <ul className="divide-y divide-border/70">
                {section.items.map((item) => (
                  <li className="flex items-start gap-3 py-2.5" key={`${item.type}-${item.id}-${item.title}`}>
                    <StatusBadge status={item.severity} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground">{item.title}</p>
                      {item.detail ? <p className="text-xs text-muted">{item.detail}</p> : null}
                    </div>
                    {section.key === "alerts" && !item.acknowledged ? (
                      <Button aria-label={`Acknowledge ${item.title}`} disabled={isPending(item.id)} onClick={() => run(item.id, () => acknowledgeAlert(item.id), { success: "Acknowledged.", onSuccess: overview.reload })} size="sm" variant="ghost">
                        <CheckCircle2 className="h-4 w-4" /> Acknowledge
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      <p className="text-xs text-muted">
        Want the reasoning behind an item? <Link className="font-semibold text-foreground underline" to="/ai/ask">Ask the assistant</Link>.
      </p>
    </div>
  );
}
