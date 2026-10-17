import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { TabNav } from "../../../components/common/TabNav.jsx";
import { getRoute } from "../../../app/routeConfig.js";
import { canOpenRoute } from "../../../lib/roles.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { DeliveriesTab } from "../components/DeliveriesTab.jsx";
import { InvoicesTab } from "../components/InvoicesTab.jsx";
import { PaymentsTab } from "../components/PaymentsTab.jsx";
import { ProcurementDashboardTab } from "../components/ProcurementDashboardTab.jsx";
import { ProcurementInventoryTab } from "../components/ProcurementInventoryTab.jsx";
import { PurchaseOrdersTab } from "../components/PurchaseOrdersTab.jsx";
import { RequestsTab } from "../components/RequestsTab.jsx";
import { VendorsTab } from "../components/VendorsTab.jsx";

// Mirrors the tab set of Angular's ProcurementComponent, but every tab is a
// URL (the Angular component derived its tab from router.url once on init).
const TABS = [
  { key: "dashboard", label: "Dashboard", to: "/procurement/dashboard", description: "Pipeline status and recent activity." },
  { key: "requests", label: "Requests", to: "/procurement/material-requests", description: "Raise material requests and track them through approval, vendor assignment and purchase." },
  { key: "approvals", label: "Approvals", to: "/procurement/approvals", description: "Material requests waiting for a project manager decision." },
  { key: "vendors", label: "Vendors", to: "/procurement/vendors", description: "Supplier directory used for vendor assignment." },
  { key: "purchase-orders", label: "Purchase Orders", to: "/procurement/purchase-orders", description: "Generate, send and track purchase orders." },
  { key: "deliveries", label: "Deliveries", to: "/procurement/deliveries", description: "Record receipts and quality inspections. Accepted stock updates inventory." },
  { key: "inventory", label: "Inventory", to: "/procurement/inventory", description: "Current stock built from inventory records and received deliveries." },
  { key: "invoices", label: "Invoices", to: "/procurement/invoices", description: "Verify, approve and pay vendor invoices." },
  { key: "payments", label: "Payments", to: "/procurement/payments", description: "Payments recorded against invoices." },
];

function ApprovalsTab() {
  return <RequestsTab approvalsOnly />;
}

const CONTENT = {
  dashboard: ProcurementDashboardTab,
  requests: RequestsTab,
  approvals: ApprovalsTab,
  vendors: VendorsTab,
  "purchase-orders": PurchaseOrdersTab,
  deliveries: DeliveriesTab,
  inventory: ProcurementInventoryTab,
  invoices: InvoicesTab,
  payments: PaymentsTab,
};

export function ProcurementPage({ tab = "dashboard" }) {
  const { user } = useAuth();
  const canOpen = (path) => canOpenRoute(user, getRoute(path));
  const tabs = TABS.filter((item) => canOpen(item.to));
  const current = TABS.find((item) => item.key === tab) || TABS[0];
  const Content = CONTENT[current.key];

  return (
    <>
      <PageHeader eyebrow="Procurement" title={current.key === "dashboard" ? "Procurement" : current.label} description={current.description} />
      <TabNav active={current.key} label="Procurement sections" tabs={tabs} />
      <Content canOpen={canOpen} />
    </>
  );
}
