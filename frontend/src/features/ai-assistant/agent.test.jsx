import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emptyBackend, on, resetApi } from "../../test/mockApi.js";
import { USERS, renderApp } from "../../test/renderApp.jsx";

// MOCKED: axios calls go to src/test/mockApi.js; the streaming chat uses
// fetch, which is replaced with a scripted NDJSON stream.
vi.mock("../../services/api.js", async () => {
  const { mockApi } = await import("../../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

const STATUS = {
  model: "gemma2:2b", reachable: true, model_available: true, embedder: "hashing-512", embed_model: "nomic-embed-text",
  chunks: 12, can_index: true, graph: "",
  specialists: [{ name: "procurement", label: "Procurement agent", tools: ["a", "b"] }, { name: "schedule", label: "Schedule agent", tools: ["c"] }],
};

const EVENTS = [
  { type: "step", step: { type: "route", agents: ["Procurement agent", "Schedule agent"], reason: "Order and schedule.", fallback: false } },
  { type: "step", step: { type: "tool", agent: "Procurement agent", tool: "get_authorized_procurement_status", label: "Checking procurement", input: { project_id: null }, thought: "Check orders." } },
  { type: "step", step: { type: "error", agent: "Schedule agent", message: "'kind' must be one of ['purchase_order', 'task']." } },
  { type: "step", step: { type: "check", ok: false, missing: ["999"], retry: true } },
  { type: "step", step: { type: "check", ok: true } },
  { type: "final", answer: "PO-0007 is late.\n\n- Slab casting depends on it", verified: true, route: ["procurement", "schedule"], sources: [{ type: "purchase_order", id: "po7", label: "PO-0007" }], tools: [], steps: [] },
  { type: "saved", conversation_id: "c1", run_id: "r1" },
];

function streamOf(events) {
  const chunks = events.map((e) => new TextEncoder().encode(`${JSON.stringify(e)}\n`));
  return { getReader: () => ({ read: async () => (chunks.length ? { value: chunks.shift(), done: false } : { value: undefined, done: true }) }) };
}

beforeEach(() => {
  resetApi();
  emptyBackend();
  on("get", "/ai/status", { chat_available: true });
  on("get", "/ai/agent/status", STATUS);
});

afterEach(() => vi.unstubAllGlobals());

describe("Agent mode", () => {
  it("streams the agents' steps live and shows the verified answer", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, body: streamOf(EVENTS) }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/ai/agent", USERS.manager);

    expect(await screen.findByText("Procurement agent")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your question"), "Will the cement order delay Tower A?");
    await user.click(screen.getByRole("button", { name: "Ask the agents" }));

    expect(await screen.findByText("Supervisor routed to Procurement agent + Schedule agent")).toBeInTheDocument();
    expect(screen.getByText("Procurement agent: Checking procurement")).toBeInTheDocument();
    expect(screen.getByText("Schedule agent: invalid step rejected, asked again")).toBeInTheDocument();
    expect(screen.getByText("Checker: figures not found in records, sent back to the writer")).toBeInTheDocument();
    expect(await screen.findByText("Verified against your records")).toBeInTheDocument();
    expect(screen.getByText("PO-0007 is late.")).toBeInTheDocument();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/ai/agent/chat");
    expect(JSON.parse(init.body)).toEqual({ message: "Will the cement order delay Tower A?" });
  });

  it("is hidden from roles without the Agent mode permission", async () => {
    renderApp("/ai/ask", USERS.worker);
    expect((await screen.findAllByRole("link", { name: "Ask AI" })).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Agent mode" })).not.toBeInTheDocument();
  });

  it("blocks opening the Agent mode page directly without the permission", async () => {
    renderApp("/ai/agent", USERS.worker);
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Your question")).not.toBeInTheDocument();
  });

  it("explains when Ollama is not running", async () => {
    on("get", "/ai/agent/status", { ...STATUS, reachable: false, model_available: false });
    renderApp("/ai/agent", USERS.manager);
    expect(await screen.findByText("Start Ollama on this computer to use agent mode.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Your question")).toBeDisabled());
  });
});
