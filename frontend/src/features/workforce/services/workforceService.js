import api from "../../../services/api.js";
import { endpoints } from "../../../services/endpoints.js";

// backend/app/modules/workforce/router.py (prefix /workforce). Notes from the
// Angular WorkforceService still apply: the worker list filters by
// `status_filter`, and there is no unfiltered allocation list endpoint.
const base = "/workforce";

function clean(params = {}) {
  return Object.fromEntries(Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ""));
}

async function get(url, params) {
  const { data } = await api.get(url, { params: clean(params) });
  return data;
}

async function send(method, url, payload) {
  const { data } = await api[method](url, payload);
  return data;
}

// Workers
export const getWorkers = ({ projectId, category, status } = {}) =>
  get(endpoints.workforceWorkers, { project_id: projectId, category, status_filter: status, limit: 1000 });
export const getWorker = (id) => get(`${endpoints.workforceWorkers}/${id}`);
export const createWorker = (payload) => send("post", endpoints.workforceWorkers, payload);
export const updateWorker = (id, payload) => send("put", `${endpoints.workforceWorkers}/${id}`, payload);
export const deleteWorker = (id) => send("delete", `${endpoints.workforceWorkers}/${id}`);
// Worker logins (backend links them by users.worker_id).
export const createWorkerLogin = (id, payload) => send("post", `${endpoints.workforceWorkers}/${id}/login`, payload);
export const linkWorkerLogin = (id, email) => send("post", `${endpoints.workforceWorkers}/${id}/login/link`, { email });
export const unlinkWorkerLogin = (id) => send("delete", `${endpoints.workforceWorkers}/${id}/login`);
export const resetWorkerPassword = (id, password) => send("put", `${endpoints.workforceWorkers}/${id}/login/password`, { password });

// Allocations
export const getProjectAllocations = (projectId) => get(`${base}/allocations/project/${projectId}`);
export const getWorkerAllocations = (workerId) => get(`${base}/allocations/worker/${workerId}`);
export const createAllocation = (payload) => send("post", `${base}/allocations`, payload);
export const updateAllocation = (id, payload) => send("put", `${base}/allocations/${id}`, payload);
export const deleteAllocation = (id) => send("delete", `${base}/allocations/${id}`);

// Attendance. The plain list ignores filters server-side, so worker/project
// filters use their dedicated routes.
export function getAttendance({ workerId, projectId, startDate, endDate, day } = {}) {
  // Every record for one calendar day ("YYYY-MM-DD"), for the daily roster.
  if (day) return get(`${base}/attendance`, { date: day });
  if (workerId) return get(`${base}/attendance/worker/${workerId}`, { start_date: startDate, end_date: endDate });
  if (projectId) return get(`${base}/attendance/project/${projectId}`);
  return get(`${base}/attendance`, { limit: 1000 });
}
export const createAttendance = (payload) => send("post", `${base}/attendance`, payload);
export const updateAttendance = (id, payload) => send("put", `${base}/attendance/${id}`, payload);
export const deleteAttendance = (id) => send("delete", `${base}/attendance/${id}`);
export const getLowAttendanceWorkers = ({ projectId, days, threshold } = {}) =>
  get(`${base}/attendance/low-attendance`, { project_id: projectId, days, threshold });
export async function notifyLowAttendance(workerId, days) {
  const { data } = await api.post(`${base}/attendance/notify-low-attendance/${workerId}`, {}, { params: clean({ days }) });
  return data;
}

// Shifts and shift assignments
export const getShifts = (projectId) => get(`${base}/shifts`, { project_id: projectId });
export const createShift = (payload) => send("post", `${base}/shifts`, payload);
export const updateShift = (id, payload) => send("put", `${base}/shifts/${id}`, payload);
export const deleteShift = (id) => send("delete", `${base}/shifts/${id}`);
export const getShiftAssignments = ({ workerId, projectId } = {}) =>
  get(`${base}/shift-assignments`, { worker_id: workerId, project_id: projectId });
export const createShiftAssignment = (payload) => send("post", `${base}/shift-assignments`, payload);
export const deleteShiftAssignment = (id) => send("delete", `${base}/shift-assignments/${id}`);

// Payroll (backend recalculates net_amount on create)
export const getPayroll = ({ workerId, projectId } = {}) => get(`${base}/payroll`, { worker_id: workerId, project_id: projectId });
export const createPayroll = (payload) => send("post", `${base}/payroll`, payload);
export const updatePayroll = (id, payload) => send("put", `${base}/payroll/${id}`, payload);
export const deletePayroll = (id) => send("delete", `${base}/payroll/${id}`);

// Summary
export const getWorkforceSummary = (projectId) => get(endpoints.workforceSummary, { project_id: projectId });
