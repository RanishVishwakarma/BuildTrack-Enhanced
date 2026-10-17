import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { Link, matchPath, useLocation } from "react-router-dom";
import { useAuth } from "../features/auth/context/AuthContext.jsx";
import { Logo } from "../components/brand/Logo.jsx";
import { cn } from "../lib/utils.js";
import { SETTINGS_ITEM, getNavigation } from "./navigation.js";

// Active-state matching that understands `?tab=` links (vendor portal) and
// treats a parent as active for any of its nested routes.
function isLinkActive(to, location, { exact = false } = {}) {
  const [path, query] = to.split("?");
  if (query) {
    const wanted = new URLSearchParams(query);
    const current = new URLSearchParams(location.search);
    const tab = current.get("tab") || "dashboard";
    return location.pathname === path && wanted.get("tab") === tab;
  }
  return Boolean(matchPath({ path, end: exact }, location.pathname));
}

function NavItemLink({ item, collapsed, onNavigate, active, child = false }) {
  const Icon = item.icon;
  return (
    <Link
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-md text-sm font-semibold text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        child ? "h-9 pl-9 pr-3 text-[13px]" : "h-11 px-3",
        active && "bg-sidebar-accent text-sidebar-accent-foreground",
        collapsed && "justify-center px-0",
      )}
      onClick={onNavigate}
      title={collapsed ? item.label : undefined}
      to={item.to}
    >
      <Icon className={cn("shrink-0", child ? "h-4 w-4" : "h-5 w-5")} />
      {!collapsed ? <span className="truncate">{item.label}</span> : null}
    </Link>
  );
}

export function Sidebar({ collapsed = false, onNavigate }) {
  const { user } = useAuth();
  const location = useLocation();
  const items = getNavigation(user);
  const [toggled, setToggled] = useState({});

  const groupContainsPath = (item) =>
    isLinkActive(item.to, location) || item.children?.some((child) => isLinkActive(child.to, location));

  return (
    <aside className={cn("chrome flex h-full flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground", collapsed ? "w-[76px]" : "w-[248px]")}>
      <div className="flex h-[76px] shrink-0 items-center gap-3 border-b border-sidebar-border px-4">
        <Logo className={cn("text-sidebar-foreground", collapsed && "mx-auto")} markClassName="h-10 w-10" showText={!collapsed} />
      </div>
      <nav aria-label="Main navigation" className="flex-1 space-y-1 overflow-y-auto p-3">
        {items.map((item) => {
          const hasChildren = Boolean(item.children?.length) && !collapsed;
          const open = toggled[item.label] ?? groupContainsPath(item);
          // A parent is highlighted on its own page and nested pages (e.g. /projects/:id)
          // unless one of its child links is the active one.
          const childActive = item.children?.some((child) => isLinkActive(child.to, location, { exact: true }));
          const parentActive = !childActive && isLinkActive(item.to, location);
          return (
            <div key={item.label}>
              <div className="flex items-center gap-1">
                <div className="min-w-0 flex-1">
                  <NavItemLink active={parentActive} collapsed={collapsed} item={item} onNavigate={onNavigate} />
                </div>
                {hasChildren ? (
                  <button
                    aria-expanded={open}
                    aria-label={`Toggle ${item.label} menu`}
                    className="flex h-9 w-8 shrink-0 items-center justify-center rounded-md text-sidebar-foreground/60 hover:bg-sidebar-accent"
                    onClick={() => setToggled((current) => ({ ...current, [item.label]: !open }))}
                    type="button"
                  >
                    <ChevronDown className={cn("h-4 w-4 transition", open && "rotate-180")} />
                  </button>
                ) : null}
              </div>
              {hasChildren && open ? (
                <div className="mt-1 space-y-1">
                  {item.children.map((child) => (
                    <NavItemLink
                      active={isLinkActive(child.to, location, { exact: true })}
                      child
                      item={child}
                      key={child.to}
                      onNavigate={onNavigate}
                    />
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </nav>
      <div className="border-t border-sidebar-border p-3">
        <NavItemLink active={isLinkActive(SETTINGS_ITEM.to, location)} collapsed={collapsed} item={SETTINGS_ITEM} onNavigate={onNavigate} />
      </div>
    </aside>
  );
}
