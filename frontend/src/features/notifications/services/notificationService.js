import api from "../../../services/api.js";

const base = "/notifications";

export async function getNotifications(params) {
  const { data } = await api.get(`${base}/`, { params });
  return Array.isArray(data) ? data : [];
}

export async function getUnreadCount() {
  const { data } = await api.get(`${base}/unread-count`);
  return data;
}

export async function markAsRead(id) {
  const { data } = await api.patch(`${base}/${id}/read`, {});
  return data;
}

export async function markAllAsRead() {
  const { data } = await api.patch(`${base}/read-all`, {});
  return data;
}

export async function deleteNotification(id) {
  const { data } = await api.delete(`${base}/${id}`);
  return data;
}

// Admin/manager only (Angular SendNotificationComponent).
export async function sendNotification(payload) {
  const { data } = await api.post(`${base}/`, payload);
  return data;
}
