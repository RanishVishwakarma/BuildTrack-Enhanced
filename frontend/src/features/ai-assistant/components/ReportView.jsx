import { formatDateTime } from "../../../lib/utils.js";

// Renders a report produced by backend app/modules/intelligence/reports.py:
// metrics, tables and lists, with its period, freshness and limitations.
export function ReportView({ report, aiSummary }) {
  if (!report) return null;
  return (
    <article className="space-y-5">
      <header className="space-y-1">
        <h3 className="text-lg font-semibold text-foreground">{report.title}</h3>
        <p className="text-sm text-muted">
          Scope: {report.scope} · Period {formatDateTime(report.period?.start)} to {formatDateTime(report.period?.end)} · Generated {formatDateTime(report.generated_at)}
        </p>
      </header>

      {aiSummary?.text ? (
        <section className="rounded-lg border border-info/30 bg-info/5 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-info">AI summary</p>
          <p className="mt-2 whitespace-pre-line text-sm text-foreground">{aiSummary.text}</p>
          <p className="mt-2 text-xs text-muted">{aiSummary.label}</p>
        </section>
      ) : null}

      {report.sections?.map((section) => (
        <section key={section.title}>
          <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">{section.title}</h4>
          {section.kind === "metrics" ? (
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {section.items.map((item) => (
                <div className="rounded-lg border border-border bg-surface p-3" key={item.label}>
                  <dt className="text-xs text-muted">{item.label}</dt>
                  <dd className="mt-1 text-lg font-semibold text-foreground">{String(item.value)}</dd>
                  {item.note ? <dd className="mt-1 text-xs text-muted">{item.note}</dd> : null}
                </div>
              ))}
            </dl>
          ) : null}
          {section.kind === "table" ? (
            <div className="table-scroll rounded-lg border border-border">
              <table className="min-w-full text-sm">
                <thead className="border-b border-border text-left">
                  <tr>{section.columns.map((column) => <th className="px-3 py-2 text-xs font-semibold uppercase text-muted" key={column} scope="col">{column}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-border/70">
                  {section.rows.map((row, index) => (
                    <tr key={index}>{row.map((cell, cellIndex) => <td className="px-3 py-2" key={cellIndex}>{cell === null || cell === undefined ? "" : String(cell)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {section.kind === "list" ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-foreground">
              {section.items.map((item, index) => <li key={index}>{item}</li>)}
            </ul>
          ) : null}
        </section>
      ))}

      {report.data_freshness && Object.keys(report.data_freshness).length ? (
        <p className="text-xs text-muted">
          Data freshness (latest record update): {Object.entries(report.data_freshness).map(([source, at]) => `${source.replace(/_/g, " ")} ${at ? formatDateTime(at) : "no records"}`).join(" · ")}
        </p>
      ) : null}
      {report.limitations?.length ? (
        <section className="rounded-lg border border-border bg-subtle p-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">Limitations</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-muted">{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      ) : null}
    </article>
  );
}
