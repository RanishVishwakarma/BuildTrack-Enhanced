export function LoadingState({ label = "Loading data..." }) {
  return (
    <div className="card flex items-center gap-3 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted/40 border-t-foreground" aria-hidden="true" />
      {label}
    </div>
  );
}
