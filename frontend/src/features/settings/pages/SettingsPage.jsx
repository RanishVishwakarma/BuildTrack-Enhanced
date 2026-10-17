import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { SearchInput } from "../../../components/common/SearchInput.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { TabNav } from "../../../components/common/TabNav.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { ALL_ROLES, can, hasPermission } from "../../../lib/roles.js";
import { formatDateTime, matchesSearch } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { AccessTab, AuditTab, CommunicationTab, MonitoringTab } from "../components/AdminTabs.jsx";
import { changePassword, deleteUser, getUsers, normalizeUser, setUserStatus, updateProfile, updateUser } from "../../auth/services/authService.js";

// PUT /auth/profile (the handler FastAPI resolves first) accepts full_name,
// phone and avatar_url only; email changes are not supported there.
const profileSchema = z.object({
  full_name: z.string().trim().min(2, "Name must be at least 2 characters."),
  phone: z.string().optional(),
  avatar_url: z.union([z.literal(""), z.string().trim().url("Enter a valid image URL.")]).optional(),
});
const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
    new_password: z.string().min(6, "New password must be at least 6 characters."),
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, { message: "Passwords do not match.", path: ["confirm_password"] });

function ProfileTab() {
  const { user, updateSessionUser } = useAuth();
  const { run, pending } = useAction();
  const profile = useForm({ resolver: zodResolver(profileSchema), defaultValues: { full_name: user?.name || "", phone: user?.phone || "", avatar_url: user?.avatarUrl || "" } });
  const password = useForm({ resolver: zodResolver(passwordSchema), defaultValues: { current_password: "", new_password: "", confirm_password: "" } });

  const saveProfile = profile.handleSubmit(async (values) => {
    const payload = { full_name: values.full_name.trim(), phone: values.phone || undefined, avatar_url: values.avatar_url || undefined };
    const result = await run("profile", () => updateProfile(payload), { success: "Profile updated.", error: "Unable to update profile." });
    if (result) {
      const saved = normalizeUser(result.user || result, user?.workerId);
      updateSessionUser({ name: saved.name, avatarUrl: saved.avatarUrl, phone: (result.user || result).phone }, result.access_token);
    }
  });

  const savePassword = password.handleSubmit(async (values) => {
    const result = await run("password", () => changePassword(values.current_password, values.new_password), { success: "Password changed.", error: "Unable to change password." });
    if (result) password.reset();
  });

  const pErr = profile.formState.errors;
  const pwErr = password.formState.errors;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form className="card space-y-4" noValidate onSubmit={saveProfile}>
        <h2 className="text-lg font-semibold">Profile</h2>
        <Input label="Full name" {...profile.register("full_name")} error={pErr.full_name?.message} />
        <Input disabled label="Email" value={user?.email || ""} />
        <Input disabled label="Role" value={user?.role || ""} />
        <Input label="Phone" type="tel" {...profile.register("phone")} />
        <Input label="Avatar image URL" {...profile.register("avatar_url")} error={pErr.avatar_url?.message} />
        <Button disabled={Boolean(pending)} type="submit">{pending === "profile" ? "Saving..." : "Save profile"}</Button>
      </form>
      <form className="card space-y-4" noValidate onSubmit={savePassword}>
        <h2 className="text-lg font-semibold">Change password</h2>
        <Input autoComplete="current-password" label="Current password" type="password" {...password.register("current_password")} error={pwErr.current_password?.message} />
        <Input autoComplete="new-password" label="New password" type="password" {...password.register("new_password")} error={pwErr.new_password?.message} />
        <Input autoComplete="new-password" label="Confirm new password" type="password" {...password.register("confirm_password")} error={pwErr.confirm_password?.message} />
        <Button disabled={Boolean(pending)} type="submit">{pending === "password" ? "Updating..." : "Update password"}</Button>
      </form>
    </div>
  );
}

function EditUserModal({ target, onClose, onSaved }) {
  const { run, pending } = useAction();
  const [values, setValues] = useState({ name: target?.name || "", email: target?.email || "", role: target?.role || "Worker" });

  async function submit(event) {
    event.preventDefault();
    const result = await run("save", () => updateUser(target.id, values), { success: "User updated.", error: "Unable to update user." });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="edit-user-form" type="submit">{pending ? "Saving..." : "Save"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(target)}
      size="sm"
      title={`Edit ${target?.email || "user"}`}
    >
      <form className="space-y-4" id="edit-user-form" onSubmit={submit}>
        <Input label="Full name" value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} />
        <Input label="Email" type="email" value={values.email} onChange={(event) => setValues({ ...values, email: event.target.value })} />
        <Select label="Role" value={values.role} onChange={(event) => setValues({ ...values, role: event.target.value })}>
          {ALL_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
        </Select>
      </form>
    </Modal>
  );
}

