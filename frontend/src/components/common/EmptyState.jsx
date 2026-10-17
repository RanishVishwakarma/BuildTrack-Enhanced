export function EmptyState({ title = "No records found", description = "There is no data to show yet." }) {
  return (
    <div className="card text-center">
      <h3 className="font-semibold text-foreground">{title}</h3>
      <p className="mt-1 text-sm text-muted">{description}</p>
    </div>
  );
}
