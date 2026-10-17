import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

export function Breadcrumbs({ items }) {
  if (items.length < 2) return null;
  return (
    <nav aria-label="Breadcrumb" className="mb-3">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted">
        {items.map((item, index) => {
          const last = index === items.length - 1;
          return (
            <li className="flex items-center gap-1" key={`${item.href}-${index}`}>
              {last ? (
                <span aria-current="page" className="font-semibold text-foreground">{item.title}</span>
              ) : (
                <Link className="hover:text-primary" to={item.href}>{item.title}</Link>
              )}
              {!last ? <ChevronRight className="h-4 w-4" /> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
