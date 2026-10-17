import api from "../../../services/api.js";
import { endpoints } from "../../../services/endpoints.js";

// Backend status codes and their display labels (Angular MockDataService
// toProjectStatus / toBackendProjectStatus).
export const PROJECT_STATUSES = [
  { value: "planning", label: "Not Started" },
  { value: "active", label: "In Progress" },
  { value: "on_hold", label: "On Hold" },
  { value: "completed", label: "Completed" },
];

// Angular stored milestone status with the project status labels.
export const MILESTONE_STATUSES = ["Not Started", "In Progress", "On Hold", "Completed"];

export const PROJECT_CATEGORIES = ["Residential", "Commercial", "Industrial", "Infrastructure", "Government"];

export function projectStatusLabel(status) {
  const normalized = String(status ?? "").toLowerCase().replace(/\s+/g, "_");
  if (normalized === "active" || normalized === "in_progress") return "In Progress";
  if (normalized === "on_hold") return "On Hold";
  if (normalized === "completed") return "Completed";
  return "Not Started";
}

export async function getProjects(params) {
  const { data } = await api.get(endpoints.projects, { params });
  return data;
}

export async function getProject(id) {
  const { data } = await api.get(`${endpoints.projects}/${id}`);
  return data;
}

export async function createProject(payload) {
  const { data } = await api.post(endpoints.projects, payload);
  return data;
}

export async function updateProject(id, payload) {
  const { data } = await api.put(`${endpoints.projects}/${id}`, payload);
  return data;
}

export async function deleteProject(id) {
  const { data } = await api.delete(`${endpoints.projects}/${id}`);
  return data;
}

// Milestones and project documents live where Angular's MockDataService kept
// them: the project_milestones / project_documents collections behind
// /frontend-data (create/update: admin or manager, delete: admin).
// Records carry both camelCase and snake_case keys, as Angular wrote them.
const frontendData = "/frontend-data";

export const recordProjectId = (record) => record?.project_id || record?.projectId || "";

export async function getMilestoneRecords() {
  const { data } = await api.get(`${frontendData}/milestones`);
  return Array.isArray(data) ? data : [];
}

export async function saveMilestoneRecord(id, { projectId, title, dueDate, status, progress, description }) {
  const payload = { projectId, project_id: projectId, title, dueDate, due_date: dueDate, status, progress, description };
  const { data } = id ? await api.put(`${frontendData}/milestones/${id}`, payload) : await api.post(`${frontendData}/milestones`, payload);
  return data;
}

export async function deleteMilestoneRecord(id) {
  const { data } = await api.delete(`${frontendData}/milestones/${id}`);
  return data;
}

export async function getDocumentRecords() {
  const { data } = await api.get(`${frontendData}/documents`);
  return Array.isArray(data) ? data : [];
}

export async function createDocumentRecord({ projectId, name, type }) {
  const uploadedAt = new Date().toISOString();
  const { data } = await api.post(`${frontendData}/documents`, {
    projectId, project_id: projectId, name, file_name: name, type, file_type: type, uploadedAt, uploaded_at: uploadedAt,
  });
  return data;
}

export async function deleteDocumentRecord(id) {
  const { data } = await api.delete(`${frontendData}/documents/${id}`);
  return data;
}
