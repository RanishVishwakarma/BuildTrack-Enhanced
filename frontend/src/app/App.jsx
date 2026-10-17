import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
import { AppLayout } from "../layouts/AppLayout.jsx";
import { AuthLayout } from "../layouts/AuthLayout.jsx";
import { GuestRoute, ProtectedRoute, RoleRoute } from "./RouteGuards.jsx";
import { LoginPage } from "../features/auth/pages/LoginPage.jsx";
import { RegisterPage } from "../features/auth/pages/RegisterPage.jsx";
import { ForgotPasswordPage } from "../features/auth/pages/ForgotPasswordPage.jsx";
import { ForbiddenPage } from "../features/forbidden/ForbiddenPage.jsx";
import { NotFoundPage } from "../features/not-found/NotFoundPage.jsx";

// Feature pages load on demand so the initial bundle stays small.
const page = (loader, name) => lazy(() => loader().then((module) => ({ default: module[name] })));
// The landing page carries the WebGL shader library, so it is split out too.
const LandingPage = page(() => import("../features/landing/pages/LandingPage.jsx"), "LandingPage");
const DashboardPage = page(() => import("../features/dashboard/pages/DashboardPage.jsx"), "DashboardPage");
const ProjectsPage = page(() => import("../features/projects/pages/ProjectsPage.jsx"), "ProjectsPage");
const ProjectDetailsPage = page(() => import("../features/projects/pages/ProjectDetailsPage.jsx"), "ProjectDetailsPage");
const MilestonesPage = page(() => import("../features/projects/pages/MilestonesPage.jsx"), "MilestonesPage");
const ProjectStatusDashboardPage = page(() => import("../features/projects/pages/ProjectStatusDashboardPage.jsx"), "ProjectStatusDashboardPage");
const InventoryPage = page(() => import("../features/inventory/pages/InventoryPage.jsx"), "InventoryPage");
const StockMonitoringPage = page(() => import("../features/inventory/pages/StockMonitoringPage.jsx"), "StockMonitoringPage");
const WorkforcePage = page(() => import("../features/workforce/pages/WorkforcePage.jsx"), "WorkforcePage");
const AttendancePage = page(() => import("../features/workforce/pages/AttendancePage.jsx"), "AttendancePage");
const ShiftSchedulingPage = page(() => import("../features/workforce/pages/ShiftSchedulingPage.jsx"), "ShiftSchedulingPage");
const PayrollPage = page(() => import("../features/workforce/pages/PayrollPage.jsx"), "PayrollPage");
const AllocationPage = page(() => import("../features/workforce/pages/AllocationPage.jsx"), "AllocationPage");
const WorkerDashboardPage = page(() => import("../features/workforce/pages/WorkerDashboardPage.jsx"), "WorkerDashboardPage");
const MyTasksPage = page(() => import("../features/tasks/pages/MyTasksPage.jsx"), "MyTasksPage");
const ProcurementPage = page(() => import("../features/procurement/pages/ProcurementPage.jsx"), "ProcurementPage");
const VendorDashboardPage = page(() => import("../features/procurement/pages/VendorDashboardPage.jsx"), "VendorDashboardPage");
const ResourcesPage = page(() => import("../features/resources/pages/ResourcesPage.jsx"), "ResourcesPage");
const EquipmentTrackingPage = page(() => import("../features/resources/pages/EquipmentTrackingPage.jsx"), "EquipmentTrackingPage");
const ResourceUtilizationPage = page(() => import("../features/resources/pages/ResourceUtilizationPage.jsx"), "ResourceUtilizationPage");
const ReportsPage = page(() => import("../features/reports/pages/ReportsPage.jsx"), "ReportsPage");
const AnalyticsPage = page(() => import("../features/analytics/pages/AnalyticsPage.jsx"), "AnalyticsPage");
const NotificationsPage = page(() => import("../features/notifications/pages/NotificationsPage.jsx"), "NotificationsPage");
const SettingsPage = page(() => import("../features/settings/pages/SettingsPage.jsx"), "SettingsPage");
const AiAssistantPage = page(() => import("../features/ai-assistant/pages/AiAssistantPage.jsx"), "AiAssistantPage");
const InsightsPage = page(() => import("../features/insights/pages/InsightsPage.jsx"), "InsightsPage");
const EvidencePage = page(() => import("../features/evidence/pages/EvidencePage.jsx"), "EvidencePage");
const HubPage = page(() => import("../features/hub/pages/HubPage.jsx"), "HubPage");

