import { EmptyState } from "../common/EmptyState.jsx";

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "Not set";
  return value;
}

export function DataTable({ columns, rows, getRowId, emptyTitle, emptyDescription }) {
  if (!rows.length) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  return (
    <div className="table-scroll rounded-lg border border-border/80 bg-surface shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="border-b border-border text-left">
          <tr>
            {columns.map((column) => (
              <th className="whitespace-nowrap px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-muted first:pl-5 last:pr-5" key={column.key} scope="col">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/70">
          {rows.map((row, index) => (
            <tr className="transition-colors hover:bg-subtle/70" key={(getRowId && getRowId(row)) || index}>
              {columns.map((column) => (
                <td className="px-4 py-3.5 align-middle text-foreground first:pl-5 last:pr-5" key={column.key}>
                  {column.render ? column.render(row) : displayValue(row[column.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
