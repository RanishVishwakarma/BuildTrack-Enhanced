// Display names for the seven canonical roles. The backend stores codes
// (admin, projectmanager, siteengineer, ...); authService.normalizeRole maps
// them here. Store-manager and finance duties are permissions, not roles.
export const ROLE = {
  ADMIN: "Administrator",
  PROJECT_MANAGER: "Project Manager",
  SITE_ENGINEER: "Site Engineer",
  CONTRACTOR: "Contractor",
  WORKER: "Worker",
  CLIENT: "Client",
  VENDOR: "Vendor",
};

export const ALL_ROLES = Object.values(ROLE);
export const INTERNAL_ROLES = ALL_ROLES.filter((role) => role !== ROLE.VENDOR);

export function hasAnyRole(user, roles) {
  if (!roles || roles.length === 0) return true;
  return Boolean(user?.role && roles.includes(user.role));
}

// A route opens for its listed roles, or for anyone granted one of its
// listed permissions (e.g. a site engineer given the delivery duty). Routes
// that list only `permissions` are opened by permission alone.
export function canOpenRoute(user, route) {
  if (!route) return false;
  if (route.roles && hasAnyRole(user, route.roles)) return true;
  const held = user?.permissions || [];
  if (route.permissions) return route.permissions.some((permission) => held.includes(permission));
  return !route.roles;
}

// Landing page after sign-in. Vendors have no internal dashboard and, as in
// Angular's DashboardComponent, workers are sent to their own dashboard.
export function getHomeRoute(user) {
  if (user?.role === ROLE.VENDOR) return "/procurement/vendor-dashboard";
  if (user?.role === ROLE.WORKER) return "/worker-dashboard";
  return "/dashboard";
}

// UI permission helpers. These mirror the checks the FastAPI routers enforce so
// we never render an action the backend is guaranteed to reject with 403.
// They are not a security boundary; the backend remains authoritative.
const is = (user, roles) => hasAnyRole(user, roles);

// True when the backend granted the permission (see /auth/me "permissions").
export function hasPermission(user, ...permissions) {
  const held = user?.permissions || [];
  return permissions.some((permission) => held.includes(permission));
}

export const can = {
  // workforce, tasks, resources, inventory, projects, milestones, reports:
  // backend allows role in ["admin", "manager"]
  manage: (user) => is(user, [ROLE.ADMIN, ROLE.PROJECT_MANAGER]),
  // most delete endpoints: role == "admin"
  adminOnly: (user) => is(user, [ROLE.ADMIN]),
  // Procurement duties are permissions (backend app/core/permissions.py), so
  // a user granted e.g. the payment duty sees those actions whatever their role.
  procurementProjectManager: (user) => hasPermission(user, "procurement.request.review"),
  procurementVendorManage: (user) => hasPermission(user, "procurement.vendor.manage"),
  vendorLoginManage: (user) => hasPermission(user, "users.create", "procurement.vendor.login.manage"),
  workerLoginManage: (user) => hasPermission(user, "workforce.login.manage"),
  // Hierarchy: project managers and site engineers run the site crew.
  markAttendance: (user) => hasPermission(user, "workforce.manage", "workforce.attendance.manage"),
  assignShifts: (user) => hasPermission(user, "workforce.manage", "workforce.shifts.assign"),
  assignTasks: (user) => hasPermission(user, "tasks.assign"),
  procurementSiteEngineer: (user) => hasPermission(user, "procurement.request.create"),
  procurementStoreManager: (user) => hasPermission(user, "procurement.delivery.receive"),
  procurementInvoiceManage: (user) => hasPermission(user, "procurement.invoice.manage"),
  procurementFinance: (user) => hasPermission(user, "procurement.payment.record"),
};
