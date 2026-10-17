import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppProviders } from "./providers.jsx";
import { App } from "./App.jsx";

describe("App", () => {
  it("renders the login route for unauthenticated users", () => {
    localStorage.clear();
    window.history.pushState({}, "", "/dashboard");
    render(
      <AppProviders>
        <App />
      </AppProviders>,
    );
    expect(screen.getByText(/welcome back/i)).toBeInTheDocument();
  });
});
