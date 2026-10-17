import { X } from "lucide-react";
import { useEffect, useId } from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/utils.js";

export function Modal({ open, title, description, onClose, children, footer, size = "md" }) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    // Keep the page behind the dialog from scrolling while it is open.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;
  const widths = { sm: "max-w-md", md: "max-w-2xl", lg: "max-w-4xl" };
  // Rendered into <body> so no transformed or overflow-clipped ancestor (such
  // as the page fade-in wrapper) can trap the fixed overlay inside the page.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button aria-label="Close dialog" className="absolute inset-0 bg-black/50" onClick={onClose} type="button" />
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className={cn("relative flex max-h-[92vh] w-full flex-col rounded-t-xl bg-surface shadow-xl sm:rounded-xl", widths[size])}
        role="dialog"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground" id={titleId}>{title}</h2>
            {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
          </div>
          <button aria-label="Close" className="rounded-md p-1 text-muted hover:bg-accent" onClick={onClose} type="button">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer ? <div className="flex flex-wrap justify-end gap-2 border-t border-border px-5 py-3">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
