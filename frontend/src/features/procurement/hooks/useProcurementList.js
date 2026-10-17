import { useState } from "react";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue.js";

export const PAGE_SIZE = 10;

// Server-side search, status/priority filters and pagination for the
// procurement list endpoints (all accept skip/limit/search/status_filter/sort).
export function useProcurementList(fetcher, { withPriority = false, fixedStatus } = {}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [page, setPage] = useState(1);
  const debouncedSearch = useDebouncedValue(search);

  const query = useAsyncData(
    () =>
      fetcher({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        search: debouncedSearch || undefined,
        status_filter: fixedStatus || status || undefined,
        priority: withPriority ? priority || undefined : undefined,
        sort_by: "created_at",
        sort_dir: "desc",
      }),
    [debouncedSearch, status, priority, page, fixedStatus],
    { initialData: { items: [], total: 0 } },
  );

  const resetPageAnd = (setter) => (value) => {
    setter(value);
    setPage(1);
  };

  return {
    ...query,
    items: query.data?.items || [],
    total: query.data?.total || 0,
    filters: { search, status, priority, page },
    setSearch: resetPageAnd(setSearch),
    setStatus: resetPageAnd(setStatus),
    setPriority: resetPageAnd(setPriority),
    setPage,
  };
}
