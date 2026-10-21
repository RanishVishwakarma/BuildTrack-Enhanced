import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { callsTo, emptyBackend, on, resetApi } from "../../test/mockApi.js";
import { USERS, renderApp } from "../../test/renderApp.jsx";

// MOCKED: HTTP is replaced by src/test/mockApi.js.
vi.mock("../../services/api.js", async () => {
  const { mockApi } = await import("../../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

beforeEach(() => {
  resetApi();
  emptyBackend();
});

describe("My Schedule (worker)", () => {
  it("lists the worker's own shifts with their times", async () => {
    on("get", "/workforce/shifts", [{ _id: "s1", name: "Morning", start_time: "08:00", end_time: "16:00", status: "ACTIVE" }]);
    on("get", "/workforce/shift-assignments", [{ _id: "a1", worker_id: "w1", shift_id: "s1", date: "2026-10-20T00:00:00", status: "ACTIVE" }]);
    renderApp("/workers/shift-scheduling", USERS.worker);

    expect(await screen.findByRole("heading", { name: "My Schedule" })).toBeInTheDocument();
    expect(await screen.findByText(/Morning/)).toBeInTheDocument();
    expect(callsTo("get", "/workforce/shift-assignments")[0].params).toMatchObject({ worker_id: "w1" });
  });

  it("explains an unlinked login instead of failing", async () => {
    renderApp("/workers/shift-scheduling", { ...USERS.worker, workerId: null });
    expect(await screen.findByText(/Ask your project manager to link it on the Workers page/)).toBeInTheDocument();
    expect(callsTo("get", "/workforce/shifts")).toHaveLength(0);
  });
});
