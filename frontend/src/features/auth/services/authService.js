import api from "../../../services/api.js";
import { endpoints } from "../../../services/endpoints.js";

// The backend stores the seven canonical role codes (app/core/roles.py);
// legacy spellings are kept so older sessions still display correctly.
const roleMap = {
  admin: "Administrator",
  administrator: "Administrator",
  projectmanager: "Project Manager",
  manager: "Project Manager",
  "project manager": "Project Manager",
  siteengineer: "Site Engineer",
  engineer: "Site Engineer",
  "site engineer": "Site Engineer",
  contractor: "Contractor",
  worker: "Worker",
  client: "Client",
  vendor: "Vendor",
};

const backendRoleMap = {
  Administrator: "admin",
  "Project Manager": "projectmanager",
  "Site Engineer": "siteengineer",
  Contractor: "contractor",
  Worker: "worker",
  Client: "client",
  Vendor: "vendor",
};

export function normalizeRole(role) {
  return roleMap[String(role || "").toLowerCase().replace(/-/g, "_").replace(/_/g, " ")] || roleMap[String(role || "").toLowerCase()] || "Worker";
}

export function normalizeUser(user, workerId) {
  const name =
    user?.full_name ||
    user?.name ||
    [user?.first_name, user?.last_name].filter(Boolean).join(" ") ||
    user?.email?.split("@")[0] ||
    "BuildTrack User";

  return {
    id: user?.id || user?._id || user?.email,
    name,
    email: user?.email,
    role: normalizeRole(user?.role),
    status: user?.status || "Active",
    avatarUrl: user?.avatar_url || user?.avatarUrl,
    vendorId: user?.vendor_id,
    // Saved by a manager on the account; the login response also carries it.
    workerId: user?.worker_id || workerId || null,
    // Effective permissions computed by the backend. Used only to decide
    // which controls to show; the backend enforces every action itself.
    permissions: Array.isArray(user?.permissions) ? user.permissions : [],
  };
}

// Reloads the signed-in user so role and permission changes made by an
// administrator show up without signing out.
export async function getCurrentUser(workerId) {
  const { data } = await api.get(endpoints.auth.me);
  // Only replace the session with a real profile; anything else keeps the
  // stored user rather than silently downgrading it.
  if (!data || Array.isArray(data) || typeof data !== "object" || !data.email || !data.role) {
    throw new Error("Unexpected profile response");
  }
  return normalizeUser(data, workerId);
}

export async function login(payload) {
  const { data } = await api.post(endpoints.auth.login, payload);
  return {
    token: data.access_token,
    user: normalizeUser(data.user, data.worker_id),
  };
}

// Staff accounts start "pending" until an administrator approves them, so
// they are not signed in; other roles are signed in straight away.
export async function register(payload) {
  const { data } = await api.post(endpoints.auth.register, {
    full_name: payload.fullName,
    email: payload.email,
    password: payload.password,
    role: backendRoleMap[payload.role] || "worker",
  });
  if (data?.pending_approval) return { pending: true, message: data.message };
  return login({ email: payload.email, password: payload.password });
}

export async function updateProfile(payload) {
  const { data } = await api.put(endpoints.auth.profile, payload);
  return data;
}

export async function requestPasswordReset(email) {
  const { data } = await api.post(endpoints.auth.passwordReset, { email });
  return data;
}

export async function confirmPasswordReset(payload) {
  const { data } = await api.post("/auth/password-reset/confirm", payload);
  return data;
}

export async function changePassword(currentPassword, newPassword) {
  const { data } = await api.post("/auth/change-password", { current_password: currentPassword, new_password: newPassword });
  return data;
}

// Administrator user management (Angular SettingsComponent "Users" tab).
export async function getUsers() {
  const { data } = await api.get(endpoints.auth.users);
  return (Array.isArray(data) ? data : []).map((user) => ({ ...normalizeUser(user), raw: user }));
}

export async function getManagers() {
  const { data } = await api.get(endpoints.auth.managers);
  return (Array.isArray(data) ? data : []).map((user) => normalizeUser(user));
}

export async function updateUser(userId, { name, email, role, status }) {
  const payload = {};
  if (name) payload.full_name = name;
  if (email) payload.email = email;
  if (role) payload.role = backendRoleMap[role] || role;
  if (status) payload.status = status;
  const { data } = await api.put(`${endpoints.auth.users}/${userId}`, payload);
  return data;
}

export async function setUserStatus(userId, statusValue) {
  const { data } = await api.post(`${endpoints.auth.users}/${userId}/status`, {}, { params: { status_value: statusValue } });
  return data;
}

export async function deleteUser(userId, banEmail = true) {
  const { data } = await api.delete(`${endpoints.auth.users}/${userId}`, { params: { ban_email: banEmail } });
  return data;
}
