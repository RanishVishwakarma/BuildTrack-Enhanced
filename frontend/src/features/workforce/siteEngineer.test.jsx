import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { emptyBackend, on, resetApi } from "../../test/mockApi.js";
import { USERS, renderApp } from "../../test/renderApp.jsx";

// MOCKED: HTTP is replaced by src/test/mockApi.js.
vi.mock("../../services/api.js", async () => {
  const { mockApi } = await import("../../test/mockApi.js");
  return { default: mockApi, API_BASE_URL: "http://api.test/api/v1" };
});

beforeEach(() => {
  resetApi();
  emptyBackend();
  on("get", "/workforce/workers", [{ _id: "w1", first_name: "Ann", last_name: "A", status: "assigned", project_id: "p1" }]);
  on("get", "/workforce/attendance", []);
  on("get", "/workforce/shifts", [{ _id: "s1", name: "Day shift", start_time: "08:00", end_time: "17:00", status: "ACTIVE" }]);
  on("get", "/workforce/shift-assignments", []);
});

// Hierarchy: site engineers run their crew (attendance, shifts) without pay.
describe("site engineer", () => {
  it("can mark attendance on the daily roster", async () => {
    renderApp("/attendance", USERS.engineer);
    const row = (await screen.findAllByRole("row")).find((r) => r.textContent.includes("Ann A"));
    expect(within(row).getByRole("button", { name: "Present" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark all present" })).toBeInTheDocument();
  });

  it("can assign workers to shifts but not create shifts", async () => {
    renderApp("/workers/shift-scheduling", USERS.engineer);
    expect(await screen.findByRole("button", { name: "Assign worker" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /new shift/i })).not.toBeInTheDocument();
  });
});
