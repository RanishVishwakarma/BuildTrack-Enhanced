import api from "../../../services/api.js";
import { downloadBlob } from "../../../services/fileDownload.js";

// Risk, materials, impact, budget and reports (backend
// app/modules/intelligence/router.py, prefix /intelligence).
const base = "/intelligence";
const clean = (params) => Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== ""));

export async function getRisks(projectId, includeCleared = false) {
  const { data } = await api.get(`${base}/risks`, { params: clean({ project_id: projectId, include_cleared: includeCleared || undefined }) });
  return Array.isArray(data) ? data : [];
}

export async function runRisks(projectId) {
  const { data } = await api.post(`${base}/risks/run`, null, { params: clean({ project_id: projectId }) });
  return data;
}

export async function reviewRisk(id, reviewStatus, note) {
  const { data } = await api.patch(`${base}/risks/${id}`, { review_status: reviewStatus, note: note || undefined });
  return data;
}

export async function getMaterialForecast(projectId, horizonDays = 30) {
  const { data } = await api.get(`${base}/materials/forecast`, { params: clean({ project_id: projectId, horizon_days: horizonDays }) });
  return data;
}

export async function analyzeImpact(kind, recordId, delayDays) {
  const { data } = await api.post(`${base}/impact`, { kind, record_id: recordId, delay_days: Number(delayDays) });
  return data;
}

export async function getBudget(projectId) {
  const { data } = await api.get(`${base}/budget`, { params: clean({ project_id: projectId }) });
  return data;
}

export async function getReportTypes() {
  const { data } = await api.get(`${base}/reports/types`);
  return Array.isArray(data) ? data : [];
}

export async function createReport({ reportType, projectId, days, aiSummary }) {
  const { data } = await api.post(`${base}/reports`, clean({ report_type: reportType, project_id: projectId, days: days === "" ? undefined : days, ai_summary: aiSummary || undefined }));
  return data;
}

export async function getGeneratedReports() {
  const { data } = await api.get(`${base}/reports`);
  return Array.isArray(data) ? data : [];
}

export async function getGeneratedReport(id) {
  const { data } = await api.get(`${base}/reports/${id}`);
  return data;
}

export async function publishReport(id) {
  const { data } = await api.post(`${base}/reports/${id}/publish`);
  return data;
}

export async function exportReport(id, format, filename) {
  const response = await api.get(`${base}/reports/${id}/export`, { params: { format }, responseType: "blob" });
  downloadBlob(response, `${filename}.${format}`);
}
