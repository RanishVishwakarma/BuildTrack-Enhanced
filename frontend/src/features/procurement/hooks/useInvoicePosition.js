import { useEffect } from "react";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { formatCurrency } from "../../../lib/utils.js";

// Mirrors backend app/modules/procurement/invoice_match.py: a vendor bills
// only what the site accepted, and never more than is left on the order.
const TOLERANCE = 1;

export function invoiceWarnings(position, amount, gst) {
  if (!position) return [];
  const value = Number(amount) || 0;
  const warnings = [];
  if (value > position.po_remaining + TOLERANCE) {
    warnings.push({ blocking: true, text: `More than is left on the order (${formatCurrency(position.po_remaining)}). This will be refused.` });
  } else if (position.received_quantity > 0 && position.billable_amount <= 0) {
    warnings.push({ text: "Everything received so far has already been invoiced." });
  } else if (position.received_quantity <= 0) {
    warnings.push({ text: "Nothing has been received and accepted on this order yet." });
  } else if (value > position.billable_amount + TOLERANCE) {
    warnings.push({ text: `More than the accepted deliveries not yet invoiced (${formatCurrency(position.billable_amount)}).` });
  }
  if (position.gst_rate !== null && position.gst_rate !== undefined) {
    const expected = Math.round(value * position.gst_rate) / 100;
    if (Math.abs((Number(gst) || 0) - expected) > TOLERANCE) {
      warnings.push({ text: `GST at the order's ${position.gst_rate}% would be ${formatCurrency(expected)}.` });
    }
  }
  return warnings;
}

// Loads what is billable on the selected order and prefills amount and GST.
export function useInvoicePosition(fetchPreview, poId, form) {
  const position = useAsyncData(() => (poId ? fetchPreview(poId) : Promise.resolve(null)), [poId], { enabled: Boolean(poId) });
  const data = poId ? position.data : null;
  useEffect(() => {
    if (!data || data.purchase_order_id !== poId) return;
    form.setValue("amount", data.billable_amount);
    form.setValue("gst", data.expected_gst ?? 0);
  }, [data, poId, form]);
  return { data: data && data.purchase_order_id === poId ? data : null, loading: position.loading && Boolean(poId), error: position.error };
}
