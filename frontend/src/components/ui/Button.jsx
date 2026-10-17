import { cn } from "../../lib/utils.js";

export function Button({ as: Component = "button", className, variant = "primary", size = "md", ...props }) {
  const variants = {
    primary: "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
    secondary: "border border-input bg-surface text-foreground shadow-sm hover:bg-accent hover:text-accent-foreground",
    ghost: "text-foreground hover:bg-accent hover:text-accent-foreground",
    danger: "bg-danger text-danger-foreground shadow-sm hover:bg-danger/90",
    // No colours: for one-off buttons that set their own (e.g. on the landing hero).
    plain: "",
  };
  const sizes = {
    sm: "h-9 px-3 text-sm",
    md: "h-10 px-4 text-sm",
    lg: "h-11 px-8 text-sm",
    icon: "h-10 w-10 p-0",
  };
  return (
    <Component
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  );
}
