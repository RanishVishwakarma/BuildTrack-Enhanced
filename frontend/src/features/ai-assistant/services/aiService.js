import api from "../../../services/api.js";

// AI Site Assistant (backend app/modules/ai/router.py, prefix /ai) and the
// Action Center (app/modules/actions/router.py, prefix /recommendations).

export async function getAiStatus() {
  const { data } = await api.get("/ai/status");
  return data;
}

export async function getOverview() {
  const { data } = await api.get("/ai/overview");
  return data;
}

export async function getSuggestedQuestions() {
  const { data } = await api.get("/ai/suggested-questions");
  return Array.isArray(data) ? data : [];
}

export async function sendChat(message, conversationId) {
  const { data } = await api.post("/ai/assistant/chat", { message, conversation_id: conversationId || undefined });
  return data;
}

export async function getConversations() {
  const { data } = await api.get("/ai/conversations");
  return Array.isArray(data) ? data : [];
}

export async function getConversation(id) {
  const { data } = await api.get(`/ai/conversations/${id}`);
  return data;
}

export async function deleteConversation(id) {
  await api.delete(`/ai/conversations/${id}`);
}

// Action Center
export async function getRecommendations(status) {
  const { data } = await api.get("/recommendations", { params: status ? { status } : undefined });
  return Array.isArray(data) ? data : [];
}

export async function generateRecommendations() {
  const { data } = await api.post("/recommendations/generate");
  return data;
}

export async function proposeRecommendation(payload) {
  const { data } = await api.post("/recommendations", payload);
  return data;
}

export async function decideRecommendation(id, decision, note) {
  const { data } = await api.post(`/recommendations/${id}/decision`, { decision, note: note || undefined });
  return data;
}

export async function retryRecommendation(id) {
  const { data } = await api.post(`/recommendations/${id}/execute`);
  return data;
}

export async function verifyRecommendation(id, effective, note) {
  const { data } = await api.post(`/recommendations/${id}/verify`, { effective, note });
  return data;
}

export async function getActivity() {
  const { data } = await api.get("/recommendations/activity");
  return Array.isArray(data) ? data : [];
}

// Monitoring alerts (app/modules/monitoring/router.py)
export async function getAlerts(status = "open") {
  const { data } = await api.get("/monitoring/alerts", { params: { status } });
  return Array.isArray(data) ? data : [];
}

export async function acknowledgeAlert(id) {
  const { data } = await api.post(`/monitoring/alerts/${id}/acknowledge`);
  return data;
}

export async function runMonitoring() {
  const { data } = await api.post("/monitoring/run");
  return data;
}

export async function getMonitoringRuns() {
  const { data } = await api.get("/monitoring/runs");
  return Array.isArray(data) ? data : [];
}
