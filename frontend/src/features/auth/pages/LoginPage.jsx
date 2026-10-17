import { zodResolver } from "@hookform/resolvers/zod";
import { AtSign, LockKeyhole } from "lucide-react";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthHeading, AuthSeparator } from "../../../components/ui/AuthPage.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { PasswordInput } from "../../../components/ui/PasswordInput.jsx";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { getHomeRoute } from "../../../lib/roles.js";
import { useAuth } from "../context/AuthContext.jsx";
import { loginSchema } from "../schemas/authSchemas.js";

export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const form = useForm({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });
  const errors = form.formState.errors;

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const session = await signIn(values);
      toast.success("Signed in successfully.");
      const from = location.state?.from;
      navigate(from ? `${from.pathname}${from.search || ""}` : getHomeRoute(session.user), { replace: true });
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Unable to sign in."));
    }
  });

  return (
    <>
      <AuthHeading title="Welcome back" description="Sign in to your BuildTrack account." />
      <form className="space-y-3" noValidate onSubmit={onSubmit}>
        <Input
          autoComplete="email"
          error={errors.email?.message}
          icon={AtSign}
          label="Email address"
          placeholder="your.email@example.com"
          type="email"
          {...form.register("email")}
        />
        <PasswordInput
          autoComplete="current-password"
          error={errors.password?.message}
          icon={LockKeyhole}
          label="Password"
          placeholder="Your password"
          {...form.register("password")}
        />
        <div className="text-right">
          <Link className="text-sm font-semibold text-foreground underline-offset-4 hover:underline" to="/auth/forgot-password">Forgot password?</Link>
        </div>
        <Button className="w-full" disabled={form.formState.isSubmitting} size="lg" type="submit">
          {form.formState.isSubmitting ? "Signing in..." : "Sign in"}
        </Button>
      </form>
      <AuthSeparator label="NEW HERE?" />
      <Button as={Link} className="w-full" size="lg" to="/auth/register" variant="secondary">
        Create an account
      </Button>
    </>
  );
}
