import {
  Activity,
  BarChart3,
  Bell,
  Boxes,
  BriefcaseBusiness,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  Clock,
  FileText,
  Gauge,
  Camera,
  HardHat,
  Lightbulb,
  ListChecks,
  Receipt,
  Settings,
  ShieldAlert,
  ShoppingCart,
  Sparkles,
  Truck,
  Users,
  Wallet,
  Warehouse,
} from "lucide-react";
import { getRoute } from "../app/routeConfig.js";
import { ROLE, canOpenRoute, hasAnyRole } from "../lib/roles.js";

// Mirrors the grouping of frontend/src/app/layout/sidebar/sidebar.component.ts.
// `onlyRoles` narrows an item further than its route allows (e.g. the
// worker-only shortcuts); everything else is filtered by the route guard roles
// in routeConfig.js so a visible link never leads to /forbidden.
export const NAV_ITEMS = [
  { label: "Dashboard", to: "/dashboard", icon: Gauge },
  {
    label: "Site Assistant",
    to: "/ai",
    icon: Sparkles,
    children: [
      { label: "Ask AI", to: "/ai/ask", icon: Sparkles },
      { label: "Action Center", to: "/ai/actions", icon: ClipboardCheck },
      { label: "AI Reports", to: "/ai/reports", icon: FileText },
      { label: "Activity", to: "/ai/activity", icon: Activity },
    ],
  },
  {
    label: "Insights",
    to: "/insights",
    icon: BarChart3,
    children: [
      { label: "Materials", to: "/insights/materials", icon: Boxes },
      { label: "Delay impact", to: "/insights/impact", icon: Clock },
      { label: "Budget", to: "/insights/budget", icon: Wallet },
    ],
  },
  { label: "Progress Evidence", to: "/evidence", icon: Camera },
  {
    label: "Innovation & Safety",
    to: "/hub",
    icon: Lightbulb,
    children: [
      { label: "Safety", to: "/hub/safety", icon: ShieldAlert },
      { label: "Corrective actions", to: "/hub/actions", icon: ClipboardList },
    ],
  },
  { label: "My Tasks", to: "/my-tasks", icon: ListChecks, onlyRoles: [ROLE.WORKER] },
  { label: "My Dashboard", to: "/worker-dashboard", icon: ClipboardCheck, onlyRoles: [ROLE.WORKER] },
  { label: "My Attendance", to: "/attendance", icon: Clock, onlyRoles: [ROLE.WORKER] },
  { label: "My Schedule", to: "/workers/shift-scheduling", icon: CalendarDays, onlyRoles: [ROLE.WORKER] },
  { label: "My Projects", to: "/projects", icon: BriefcaseBusiness, onlyRoles: [ROLE.WORKER] },
  {
    label: "Projects",
    to: "/projects",
    icon: BriefcaseBusiness,
    excludeRoles: [ROLE.WORKER],
    children: [
      { label: "Milestones", to: "/projects/milestones", icon: ListChecks },
      { label: "Status Dashboard", to: "/projects/status-dashboard", icon: Gauge },
    ],
  },
  {
    label: "Resources",
    to: "/resources",
    icon: HardHat,
    children: [
      { label: "Equipment", to: "/resources/equipment", icon: Truck },
      { label: "Utilization", to: "/resources/utilization", icon: BarChart3 },
    ],
  },
  {
    label: "Inventory",
    to: "/inventory",
    icon: Boxes,
    children: [{ label: "Stock Monitor", to: "/inventory/stock-monitoring", icon: Warehouse }],
  },
  {
    label: "Workers",
    to: "/workers",
    icon: Users,
    excludeRoles: [ROLE.WORKER],
    children: [
      { label: "Attendance", to: "/attendance", icon: Clock },
      { label: "Shifts", to: "/workers/shift-scheduling", icon: CalendarDays },
      { label: "Allocation", to: "/workers/allocation", icon: Users },
      { label: "Payroll", to: "/workers/payroll", icon: Wallet },
    ],
  },
  {
    label: "Procurement",
    to: "/procurement",
    icon: ShoppingCart,
    children: [
      { label: "Requests", to: "/procurement/request", icon: ClipboardList },
      { label: "Approvals", to: "/procurement/approvals", icon: ClipboardCheck },
      { label: "Purchase Orders", to: "/procurement/purchase-orders", icon: FileText },
      { label: "Vendors", to: "/procurement/vendors", icon: Truck },
      { label: "Deliveries", to: "/procurement/deliveries", icon: Boxes },
      { label: "Invoices", to: "/procurement/invoices", icon: Receipt },
      { label: "Payments", to: "/procurement/payments", icon: Wallet },
    ],
  },
  {
    label: "Vendor Portal",
    to: "/procurement/vendor-dashboard",
    icon: Truck,
    children: [
      { label: "Dashboard", to: "/procurement/vendor-dashboard?tab=dashboard", icon: Gauge },
      { label: "Assigned Requests", to: "/procurement/vendor-dashboard?tab=requests", icon: ClipboardList },
      { label: "Purchase Orders", to: "/procurement/vendor-dashboard?tab=orders", icon: FileText },
      { label: "Deliveries", to: "/procurement/vendor-dashboard?tab=deliveries", icon: Boxes },
      { label: "Invoices", to: "/procurement/vendor-dashboard?tab=invoices", icon: Receipt },
      { label: "Profile", to: "/procurement/vendor-dashboard?tab=profile", icon: Settings },
    ],
  },
  {
    label: "Reports",
    to: "/reports",
    icon: BarChart3,
    children: [
      { label: "Progress Analytics", to: "/analytics/progress", icon: BarChart3 },
      { label: "Budget Analytics", to: "/analytics/budget", icon: Wallet },
      { label: "Resource Analytics", to: "/analytics/resource", icon: HardHat },
      { label: "Procurement Analytics", to: "/analytics/procurement", icon: ShoppingCart },
    ],
  },
  { label: "Notifications", to: "/notifications", icon: Bell },
];

export const SETTINGS_ITEM = { label: "Settings", to: "/settings", icon: Settings };

function isVisible(item, user) {
  if (item.onlyRoles && !hasAnyRole(user, item.onlyRoles)) return false;
  if (item.excludeRoles && hasAnyRole(user, item.excludeRoles)) return false;
  const route = getRoute(item.to.split("?")[0]);
  return canOpenRoute(user, route);
}

export function getNavigation(user) {
  return NAV_ITEMS.filter((item) => isVisible(item, user)).map((item) => ({
    ...item,
    children: item.children?.filter((child) => isVisible(child, user)),
  }));
}
