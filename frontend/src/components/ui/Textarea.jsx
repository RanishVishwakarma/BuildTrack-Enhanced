import { forwardRef, useId } from "react";
import { cn } from "../../lib/utils.js";

export const Textarea = forwardRef(function Textarea({ label, error, className, rows = 3, id, ...props }, ref) {
  const generatedId = useId();
  const fieldId = id || generatedId;
  const errorId = `${fieldId}-error`;
  return (
    <div>
      {label ? <label className="mb-1 block text-sm font-medium text-foreground" htmlFor={fieldId}>{label}</label> : null}
      <textarea
        ref={ref}
        aria-describedby={error ? errorId : undefined}
        aria-invalid={error ? true : undefined}
        className={cn("w-full rounded-md border border-input bg-surface px-3 py-2 text-sm text-foreground shadow-sm", error && "border-danger", className)}
        id={fieldId}
        rows={rows}
        {...props}
      />
      {error ? <span className="mt-1 block text-sm text-danger" id={errorId}>{error}</span> : null}
    </div>
  );
});
