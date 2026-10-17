import { useState } from "react";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { hasPermission } from "../../../lib/roles.js";
import { formatDateTime, formatStatus, getId, projectName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getUsers } from "../../auth/services/authService.js";
import { getMonitoringRuns, runMonitoring } from "../../ai-assistant/services/aiService.js";
import {
  addProjectMember, getAuditLogs, getCallLogs, getPermissionRegistry, getProjectMembers, getUserPermissions, getVoicePreferences,
  removeProjectMember, setUserPermissions, setVoicePreferences,
} from "../services/accessService.js";

// Automated-call consent and phone number (spec §12).
export function CommunicationTab() {
  const prefs = useAsyncData(getVoicePreferences, []);
  const calls = useAsyncData(getCallLogs, [], { initialData: [] });
  const [phone, setPhone] = useState("");
  const { run, pending } = useAction();
  if (prefs.loading && !prefs.data) return <LoadingState />;
  if (prefs.error) return <ErrorState message={getApiErrorMessage(prefs.error)} onRetry={prefs.reload} />;
  const data = prefs.data;

  return (
    <div className="space-y-6">
      <section className="card max-w-2xl space-y-3">
        <h3 className="text-base font-semibold">Automated calls</h3>
        <p className="text-sm text-muted">
          If you consent, BuildTrack may call you about a critical alert you have not acknowledged, only between the configured calling hours.
          The call says it is an automated assistant; pressing 1 acknowledges the alert and pressing 2 asks your manager to call you. A call never
          changes a task, stock or order record. It is not a replacement for emergency services.
        </p>
        {!data.calls_enabled ? <p className="rounded bg-subtle px-3 py-2 text-xs text-muted">Calls are not switched on for this installation yet; your preference is saved for when they are.</p> : null}
        {!data.can_receive ? <p className="text-sm text-muted">Your role does not receive automated calls.</p> : (
          <>
            <p className="text-sm">Status: <StatusBadge status={data.voice_consent ? "active" : "inactive"} /> {data.phone ? `· number ending ${data.phone.slice(-4)}` : "· no number saved"}</p>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
              <Input label="Mobile number (international format, e.g. +919876543210)" onChange={(e) => setPhone(e.target.value)} pattern="^\+[1-9]\d{7,14}$" placeholder={data.phone || "+91..."} value={phone} />
              <div className="flex gap-2">
                <Button disabled={pending === "on" || (!phone && !data.phone)} onClick={() => run("on", () => setVoicePreferences(true, phone), { success: "Consent saved.", onSuccess: prefs.reload })}>Allow calls</Button>
                {data.voice_consent ? <Button disabled={pending === "off"} onClick={() => run("off", () => setVoicePreferences(false), { success: "Calls turned off.", onSuccess: prefs.reload })} variant="secondary">Stop calls</Button> : null}
              </div>
            </div>
          </>
        )}
      </section>
      {calls.data?.length ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold">Call log</h3>
          <DataTable
            columns={[
              { key: "created_at", header: "Queued", render: (c) => formatDateTime(c.created_at) },
              { key: "status", header: "Status", render: (c) => <StatusBadge status={c.status} /> },
              { key: "outcome", header: "Outcome", render: (c) => formatStatus(c.outcome || c.reason || "") },
              { key: "attempts", header: "Attempts" },
            ]}
            getRowId={(c) => c._id}
            rows={calls.data}
          />
        </section>
      ) : null}
    </div>
  );
}

