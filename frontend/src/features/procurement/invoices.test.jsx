import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MockHttpError, callsTo, emptyBackend, on, resetApi } from "../../test/mockApi.js";
import { USERS, renderApp } from "../../test/renderApp.jsx";

// MOCKED: HTTP is replaced by src/test/mockApi.js.
vi.mock("../../services/api.js", async () => {
  const { mockApi } = await import("../../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

const PO = { _id: "po1", po_number: "PO-0001", vendor_id: "v1", materials: "Cement", quantity: 100, unit_price: 380, subtotal: 38000, gst_rate: 18, total_cost: 44840 };
// 80 of 100 bags accepted on site.
const POSITION = {
  purchase_order_id: "po1", po_number: "PO-0001", ordered_quantity: 100, received_quantity: 80, unit_price: 380, po_subtotal: 38000,
  delivered_value: 30400, previously_invoiced: 0, billable_amount: 30400, po_remaining: 38000, gst_rate: 18, expected_gst: 5472,
  supply_type: "intra_state", flags: [],
};
const INVOICE = { _id: "i1", invoice_number: "SC/101", purchase_order_id: "po1", vendor_id: "v1", amount: 38000, gst: 6840, status: "pending", payment_status: "pending" };

beforeEach(() => {
  resetApi();
  emptyBackend();
  on("get", "/procurement/purchase-orders", { items: [PO], total: 1 });
  on("get", "/procurement/vendors", { items: [{ _id: "v1", vendor_name: "Shree Cement", status: "active" }], total: 1 });
});

describe("recording a vendor invoice", () => {
  it("prefills what was accepted, not the PO total, and warns on over-billing", async () => {
    on("get", "/procurement/invoices", { items: [], total: 0 });
    on("get", "/procurement/purchase-orders/po1/invoice-preview", POSITION);
    on("post", "/procurement/invoices", ({ body }) => ({ ...body, _id: "i2" }));
    const user = userEvent.setup();
    renderApp("/procurement/invoices", USERS.admin);

    await user.click(await screen.findByRole("button", { name: "Record invoice" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Purchase order"), "po1");
    await waitFor(() => expect(within(dialog).getByLabelText("Amount before GST (Rs)")).toHaveValue(30400));
    expect(within(dialog).getByLabelText("GST (Rs)")).toHaveValue(5472);
    expect(within(dialog).getByLabelText("Vendor invoice number")).toHaveValue("");
    expect(within(dialog).getByText("Matches the order and accepted deliveries.")).toBeInTheDocument();

    await user.clear(within(dialog).getByLabelText("Amount before GST (Rs)"));
    await user.type(within(dialog).getByLabelText("Amount before GST (Rs)"), "38000");
    expect(within(dialog).getByText(/More than the accepted deliveries not yet invoiced/)).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("Amount before GST (Rs)"));
    await user.type(within(dialog).getByLabelText("Amount before GST (Rs)"), "40000");
    expect(within(dialog).getByText(/This will be refused/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Record invoice" })).toBeDisabled();

    await user.clear(within(dialog).getByLabelText("Amount before GST (Rs)"));
    await user.type(within(dialog).getByLabelText("Amount before GST (Rs)"), "30400");
    await user.type(within(dialog).getByLabelText("Vendor invoice number"), "SC/101");
    await user.click(within(dialog).getByRole("button", { name: "Record invoice" }));
    await waitFor(() => expect(callsTo("post", "/procurement/invoices")).toHaveLength(1));
    expect(callsTo("post", "/procurement/invoices")[0].body).toMatchObject({ purchase_order_id: "po1", invoice_number: "SC/101", amount: 30400, gst: 5472 });
  });
});

describe("reviewing an invoice", () => {
  it("shows the three-way match and asks for a reason when it does not match", async () => {
    on("get", "/procurement/invoices", { items: [INVOICE], total: 1 });
    on("get", "/procurement/invoices/i1/match", { ...POSITION, amount: 38000, gst: 6840, flags: ["Bills Rs 38,000.00 but accepted deliveries not yet invoiced are worth Rs 30,400.00."] });
    on("patch", "/procurement/invoices/i1/verify", ({ body }) => (body.comments ? { ...INVOICE, status: "verified" } : new MockHttpError(409, "Add a comment")));
    const user = userEvent.setup();
    renderApp("/procurement/invoices", USERS.admin);

    const row = (await screen.findAllByRole("row")).find((r) => r.textContent.includes("SC/101"));
    await user.click(within(row).getByRole("button", { name: "Review" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/accepted deliveries not yet invoiced are worth/)).toBeInTheDocument();
    expect(within(dialog).getByRole("columnheader", { name: "Received" })).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Submit" }));
    expect(await screen.findByText(/Explain in the comments/)).toBeInTheDocument();
    expect(callsTo("patch", "/procurement/invoices/i1/verify")).toHaveLength(0);

    await user.type(within(dialog).getByLabelText("Reason for accepting despite the differences"), "Balance delivered today");
    await user.click(within(dialog).getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(callsTo("patch", "/procurement/invoices/i1/verify")).toHaveLength(1));
    expect(callsTo("patch", "/procurement/invoices/i1/verify")[0].body).toEqual({ comments: "Balance delivered today" });
  });
});
