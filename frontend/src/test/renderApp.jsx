import { render } from "@testing-library/react";
import { Toaster } from "react-hot-toast";
import { App } from "../app/App.jsx";
import { AppProviders } from "../app/providers.jsx";
import { persistSession } from "../features/auth/services/session.js";
import { ROLE_PERMISSIONS } from "./permissions.js";

const withPermissions = (user, extra = []) => ({ ...user, permissions: [...ROLE_PERMISSIONS[user.role], ...extra] });

export const USERS = {
  admin: withPermissions({ id: "u-admin", name: "Asha Admin", email: "admin@test.local", role: "Administrator" }),
  manager: withPermissions({ id: "u-pm", name: "Priya PM", email: "pm@test.local", role: "Project Manager" }),
  engineer: withPermissions({ id: "u-se", name: "Sam Engineer", email: "se@test.local", role: "Site Engineer" }),
  // Finance is a duty, not a role: a site engineer granted payment and invoice permissions.
  finance: withPermissions({ id: "u-fin", name: "Farah Finance", email: "fin@test.local", role: "Site Engineer" }, [
    "procurement.payment.record",
    "procurement.invoice.manage",
  ]),
  // Receiving deliveries is part of the Site Engineer defaults.
  store: withPermissions({ id: "u-store", name: "Stan Store", email: "store@test.local", role: "Site Engineer" }),
  worker: withPermissions({ id: "u-worker", name: "Wes Worker", email: "worker@test.local", role: "Worker", workerId: "w1" }),
  client: withPermissions({ id: "u-client", name: "Cara Client", email: "client@test.local", role: "Client" }),
  vendor: withPermissions({ id: "u-vendor", name: "Vik Vendor", email: "vendor@test.local", role: "Vendor", vendorId: "v1" }),
};

export function renderApp(path, user) {
  localStorage.clear();
  if (user) persistSession("test-token", user);
  window.history.pushState({}, "", path);
  return render(
    <AppProviders>
      <App />
      <Toaster />
    </AppProviders>,
  );
}
