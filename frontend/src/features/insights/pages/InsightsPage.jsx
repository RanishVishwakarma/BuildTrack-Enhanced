import { useState } from "react";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { TabNav } from "../../../components/common/TabNav.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { hasPermission } from "../../../lib/roles.js";
import { getId, projectName } from "../../../lib/utils.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { BudgetTab } from "../components/BudgetTab.jsx";
import { ImpactTab } from "../components/ImpactTab.jsx";
import { MaterialsTab } from "../components/MaterialsTab.jsx";
import { RisksTab } from "../components/RisksTab.jsx";

// Project risk, material forecasting, change impact and budget intelligence.
export function InsightsPage({ tab = "risks" }) {
  const { user } = useAuth();
  const { projects } = useProjectOptions();
  const [projectId, setProjectId] = useState("");
  const tabs = [
    { key: "risks", label: "Risks", to: "/insights", show: hasPermission(user, "risks.read.assigned") },
    { key: "materials", label: "Materials", to: "/insights/materials", show: hasPermission(user, "inventory.read.assigned") },
    { key: "impact", label: "Delay impact", to: "/insights/impact", show: hasPermission(user, "tasks.read.assigned", "procurement.read.assigned") },
    { key: "budget", label: "Budget", to: "/insights/budget", show: hasPermission(user, "budget.forecast.read") },
  ].filter((t) => t.show);
  const active = tabs.some((t) => t.key === tab) ? tab : tabs[0]?.key;

  return (
    <>
      <PageHeader description="Calculated from your project records; every figure states how it was derived." eyebrow="Insights" title="Operations intelligence" />
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <TabNav active={active} label="Insight sections" tabs={tabs} />
        <div className="mb-6 w-64">
          <Select aria-label="Project" onChange={(event) => setProjectId(event.target.value)} value={projectId}>
            <option value="">All my projects</option>
            {projects.map((p) => <option key={getId(p)} value={getId(p)}>{projectName(p)}</option>)}
          </Select>
        </div>
      </div>
      {active === "risks" ? <RisksTab projectId={projectId || undefined} /> : null}
      {active === "materials" ? <MaterialsTab projectId={projectId || undefined} /> : null}
      {active === "impact" ? <ImpactTab projectId={projectId || undefined} /> : null}
      {active === "budget" ? <BudgetTab projectId={projectId || undefined} /> : null}
    </>
  );
}
