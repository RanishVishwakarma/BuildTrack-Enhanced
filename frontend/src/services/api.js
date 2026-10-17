import axios from "axios";
import { clearStoredSession, getStoredToken } from "../features/auth/services/session.js";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001/api/v1";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Only a rejected *authenticated* request means the session expired. A 401
    // from /auth/login (wrong password) must not trigger a sign-out.
    const sentToken = Boolean(error.config?.headers?.Authorization);
    const isAuthEndpoint = String(error.config?.url || "").startsWith("/auth/login");
    if (error.response?.status === 401 && sentToken && !isAuthEndpoint) {
      clearStoredSession();
      window.dispatchEvent(new Event("buildtrack:session-expired"));
    }
    return Promise.reject(error);
  },
);

export default api;
