import { forwardRef, useId } from "react";
import { cn } from "../../lib/utils.js";

export const Select = forwardRef(function Select({ label, error, children, className, id, ...props }, ref) {
  const generatedId = useId();
  const selectId = id || generatedId;
  const errorId = `${selectId}-error`;
  return (
    <div>
      {label ? <label className="mb-1 block text-sm font-medium text-foreground" htmlFor={selectId}>{label}</label> : null}
      <select
        ref={ref}
        aria-describedby={error ? errorId : undefined}
        aria-invalid={error ? true : undefined}
        className={cn("h-11 w-full rounded-md border border-input bg-surface px-3 text-sm text-foreground shadow-sm", error && "border-danger", className)}
        id={selectId}
        {...props}
      >
        {children}
      </select>
      {error ? <span className="mt-1 block text-sm text-danger" id={errorId}>{error}</span> : null}
    </div>
  );
});
