import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { callsTo, emptyBackend, on, resetApi } from "../../test/mockApi.js";
import { renderApp } from "../../test/renderApp.jsx";

// MOCKED: HTTP is replaced by src/test/mockApi.js.
vi.mock("../../services/api.js", async () => {
  const { mockApi } = await import("../../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

beforeEach(() => {
  resetApi();
  emptyBackend();
});

async function fillForm(user, { password = "Strong#Pass1", confirm = "Strong#Pass1" } = {}) {
  await user.type(await screen.findByLabelText("Full name"), "Asha Engineer");
  await user.type(screen.getByLabelText("Email address"), "asha@example.com");
  await user.type(screen.getByLabelText("Password"), password);
  await user.type(screen.getByLabelText("Confirm password"), confirm);
}

describe("sign up", () => {
  it("rejects a confirmation that does not match and sends nothing", async () => {
    const user = userEvent.setup();
    renderApp("/auth/register");
    await fillForm(user, { confirm: "Different#1" });
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(callsTo("post", "/auth/register")).toHaveLength(0);
  });

  it("shows and hides the password with the eye button", async () => {
    const user = userEvent.setup();
    renderApp("/auth/register");
    const password = await screen.findByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    const [toggle] = screen.getAllByRole("button", { name: "Show password" });
    await user.click(toggle);
    expect(password).toHaveAttribute("type", "text");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
  });

  it("registers without sending the confirmation field", async () => {
    on("post", "/auth/register", { message: "User registered successfully" });
    on("post", "/auth/login", { access_token: "t", user: { email: "asha@example.com", role: "worker", permissions: [] } });
    const user = userEvent.setup();
    renderApp("/auth/register");
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(callsTo("post", "/auth/register")).toHaveLength(1));
    const body = callsTo("post", "/auth/register")[0].body;
    expect(body).toEqual({ full_name: "Asha Engineer", email: "asha@example.com", password: "Strong#Pass1", role: "worker" });
  });
  it("does not sign in a staff account that is waiting for approval", async () => {
    on("post", "/auth/register", { message: "Account created. An administrator must approve it before you can sign in.", pending_approval: true });
    const user = userEvent.setup();
    renderApp("/auth/register");
    await fillForm(user);
    await user.selectOptions(screen.getByLabelText("Role"), "Project Manager");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Account created. An administrator must approve it before you can sign in.")).toBeInTheDocument();
    expect(callsTo("post", "/auth/login")).toHaveLength(0);
    expect(await screen.findByText(/welcome back/i)).toBeInTheDocument();
    expect(localStorage.getItem("buildtrack_token")).toBeNull();
  });
});
