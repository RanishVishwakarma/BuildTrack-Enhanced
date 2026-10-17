import { Bell, LogOut, Menu, PanelLeftClose, PanelLeftOpen, RefreshCw, UserRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../features/auth/context/AuthContext.jsx";
import { getUnreadCount } from "../features/notifications/services/notificationService.js";
import { Button } from "../components/ui/Button.jsx";
import { NOTIFICATIONS_CHANGED } from "../lib/events.js";
import { cn } from "../lib/utils.js";

// Matte-black app bar: the current page's title and description on the left,
// refresh, notifications, profile and sign-out on the right.
export function Header({ onMenuClick, onToggleCollapse, onRefresh, collapsed, meta, fallbackTitle }) {
  const { user, signOut } = useAuth();
  const [unread, setUnread] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  async function refresh() {
    if (!onRefresh || refreshing) return;
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  }
  const title = meta?.title || fallbackTitle || "BuildTrack";

  const refreshUnread = useCallback(async () => {
    try {
      const data = await getUnreadCount();
      setUnread(Number(data?.count ?? 0));
    } catch {
      setUnread(null);
    }
  }, []);

  useEffect(() => {
    refreshUnread();
    window.addEventListener(NOTIFICATIONS_CHANGED, refreshUnread);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED, refreshUnread);
  }, [refreshUnread]);

  return (
    <header className="chrome sticky top-0 z-30 flex h-[76px] items-center justify-between gap-4 border-b border-sidebar-border bg-sidebar px-4 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <Button aria-label="Open navigation" className="shrink-0 lg:hidden" size="icon" variant="ghost" onClick={onMenuClick}>
          <Menu className="h-5 w-5" />
        </Button>
        <Button
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          className="hidden shrink-0 lg:inline-flex"
          onClick={onToggleCollapse}
          size="icon"
          title={collapsed ? "Expand navigation" : "Collapse navigation"}
          variant="ghost"
        >
          {collapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
        </Button>
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold tracking-tight text-foreground md:text-xl">
            {meta?.eyebrow && meta.eyebrow !== title ? <span className="font-medium text-muted">{meta.eyebrow} / </span> : null}
            {title}
          </h1>
          {meta?.description ? <p className="hidden truncate text-sm text-muted sm:block">{meta.description}</p> : null}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        {onRefresh ? (
          <Button aria-label="Refresh this page" disabled={refreshing} onClick={refresh} size="icon" title="Refresh" variant="ghost">
            <RefreshCw className={cn("h-5 w-5", refreshing && "animate-spin")} />
          </Button>
        ) : null}
        <Link
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
          className="relative inline-flex h-10 w-10 items-center justify-center rounded-md text-foreground transition-colors hover:bg-accent"
          to="/notifications"
        >
          <Bell className="h-5 w-5" />
          {unread ? (
            <span className="absolute right-1 top-1 min-w-[18px] rounded-full bg-danger px-1 text-center text-[11px] font-bold leading-[18px] text-danger-foreground">
              {unread > 99 ? "99+" : unread}
            </span>
          ) : null}
        </Link>
        <div className="mx-1 hidden h-8 w-px bg-border md:block" />
        <div className="hidden text-right md:block">
          <p className="text-sm font-semibold text-foreground">{user?.name || "BuildTrack User"}</p>
          <p className="text-xs text-muted">{user?.role}</p>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent text-accent-foreground">
          <UserRound className="h-5 w-5" />
        </div>
        <Button aria-label="Sign out" size="icon" title="Sign out" variant="ghost" onClick={signOut}>
          <LogOut className="h-5 w-5" />
        </Button>
      </div>
    </header>
  );
}
