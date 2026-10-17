import api from "../../../services/api.js";
import { endpoints } from "../../../services/endpoints.js";

// backend/app/modules/reports/router.py (prefix /reports)
export async function getSavedReports() {
  const { data } = await api.get(`${endpoints.reports}/`, { params: { limit: 50 } });
  return Array.isArray(data) ? data : [];
}

export async function getReportMetrics() {
  const { data } = await api.get(endpoints.dashboardMetrics);
  return data;
}

// Summaries of the legacy `procurements` collection.
export async function getProjectSummary(projectId) {
  const { data } = await api.get("/reports/project", { params: projectId ? { project_id: projectId } : undefined });
  return Array.isArray(data) ? data : [];
}

export async function getProcurementSummary() {
  const { data } = await api.get("/reports/procurement");
  return data;
}

// PDF/Excel of the procurement summary; admin or manager only.
export function exportReport(format) {
  return api.get(`/reports/export/${format}`, { responseType: "blob" });
}
