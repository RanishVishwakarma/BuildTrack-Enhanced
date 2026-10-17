import { useCallback, useRef, useState } from "react";
import toast from "react-hot-toast";
import { getApiErrorMessage } from "../services/apiError.js";

// Wraps a mutation: blocks duplicate submits while one is in flight, shows the
// backend error message on failure and a success toast only after the API
// call resolves. Returns the API result, or undefined when it failed.
export function useAction() {
  const [pending, setPending] = useState(null);
  const inFlight = useRef(false);

  const run = useCallback(async (key, action, { success, error = "The request failed.", onSuccess } = {}) => {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    setPending(key);
    try {
      const result = await action();
      if (success) toast.success(typeof success === "function" ? success(result) : success);
      if (onSuccess) await onSuccess(result);
      return result ?? true;
    } catch (err) {
      toast.error(getApiErrorMessage(err, error));
      return undefined;
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }, []);

  return { run, pending, isPending: (key) => pending === key };
}

export function confirmAction(message) {
  return window.confirm(message);
}
