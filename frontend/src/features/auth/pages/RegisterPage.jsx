import { zodResolver } from "@hookform/resolvers/zod";
import { AtSign, LockKeyhole, ShieldCheck, UserRound } from "lucide-react";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { Link, useNavigate } from "react-router-dom";
import { AuthHeading, AuthSeparator } from "../../../components/ui/AuthPage.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { PasswordInput } from "../../../components/ui/PasswordInput.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { REGISTRATION_ROLES } from "../../../lib/constants.js";
import { getHomeRoute } from "../../../lib/roles.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../context/AuthContext.jsx";
import { registerSchema } from "../schemas/authSchemas.js";

export function RegisterPage() {
  const { signUp } = useAuth();
  const navigate = useNavigate();
  const form = useForm({ resolver: zodResolver(registerSchema), defaultValues: { fullName: "", email: "", password: "", confirmPassword: "", role: "Worker" } });
  const errors = form.formState.errors;

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const session = await signUp(values);
      toast.success("Account created.");
      navigate(getHomeRoute(session.user), { replace: true });
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Unable to create account."));
    }
  });

  return (
    <>
      <AuthHeading title="Create your account" description="Join your team on BuildTrack." />
      <form className="space-y-3" noValidate onSubmit={onSubmit}>
        <Input autoComplete="name" error={errors.fullName?.message} icon={UserRound} label="Full name" placeholder="Your full name" {...form.register("fullName")} />
        <Input autoComplete="email" error={errors.email?.message} icon={AtSign} label="Email address" placeholder="your.email@example.com" type="email" {...form.register("email")} />
        <PasswordInput autoComplete="new-password" error={errors.password?.message} icon={LockKeyhole} label="Password" placeholder="At least 8 characters" {...form.register("password")} />
        <PasswordInput autoComplete="new-password" error={errors.confirmPassword?.message} icon={ShieldCheck} label="Confirm password" placeholder="Type the password again" {...form.register("confirmPassword")} />
        <Select label="Role" {...form.register("role")} error={errors.role?.message}>
          {REGISTRATION_ROLES.map((role) => <option key={role}>{role}</option>)}
        </Select>
        <Button className="w-full" disabled={form.formState.isSubmitting} size="lg" type="submit">
          {form.formState.isSubmitting ? "Creating account..." : "Create account"}
        </Button>
      </form>
      <p className="text-xs text-muted">Vendor accounts are created by an administrator from the Vendors page.</p>
      <AuthSeparator label="ALREADY REGISTERED?" />
      <Button as={Link} className="w-full" size="lg" to="/auth/login" variant="secondary">
        Sign in
      </Button>
    </>
  );
}
