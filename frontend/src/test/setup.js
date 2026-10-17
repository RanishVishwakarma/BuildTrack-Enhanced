import "@testing-library/jest-dom";
import { afterEach } from "vitest";
import { cleanup, configure } from "@testing-library/react";
import toast from "react-hot-toast";

// Pages are lazily loaded; the first import in a file is transformed on demand,
// which can take several seconds when test files run in parallel.
configure({ asyncUtilTimeout: 15000 });

// Recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// react-hot-toast checks prefers-reduced-motion through matchMedia.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false,
  });
}

afterEach(() => {
  cleanup();
  // react-hot-toast keeps toasts in a module-level store shared across tests.
  toast.remove();
});
