import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../features/auth/context/AuthContext.jsx";
import { canOpenRoute, getHomeRoute } from "../lib/roles.js";
import { getRoute } from "./routeConfig.js";

export function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) return <Navigate replace to="/auth/login" state={{ from: location }} />;
  return children;
}

// Sign-in pages are pointless for an active session; send the user home instead.
export function GuestRoute({ children }) {
  const { isAuthenticated, user } = useAuth();
  if (isAuthenticated) return <Navigate replace to={getHomeRoute(user)} />;
  return children;
}

// Enforces the per-route role list from routeConfig, so typing a URL by hand
// cannot open a page the user's role is not allowed to see.
export function RoleRoute({ path, children }) {
  const { user, profilePending } = useAuth();
  const route = getRoute(path);
  if (!route) throw new Error(`Route ${path} is missing from routeConfig.js`);
  if (!canOpenRoute(user, route)) {
    // Wait for the profile refresh before denying: the stored session may
    // predate a permission the user has since been granted.
    if (profilePending) return <div className="p-6 text-sm text-muted" role="status">Loading...</div>;
    return <Navigate replace to="/forbidden" state={{ from: path }} />;
  }
  return children;
}