// Project membership (admins and project managers) and per-user permission
// grants (administrators).
export function AccessTab() {
  const { user } = useAuth();
  const isAdmin = hasPermission(user, "users.roles.assign");
  const { projects } = useProjectOptions();
  const [projectId, setProjectId] = useState("");
  const members = useAsyncData(() => (projectId ? getProjectMembers(projectId) : []), [projectId], { initialData: [] });
  const users = useAsyncData(() => (isAdmin ? getUsers() : []), [isAdmin], { initialData: [] });
  const registry = useAsyncData(() => (isAdmin ? getPermissionRegistry() : null), [isAdmin]);
  const [newMember, setNewMember] = useState("");
  const [userId, setUserId] = useState("");
  const perms = useAsyncData(() => (userId ? getUserPermissions(userId) : null), [userId]);
  const [draft, setDraft] = useState(null);
  const { run, pending } = useAction();

  const current = draft || (perms.data ? { granted: perms.data.granted, revoked: perms.data.revoked } : null);
  function toggle(list, id) {
    const next = { ...current, [list]: current[list].includes(id) ? current[list].filter((p) => p !== id) : [...current[list], id] };
    setDraft(next);
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h3 className="text-base font-semibold">Project members</h3>
        <p className="text-sm text-muted">People see a project, its tasks and its records only when they are members (clients also see projects listing their email).</p>
        <div className="w-72">
          <Select aria-label="Project" onChange={(e) => setProjectId(e.target.value)} value={projectId}>
            <option value="">Choose a project</option>
            {projects.map((p) => <option key={getId(p)} value={getId(p)}>{projectName(p)}</option>)}
          </Select>
        </div>
        {projectId ? (
          <>
            {members.error ? <ErrorState message={getApiErrorMessage(members.error)} onRetry={members.reload} /> : (
              <DataTable
                columns={[
                  { key: "name", header: "Name", render: (m) => m.name || m.email },
                  { key: "role", header: "Role", render: (m) => formatStatus(m.role) },
                  { key: "reason", header: "Added because", render: (m) => m.reason || "" },
                  { key: "x", header: "", render: (m) => <Button onClick={() => confirmAction(`Remove ${m.name || m.email} from this project?`) && run("rm", () => removeProjectMember(projectId, m.user_id), { success: "Removed.", onSuccess: members.reload })} size="sm" variant="secondary">Remove</Button> },
                ]}
                emptyTitle="No members yet"
                getRowId={(m) => m.user_id}
                rows={members.data || []}
              />
            )}
            {isAdmin ? (
              <div className="flex flex-wrap items-end gap-2">
                <div className="w-72">
                  <Select aria-label="User to add" onChange={(e) => setNewMember(e.target.value)} value={newMember}>
                    <option value="">Add a user</option>
                    {(users.data || []).filter((u) => u.role !== "Vendor" && !(members.data || []).some((m) => m.user_id === u.id)).map((u) => <option key={u.id} value={u.id}>{u.name} ({u.role})</option>)}
                  </Select>
                </div>
                <Button disabled={!newMember || pending === "add"} onClick={() => run("add", () => addProjectMember(projectId, newMember), { success: "Added.", onSuccess: () => { setNewMember(""); members.reload(); } })}>Add</Button>
              </div>
            ) : <p className="text-xs text-muted">To add someone, ask an administrator or use their account id.</p>}
          </>
        ) : null}
      </section>

      {isAdmin ? (
        <section className="space-y-3">
          <h3 className="text-base font-semibold">Extra permissions for a user</h3>
          <p className="text-sm text-muted">Grant a duty (for example recording payments or receiving deliveries) without changing someone&apos;s role. Every change is audited. You cannot change your own permissions.</p>
          <div className="w-72">
            <Select aria-label="User" onChange={(e) => { setUserId(e.target.value); setDraft(null); }} value={userId}>
              <option value="">Choose a user</option>
              {(users.data || []).filter((u) => u.id !== user?.id).map((u) => <option key={u.id} value={u.id}>{u.name} ({u.role})</option>)}
            </Select>
          </div>
          {perms.loading && userId ? <LoadingState /> : null}
          {perms.data && registry.data && current ? (
            <>
              <div className="table-scroll max-h-[50vh] overflow-y-auto rounded-lg border border-border">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 bg-surface text-left"><tr><th className="px-3 py-2" scope="col">Permission</th><th className="px-3 py-2" scope="col">Role default</th><th className="px-3 py-2" scope="col">Grant</th><th className="px-3 py-2" scope="col">Revoke</th></tr></thead>
                  <tbody className="divide-y divide-border/70">
                    {registry.data.permissions.map((p) => {
                      const byRole = perms.data.role_defaults.includes(p.id);
                      return (
                        <tr key={p.id}>
                          <td className="px-3 py-1.5"><span className="font-mono text-xs">{p.id}</span><br /><span className="text-xs text-muted">{p.description}</span></td>
                          <td className="px-3 py-1.5 text-xs">{byRole ? "Yes" : ""}</td>
                          <td className="px-3 py-1.5">{!byRole ? <input aria-label={`Grant ${p.id}`} checked={current.granted.includes(p.id)} onChange={() => toggle("granted", p.id)} type="checkbox" /> : null}</td>
                          <td className="px-3 py-1.5">{byRole ? <input aria-label={`Revoke ${p.id}`} checked={current.revoked.includes(p.id)} onChange={() => toggle("revoked", p.id)} type="checkbox" /> : null}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Button disabled={!draft || pending === "perms"} onClick={() => run("perms", () => setUserPermissions(userId, current.granted, current.revoked), { success: "Permissions saved.", onSuccess: () => { setDraft(null); perms.reload(); } })}>Save permissions</Button>
            </>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

export function AuditTab() {
  const [eventType, setEventType] = useState("");
  const logs = useAsyncData(() => getAuditLogs({ event_type: eventType || undefined, limit: 200 }), [eventType], { initialData: [] });
  return (
    <div className="space-y-3">
      <div className="w-72"><Input aria-label="Filter by event type" onChange={(e) => setEventType(e.target.value.trim())} placeholder="Event type, e.g. user.role.changed" value={eventType} /></div>
      {logs.error ? <ErrorState message={getApiErrorMessage(logs.error)} onRetry={logs.reload} /> : (
        <DataTable
          columns={[
            { key: "timestamp", header: "When", render: (l) => formatDateTime(l.timestamp) },
            { key: "event_type", header: "Event", render: (l) => <span className="font-mono text-xs">{l.event_type}</span> },
            { key: "actor", header: "Actor", render: (l) => (l.actor_role ? `${formatStatus(l.actor_role)} ${String(l.actor_id || "").slice(-6)}` : "System or anonymous") },
            { key: "resource", header: "Record", render: (l) => (l.resource_type ? `${l.resource_type} ${String(l.resource_id || "").slice(-6)}` : "") },
            { key: "outcome", header: "Outcome", render: (l) => <StatusBadge status={l.outcome} /> },
          ]}
          emptyTitle="No events"
          getRowId={(l) => l._id}
          rows={logs.data || []}
        />
      )}
    </div>
  );
}

export function MonitoringTab() {
  const runs = useAsyncData(getMonitoringRuns, [], { initialData: [] });
  const { run, pending } = useAction();
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Button disabled={pending === "run"} onClick={() => run("run", runMonitoring, { success: (r) => `Run ${r.status}: ${r.alerts_created ?? 0} new alert(s).`, onSuccess: runs.reload })}>{pending === "run" ? "Running..." : "Run monitoring now"}</Button>
        <p className="text-xs text-muted">Monitoring also runs automatically on the server schedule, whether or not anyone has the app open.</p>
      </div>
      <DataTable
        columns={[
          { key: "started_at", header: "Started", render: (r) => formatDateTime(r.started_at) },
          { key: "trigger", header: "Trigger" },
          { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
          { key: "alerts", header: "Alerts new / resolved / escalated", render: (r) => `${r.alerts_created ?? "-"} / ${r.alerts_resolved ?? "-"} / ${r.alerts_escalated ?? "-"}` },
          { key: "errors", header: "Errors", render: (r) => (r.rule_errors && Object.keys(r.rule_errors).length ? Object.entries(r.rule_errors).map(([k, v]) => `${k}: ${v}`).join("; ") : r.error || r.reason || "") },
        ]}
        emptyTitle="No runs yet"
        getRowId={(r) => r._id}
        rows={runs.data || []}
      />
    </div>
  );
}
