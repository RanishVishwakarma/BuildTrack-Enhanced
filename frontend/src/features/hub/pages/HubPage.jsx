import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { TabNav } from "../../../components/common/TabNav.jsx";
import { hasPermission } from "../../../lib/roles.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { ActionsTab } from "../components/ActionsTab.jsx";
import { SafetyTab } from "../components/SafetyTab.jsx";
import { SuggestionsTab } from "../components/SuggestionsTab.jsx";

// Innovation & Safety Hub (spec §13).
export function HubPage({ tab = "suggestions" }) {
  const { user } = useAuth();
  const tabs = [
    { key: "suggestions", label: "Suggestions", to: "/hub", show: hasPermission(user, "suggestions.create", "suggestions.review.assigned") },
    { key: "safety", label: "Safety", to: "/hub/safety", show: hasPermission(user, "safety_reports.create", "safety_reports.read.assigned") },
    { key: "actions", label: "Corrective actions", to: "/hub/actions", show: hasPermission(user, "safety_actions.update.own", "safety_actions.assign", "safety_actions.close") },
  ].filter((t) => t.show);
  const active = tabs.some((t) => t.key === tab) ? tab : tabs[0]?.key;

  return (
    <>
      <PageHeader description="Share ideas for better work and report safety issues. Every submission is tracked to an outcome." eyebrow="Hub" title="Innovation & Safety" />
      <TabNav active={active} label="Hub sections" tabs={tabs} />
      {active === "suggestions" ? <SuggestionsTab /> : null}
      {active === "safety" ? <SafetyTab /> : null}
      {active === "actions" ? <ActionsTab /> : null}
    </>
  );
}
