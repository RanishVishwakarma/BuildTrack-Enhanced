"""Three-way match: purchase order vs accepted deliveries vs vendor invoice.

A vendor may bill only for what the site accepted (status accepted/partial
with quality passed, the same rule that credits inventory), and all
invoices on one order together may not exceed the order subtotal.
Differences that are not hard limits are returned as flags, and an invoice
with flags can only be verified or approved with a written reason.
"""

from app.modules.procurement.gst import GST_SLABS, price_order

# Rounding slack for comparing rupee amounts.
TOLERANCE = 1.0


def delivery_accepted(delivery: dict) -> bool:
    return delivery.get("status") in {"accepted", "partial"} and delivery.get("quality_status") == "passed"


def to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def match_invoice(db, po: dict, *, amount=None, gst=None, exclude_invoice_id=None, vendor_gstin=None) -> dict:
    """Billing position of `po`, and flags for an invoice of `amount` + `gst`.

    With `amount` None, the invoice is assumed to bill everything still
    billable (used to prefill a new invoice).
    """
    po_id = str(po["_id"])
    unit_price = to_float(po.get("unit_price"))
    ordered_qty = to_float(po.get("quantity"))
    po_subtotal = to_float(po.get("subtotal")) or round(ordered_qty * unit_price, 2)

    deliveries = await db.deliveries.find({"purchase_order_id": po_id}).to_list(1000)
    received_qty = sum(to_float(d.get("quantity_received")) for d in deliveries if delivery_accepted(d))
    awaiting_qty = sum(to_float(d.get("quantity_received")) for d in deliveries if not delivery_accepted(d) and d.get("status") not in {"rejected", "cancelled"})
    delivered_value = round(min(received_qty, ordered_qty or received_qty) * unit_price, 2)

    others = await db.invoices.find({"purchase_order_id": po_id, "status": {"$ne": "rejected"}}).to_list(1000)
    others = [i for i in others if str(i["_id"]) != str(exclude_invoice_id or "")]
    previously_invoiced = round(sum(to_float(i.get("amount")) for i in others), 2)

    billable = round(max(0.0, delivered_value - previously_invoiced), 2)
    po_remaining = round(max(0.0, po_subtotal - previously_invoiced), 2)
    amount = billable if amount is None else round(to_float(amount), 2)

    rate = po.get("gst_rate")
    rate = float(rate) if rate is not None and float(rate) in GST_SLABS else None
    expected = price_order(1, amount, gst_rate=rate, vendor_gstin=vendor_gstin) if rate is not None else None
    expected_gst = expected["gst"] if expected else None
    gst = expected_gst if gst is None and expected_gst is not None else round(to_float(gst), 2)

    flags = []
    if received_qty <= 0:
        flags.append("Nothing has been received and accepted on this order yet.")
    elif billable <= 0 and amount > TOLERANCE:
        flags.append(f"Everything received so far (Rs {delivered_value:,.2f}) has already been invoiced.")
    elif amount > billable + TOLERANCE:
        flags.append(
            f"Bills Rs {amount:,.2f} but accepted deliveries not yet invoiced are worth Rs {billable:,.2f} "
            f"({received_qty:g} of {ordered_qty:g} received at Rs {unit_price:,.2f})."
        )
    if expected_gst is not None and abs(gst - expected_gst) > TOLERANCE:
        flags.append(f"GST Rs {gst:,.2f} differs from Rs {expected_gst:,.2f} at the order's {rate:g}% rate.")
    if awaiting_qty > 0:
        flags.append(f"{awaiting_qty:g} more is delivered but not yet inspected and accepted.")

    return {
        "purchase_order_id": po_id,
        "po_number": po.get("po_number"),
        "ordered_quantity": ordered_qty,
        "received_quantity": received_qty,
        "unit_price": unit_price,
        "po_subtotal": po_subtotal,
        "delivered_value": delivered_value,
        "previously_invoiced": previously_invoiced,
        "billable_amount": billable,
        "po_remaining": po_remaining,
        "gst_rate": rate,
        "expected_gst": expected_gst,
        "cgst": expected["cgst"] if expected else None,
        "sgst": expected["sgst"] if expected else None,
        "igst": expected["igst"] if expected else None,
        "supply_type": expected["supply_type"] if expected else "manual",
        "amount": amount,
        "gst": gst,
        "exceeds_po": amount > po_remaining + TOLERANCE,
        "flags": flags,
    }


def over_po_message(match: dict) -> str:
    return (
        f"Invoice amount Rs {match['amount']:,.2f} exceeds what is left on {match['po_number'] or 'the order'}: "
        f"Rs {match['po_remaining']:,.2f} of Rs {match['po_subtotal']:,.2f} (Rs {match['previously_invoiced']:,.2f} already invoiced)."
    )
