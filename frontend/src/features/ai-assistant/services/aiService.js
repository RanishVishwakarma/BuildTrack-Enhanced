import api, { API_BASE_URL } from "../../../services/api.js";
import { getStoredToken } from "../../auth/services/session.js";

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

// Agent mode (backend app/modules/agent/router.py, prefix /ai/agent).
export async function getAgentStatus() {
  const { data } = await api.get("/ai/agent/status");
  return data;
}

export async function rebuildAgentIndex() {
  const { data } = await api.post("/ai/agent/index");
  return data;
}

// Streams the run: calls onEvent for every newline-delimited JSON event
// ("step" while the agents work, then "final", "saved" or "error").
// fetch is used because axios cannot read a response while it streams.
export async function streamAgentChat(message, conversationId, onEvent, signal) {
  const token = getStoredToken();
  const response = await fetch(`${API_BASE_URL}/ai/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ message, conversation_id: conversationId || undefined }),
    signal,
  });
  if (!response.ok) {
    if (response.status === 401 && token) window.dispatchEvent(new Event("buildtrack:session-expired"));
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Agent mode is not available.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = done ? "" : lines.pop();
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
    if (done) break;
  }
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
