import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "react-hot-toast";
import { AppProviders } from "./app/providers.jsx";
import { App } from "./app/App.jsx";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AppProviders>
      <App />
      <Toaster position="top-right" />
    </AppProviders>
  </React.StrictMode>,
);
