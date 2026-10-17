import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MockHttpError, callsTo, emptyBackend, on, resetApi } from "../../test/mockApi.js";
import { USERS, renderApp } from "../../test/renderApp.jsx";

// MOCKED: HTTP is replaced by src/test/mockApi.js. These tests check the UI
// workflow and the requests it sends, not the live backend.
vi.mock("../../services/api.js", async () => {
  const { mockApi } = await import("../../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

const PROJECT = { _id: "p1", name: "Tower A", status: "active" };
const pendingRequest = { _id: "r1", request_id: "MR-001", project: "Tower A", project_id: "p1", material_name: "Cement", quantity: 50, unit: "bags", required_date: "2026-11-01T00:00:00", priority: "high", status: "pending" };
const acceptedRequest = { ...pendingRequest, _id: "r2", request_id: "MR-002", status: "vendor_accepted", vendor_id: "v1", vendor_name: "Acme Supplies" };

beforeEach(() => {
  resetApi();
  emptyBackend();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  on("get", "/projects", [PROJECT]);
  on("get", "/procurement/materials", [{ _id: "m1", material: "Cement", material_name: "Cement", available_stock: 10, unit: "bags" }]);
});

describe("material requests", () => {
  it("validates and creates a request with the backend payload, then reloads the list", async () => {
    let created = null;
    on("get", "/procurement/material-requests", () => ({ items: created ? [created] : [], total: created ? 1 : 0 }));
    on("post", "/procurement/material-requests", ({ body }) => {
      created = { ...body, _id: "new", request_id: "MR-009", status: "pending" };
      return created;
    });
    const user = userEvent.setup();
    renderApp("/procurement/material-requests", USERS.engineer);

    await user.click(await screen.findByRole("button", { name: /new request/i }));
    const dialog = await screen.findByRole("dialog");
    await user.clear(within(dialog).getByLabelText("Material"));
    await user.click(within(dialog).getByRole("button", { name: /save request/i }));
    expect(await within(dialog).findByText("Select a project.")).toBeInTheDocument();
    expect(within(dialog).getByText(/at least 2 characters/i)).toBeInTheDocument();
    expect(callsTo("post", "/procurement/material-requests")).toHaveLength(0);

    await waitFor(() => expect(within(dialog).getByRole("option", { name: "Tower A" })).toBeInTheDocument());
    await user.selectOptions(within(dialog).getByLabelText("Project"), "p1");
    await user.type(within(dialog).getByLabelText("Material"), "Cement");
    await user.clear(within(dialog).getByLabelText("Quantity"));
    await user.type(within(dialog).getByLabelText("Quantity"), "25");
    await user.selectOptions(within(dialog).getByLabelText("Priority"), "high");
    await user.click(within(dialog).getByRole("button", { name: /save request/i }));

    await waitFor(() => expect(callsTo("post", "/procurement/material-requests")).toHaveLength(1));
    const payload = callsTo("post", "/procurement/material-requests")[0].body;
    expect(payload).toMatchObject({ project: "Tower A", project_id: "p1", material_name: "Cement", material_id: "m1", unit: "bags", quantity: 25, priority: "high" });
    expect(payload.required_date).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(await screen.findByText("Material request created.")).toBeInTheDocument();
    expect(await screen.findByText("MR-009")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("approves a pending request through the approval endpoint", async () => {
    on("get", "/procurement/material-requests", { items: [pendingRequest], total: 1 });
    on("patch", "/procurement/material-requests/r1/approval", ({ body }) => ({ ...pendingRequest, status: body.status }));
    const user = userEvent.setup();
    renderApp("/procurement/approvals", USERS.manager);

    await user.click(await screen.findByRole("button", { name: "Review" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Comments"), "Stock needed for slab");
    await user.click(within(dialog).getByRole("button", { name: /approve request/i }));

    await waitFor(() => expect(callsTo("patch", "/procurement/material-requests/r1/approval")).toHaveLength(1));
    expect(callsTo("patch", "/procurement/material-requests/r1/approval")[0].body).toEqual({ status: "approved", comments: "Stock needed for slab" });
    expect(await screen.findByText("Material request approved.")).toBeInTheDocument();
  });

  it("shows backend errors and keeps the dialog open", async () => {
    on("get", "/procurement/material-requests", { items: [pendingRequest], total: 1 });
    on("patch", "/procurement/material-requests/r1/approval", () => new MockHttpError(403, "Insufficient procurement permissions"));
    const user = userEvent.setup();
    renderApp("/procurement/approvals", USERS.manager);

    await user.click(await screen.findByRole("button", { name: "Review" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /approve request/i }));
    expect(await screen.findByText("Insufficient procurement permissions")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByText("Material request approved.")).not.toBeInTheDocument();
  });

  it("offers PO generation only once the vendor has accepted", async () => {
    on("get", "/procurement/material-requests", { items: [pendingRequest, acceptedRequest], total: 2 });
    renderApp("/procurement/material-requests", USERS.manager);
    const rows = await screen.findAllByRole("row");
    const pendingRow = rows.find((row) => row.textContent.includes("MR-001"));
    const acceptedRow = rows.find((row) => row.textContent.includes("MR-002"));
    expect(within(pendingRow).queryByRole("button", { name: "Generate PO" })).not.toBeInTheDocument();
    expect(within(acceptedRow).getByRole("button", { name: "Generate PO" })).toBeInTheDocument();
  });

  it("sends search and status filters to the backend", async () => {
    on("get", "/procurement/material-requests", { items: [], total: 0 });
    renderApp("/procurement/material-requests", USERS.manager);
    fireEvent.change(await screen.findByLabelText("Filter by status"), { target: { value: "approved" } });
    fireEvent.change(screen.getByLabelText(/search request id/i), { target: { value: "cement" } });
    await waitFor(() => {
      const last = callsTo("get", "/procurement/material-requests").at(-1);
      expect(last.params).toMatchObject({ status_filter: "approved", search: "cement", skip: 0, limit: 10 });
    });
  });
});

describe("purchase orders", () => {
  it("generates a PO from a vendor-accepted request", async () => {
    on("get", "/procurement/material-requests", { items: [acceptedRequest], total: 1 });
    on("get", "/procurement/vendors", { items: [{ _id: "v1", vendor_name: "Acme Supplies", status: "active", gst_number: "27AAFCV9876K1Z2" }], total: 1 });
    on("get", "/procurement/gst-config", { slabs: [0, 5, 12, 18, 28], company_state_code: "27", company_gstin_configured: true });
    on("get", "/inventory", [{ _id: "i1", material_name: "Cement", gst_rate: 28 }]);
    on("post", "/procurement/purchase-orders", ({ body }) => ({ ...body, _id: "po1", po_number: "PO-0001", total_cost: 1000 }));
    const user = userEvent.setup();
    renderApp("/procurement/material-requests", USERS.manager);

    await user.click(await screen.findByRole("button", { name: "Generate PO" }));
    const dialog = await screen.findByRole("dialog");
    await user.clear(within(dialog).getByLabelText("Unit price (Rs)"));
    await user.type(within(dialog).getByLabelText("Unit price (Rs)"), "400");
    // The rate is pre-filled from the material's inventory record, then changed.
    await waitFor(() => expect(within(dialog).getByLabelText("GST rate")).toHaveValue("28"));
    await user.selectOptions(within(dialog).getByLabelText("GST rate"), "18");
    expect(within(dialog).getByText(/Total .*23,600/)).toBeInTheDocument();
    expect(within(dialog).getByText(/CGST .*1,800 \+ SGST .*1,800/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Generate PO" }));

    await waitFor(() => expect(callsTo("post", "/procurement/purchase-orders")).toHaveLength(1));
    expect(callsTo("post", "/procurement/purchase-orders")[0].body).toMatchObject({ request_id: "r2", vendor_id: "v1", materials: "Cement", quantity: 50, unit_price: 400, gst_rate: 18, status: "created" });
    expect(await screen.findByText("Purchase order PO-0001 created.")).toBeInTheDocument();
  });

  it("sends a created PO to the vendor", async () => {
    on("get", "/procurement/purchase-orders", { items: [{ _id: "po1", po_number: "PO-0001", status: "created", vendor_id: "v1", project: "Tower A", materials: "Cement", quantity: 5, total_cost: 100 }], total: 1 });
    on("put", "/procurement/purchase-orders/po1/send", { _id: "po1", status: "sent" });
    const user = userEvent.setup();
    renderApp("/procurement/purchase-orders", USERS.manager);
    await user.click(await screen.findByRole("button", { name: "Send" }));
    await waitFor(() => expect(callsTo("put", "/procurement/purchase-orders/po1/send")).toHaveLength(1));
    expect(await screen.findByText("PO-0001 sent to vendor.")).toBeInTheDocument();
  });
});

describe("deliveries", () => {
  it("accepts a shipped delivery so the backend adds stock", async () => {
    on("get", "/procurement/deliveries", { items: [{ _id: "d1", material: "Cement", quantity_received: 20, status: "shipped", quality_status: "pending", po_number: "PO-0001" }], total: 1 });
    on("put", "/procurement/deliveries/d1", ({ body }) => ({ _id: "d1", ...body }));
    const user = userEvent.setup();
    renderApp("/procurement/deliveries", USERS.store);
    await user.click(await screen.findByRole("button", { name: /accept & stock/i }));
    await waitFor(() => expect(callsTo("put", "/procurement/deliveries/d1")).toHaveLength(1));
    expect(callsTo("put", "/procurement/deliveries/d1")[0].body).toEqual({ status: "accepted", quality_status: "passed", quantity_received: 20 });
  });
});
