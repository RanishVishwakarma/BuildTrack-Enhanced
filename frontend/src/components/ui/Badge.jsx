import { cn } from "../../lib/utils.js";

export function Badge({ children, tone = "slate" }) {
  const tones = {
    slate: "border-border bg-secondary text-secondary-foreground",
    blue: "border-info/30 bg-info/10 text-info",
    green: "border-success/30 bg-success/10 text-success",
    amber: "border-warning/30 bg-warning/10 text-warning",
    red: "border-danger/30 bg-danger/10 text-danger",
  };
  return <span className={cn("inline-flex whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold", tones[tone])}>{children}</span>;
}
