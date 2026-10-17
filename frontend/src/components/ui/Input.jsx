import { forwardRef, useId } from "react";
import { cn } from "../../lib/utils.js";

// `icon` renders a decorative leading icon inside the field; `endAdornment`
// renders an interactive element (e.g. a show-password button) at the end.
export const Input = forwardRef(function Input({ label, error, className, id, icon: Icon, endAdornment, ...props }, ref) {
  const generatedId = useId();
  const inputId = id || generatedId;
  const errorId = `${inputId}-error`;
  const field = (
    <input
      ref={ref}
      aria-describedby={error ? errorId : undefined}
      aria-invalid={error ? true : undefined}
      className={cn(
        "peer h-11 w-full rounded-md border border-input bg-surface px-3 text-sm text-foreground shadow-sm transition placeholder:text-muted disabled:bg-subtle disabled:text-muted",
        Icon && "ps-9",
        endAdornment && "pe-11",
        error && "border-danger",
        className,
      )}
      id={inputId}
      {...props}
    />
  );
  return (
    <div>
      {label ? <label className="mb-1 block text-sm font-medium text-foreground" htmlFor={inputId}>{label}</label> : null}
      {Icon || endAdornment ? (
        <div className="relative">
          {field}
          {Icon ? (
            <div className="pointer-events-none absolute inset-y-0 start-0 flex items-center ps-3 text-muted peer-disabled:opacity-50">
              <Icon aria-hidden="true" className="size-4" />
            </div>
          ) : null}
          {endAdornment ? <div className="absolute inset-y-0 end-0 flex items-center pe-1.5">{endAdornment}</div> : null}
        </div>
      ) : (
        field
      )}
      {error ? <span className="mt-1 block text-sm text-danger" id={errorId}>{error}</span> : null}
    </div>
  );
});
