export function StatCard({ label, value, helper }) {
  return (
    <div className="card h-full transition-shadow duration-200 hover:shadow-md">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-3 text-3xl font-semibold tracking-tight text-foreground">{value}</p>
      {helper ? <p className="mt-1.5 text-xs text-muted">{helper}</p> : null}
    </div>
  );
}
