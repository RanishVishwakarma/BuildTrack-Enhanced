import api, { API_BASE_URL } from "../../../services/api.js";

// Progress evidence (backend app/modules/evidence/router.py, prefix /evidence).

export async function getEvidence({ projectId, taskId } = {}) {
  const { data } = await api.get("/evidence", { params: { project_id: projectId || undefined, task_id: taskId || undefined } });
  return Array.isArray(data) ? data : [];
}

export async function uploadEvidence({ file, projectId, description, taskId, location }) {
  const form = new FormData();
  form.append("file", file);
  form.append("project_id", projectId);
  form.append("description", description);
  if (taskId) form.append("task_id", taskId);
  if (location) form.append("location", location);
  const { data } = await api.post("/evidence", form, { headers: { "Content-Type": "multipart/form-data" } });
  return data;
}

// Short-lived signed link, re-checked against the user's current access.
export async function getEvidenceUrl(id) {
  const { data } = await api.post(`/evidence/${id}/link`);
  const origin = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
  return `${origin}${data.url}`;
}

export async function analyzeEvidence(id) {
  const { data } = await api.post(`/evidence/${id}/analyze`);
  return data;
}

export async function reviewEvidence(id, reviewStatus, note) {
  const { data } = await api.patch(`/evidence/${id}/review`, { review_status: reviewStatus, note });
  return data;
}

export async function getEvidenceFlags(projectId) {
  const { data } = await api.get("/evidence/flags", { params: { project_id: projectId || undefined } });
  return data;
}
