import api from "../../../services/api.js";

// backend/app/modules/tasks/router.py. Create/update require admin or
// manager; delete requires admin.
export async function getTasksForWorker(workerId) {
  const { data } = await api.get(`/tasks/worker/${workerId}`);
  return Array.isArray(data) ? data : [];
}

export async function getTasksForProject(projectId) {
  const { data } = await api.get(`/tasks/project/${projectId}`);
  return Array.isArray(data) ? data : [];
}

export async function createTask(payload) {
  const { data } = await api.post("/tasks/", payload);
  return data;
}

export async function updateTask(id, payload) {
  const { data } = await api.put(`/tasks/${id}`, payload);
  return data;
}

export async function deleteTask(id) {
  const { data } = await api.delete(`/tasks/${id}`);
  return data;
}
