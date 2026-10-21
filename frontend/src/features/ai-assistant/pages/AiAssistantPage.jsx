import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { TabNav } from "../../../components/common/TabNav.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { hasPermission } from "../../../lib/roles.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { ActionCenterTab } from "../components/ActionCenterTab.jsx";
import { ActivityTab } from "../components/ActivityTab.jsx";
import { AgentTab } from "../components/AgentTab.jsx";
import { AskAiTab } from "../components/AskAiTab.jsx";
import { OverviewTab } from "../components/OverviewTab.jsx";
import { ReportsTab } from "../components/ReportsTab.jsx";
import { getAiStatus } from "../services/aiService.js";

// AI Site Assistant (spec §22): Overview, Ask AI, Action Center, Reports and
// Activity. Tabs are hidden when the user lacks the permission behind them;
// the backend checks every request regardless.
export function AiAssistantPage({ tab = "overview" }) {
  const { user } = useAuth();
  const status = useAsyncData(getAiStatus, []);
  const tabs = [
    { key: "overview", label: "Overview", to: "/ai", show: true },
    { key: "ask", label: "Ask AI", to: "/ai/ask", show: hasPermission(user, "ai.query") },
    { key: "agent", label: "Agent mode", to: "/ai/agent", show: hasPermission(user, "ai.agent.use") },
    { key: "actions", label: "Action Center", to: "/ai/actions", show: hasPermission(user, "ai.recommendation.review") },
    { key: "reports", label: "Reports", to: "/ai/reports", show: hasPermission(user, "reports.generate", "reports.read.assigned") },
    { key: "activity", label: "Activity", to: "/ai/activity", show: true },
  ].filter((t) => t.show);
  const active = tabs.some((t) => t.key === tab) ? tab : "overview";

  return (
    <>
      <PageHeader
        description="What needs attention across your authorized projects, with answers grounded in your records."
        eyebrow="AI"
        title="Site Assistant"
      />
      <TabNav active={active} label="Site Assistant sections" tabs={tabs} />
      {active === "overview" ? <OverviewTab /> : null}
      {active === "ask" ? <AskAiTab status={status.data} /> : null}
      {active === "agent" ? <AgentTab /> : null}
      {active === "actions" ? <ActionCenterTab /> : null}
      {active === "reports" ? <ReportsTab status={status.data} /> : null}
      {active === "activity" ? <ActivityTab /> : null}
    </>
  );
}
