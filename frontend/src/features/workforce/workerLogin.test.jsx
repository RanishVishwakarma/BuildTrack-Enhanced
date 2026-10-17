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

const workers = [
  { _id: "w1", first_name: "Ravi", last_name: "Kumar", email: "ravi@site.io", status: "available", login_email: null },
  { _id: "w2", first_name: "Sunil", last_name: "Rao", email: "sunil@site.io", status: "assigned", login_email: "sunil@site.io" },
];

beforeEach(() => {
  resetApi();
  emptyBackend();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  on("get", "/workforce/workers", workers);
});

const rowFor = async (name) => (await screen.findAllByRole("row")).find((row) => row.textContent.includes(name));

describe("worker logins", () => {
  it("creates a login tied to the worker record", async () => {
    on("post", "/workforce/workers/w1/login", { message: "Login created. Login email: ravi@site.io" });
    const user = userEvent.setup();
    renderApp("/workers", USERS.manager);

    await user.click(within(await rowFor("Ravi")).getByRole("button", { name: "Create login" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Login email")).toHaveValue("ravi@site.io");
    await user.type(within(dialog).getByLabelText("Password"), "ravi-2026x");
    await user.type(within(dialog).getByLabelText("Confirm password"), "ravi-2026x");
    await user.click(within(dialog).getByRole("button", { name: "Create login" }));

    await waitFor(() => expect(callsTo("post", "/workforce/workers/w1/login")).toHaveLength(1));
    expect(callsTo("post", "/workforce/workers/w1/login")[0].body).toEqual({ email: "ravi@site.io", password: "ravi-2026x" });
    expect(await screen.findByText("Login created. Login email: ravi@site.io")).toBeInTheDocument();
  });

  it("links an account the worker registered, without a password", async () => {
    on("post", "/workforce/workers/w1/login/link", { message: "Linked ravi.k@mail.io to this worker." });
    const user = userEvent.setup();
    renderApp("/workers", USERS.manager);

    await user.click(within(await rowFor("Ravi")).getByRole("button", { name: "Create login" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Link existing account" }));
    expect(within(dialog).queryByLabelText("Password")).not.toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("Email of their account"));
    await user.type(within(dialog).getByLabelText("Email of their account"), "ravi.k@mail.io");
    await user.click(within(dialog).getByRole("button", { name: "Link account" }));

    await waitFor(() => expect(callsTo("post", "/workforce/workers/w1/login/link")).toHaveLength(1));
    expect(callsTo("post", "/workforce/workers/w1/login/link")[0].body).toEqual({ email: "ravi.k@mail.io" });
  });

  it("resets or unlinks an existing login", async () => {
    on("put", "/workforce/workers/w2/login/password", { message: "Password updated for sunil@site.io." });
    on("delete", "/workforce/workers/w2/login", { message: "sunil@site.io is no longer linked to this worker." });
    const user = userEvent.setup();
    renderApp("/workers", USERS.manager);

    const row = await rowFor("Sunil");
    expect(within(row).getByText("sunil@site.io", { selector: "td *, td" })).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Manage login" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("New password"), "new-pass-1");
    await user.type(within(dialog).getByLabelText("Confirm password"), "new-pass-1");
    await user.click(within(dialog).getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(callsTo("put", "/workforce/workers/w2/login/password")).toHaveLength(1));
    expect(callsTo("put", "/workforce/workers/w2/login/password")[0].body).toEqual({ password: "new-pass-1" });

    await user.click(within(await rowFor("Sunil")).getByRole("button", { name: "Manage login" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Unlink" }));
    await waitFor(() => expect(callsTo("delete", "/workforce/workers/w2/login")).toHaveLength(1));
  });

  it("hides login controls without the permission", async () => {
    const manager = { ...USERS.manager, permissions: USERS.manager.permissions.filter((p) => p !== "workforce.login.manage") };
    renderApp("/workers", manager);
    await rowFor("Ravi");
    expect(screen.queryByRole("button", { name: "Create login" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Login" })).not.toBeInTheDocument();
  });
});
