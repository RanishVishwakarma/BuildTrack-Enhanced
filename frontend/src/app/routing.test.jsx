import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { emptyBackend, resetApi } from "../test/mockApi.js";
import { USERS, renderApp } from "../test/renderApp.jsx";
import { ROUTES, getBreadcrumbs } from "./routeConfig.js";

// MOCKED: the HTTP client is replaced; these tests verify routing, guards
// and navigation, not live backend responses.
vi.mock("../services/api.js", async () => {
  const { mockApi } = await import("../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

const userFor = (route) => {
  // Permission-only routes (AI, insights, evidence, hub): the admin holds
  // every default permission.
  if (!route.roles) return USERS.admin;
  if (route.roles.includes("Administrator")) return USERS.admin;
  if (route.roles.includes("Worker")) return USERS.worker;
  return USERS.vendor;
};

beforeEach(() => {
  resetApi();
  emptyBackend();
});

describe("route map", () => {
  // Every static route renders its own page (not 404/403) with the matching document title.
  const staticRoutes = ROUTES.filter((route) => !route.path.includes(":"));
  it.each(staticRoutes.map((route) => [route.path, route]))("%s renders its page", async (path, route) => {
    renderApp(path, userFor(route));
    await waitFor(() => expect(document.title).toBe(`${route.title} | BuildTrack`));
    // First render of a lazily loaded page can exceed the 1s default.
    expect(await screen.findByRole("heading", { level: 1 }, { timeout: 15000 })).toBeInTheDocument();
    expect(screen.queryByText("Page not found")).not.toBeInTheDocument();
    expect(screen.queryByText("Access denied")).not.toBeInTheDocument();
  });

  it("gives each procurement route its own content", async () => {
    const headings = {};
    for (const path of ["/procurement/material-requests", "/procurement/approvals", "/procurement/vendors", "/procurement/purchase-orders", "/procurement/deliveries", "/procurement/invoices", "/procurement/payments"]) {
      const view = renderApp(path, USERS.admin);
      headings[path] = (await screen.findByRole("heading", { level: 1 }, { timeout: 15000 })).textContent;
      view.unmount();
    }
    expect(new Set(Object.values(headings)).size).toBe(Object.keys(headings).length);
  });

  it("builds breadcrumbs from the route parents", () => {
    expect(getBreadcrumbs("/procurement/invoices").map((crumb) => crumb.title)).toEqual(["Procurement", "Invoices"]);
    expect(getBreadcrumbs("/projects/abc123").map((crumb) => crumb.title)).toEqual(["Projects", "Project Details"]);
  });
});

describe("guards", () => {
  it("sends unauthenticated users to sign in", async () => {
    renderApp("/procurement/invoices");
    expect(await screen.findByText(/welcome back/i)).toBeInTheDocument();
  });

  it("blocks a role from a page by URL", async () => {
    renderApp("/workers/payroll", USERS.worker);
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
  });

  it("opens a duty page only for users granted that permission", async () => {
    renderApp("/procurement/payments", USERS.engineer);
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
  });

  it("shows a not-found page for unknown URLs", async () => {
    renderApp("/does-not-exist", USERS.admin);
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });

  it("redirects a signed-in user away from the login page", async () => {
    renderApp("/auth/login", USERS.manager);
    await waitFor(() => expect(window.location.pathname).toBe("/dashboard"));
  });

  it("sends workers from the dashboard to their own dashboard", async () => {
    renderApp("/dashboard", USERS.worker);
    await waitFor(() => expect(window.location.pathname).toBe("/worker-dashboard"));
  });
});

describe("sidebar", () => {
  const navLinks = async () => {
    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    return within(nav).getAllByRole("link").map((link) => link.textContent);
  };

  it("shows payment pages to a user granted the finance duty", async () => {
    renderApp("/procurement/invoices", USERS.finance);
    const links = await navLinks();
    expect(links).toEqual(expect.arrayContaining(["Procurement", "Invoices", "Payments"]));
    expect(links).not.toContain("Purchase Orders");
  });

  it("hides payment pages from the same role without the duty", async () => {
    renderApp("/procurement", USERS.engineer);
    const links = await navLinks();
    expect(links).toContain("Procurement");
    expect(links).not.toContain("Payments");
  });

  it("shows workers their personal shortcuts only", async () => {
    renderApp("/worker-dashboard", USERS.worker);
    const links = await navLinks();
    expect(links).toEqual(expect.arrayContaining(["My Tasks", "My Attendance", "My Schedule", "My Projects"]));
    expect(links).not.toContain("Inventory");
    expect(links).not.toContain("Procurement");
  });

  it("highlights the active child link", async () => {
    renderApp("/procurement/invoices", USERS.admin);
    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    const active = within(nav).getAllByRole("link").filter((link) => link.getAttribute("aria-current") === "page");
    expect(active.map((link) => link.textContent)).toEqual(["Invoices"]);
  });
});
