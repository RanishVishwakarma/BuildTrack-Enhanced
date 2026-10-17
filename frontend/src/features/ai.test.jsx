import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { callsTo, emptyBackend, on, resetApi } from "../test/mockApi.js";
import { USERS, renderApp } from "../test/renderApp.jsx";

// MOCKED: HTTP is replaced by src/test/mockApi.js. These tests check the AI,
// Action Center, Hub and Insights screens and the requests they send.
vi.mock("../services/api.js", async () => {
  const { mockApi } = await import("../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

beforeEach(() => {
  resetApi();
  emptyBackend();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  on("get", "/projects", [{ _id: "p1", name: "Tower A", status: "active" }]);
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
});

describe("site assistant", () => {
  it("blocks questions when Claude is selected but not enabled", async () => {
    on("get", "/ai/status", { configured: false, chat_available: false, can_query: true });
    renderApp("/ai/ask", USERS.manager);
    expect(await screen.findByText(/not available/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Ask the assistant")).toBeDisabled();
  });

  it("works in free quick-answer mode without any API key", async () => {
    on("get", "/ai/status", { configured: false, chat_available: true, chat_engine: "Quick answers (no AI model)", chat_provider: "quick" });
    renderApp("/ai/ask", USERS.manager);
    expect(await screen.findByText("Quick answers (no AI model)")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask the assistant")).toBeEnabled();
  });

  it("sends a question and shows the answer, tools used and a refused tool", async () => {
    on("get", "/ai/status", { configured: true, can_query: true });
    on("get", "/ai/suggested-questions", ["What needs attention at my sites today?"]);
    on("post", "/ai/assistant/chat", {
      conversation_id: "c1", answer: "- Podium slab is 16 days late\n- Cement short by 150 bags", error: null, notice: null,
      tools: [{ name: "get_upcoming_deadlines", label: "Checking deadlines", ok: true }, { name: "get_budget_summary", label: "Checking budgets", ok: false }],
      sources: [{ type: "milestone", id: "m1", label: "Podium slab" }],
    });
    const user = userEvent.setup();
    renderApp("/ai/ask", USERS.manager);
    await user.click(await screen.findByRole("button", { name: "What needs attention at my sites today?" }));
    expect(await screen.findByText("Podium slab is 16 days late")).toBeInTheDocument();
    expect(screen.getByText("Checking deadlines")).toBeInTheDocument();
    expect(screen.getByText(/Checking budgets.*not permitted/)).toBeInTheDocument();
    expect(callsTo("post", "/ai/assistant/chat")[0].body).toEqual({ message: "What needs attention at my sites today?", conversation_id: undefined });
  });

  it("shows a service error instead of an answer", async () => {
    on("get", "/ai/status", { configured: true });
    on("post", "/ai/assistant/chat", { conversation_id: "c1", answer: "", error: "The AI service is busy. Please try again in a minute.", tools: [], sources: [] });
    const user = userEvent.setup();
    renderApp("/ai/ask", USERS.manager);
    await user.type(await screen.findByLabelText("Ask the assistant"), "hello{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("The AI service is busy");
  });

  it("renders the deterministic overview", async () => {
    on("get", "/ai/overview", { sections: [{ key: "shortages", title: "Material shortages", items: [{ title: "Cement short by 150 bags", detail: "600 required - 350 available - 100 confirmed incoming", severity: "high", type: "inventory_item", id: "i1" }] }] });
    renderApp("/ai", USERS.manager);
    expect(await screen.findByText("Cement short by 150 bags")).toBeInTheDocument();
    expect(screen.getByText(/600 required - 350 available/)).toBeInTheDocument();
  });

  it("hides the Action Center and Reports from a worker", async () => {
    renderApp("/ai", USERS.worker);
    const nav = await screen.findByRole("navigation", { name: "Site Assistant sections" });
    expect(within(nav).queryByText("Action Center")).not.toBeInTheDocument();
    expect(within(nav).getByText("Ask AI")).toBeInTheDocument();
  });
});

describe("action center", () => {
  const rec = (overrides) => ({ _id: "r1", title: "Raise a material request for 150 bags Cement", rationale: "Projected shortfall 150.", status: "proposed", priority: "high", created_by: "system",
    action: { type: "create_material_request", params: { quantity: 150, unit: "bags", material_name: "Cement" } }, created_at: new Date().toISOString(), ...overrides });

  it("approves a system recommendation and explains what approval does", async () => {
    on("get", "/recommendations", [rec()]);
    on("post", "/recommendations/r1/decision", rec({ status: "executed", execution_result: { request_id: "MR-00009" } }));
    const user = userEvent.setup();
    renderApp("/ai/actions", USERS.manager);
    expect(await screen.findByText(/still needs procurement approval/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(callsTo("post", "/recommendations/r1/decision")[0].body).toEqual({ decision: "approve", note: undefined }));
  });

  it("does not offer approval of your own proposal", async () => {
    on("get", "/recommendations", [rec({ created_by: USERS.manager.id, action: { type: "manual", params: { instruction: "Plan a night shift" } } })]);
    renderApp("/ai/actions", USERS.manager);
    expect(await screen.findByText(/Awaiting approval by someone else/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("requires a reason to reject", async () => {
    on("get", "/recommendations", [rec()]);
    const user = userEvent.setup();
    renderApp("/ai/actions", USERS.manager);
    await user.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Reject" })).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Reason (required)"), "Stock arriving from other site");
    expect(within(dialog).getByRole("button", { name: "Reject" })).toBeEnabled();
  });
});

describe("innovation & safety hub", () => {
  it("submits an urgent anonymous safety report and reports the escalation", async () => {
    on("post", "/hub/safety/reports", ({ body }) => ({ _id: "s1", ...body, status: "open", escalated_to_count: 2 }));
    const user = userEvent.setup();
    renderApp("/hub/safety", USERS.worker);
    await user.click(await screen.findByRole("button", { name: /Report a safety issue/ }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Severity"), "urgent");
    await user.type(within(dialog).getByLabelText("Short title"), "Open lift shaft");
    await user.type(within(dialog).getByLabelText("What did you see or what happened?"), "No barrier around the shaft on level 3.");
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(within(dialog).getByRole("button", { name: "Submit report" }));
    expect(await screen.findByText(/escalated to 2 responsible person/)).toBeInTheDocument();
    const body = callsTo("post", "/hub/safety/reports")[0].body;
    expect(body).toMatchObject({ severity: "urgent", anonymous: true, title: "Open lift shaft" });
  });

  it("lets a worker submit a suggestion with their own words", async () => {
    on("post", "/hub/suggestions", ({ body }) => ({ _id: "g1", ...body, status: "submitted", related: [] }));
    const user = userEvent.setup();
    renderApp("/hub", USERS.worker);
    await user.click(await screen.findByRole("button", { name: /New suggestion/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Title"), "Reuse formwork");
    await user.type(within(dialog).getByLabelText("What is the problem?"), "Plywood is thrown away after two uses.");
    await user.type(within(dialog).getByLabelText("What do you propose?"), "Use aluminium formwork for typical floors.");
    await user.click(within(dialog).getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(callsTo("post", "/hub/suggestions")).toHaveLength(1));
    expect(callsTo("post", "/hub/suggestions")[0].body).toMatchObject({ title: "Reuse formwork", category: "productivity" });
  });
});

describe("insights", () => {
  it("shows rule-based risks with their factors", async () => {
    on("get", "/intelligence/risks", [{ _id: "k1", project_name: "Tower A", category: "schedule", rule: "overdue_milestones", level: "high", status: "active", review_status: "open",
      factors: ["Podium slab is 16 day(s) past its due date"], recommended_action: "Review the late milestones.", sources: [] }]);
    renderApp("/insights", USERS.manager);
    expect(await screen.findByText("Podium slab is 16 day(s) past its due date")).toBeInTheDocument();
    expect(screen.getByText(/No probabilities are estimated/)).toBeInTheDocument();
  });

  it("hides the budget tab from a site engineer", async () => {
    renderApp("/insights", USERS.engineer);
    const nav = await screen.findByRole("navigation", { name: "Insight sections" });
    expect(within(nav).queryByText("Budget")).not.toBeInTheDocument();
  });
});
