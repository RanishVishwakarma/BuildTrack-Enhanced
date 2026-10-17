import { vi } from "vitest";

// In-memory stand-in for the shared Axios instance (src/services/api.js).
// Service modules run unchanged, so tests exercise their real URLs and
// payload mapping; only the network is replaced. Tests using this are
// MOCKED tests and do not prove the live backend behaves the same way.
const handlers = [];
export const calls = [];

function match(method, url) {
  const path = url.split("?")[0];
  for (let index = handlers.length - 1; index >= 0; index -= 1) {
    const handler = handlers[index];
    if (handler.method !== method) continue;
    if (typeof handler.path === "string" ? handler.path === path : handler.path.test(path)) return handler;
  }
  return null;
}

function request(method) {
  return vi.fn(async (url, bodyOrConfig, maybeConfig) => {
    const body = ["post", "put", "patch"].includes(method) ? bodyOrConfig : undefined;
    const config = ["post", "put", "patch"].includes(method) ? maybeConfig : bodyOrConfig;
    calls.push({ method, url, body, params: config?.params });
    const handler = match(method, url);
    if (!handler) {
      const error = new Error(`No mock for ${method.toUpperCase()} ${url}`);
      error.response = { status: 404, data: { detail: `No mock for ${method.toUpperCase()} ${url}` } };
      throw error;
    }
    const result = typeof handler.respond === "function" ? await handler.respond({ url, body, params: config?.params }) : handler.respond;
    if (result instanceof MockHttpError) {
      const error = new Error(result.detail);
      error.response = { status: result.status, data: { detail: result.detail } };
      throw error;
    }
    return { data: result, headers: {} };
  });
}

export class MockHttpError {
  constructor(status, detail) {
    this.status = status;
    this.detail = detail;
  }
}

export const mockApi = {
  get: request("get"),
  post: request("post"),
  put: request("put"),
  patch: request("patch"),
  delete: request("delete"),
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
};

export function on(method, path, respond) {
  handlers.push({ method: method.toLowerCase(), path, respond });
}

export function resetApi() {
  handlers.length = 0;
  calls.length = 0;
  for (const key of ["get", "post", "put", "patch", "delete"]) mockApi[key].mockClear();
}

export function callsTo(method, path) {
  return calls.filter((call) => call.method === method.toLowerCase() && call.url.split("?")[0] === path);
}

// Every GET not explicitly mocked returns an empty list, which most pages
// render as an empty state.
export function emptyBackend() {
  on("get", /.*/, []);
  on("get", "/notifications/unread-count", { count: 0 });
  on("get", "/procurement/dashboard", { pending_requests: 0, active_purchase_orders: 0, pending_deliveries: 0, pending_payments: 0, recent_activity: [] });
  on("get", "/procurement/vendor/dashboard", { total_assigned: 0, requests: [], purchase_orders: [], deliveries: [], invoices: [] });
  on("get", "/reports/procurement", {});
  on("get", "/reports/dashboard/metrics", { total_projects: 0, low_stock_items: 0, total_resources: 0, available_resources: 0, total_inventory_value: 0 });
  on("get", "/workforce/dashboard/summary", { total_workers: 0, category_distribution: [] });
}
