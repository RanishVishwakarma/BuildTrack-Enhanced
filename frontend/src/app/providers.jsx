import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../features/auth/context/AuthContext.jsx";

export function AppProviders({ children }) {
  return (
    <BrowserRouter>
      <AuthProvider>{children}</AuthProvider>
    </BrowserRouter>
  );
}
