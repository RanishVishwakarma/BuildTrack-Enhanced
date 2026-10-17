import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { callsTo, emptyBackend, on, resetApi } from "../test/mockApi.js";
import { USERS, renderApp } from "../test/renderApp.jsx";

// MOCKED: HTTP is replaced by src/test/mockApi.js. These tests check UI
// workflows and the requests they send, not the live backend.
vi.mock("../services/api.js", async () => {
  const { mockApi } = await import("../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

beforeEach(() => {
  resetApi();
  emptyBackend();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  on("get", "/projects", [{ _id: "p1", name: "Tower A", status: "active" }]);
});

const rowFor = async (text) => (await screen.findAllByRole("row")).find((row) => row.textContent.includes(text));

describe("inventory", () => {
  const cement = { _id: "i1", material_name: "Cement", quantity: 12, unit: "bags", unit_cost: 400, reorder_level: 10, status: "in_stock", location: "Yard" };

  it("refuses to issue more stock than is on hand", async () => {
    on("get", "/inventory", [cement]);
    on("get", "/inventory/i1/transactions", []);
    const user = userEvent.setup();
    renderApp("/inventory", USERS.manager);

    await user.click(within(await rowFor("Cement")).getByRole("button", { name: "Stock in/out" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Movement"), "out");
    await user.type(within(dialog).getByLabelText("Quantity"), "20");
    await user.click(within(dialog).getByRole("button", { name: "Record" }));
    expect(await within(dialog).findByText("Only 12 bags in stock.")).toBeInTheDocument();
    expect(callsTo("post", "/inventory/i1/transactions")).toHaveLength(0);
  });

  it("records a stock receipt and refreshes inventory", async () => {
    on("get", "/inventory", [cement]);
    on("get", "/inventory/i1/transactions", []);
    on("post", "/inventory/i1/transactions", ({ body }) => ({ _id: "t1", item_id: "i1", ...body, created_at: new Date().toISOString() }));
    const user = userEvent.setup();
    renderApp("/inventory", USERS.manager);

    await user.click(within(await rowFor("Cement")).getByRole("button", { name: "Stock in/out" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Quantity"), "8");
    await user.type(within(dialog).getByLabelText("Reason"), "Delivery from yard");
    await user.click(within(dialog).getByRole("button", { name: "Record" }));

    await waitFor(() => expect(callsTo("post", "/inventory/i1/transactions")).toHaveLength(1));
    expect(callsTo("post", "/inventory/i1/transactions")[0].body).toEqual({ transaction_type: "in", quantity: 8, reason: "Delivery from yard", created_by: USERS.manager.name });
    await waitFor(() => expect(callsTo("get", "/inventory").length).toBeGreaterThanOrEqual(2));
  });

  it("hides mutations from roles the backend rejects", async () => {
    on("get", "/inventory", [cement]);
    renderApp("/inventory", USERS.engineer);
    const row = await rowFor("Cement");
    expect(within(row).queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add item/i })).not.toBeInTheDocument();
  });
});

describe("workforce", () => {
  it("requires a skill and sends the WorkerCreate payload", async () => {
    on("get", "/workforce/workers", []);
    on("post", "/workforce/workers", ({ body }) => ({ _id: "w9", ...body }));
    const user = userEvent.setup();
    renderApp("/workers", USERS.manager);

    await user.click(await screen.findByRole("button", { name: /add worker/i }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("First name"), "Ravi");
    await user.type(within(dialog).getByLabelText("Last name"), "Kumar");
    await user.type(within(dialog).getByLabelText("Email"), "ravi@test.local");
    await user.click(within(dialog).getByRole("button", { name: /save worker/i }));
    expect(await within(dialog).findByText(/skill is required/i)).toBeInTheDocument();
    expect(callsTo("post", "/workforce/workers")).toHaveLength(0);

    await user.type(within(dialog).getByLabelText("Skill"), "mason");
    await user.selectOptions(within(dialog).getByLabelText("Project"), "p1");
    await user.click(within(dialog).getByRole("button", { name: /save worker/i }));
    await waitFor(() => expect(callsTo("post", "/workforce/workers")).toHaveLength(1));
    expect(callsTo("post", "/workforce/workers")[0].body).toMatchObject({
      first_name: "Ravi",
      last_name: "Kumar",
      email: "ravi@test.local",
      skill_type: "mason",
      category: "SKILLED_WORKER",
      employment_type: "FULL_TIME",
      project_id: "p1",
      status: "available",
    });
  });

  it("filters workers by status on the client", async () => {
    on("get", "/workforce/workers", [
      { _id: "w1", first_name: "Ann", last_name: "A", status: "available", category: "ENGINEER" },
      { _id: "w2", first_name: "Bob", last_name: "B", status: "assigned", category: "ENGINEER" },
    ]);
    const user = userEvent.setup();
    renderApp("/workers", USERS.manager);
    expect(await screen.findByText("Ann A")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Filter by status"), "assigned");
    expect(screen.queryByText("Ann A")).not.toBeInTheDocument();
    expect(screen.getByText("Bob B")).toBeInTheDocument();
  });

  it("marks attendance from the daily roster", async () => {
    on("get", "/workforce/workers", [{ _id: "w1", first_name: "Ann", last_name: "A", status: "available", project_id: "p1" }]);
    on("get", "/workforce/attendance", []);
    on("post", "/workforce/attendance", ({ body }) => ({ _id: "a1", ...body }));
    const user = userEvent.setup();
    renderApp("/attendance", USERS.manager);
    const row = await rowFor("Ann A");
    await user.click(within(row).getByRole("button", { name: "Present" }));
    await waitFor(() => expect(callsTo("post", "/workforce/attendance")).toHaveLength(1));
    expect(callsTo("post", "/workforce/attendance")[0].body).toMatchObject({ worker_id: "w1", project_id: "p1", status: "present" });
  });

  it("requires choosing a project before allocations load", async () => {
    on("get", "/workforce/workers", []);
    on("get", "/workforce/allocations/project/p1", []);
    const user = userEvent.setup();
    renderApp("/workers/allocation", USERS.manager);
    expect(await screen.findByText("Choose a project")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /allocate worker/i })).toBeDisabled();
    await waitFor(() => expect(screen.getByRole("option", { name: "Tower A" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Project"), "p1");
    await waitFor(() => expect(callsTo("get", "/workforce/allocations/project/p1")).toHaveLength(1));
  });
});

describe("project milestones", () => {
  it("lists this project's milestone records and saves edits in Angular's record format", async () => {
    on("get", "/projects/p1", { _id: "p1", name: "Tower A", status: "active", milestones: [] });
    on("get", "/frontend-data/milestones", [
      { _id: "m1", projectId: "p1", project_id: "p1", title: "Foundation", due_date: "2026-11-01T00:00:00", status: "In Progress", progress: 40 },
      { _id: "m2", projectId: "p2", project_id: "p2", title: "Other project milestone", due_date: "2026-11-02T00:00:00", status: "Not Started", progress: 0 },
    ]);
    on("put", "/frontend-data/milestones/m1", ({ body }) => ({ _id: "m1", ...body }));
    const user = userEvent.setup();
    renderApp("/projects/p1", USERS.manager);

    await user.click(await screen.findByRole("tab", { name: "milestones" }));
    const row = await rowFor("Foundation");
    expect(screen.queryByText("Other project milestone")).not.toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Status"), "Completed");
    await user.click(within(dialog).getByRole("button", { name: /save milestone/i }));

    await waitFor(() => expect(callsTo("put", "/frontend-data/milestones/m1")).toHaveLength(1));
    expect(callsTo("put", "/frontend-data/milestones/m1")[0].body).toMatchObject({ projectId: "p1", project_id: "p1", title: "Foundation", status: "Completed", progress: 100 });
  });
});

describe("settings", () => {
  it("only sends fields the profile endpoint accepts", async () => {
    on("put", "/auth/profile", ({ body }) => ({ _id: "u-pm", email: USERS.manager.email, role: "manager", full_name: body.full_name }));
    const user = userEvent.setup();
    renderApp("/settings", USERS.manager);
    const name = await screen.findByLabelText("Full name");
    expect(screen.getByLabelText("Email")).toBeDisabled();
    await user.clear(name);
    await user.type(name, "Priya Sharma");
    await user.click(screen.getByRole("button", { name: /save profile/i }));
    await waitFor(() => expect(callsTo("put", "/auth/profile")).toHaveLength(1));
    expect(callsTo("put", "/auth/profile")[0].body).toEqual({ full_name: "Priya Sharma" });
    expect(await screen.findByText("Priya Sharma")).toBeInTheDocument();
  });

  it("shows user management to administrators only", async () => {
    renderApp("/settings?tab=users", USERS.manager);
    await screen.findByLabelText("Full name");
    expect(screen.queryByRole("link", { name: "User management" })).not.toBeInTheDocument();
  });
});

describe("my tasks", () => {
  it("is read-only for workers because the backend rejects worker task updates", async () => {
    on("get", "/tasks/worker/w1", [{ _id: "t1", title: "Pour slab", project_id: "p1", status: "pending", due_date: "2026-12-01" }]);
    renderApp("/my-tasks", USERS.worker);
    expect(await screen.findByText("Pour slab")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /complete/i })).not.toBeInTheDocument();
  });
});