function UsersTab() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useAsyncData(getUsers, [], { initialData: [] });
  const { run } = useAction();
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [editing, setEditing] = useState(null);
  const rows = (data || []).filter((item) => matchesSearch([item.name, item.email, item.role], query) && (!role || item.role === role));
  const isSelf = (item) => item.id === user?.id || item.email === user?.email;

  async function toggle(item) {
    const next = String(item.status).toLowerCase() === "suspended" ? "active" : "suspended";
    if (!confirmAction(`${next === "active" ? "Reactivate" : "Suspend"} ${item.email}?`)) return;
    await run(`status-${item.id}`, () => setUserStatus(item.id, next), { success: `User ${next === "active" ? "reactivated" : "suspended"}.`, error: "Unable to change user status.", onSuccess: reload });
  }

  async function remove(item) {
    if (!confirmAction(`Remove ${item.email}? Their email will be blocked from registering again.`)) return;
    await run("delete", () => deleteUser(item.id, true), { success: "User removed.", error: "Unable to remove user.", onSuccess: reload });
  }

  if (loading) return <LoadingState label="Loading users..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;
  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="sm:col-span-2"><SearchInput aria-label="Search users" placeholder="Search name or email..." value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <Select aria-label="Filter by role" className="h-10" value={role} onChange={(event) => setRole(event.target.value)}>
          <option value="">All roles</option>
          {ALL_ROLES.map((value) => <option key={value} value={value}>{value}</option>)}
        </Select>
      </div>
      <DataTable
        columns={[
          { key: "name", header: "Name", render: (row) => <span className="font-semibold">{row.name}</span> },
          { key: "email", header: "Email" },
          { key: "role", header: "Role" },
          { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
          { key: "created", header: "Joined", render: (row) => formatDateTime(row.raw?.created_at) },
          {
            key: "actions",
            header: "Actions",
            render: (row) =>
              isSelf(row) ? <span className="text-sm text-muted">You</span> : (
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => setEditing(row)} size="sm" variant="secondary">Edit</Button>
                  <Button onClick={() => toggle(row)} size="sm" variant="secondary">{String(row.status).toLowerCase() === "suspended" ? "Reactivate" : "Suspend"}</Button>
                  <Button onClick={() => remove(row)} size="sm" variant="danger">Remove</Button>
                </div>
              ),
          },
        ]}
        emptyDescription="No users match the filters."
        emptyTitle="No users"
        getRowId={(row) => row.id}
        rows={rows}
      />
      <EditUserModal key={editing?.id || "none"} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} target={editing} />
    </>
  );
}

export function SettingsPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const tabs = [
    { key: "profile", label: "Profile & security", to: "/settings" },
    { key: "communication", label: "Communication", to: "/settings?tab=communication" },
    ...(can.adminOnly(user) ? [{ key: "users", label: "User management", to: "/settings?tab=users" }] : []),
    ...(hasPermission(user, "projects.access.manage", "users.roles.assign") ? [{ key: "access", label: "Access", to: "/settings?tab=access" }] : []),
    ...(hasPermission(user, "audit_logs.read") ? [{ key: "audit", label: "Audit log", to: "/settings?tab=audit" }] : []),
    ...(hasPermission(user, "monitoring.run") ? [{ key: "monitoring", label: "Monitoring", to: "/settings?tab=monitoring" }] : []),
  ];
  const tab = tabs.some((item) => item.key === params.get("tab")) ? params.get("tab") : "profile";

  return (
    <>
      <PageHeader title="Settings" description="Your profile and password. Administrators also manage user accounts here." />
      <TabNav active={tab} label="Settings sections" tabs={tabs} />
      {tab === "users" ? <UsersTab /> : null}
      {tab === "communication" ? <CommunicationTab /> : null}
      {tab === "access" ? <AccessTab /> : null}
      {tab === "audit" ? <AuditTab /> : null}
      {tab === "monitoring" ? <MonitoringTab /> : null}
      {tab === "profile" ? <ProfileTab /> : null}
    </>
  );
}