// path -> page element. Every path must also exist in routeConfig.js, which
// holds its title, breadcrumb parent and allowed roles.
const pages = [
  ["/dashboard", <DashboardPage key="dashboard" />],
  ["/projects", <ProjectsPage key="projects" />],
  ["/projects/milestones", <MilestonesPage key="milestones" />],
  ["/projects/status-dashboard", <ProjectStatusDashboardPage key="status" />],
  ["/projects/:projectId", <ProjectDetailsPage key="project" />],
  ["/resources", <ResourcesPage key="resources" />],
  ["/resources/equipment", <EquipmentTrackingPage key="equipment" />],
  ["/resources/utilization", <ResourceUtilizationPage key="utilization" />],
  ["/inventory", <InventoryPage key="inventory" />],
  ["/inventory/stock-monitoring", <StockMonitoringPage key="stock" />],
  ["/workers", <WorkforcePage key="workers" />],
  ["/workers/shift-scheduling", <ShiftSchedulingPage key="shifts" />],
  ["/workers/allocation", <AllocationPage key="allocation" />],
  ["/workers/payroll", <PayrollPage key="payroll" />],
  ["/attendance", <AttendancePage key="attendance" />],
  ["/my-tasks", <MyTasksPage key="tasks" />],
  ["/worker-dashboard", <WorkerDashboardPage key="worker-dashboard" />],
  ["/procurement", <ProcurementPage key="p-dashboard" tab="dashboard" />],
  ["/procurement/dashboard", <ProcurementPage key="p-dashboard2" tab="dashboard" />],
  ["/procurement/request", <ProcurementPage key="p-request" tab="requests" />],
  ["/procurement/material-requests", <ProcurementPage key="p-requests" tab="requests" />],
  ["/procurement/approvals", <ProcurementPage key="p-approvals" tab="approvals" />],
  ["/procurement/purchase-orders", <ProcurementPage key="p-po" tab="purchase-orders" />],
  ["/procurement/vendors", <ProcurementPage key="p-vendors" tab="vendors" />],
  ["/procurement/deliveries", <ProcurementPage key="p-deliveries" tab="deliveries" />],
  ["/procurement/inventory", <ProcurementPage key="p-inventory" tab="inventory" />],
  ["/procurement/invoices", <ProcurementPage key="p-invoices" tab="invoices" />],
  ["/procurement/payments", <ProcurementPage key="p-payments" tab="payments" />],
  ["/procurement/vendor-dashboard", <VendorDashboardPage key="vendor" />],
  ["/reports", <ReportsPage key="reports" />],
  ["/analytics/progress", <AnalyticsPage key="a-progress" type="progress" />],
  ["/analytics/budget", <AnalyticsPage key="a-budget" type="budget" />],
  ["/analytics/resource", <AnalyticsPage key="a-resource" type="resource" />],
  ["/analytics/procurement", <AnalyticsPage key="a-procurement" type="procurement" />],
  ["/ai", <AiAssistantPage key="ai-overview" tab="overview" />],
  ["/ai/ask", <AiAssistantPage key="ai-ask" tab="ask" />],
  ["/ai/actions", <AiAssistantPage key="ai-actions" tab="actions" />],
  ["/ai/reports", <AiAssistantPage key="ai-reports" tab="reports" />],
  ["/ai/activity", <AiAssistantPage key="ai-activity" tab="activity" />],
  ["/insights", <InsightsPage key="insights-risks" tab="risks" />],
  ["/insights/materials", <InsightsPage key="insights-materials" tab="materials" />],
  ["/insights/impact", <InsightsPage key="insights-impact" tab="impact" />],
  ["/insights/budget", <InsightsPage key="insights-budget" tab="budget" />],
  ["/evidence", <EvidencePage key="evidence" />],
  ["/hub", <HubPage key="hub-suggestions" tab="suggestions" />],
  ["/hub/safety", <HubPage key="hub-safety" tab="safety" />],
  ["/hub/actions", <HubPage key="hub-actions" tab="actions" />],
  ["/notifications", <NotificationsPage key="notifications" />],
  ["/settings", <SettingsPage key="settings" />],
];

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Suspense fallback={<div className="min-h-screen bg-black" />}><LandingPage /></Suspense>} />
      <Route element={<GuestRoute><AuthLayout /></GuestRoute>}>
        <Route path="/auth/login" element={<LoginPage />} />
        <Route path="/auth/register" element={<RegisterPage />} />
        <Route path="/auth/forgot-password" element={<ForgotPasswordPage />} />
      </Route>
      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/forbidden" element={<ForbiddenPage />} />
        {pages.map(([path, element]) => (
          <Route key={path} path={path} element={<RoleRoute path={path}>{element}</RoleRoute>} />
        ))}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
