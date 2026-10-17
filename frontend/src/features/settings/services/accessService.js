import api from "../../../services/api.js";

// Access control (backend app/modules/access/router.py) and voice-call
// preferences (app/modules/voice/router.py).

export async function getPermissionRegistry() {
  const { data } = await api.get("/access/permissions");
  return data;
}

export async function getUserPermissions(userId) {
  const { data } = await api.get(`/access/users/${userId}/permissions`);
  return data;
}

export async function setUserPermissions(userId, granted, revoked) {
  const { data } = await api.put(`/access/users/${userId}/permissions`, { granted, revoked });
  return data;
}

export async function getProjectMembers(projectId) {
  const { data } = await api.get(`/access/projects/${projectId}/members`);
  return Array.isArray(data) ? data : [];
}

export async function addProjectMember(projectId, userId) {
  const { data } = await api.post(`/access/projects/${projectId}/members`, { user_id: userId });
  return data;
}

export async function removeProjectMember(projectId, userId) {
  const { data } = await api.delete(`/access/projects/${projectId}/members/${userId}`);
  return data;
}

export async function getAuditLogs(params = {}) {
  const { data } = await api.get("/access/audit-logs", { params });
  return Array.isArray(data) ? data : [];
}

export async function getVoicePreferences() {
  const { data } = await api.get("/voice/preferences");
  return data;
}

export async function setVoicePreferences(voiceConsent, phone) {
  const { data } = await api.put("/voice/preferences", { voice_consent: voiceConsent, phone: phone || undefined });
  return data;
}

export async function getCallLogs() {
  const { data } = await api.get("/voice/calls");
  return Array.isArray(data) ? data : [];
}
