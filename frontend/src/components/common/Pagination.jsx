import { Button } from "../ui/Button.jsx";

export function Pagination({ page, pageSize, total, onPageChange }) {
  const pages = Math.max(1, Math.ceil((total || 0) / pageSize));
  if (!total || pages <= 1) return null;
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
      <span>
        Page {page} of {pages} · {total} records
      </span>
      <div className="flex gap-2">
        <Button disabled={page <= 1} onClick={() => onPageChange(page - 1)} size="sm" variant="secondary">Previous</Button>
        <Button disabled={page >= pages} onClick={() => onPageChange(page + 1)} size="sm" variant="secondary">Next</Button>
      </div>
    </div>
  );
}
