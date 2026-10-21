import { matchPath } from "react-router-dom";
import { ALL_ROLES, INTERNAL_ROLES, ROLE } from "../lib/roles.js";

const { ADMIN, PROJECT_MANAGER, SITE_ENGINEER, CONTRACTOR, WORKER, CLIENT, VENDOR } = ROLE;

const SITE_TEAM = [ADMIN, PROJECT_MANAGER, SITE_ENGINEER];

// Route metadata for every protected page. `roles` mirror the Angular
// `roleGuard` data in frontend/src/app/app.routes.ts; deviations are noted
// inline and in MIGRATION_STATUS.md. `parent` drives breadcrumbs.
export const ROUTES = [
  // Angular omitted Store Manager/Finance here, which locked those roles out of
  // their own landing page after login; they are included in React.
  { path: "/dashboard", title: "Dashboard", roles: INTERNAL_ROLES },
  { path: "/projects", title: "Projects", roles: [ADMIN, PROJECT_MANAGER, SITE_ENGINEER, CONTRACTOR, CLIENT, WORKER] },
  { path: "/projects/milestones", title: "Milestones", parent: "/projects", roles: [ADMIN, PROJECT_MANAGER, SITE_ENGINEER, CONTRACTOR, CLIENT] },
  { path: "/projects/status-dashboard", title: "Status Dashboard", parent: "/projects", roles: [ADMIN, PROJECT_MANAGER, SITE_ENGINEER, CONTRACTOR, CLIENT] },
  { path: "/projects/:projectId", title: "Project Details", parent: "/projects", roles: [ADMIN, PROJECT_MANAGER, SITE_ENGINEER, CONTRACTOR, CLIENT, WORKER] },
  { path: "/resources", title: "Resources", roles: SITE_TEAM },
  { path: "/resources/equipment", title: "Equipment Tracking", parent: "/resources", roles: SITE_TEAM },
  { path: "/resources/utilization", title: "Resource Utilization", parent: "/resources", roles: SITE_TEAM },
  { path: "/inventory", title: "Inventory", roles: SITE_TEAM },
  { path: "/inventory/stock-monitoring", title: "Stock Monitoring", parent: "/inventory", roles: SITE_TEAM },
  { path: "/workers", title: "Workers", roles: SITE_TEAM },
  { path: "/workers/shift-scheduling", title: "Shift Scheduling", parent: "/workers", roles: [...SITE_TEAM, WORKER] },
  { path: "/workers/allocation", title: "Allocation", parent: "/workers", roles: SITE_TEAM },
  { path: "/workers/payroll", title: "Payroll", parent: "/workers", roles: [ADMIN, PROJECT_MANAGER] },
  { path: "/attendance", title: "Attendance", parent: "/workers", roles: [...SITE_TEAM, WORKER] },
  { path: "/my-tasks", title: "My Tasks", roles: [WORKER] },
  { path: "/worker-dashboard", title: "Worker Dashboard", roles: [WORKER] },
  { path: "/procurement", title: "Procurement", roles: [ADMIN, PROJECT_MANAGER, SITE_ENGINEER], permissions: ["procurement.read.assigned"] },
  { path: "/procurement/dashboard", title: "Procurement Dashboard", parent: "/procurement", roles: [ADMIN, PROJECT_MANAGER, SITE_ENGINEER], permissions: ["procurement.read.assigned"] },
  { path: "/procurement/request", title: "Material Requests", parent: "/procurement", roles: SITE_TEAM },
  { path: "/procurement/material-requests", title: "Material Requests", parent: "/procurement", roles: SITE_TEAM },
  // Angular showed approvals as an in-page tab for project managers; React gives it a URL.
  { path: "/procurement/approvals", title: "Approvals", parent: "/procurement", roles: [ADMIN, PROJECT_MANAGER] },
  { path: "/procurement/purchase-orders", title: "Purchase Orders", parent: "/procurement", roles: [ADMIN, PROJECT_MANAGER] },
  { path: "/procurement/vendors", title: "Vendors", parent: "/procurement", roles: [ADMIN, PROJECT_MANAGER] },
  { path: "/procurement/deliveries", title: "Deliveries", parent: "/procurement", roles: [ADMIN, PROJECT_MANAGER], permissions: ["procurement.delivery.receive"] },
  { path: "/procurement/inventory", title: "Procurement Inventory", parent: "/procurement", roles: [ADMIN, PROJECT_MANAGER, SITE_ENGINEER] },
  { path: "/procurement/invoices", title: "Invoices", parent: "/procurement", roles: [ADMIN, PROJECT_MANAGER], permissions: ["procurement.invoice.manage", "procurement.payment.record"] },
  { path: "/procurement/payments", title: "Payments", parent: "/procurement", roles: [ADMIN], permissions: ["procurement.payment.record"] },
  { path: "/procurement/vendor-dashboard", title: "Vendor Portal", roles: [VENDOR] },
  { path: "/reports", title: "Reports", roles: [ADMIN, PROJECT_MANAGER, CLIENT] },
  { path: "/analytics/progress", title: "Progress Analytics", parent: "/reports", roles: [ADMIN, PROJECT_MANAGER, CLIENT] },
  { path: "/analytics/budget", title: "Budget Analytics", parent: "/reports", roles: [ADMIN, PROJECT_MANAGER, CLIENT] },
  { path: "/analytics/resource", title: "Resource Analytics", parent: "/reports", roles: [ADMIN, PROJECT_MANAGER] },
  { path: "/analytics/procurement", title: "Procurement Analytics", parent: "/reports", roles: [ADMIN, PROJECT_MANAGER] },
  // AI and operations intelligence: opened by permission (backend app/core/permissions.py).
  { path: "/ai", title: "Site Assistant", permissions: ["ai.query"] },
  { path: "/ai/ask", title: "Ask AI", parent: "/ai", permissions: ["ai.query"] },
  { path: "/ai/agent", title: "Agent mode", parent: "/ai", permissions: ["ai.agent.use"] },
  { path: "/ai/actions", title: "Action Center", parent: "/ai", permissions: ["ai.recommendation.review"] },
  { path: "/ai/reports", title: "Reports", parent: "/ai", permissions: ["reports.generate", "reports.read.assigned"] },
  { path: "/ai/activity", title: "Activity", parent: "/ai", permissions: ["ai.query"] },
  { path: "/insights", title: "Insights", permissions: ["risks.read.assigned", "inventory.read.assigned", "budget.forecast.read"] },
  { path: "/insights/materials", title: "Materials", parent: "/insights", permissions: ["inventory.read.assigned"] },
  { path: "/insights/impact", title: "Delay impact", parent: "/insights", permissions: ["tasks.read.assigned", "procurement.read.assigned"] },
  { path: "/insights/budget", title: "Budget", parent: "/insights", permissions: ["budget.forecast.read"] },
  { path: "/evidence", title: "Progress Evidence", permissions: ["evidence.upload", "evidence.read.assigned"] },
  { path: "/hub", title: "Innovation & Safety", permissions: ["suggestions.create", "suggestions.review.assigned", "safety_reports.create", "safety_reports.read.assigned"] },
  { path: "/hub/safety", title: "Safety", parent: "/hub", permissions: ["safety_reports.create", "safety_reports.read.assigned"] },
  { path: "/hub/actions", title: "Corrective actions", parent: "/hub", permissions: ["safety_actions.update.own", "safety_actions.assign", "safety_actions.close"] },
  { path: "/notifications", title: "Notifications", roles: ALL_ROLES },
  // Angular restricted the whole page to Administrators. React keeps profile
  // editing available to every user and gates the Users tab to Administrators.
  { path: "/settings", title: "Settings", roles: ALL_ROLES },
];

const STATIC_FIRST = [...ROUTES].sort((a, b) => Number(a.path.includes(":")) - Number(b.path.includes(":")));

export function findRoute(pathname) {
  return STATIC_FIRST.find((route) => matchPath({ path: route.path, end: true }, pathname)) || null;
}

export function getRoute(path) {
  return ROUTES.find((route) => route.path === path) || null;
}

export function getBreadcrumbs(pathname) {
  const crumbs = [];
  let route = findRoute(pathname);
  let href = pathname;
  while (route) {
    crumbs.unshift({ title: route.title, href });
    route = route.parent ? getRoute(route.parent) : null;
    href = route?.path;
  }
  return crumbs;
}
