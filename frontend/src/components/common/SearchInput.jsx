import { Search } from "lucide-react";

export function SearchInput(props) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
      <input className="h-10 w-full rounded-md border border-input bg-surface pl-9 pr-3 text-sm shadow-sm" {...props} />
    </div>
  );
}
