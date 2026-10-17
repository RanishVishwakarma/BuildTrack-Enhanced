import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { callsTo, emptyBackend, on, resetApi } from "../../test/mockApi.js";
import { USERS, renderApp } from "../../test/renderApp.jsx";

// MOCKED: HTTP is replaced by src/test/mockApi.js.
vi.mock("../../services/api.js", async () => {
  const { mockApi } = await import("../../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

const vendors = [
  { _id: "v1", vendor_name: "Shree Cement", email: "sales@shree.io", status: "active", login_email: null },
  { _id: "v2", vendor_name: "Steel Co", email: "steel@co.io", status: "active", login_email: "steel@co.io" },
];

beforeEach(() => {
  resetApi();
  emptyBackend();
  on("get", "/procurement/vendors", { items: vendors, total: 2 });
});

describe("vendor portal logins", () => {
  it("lets a project manager create a login for an existing vendor", async () => {
    on("post", "/procurement/vendors/v1/login", { message: "Portal login created. Login email: sales@shree.io" });
    const user = userEvent.setup();
    renderApp("/procurement/vendors", USERS.manager);

    const row = (await screen.findAllByRole("row")).find((r) => r.textContent.includes("Shree Cement"));
    await user.click(within(row).getByRole("button", { name: "Create login" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Login email")).toHaveValue("sales@shree.io");
    await user.type(within(dialog).getByLabelText("Password"), "cement-2026");
    await user.type(within(dialog).getByLabelText("Confirm password"), "cement-2027");
    await user.click(within(dialog).getByRole("button", { name: "Create login" }));
    expect(await within(dialog).findByText("Passwords do not match.")).toBeInTheDocument();

    await user.clear(within(dialog).getByLabelText("Confirm password"));
    await user.type(within(dialog).getByLabelText("Confirm password"), "cement-2026");
    await user.click(within(dialog).getByRole("button", { name: "Create login" }));
    await waitFor(() => expect(callsTo("post", "/procurement/vendors/v1/login")).toHaveLength(1));
    expect(callsTo("post", "/procurement/vendors/v1/login")[0].body).toEqual({ email: "sales@shree.io", password: "cement-2026" });
    expect(await screen.findByText("Portal login created. Login email: sales@shree.io")).toBeInTheDocument();
  });

  it("offers a password reset when the vendor already has a login", async () => {
    renderApp("/procurement/vendors", USERS.manager);
    const row = (await screen.findAllByRole("row")).find((r) => r.textContent.includes("Steel Co"));
    expect(within(row).getByRole("button", { name: "Reset password" })).toBeInTheDocument();
  });

  it("hides login controls without the vendor-login permission", async () => {
    const manager = { ...USERS.manager, permissions: USERS.manager.permissions.filter((p) => p !== "procurement.vendor.login.manage") };
    renderApp("/procurement/vendors", manager);
    await screen.findAllByRole("row");
    expect(screen.queryByRole("button", { name: "Create login" })).not.toBeInTheDocument();
    expect(screen.queryByText("Portal login")).not.toBeInTheDocument();
  });
});
