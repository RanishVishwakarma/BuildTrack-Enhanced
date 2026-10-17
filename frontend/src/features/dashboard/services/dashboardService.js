import api from "../../../services/api.js";
import { endpoints } from "../../../services/endpoints.js";
import { normalizeList } from "../../../lib/utils.js";

// Each source is optional: a failing endpoint (e.g. a role without access)
// leaves its section empty and is reported, instead of failing the page.
export async function getDashboardData() {
  const sources = {
    projects: api.get(endpoints.projects),
    metrics: api.get(endpoints.dashboardMetrics),
    workforce: api.get(endpoints.workforceSummary),
    procurement: api.get(endpoints.procurement.dashboard),
    milestones: api.get("/frontend-data/milestones"),
  };
  const keys = Object.keys(sources);
  const settled = await Promise.allSettled(Object.values(sources));
  const result = { failed: [] };
  settled.forEach((outcome, index) => {
    const key = keys[index];
    if (outcome.status === "fulfilled") result[key] = outcome.value.data;
    else {
      result[key] = null;
      result.failed.push(key);
    }
  });
  result.projects = normalizeList(result.projects).items;
  result.milestones = normalizeList(result.milestones).items;
  if (result.failed.length === keys.length) throw settled[0].reason;
  return result;
}
