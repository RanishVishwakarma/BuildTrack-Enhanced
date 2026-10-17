import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { PasswordInput } from "../../../components/ui/PasswordInput.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { getId, workerName } from "../../../lib/utils.js";
import { createWorkerLogin, linkWorkerLogin, resetWorkerPassword, unlinkWorkerLogin } from "../services/workforceService.js";

const passwordFields = {
  password: z.string().min(8, "Password must be at least 8 characters."),
  confirmPassword: z.string(),
};
const matching = [(values) => values.password === values.confirmPassword, { message: "Passwords do not match.", path: ["confirmPassword"] }];
const schemas = {
  create: z.object({ email: z.string().trim().email("Enter a valid email."), ...passwordFields }).refine(...matching),
  link: z.object({ email: z.string().trim().email("Enter a valid email.") }),
  reset: z.object(passwordFields).refine(...matching),
};

// The login is tied to this worker record by id (users.worker_id), so the
// worker sees only their own tasks, attendance and pay.
export function WorkerLoginModal({ worker, onClose, onSaved }) {
  const hasLogin = Boolean(worker?.login_email);
  const [mode, setMode] = useState(hasLogin ? "reset" : "create");
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(schemas[mode]),
    values: worker ? { email: worker.email || "", password: "", confirmPassword: "" } : undefined,
  });
  const errors = form.formState.errors;
  const id = getId(worker);

  const submit = form.handleSubmit(async ({ email, password }) => {
    const actions = {
      create: () => createWorkerLogin(id, { email, password }),
      link: () => linkWorkerLogin(id, email),
      reset: () => resetWorkerPassword(id, password),
    };
    const result = await run("login", actions[mode], { success: (response) => response?.message, error: "Unable to update the login." });
    if (result) onSaved();
  });

  async function unlink() {
    if (!confirmAction(`Unlink ${worker.login_email} from ${workerName(worker)}? The account stays, but loses access to this worker's records.`)) return;
    const result = await run("unlink", () => unlinkWorkerLogin(id), { success: (response) => response?.message, error: "Unable to unlink the login." });
    if (result) onSaved();
  }

  const submitLabel = { create: "Create login", link: "Link account", reset: "Reset password" }[mode];

  return (
    <Modal
      footer={
        <>
          {hasLogin ? <Button className="me-auto" disabled={Boolean(pending)} onClick={unlink} variant="danger">Unlink</Button> : null}
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="worker-login-form" type="submit">{pending ? "Saving..." : submitLabel}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(worker)}
      title={`Login for ${workerName(worker)}`}
    >
      <form className="grid gap-4" id="worker-login-form" noValidate onSubmit={submit}>
        {hasLogin ? (
          <p className="text-sm text-muted">
            Signs in as <span className="font-semibold text-foreground">{worker.login_email}</span>. Set a new password and share it with the worker privately.
          </p>
        ) : (
          <>
            <div className="flex gap-2" role="group" aria-label="Login type">
              <Button aria-pressed={mode === "create"} onClick={() => setMode("create")} type="button" size="sm" variant={mode === "create" ? "primary" : "secondary"}>New login</Button>
              <Button aria-pressed={mode === "link"} onClick={() => setMode("link")} type="button" size="sm" variant={mode === "link" ? "primary" : "secondary"}>Link existing account</Button>
            </div>
            <p className="text-sm text-muted">
              {mode === "create"
                ? "The worker signs in with this email to see their own tasks, attendance and pay."
                : "Use this when the worker already signed up. Check it is really their account before linking."}
            </p>
            <Input label={mode === "create" ? "Login email" : "Email of their account"} type="email" {...form.register("email")} error={errors.email?.message} />
          </>
        )}
        {mode !== "link" ? (
          <>
            <PasswordInput autoComplete="new-password" label={hasLogin ? "New password" : "Password"} {...form.register("password")} error={errors.password?.message} />
            <PasswordInput autoComplete="new-password" label="Confirm password" {...form.register("confirmPassword")} error={errors.confirmPassword?.message} />
          </>
        ) : null}
      </form>
    </Modal>
  );
}
