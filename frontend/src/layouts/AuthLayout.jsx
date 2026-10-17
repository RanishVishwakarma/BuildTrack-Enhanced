import { Outlet } from "react-router-dom";
import { AuthPage } from "../components/ui/AuthPage.jsx";

// Sign in, register and password reset share the split-screen auth design.
export function AuthLayout() {
  return (
    <AuthPage>
      <Outlet />
    </AuthPage>
  );
}
