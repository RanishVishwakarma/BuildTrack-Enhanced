import { formatCurrency, formatNumber } from "../../../lib/utils.js";
import { invoiceWarnings } from "../hooks/useInvoicePosition.js";

export function InvoicePosition({ position, loading, amount, gst, warnings = invoiceWarnings(position, amount, gst) }) {
  if (loading) return <p className="text-sm text-muted sm:col-span-2">Checking order and deliveries...</p>;
  if (!position) return null;
  const rows = [
    ["Ordered", `${formatNumber(position.ordered_quantity)} × ${formatCurrency(position.unit_price)} = ${formatCurrency(position.po_subtotal)}`],
    ["Received and accepted", `${formatNumber(position.received_quantity)} (${formatCurrency(position.delivered_value)})`],
    ["Already invoiced", formatCurrency(position.previously_invoiced)],
    ["Billable now", formatCurrency(position.billable_amount)],
  ];
  return (
    <div aria-live="polite" className="space-y-2 rounded-md border border-border p-3 text-sm sm:col-span-2">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        {rows.map(([label, value]) => (
          <div className="contents" key={label}>
            <dt className="text-muted">{label}</dt>
            <dd className="text-right font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      {position.supply_type === "intra_state" ? <p className="text-muted">Tax: CGST + SGST (same state), {position.gst_rate}%</p> : null}
      {position.supply_type === "inter_state" ? <p className="text-muted">Tax: IGST (different states), {position.gst_rate}%</p> : null}
      {warnings.length ? (
        <ul className="space-y-1">
          {warnings.map((warning) => (
            <li className={warning.blocking ? "font-medium text-danger" : "text-warning"} key={warning.text}>{warning.text}</li>
          ))}
        </ul>
      ) : (
        <p className="text-success">Matches the order and accepted deliveries.</p>
      )}
    </div>
  );
}
