import { useCallback, useEffect, useRef, useState } from "react";

// Loads data for a page or section and exposes { data, loading, error, reload }.
// Responses from superseded requests (fast filter changes, unmounted pages)
// are discarded so stale data never overwrites newer state.
export function useAsyncData(fetcher, deps = [], { initialData = null, enabled = true } = {}) {
  const [state, setState] = useState({ data: initialData, loading: enabled, error: null });
  const requestId = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  const reload = useCallback(async () => {
    const id = ++requestId.current;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await run();
      if (mounted.current && id === requestId.current) setState({ data, loading: false, error: null });
      return data;
    } catch (error) {
      if (mounted.current && id === requestId.current) setState((current) => ({ ...current, loading: false, error }));
      return undefined;
    }
  }, [run]);

  useEffect(() => {
    if (enabled) reload();
    else setState({ data: initialData, loading: false, error: null });
    // initialData is only a starting value; it must not retrigger loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, enabled]);

  return { ...state, reload, setData: (data) => setState((current) => ({ ...current, data })) };
}
