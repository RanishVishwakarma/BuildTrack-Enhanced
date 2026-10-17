import { Link } from "react-router-dom";
import { cn } from "../../lib/utils.js";

// Route-backed tabs as a segmented control: each tab is a real URL so
// refresh and deep links work.
export function TabNav({ tabs, active, label = "Sections" }) {
  if (tabs.length < 2) return null;
  return (
    <nav aria-label={label} className="no-scrollbar mb-6 overflow-x-auto">
      <ul className="inline-flex min-w-max gap-1 rounded-lg border border-border/80 bg-surface p-1 shadow-sm">
        {tabs.map((tab) => (
          <li key={tab.key}>
            <Link
              aria-current={tab.key === active ? "page" : undefined}
              className={cn(
                "inline-flex h-9 items-center rounded-md px-3.5 text-sm font-semibold transition-colors",
                tab.key === active ? "bg-primary text-primary-foreground shadow-sm" : "text-muted hover:bg-subtle hover:text-foreground",
              )}
              to={tab.to}
            >
              {tab.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
