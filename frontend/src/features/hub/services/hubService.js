import api from "../../../services/api.js";

// Innovation & Safety Hub (backend app/modules/hub, prefixes
// /hub/suggestions and /hub/safety).

export const SUGGESTION_CATEGORIES = [
  ["productivity", "Productivity"],
  ["safety_improvement", "Safety improvement"],
  ["cost_reduction", "Cost reduction"],
  ["quality_improvement", "Quality improvement"],
  ["material_wastage", "Material wastage"],
  ["equipment_efficiency", "Equipment efficiency"],
  ["environmental_sustainability", "Environmental sustainability"],
  ["new_technology", "New technology"],
  ["other", "Other"],
];

export const OUTCOME_METRICS = [
  ["time_saved_hours", "Time saved (hours)"],
  ["material_wastage_reduced", "Material wastage reduced"],
  ["cost_reduced_rs", "Cost reduced (Rs)"],
  ["productivity_change_percent", "Productivity change (%)"],
  ["other", "Other"],
];

export async function getSuggestions({ mine, status } = {}) {
  const { data } = await api.get("/hub/suggestions", { params: { mine: mine || undefined, status: status || undefined } });
  return Array.isArray(data) ? data : [];
}

export async function getSuggestion(id) {
  const { data } = await api.get(`/hub/suggestions/${id}`);
  return data;
}

export async function createSuggestion(payload) {
  const { data } = await api.post("/hub/suggestions", payload);
  return data;
}

export async function editSuggestion(id, payload) {
  const { data } = await api.patch(`/hub/suggestions/${id}`, payload);
  return data;
}

export async function assistSuggestion(payload) {
  const { data } = await api.post("/hub/suggestions/assist", payload);
  return data;
}

export async function transitionSuggestion(id, toStatus, note) {
  const { data } = await api.post(`/hub/suggestions/${id}/transition`, { to_status: toStatus, note: note || undefined });
  return data;
}

export async function addSuggestionOutcome(id, payload) {
  const { data } = await api.post(`/hub/suggestions/${id}/outcomes`, payload);
  return data;
}

export async function analyzeSuggestion(id) {
  const { data } = await api.post(`/hub/suggestions/${id}/impact-analysis`);
  return data;
}

// Safety
export async function getSafetyReports(mine = false) {
  const { data } = await api.get("/hub/safety/reports", { params: { mine: mine || undefined } });
  return Array.isArray(data) ? data : [];
}

export async function getSafetyReport(id) {
  const { data } = await api.get(`/hub/safety/reports/${id}`);
  return data;
}

export async function submitSafetyReport(payload) {
  const { data } = await api.post("/hub/safety/reports", payload);
  return data;
}

export async function reviewSafetyReport(id, payload) {
  const { data } = await api.post(`/hub/safety/reports/${id}/review`, payload);
  return data;
}

export async function safetyAiAssist(id) {
  const { data } = await api.post(`/hub/safety/reports/${id}/ai-assist`);
  return data;
}

export async function revealReporter(id, reason) {
  const { data } = await api.post(`/hub/safety/reports/${id}/reveal-reporter`, { reason });
  return data;
}

export async function createCorrectiveAction(reportId, payload) {
  const { data } = await api.post(`/hub/safety/reports/${reportId}/actions`, payload);
  return data;
}

export async function getCorrectiveActions() {
  const { data } = await api.get("/hub/safety/actions");
  return Array.isArray(data) ? data : [];
}

export async function updateCorrectiveAction(id, status, note) {
  const { data } = await api.post(`/hub/safety/actions/${id}/update`, { status, note });
  return data;
}

export async function closeCorrectiveAction(id, decision, verificationNote) {
  const { data } = await api.post(`/hub/safety/actions/${id}/close`, { decision, verification_note: verificationNote });
  return data;
}
