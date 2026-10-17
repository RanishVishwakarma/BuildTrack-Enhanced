import { Link, useLocation } from "react-router-dom";
import { Button } from "../../components/ui/Button.jsx";
import { getHomeRoute } from "../../lib/roles.js";
import { useAuth } from "../auth/context/AuthContext.jsx";

export function NotFoundPage() {
  const { user } = useAuth();
  const location = useLocation();
  return (
    <div className="card mx-auto max-w-xl text-center">
      <p className="text-sm font-semibold text-primary">404</p>
      <h1 className="mt-2 text-2xl font-bold">Page not found</h1>
      <p className="mt-2 break-words text-sm text-muted">
        <code>{location.pathname}</code> is not a BuildTrack page.
      </p>
      <Button as={Link} className="mt-6" to={getHomeRoute(user)}>Go to my home page</Button>
    </div>
  );
}
