import { Eye, EyeOff, LockKeyhole } from "lucide-react";
import { forwardRef, useState } from "react";
import { Input } from "./Input.jsx";

// Password field with a show/hide toggle. Works with react-hook-form's
// register() like a normal Input.
export const PasswordInput = forwardRef(function PasswordInput({ icon = LockKeyhole, ...props }, ref) {
  const [visible, setVisible] = useState(false);
  const Toggle = visible ? EyeOff : Eye;
  return (
    <Input
      ref={ref}
      icon={icon}
      type={visible ? "text" : "password"}
      endAdornment={
        <button
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          className="rounded-md p-2 text-muted transition hover:bg-subtle hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
          onClick={() => setVisible((value) => !value)}
          type="button"
        >
          <Toggle aria-hidden="true" className="size-4" />
        </button>
      }
      {...props}
    />
  );
});
