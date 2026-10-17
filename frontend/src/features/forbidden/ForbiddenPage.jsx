import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "../../components/ui/Button.jsx";
import { getHomeRoute } from "../../lib/roles.js";
import { useAuth } from "../auth/context/AuthContext.jsx";

export function ForbiddenPage() {
  const { user } = useAuth();
  return (
    <div className="card mx-auto max-w-xl text-center">
      <ShieldAlert className="mx-auto h-10 w-10 text-danger" />
      <h1 className="mt-4 text-2xl font-bold">Access denied</h1>
      <p className="mt-2 text-sm text-muted">
        Your role ({user?.role || "unknown"}) does not have permission to open this page.
      </p>
      <Button as={Link} className="mt-6" to={getHomeRoute(user)}>Go to my home page</Button>
    </div>
  );
}
