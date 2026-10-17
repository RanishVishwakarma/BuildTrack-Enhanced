import { CheckCheck, Send } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { EmptyState } from "../../../components/common/EmptyState.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { emitNotificationsChanged } from "../../../lib/events.js";
import { ROLE, can, hasAnyRole } from "../../../lib/roles.js";
import { cn, formatDateTime, formatStatus, getId } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getUsers } from "../../auth/services/authService.js";
import { deleteNotification, getNotifications, markAllAsRead, markAsRead, sendNotification } from "../services/notificationService.js";

const CATEGORIES = ["project_update", "task_assignment", "procurement_alert", "attendance_alert", "deadline", "system"];
const TYPES = ["info", "success", "warning", "alert"];
const PAGE = 20;

// Same destinations as Angular NotificationComponent.onNotificationClick.
function targetFor(item, user) {
  if (item.entity_type === "project" && item.entity_id) return `/projects/${item.entity_id}`;
  if (item.entity_type === "procurement") return "/procurement";
  if (item.entity_type === "attendance") return "/attendance";
  if (item.entity_type === "task" || item.category === "task_assignment") return hasAnyRole(user, [ROLE.WORKER]) ? "/my-tasks" : "/workers";
  return null;
}

function SendNotificationModal({ open, onClose, onSent }) {
  const { user } = useAuth();
  const users = useAsyncData(getUsers, [], { initialData: [], enabled: open && can.adminOnly(user) });
  const { run, pending } = useAction();
  const [values, setValues] = useState({ user_id: "", title: "", message: "", type: "info", category: "system" });
  const [errors, setErrors] = useState({});

  async function submit(event) {
    event.preventDefault();
    const next = {};
    if (values.title.trim().length < 2) next.title = "Enter a title.";
    if (values.message.trim().length < 2) next.message = "Enter a message.";
    setErrors(next);
    if (Object.keys(next).length) return;
    const payload = { ...values, title: values.title.trim(), message: values.message.trim(), user_id: values.user_id || undefined };
    const result = await run("send", () => sendNotification(payload), { success: "Notification sent.", error: "Unable to send notification." });
    if (result) {
      setValues({ user_id: "", title: "", message: "", type: "info", category: "system" });
      onSent();
    }
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="send-notification-form" type="submit">{pending ? "Sending..." : "Send"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title="Send notification"
    >
      <form className="grid gap-4 sm:grid-cols-2" id="send-notification-form" noValidate onSubmit={submit}>
        <div className="sm:col-span-2">
          {can.adminOnly(user) ? (
            <Select label="Recipient" value={values.user_id} onChange={(event) => setValues({ ...values, user_id: event.target.value })}>
              <option value="">Myself</option>
              {(users.data || []).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.role}</option>)}
            </Select>
          ) : (
            <p className="text-sm text-muted">The recipient list requires administrator access; this notification will be sent to your own inbox.</p>
          )}
        </div>
        <div className="sm:col-span-2"><Input error={errors.title} label="Title" value={values.title} onChange={(event) => setValues({ ...values, title: event.target.value })} /></div>
        <div className="sm:col-span-2"><Textarea error={errors.message} label="Message" value={values.message} onChange={(event) => setValues({ ...values, message: event.target.value })} /></div>
        <Select label="Type" value={values.type} onChange={(event) => setValues({ ...values, type: event.target.value })}>
          {TYPES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Select label="Category" value={values.category} onChange={(event) => setValues({ ...values, category: event.target.value })}>
          {CATEGORIES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
      </form>
    </Modal>
  );
}

export function NotificationsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { run } = useAction();
  const [filters, setFilters] = useState({ category: "", read: "" });
  const [limit, setLimit] = useState(PAGE);
  const [sending, setSending] = useState(false);

  const { data, loading, error, reload } = useAsyncData(
    () => getNotifications({ limit, category: filters.category || undefined, is_read: filters.read === "" ? undefined : filters.read === "read" }),
    [limit, filters.category, filters.read],
    { initialData: [] },
  );
  const items = data || [];
  const changed = () => {
    reload();
    emitNotificationsChanged();
  };

  async function open(item) {
    if (!item.is_read) await run(`read-${getId(item)}`, () => markAsRead(getId(item)), { onSuccess: emitNotificationsChanged });
    const target = targetFor(item, user);
    if (target) navigate(target);
    else reload();
  }

  async function remove(item) {
    if (!confirmAction(`Delete notification "${item.title}"?`)) return;
    await run("delete", () => deleteNotification(getId(item)), { success: "Notification deleted.", error: "Unable to delete notification.", onSuccess: changed });
  }

  return (
    <>
      <PageHeader
        onRefresh={reload}
        title="Notifications"
        description="Alerts about projects, tasks, procurement and attendance."
        action={
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => run("all", markAllAsRead, { success: "All notifications marked read.", error: "Unable to mark notifications read.", onSuccess: changed })} variant="secondary">
              <CheckCheck className="h-4 w-4" /> Mark all read
            </Button>
            {can.manage(user) ? <Button onClick={() => setSending(true)}><Send className="h-4 w-4" /> Send</Button> : null}
          </div>
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:max-w-2xl">
        <Select aria-label="Filter by category" className="h-10" value={filters.category} onChange={(event) => { setFilters({ ...filters, category: event.target.value }); setLimit(PAGE); }}>
          <option value="">All categories</option>
          {CATEGORIES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Select aria-label="Filter by read state" className="h-10" value={filters.read} onChange={(event) => { setFilters({ ...filters, read: event.target.value }); setLimit(PAGE); }}>
          <option value="">Read and unread</option>
          <option value="unread">Unread only</option>
          <option value="read">Read only</option>
        </Select>
      </div>
      {loading && !items.length ? <LoadingState label="Loading notifications..." /> : null}
      {!loading && error ? <ErrorState message={getApiErrorMessage(error)} onRetry={reload} /> : null}
      {!error && !(loading && !items.length) ? (
        items.length ? (
          <ul className="space-y-3">
            {items.map((item) => (
              <li className={cn("card flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between", !item.is_read && "border-l-4 border-l-primary")} key={getId(item)}>
                <button className="min-w-0 flex-1 text-left" onClick={() => open(item)} type="button">
                  <p className={cn("text-sm", !item.is_read && "font-semibold")}>{item.title}</p>
                  <p className="mt-1 text-sm text-muted">{item.message}</p>
                  <p className="mt-2 text-xs text-muted">{formatStatus(item.category)} · {formatDateTime(item.created_at)}</p>
                </button>
                <div className="flex shrink-0 gap-2">
                  {!item.is_read ? (
                    <Button onClick={() => run(`read-${getId(item)}`, () => markAsRead(getId(item)), { error: "Unable to mark read.", onSuccess: changed })} size="sm" variant="secondary">Mark read</Button>
                  ) : null}
                  <Button onClick={() => remove(item)} size="sm" variant="danger">Delete</Button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState description="You're all caught up." title="No notifications" />
        )
      ) : null}
      {items.length >= limit && limit < 100 ? (
        <div className="mt-4 text-center"><Button onClick={() => setLimit((value) => Math.min(100, value + PAGE))} variant="secondary">Load more</Button></div>
      ) : null}
      <SendNotificationModal onClose={() => setSending(false)} onSent={() => { setSending(false); changed(); }} open={sending} />
    </>
  );
}
