export function DetailList({ items }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div className="border-b border-border pb-2" key={label}>
          <dt className="text-xs font-semibold uppercase text-muted">{label}</dt>
          <dd className="mt-1 break-words text-sm text-foreground">
            {value === null || value === undefined || value === "" ? "Not set" : value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
