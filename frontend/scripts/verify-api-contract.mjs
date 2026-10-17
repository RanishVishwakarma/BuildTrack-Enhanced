// Live check: every endpoint the React services call must exist, with the
// same HTTP method, in the running FastAPI server's OpenAPI schema.
// Read-only (fetches /openapi.json only); no authentication or data writes.
//
//   node scripts/verify-api-contract.mjs [http://127.0.0.1:8001]
//
// Keep this list in sync with src/features/*/services/*.js.
const USED = [
  ["post", "/auth/login"], ["post", "/auth/register"], ["put", "/auth/profile"], ["post", "/auth/change-password"],
  ["post", "/auth/password-reset/request"], ["post", "/auth/password-reset/confirm"], ["get", "/auth/users"], ["get", "/auth/managers"],
  ["put", "/auth/users/{id}"], ["delete", "/auth/users/{id}"], ["post", "/auth/users/{id}/status"],
  ["get", "/projects"], ["post", "/projects"], ["get", "/projects/{id}"], ["put", "/projects/{id}"], ["delete", "/projects/{id}"],
  ["get", "/frontend-data/milestones"], ["post", "/frontend-data/milestones"], ["put", "/frontend-data/milestones/{id}"], ["delete", "/frontend-data/milestones/{id}"],
  ["get", "/frontend-data/documents"], ["post", "/frontend-data/documents"], ["delete", "/frontend-data/documents/{id}"],
  ["get", "/tasks/project/{id}"], ["get", "/tasks/worker/{id}"], ["post", "/tasks/"], ["put", "/tasks/{id}"], ["delete", "/tasks/{id}"],
  ["get", "/inventory"], ["post", "/inventory"], ["get", "/inventory/low-stock"], ["put", "/inventory/{id}"], ["delete", "/inventory/{id}"],
  ["get", "/inventory/{id}/transactions"], ["post", "/inventory/{id}/transactions"],
  ["get", "/resources"], ["post", "/resources"], ["get", "/resources/available"], ["get", "/resources/project/{id}"], ["put", "/resources/{id}"], ["delete", "/resources/{id}"],
  ["post", "/resources/{id}/assign/{worker}/{project}"], ["post", "/resources/{id}/unassign"], ["get", "/resources/{id}/maintenance"], ["post", "/resources/{id}/maintenance"],
  ["get", "/workforce/workers"], ["post", "/workforce/workers"], ["get", "/workforce/workers/{id}"], ["put", "/workforce/workers/{id}"], ["delete", "/workforce/workers/{id}"],
  ["get", "/workforce/allocations/project/{id}"], ["get", "/workforce/allocations/worker/{id}"], ["post", "/workforce/allocations"], ["put", "/workforce/allocations/{id}"], ["delete", "/workforce/allocations/{id}"],
  ["get", "/workforce/attendance"], ["post", "/workforce/attendance"], ["get", "/workforce/attendance/worker/{id}"], ["get", "/workforce/attendance/project/{id}"],
  ["put", "/workforce/attendance/{id}"], ["delete", "/workforce/attendance/{id}"], ["get", "/workforce/attendance/low-attendance"], ["post", "/workforce/attendance/notify-low-attendance/{id}"],
  ["get", "/workforce/shifts"], ["post", "/workforce/shifts"], ["put", "/workforce/shifts/{id}"], ["delete", "/workforce/shifts/{id}"],
  ["get", "/workforce/shift-assignments"], ["post", "/workforce/shift-assignments"], ["delete", "/workforce/shift-assignments/{id}"],
  ["get", "/workforce/payroll"], ["post", "/workforce/payroll"], ["put", "/workforce/payroll/{id}"], ["delete", "/workforce/payroll/{id}"], ["get", "/workforce/dashboard/summary"],
  ["get", "/procurement/dashboard"], ["get", "/procurement/vendors"], ["get", "/procurement/vendors/active"], ["post", "/procurement/vendors"], ["post", "/procurement/vendors/create-account"],
  ["put", "/procurement/vendors/{id}"], ["delete", "/procurement/vendors/{id}"],
  ["get", "/procurement/material-requests"], ["post", "/procurement/material-requests"], ["put", "/procurement/material-requests/{id}"], ["delete", "/procurement/material-requests/{id}"],
  ["patch", "/procurement/material-requests/{id}/approval"], ["put", "/procurement/material-requests/{id}/assign-vendor"], ["get", "/procurement/materials"],
  ["get", "/procurement/purchase-orders"], ["post", "/procurement/purchase-orders"], ["put", "/procurement/purchase-orders/{id}"], ["put", "/procurement/purchase-orders/{id}/send"],
  ["delete", "/procurement/purchase-orders/{id}"], ["get", "/procurement/purchase-orders/{id}/pdf"],
  ["get", "/procurement/deliveries"], ["post", "/procurement/deliveries"], ["put", "/procurement/deliveries/{id}"],
  ["get", "/procurement/inventory"], ["get", "/procurement/inventory/history"],
  ["get", "/procurement/invoices"], ["post", "/procurement/invoices"], ["put", "/procurement/invoices/{id}"], ["delete", "/procurement/invoices/{id}"], ["patch", "/procurement/invoices/{id}/{action}"],
  ["get", "/procurement/invoices/{id}/pdf"], ["get", "/procurement/invoices/{id}/qr"], ["post", "/procurement/invoices/{id}/quick-pay"], ["post", "/procurement/invoices/upload"],
  ["get", "/procurement/payments"], ["post", "/procurement/payments"], ["put", "/procurement/payments/{id}"], ["get", "/procurement/export/{collection}"],
  ["get", "/procurement/vendor/dashboard"], ["get", "/procurement/vendor/material-requests"], ["post", "/procurement/vendor/material-requests/{id}/accept"],
  ["post", "/procurement/vendor/material-requests/{id}/reject"], ["get", "/procurement/vendor/purchase-orders"], ["post", "/procurement/vendor/purchase-orders/{id}/accept"],
  ["post", "/procurement/vendor/purchase-orders/{id}/reject"], ["get", "/procurement/vendor/deliveries"], ["post", "/procurement/vendor/deliveries"], ["put", "/procurement/vendor/deliveries/{id}"],
  ["get", "/procurement/vendor/invoices"], ["post", "/procurement/vendor/invoices"], ["get", "/procurement/vendor/profile"], ["put", "/procurement/vendor/profile"],
  ["get", "/reports/"], ["get", "/reports/dashboard/metrics"], ["get", "/reports/project"], ["get", "/reports/procurement"], ["get", "/reports/export/pdf"], ["get", "/reports/export/excel"],
  ["get", "/notifications/"], ["post", "/notifications/"], ["get", "/notifications/unread-count"], ["patch", "/notifications/{id}/read"], ["patch", "/notifications/read-all"], ["delete", "/notifications/{id}"],
];

