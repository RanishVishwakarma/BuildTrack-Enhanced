import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { AtSign, KeyRound, LockKeyhole } from "lucide-react";
import { AuthHeading } from "../../../components/ui/AuthPage.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { confirmPasswordReset, requestPasswordReset } from "../services/authService.js";

const requestSchema = z.object({ email: z.string().email("Enter a valid email.") });
const confirmSchema = z
  .object({
    email: z.string().email("Enter a valid email."),
    token: z.string().min(1, "Enter the reset token you received."),
    new_password: z.string().min(8, "Password must be at least 8 characters."),
    confirm: z.string(),
  })
  .refine((values) => values.new_password === values.confirm, { message: "Passwords do not match.", path: ["confirm"] });

export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [sentMessage, setSentMessage] = useState("");
  const requestForm = useForm({ resolver: zodResolver(requestSchema), defaultValues: { email: "" } });
  const confirmForm = useForm({ resolver: zodResolver(confirmSchema), defaultValues: { email: "", token: "", new_password: "", confirm: "" } });

  const submitRequest = requestForm.handleSubmit(async ({ email }) => {
    try {
      const response = await requestPasswordReset(email);
      setSentMessage(response?.message || "If an account exists for that email, a reset link has been generated.");
      confirmForm.setValue("email", email);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Unable to request a password reset."));
    }
  });

  const submitConfirm = confirmForm.handleSubmit(async ({ email, token, new_password: newPassword }) => {
    try {
      await confirmPasswordReset({ email, token, new_password: newPassword });
      toast.success("Password updated. Sign in with your new password.");
      navigate("/auth/login", { replace: true });
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Unable to reset password."));
    }
  });

  return (
    <>
      <AuthHeading title="Reset password" description="Request a reset token for your account, then set a new password." />
      <form className="space-y-3" noValidate onSubmit={submitRequest}>
        <Input autoComplete="email" error={requestForm.formState.errors.email?.message} icon={AtSign} label="Email address" placeholder="your.email@example.com" type="email" {...requestForm.register("email")} />
        <Button className="w-full" disabled={requestForm.formState.isSubmitting} size="lg" type="submit">
          {requestForm.formState.isSubmitting ? "Sending..." : "Request reset"}
        </Button>
      </form>
      {sentMessage ? <p className="rounded-md border border-border bg-subtle p-3 text-sm text-foreground" role="status">{sentMessage}</p> : null}
      <details className="rounded-md border border-border p-4" open={Boolean(sentMessage)}>
        <summary className="cursor-pointer text-sm font-semibold">I have a reset token</summary>
        <form className="mt-4 space-y-3" noValidate onSubmit={submitConfirm}>
          <Input icon={AtSign} label="Email address" type="email" {...confirmForm.register("email")} error={confirmForm.formState.errors.email?.message} />
          <Input icon={KeyRound} label="Reset token" autoComplete="one-time-code" {...confirmForm.register("token")} error={confirmForm.formState.errors.token?.message} />
          <Input icon={LockKeyhole} label="New password" type="password" autoComplete="new-password" {...confirmForm.register("new_password")} error={confirmForm.formState.errors.new_password?.message} />
          <Input icon={LockKeyhole} label="Confirm new password" type="password" autoComplete="new-password" {...confirmForm.register("confirm")} error={confirmForm.formState.errors.confirm?.message} />
          <Button className="w-full" disabled={confirmForm.formState.isSubmitting} type="submit">
            {confirmForm.formState.isSubmitting ? "Updating..." : "Set new password"}
          </Button>
        </form>
      </details>
      <p className="text-sm text-muted">
        Remembered it? <Link className="font-semibold text-foreground underline-offset-4 hover:underline" to="/auth/login">Sign in</Link>
      </p>
    </>
  );
}
