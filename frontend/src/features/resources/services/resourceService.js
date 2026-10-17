import api from "../../../services/api.js";

// backend/app/modules/resources/router.py. Mutations require admin or
// manager; delete requires admin.
const base = "/resources";

export const RESOURCE_TYPES = ["equipment", "tool", "vehicle", "material"];
export const RESOURCE_STATUSES = ["available", "in_use", "maintenance", "retired"];

export async function getResources() {
  const { data } = await api.get(base);
  return Array.isArray(data) ? data : [];
}

export async function getAvailableResources() {
  const { data } = await api.get(`${base}/available`);
  return Array.isArray(data) ? data : [];
}

export async function getProjectResources(projectId) {
  const { data } = await api.get(`${base}/project/${projectId}`);
  return Array.isArray(data) ? data : [];
}

export async function createResource(payload) {
  const { data } = await api.post(base, payload);
  return data;
}

export async function updateResource(id, payload) {
  const { data } = await api.put(`${base}/${id}`, payload);
  return data;
}

export async function deleteResource(id) {
  const { data } = await api.delete(`${base}/${id}`);
  return data;
}

export async function assignResource(id, workerId, projectId) {
  const { data } = await api.post(`${base}/${id}/assign/${workerId}/${projectId}`, {});
  return data;
}

export async function unassignResource(id) {
  const { data } = await api.post(`${base}/${id}/unassign`, {});
  return data;
}

export async function getMaintenanceLogs(id) {
  const { data } = await api.get(`${base}/${id}/maintenance`);
  return Array.isArray(data) ? data : [];
}

export async function recordMaintenance(id, payload) {
  const { data } = await api.post(`${base}/${id}/maintenance`, payload);
  return data;
}