const base = (process.argv[2] || process.env.API_ORIGIN || "http://127.0.0.1:8001").replace(/\/$/, "");
const response = await fetch(`${base}/openapi.json`);
if (!response.ok) {
  console.error(`Could not fetch ${base}/openapi.json (HTTP ${response.status}). Is the backend running?`);
  process.exit(2);
}
const schema = await response.json();
const PREFIX = "/api/v1";
const live = Object.entries(schema.paths).flatMap(([path, methods]) =>
  Object.keys(methods).map((method) => ({ method, path: path.startsWith(PREFIX) ? path.slice(PREFIX.length) : path })),
);
// Compare structurally: any {param} matches any {param}; trailing slashes ignored.
const shape = (path) => path.replace(/\{[^}]+\}/g, "{}").replace(/\/$/, "") || "/";
const liveSet = new Set(live.map(({ method, path }) => `${method} ${shape(path)}`));
const missing = USED.filter(([method, path]) => !liveSet.has(`${method} ${shape(path)}`));

console.log(`Checked ${USED.length} endpoint usages against ${live.length} live operations at ${base}.`);
if (missing.length) {
  console.error("Missing from the running backend:");
  for (const [method, path] of missing) console.error(`  ${method.toUpperCase()} ${path}`);
  process.exit(1);
}
console.log("All endpoints used by the React app exist on the running backend.");
