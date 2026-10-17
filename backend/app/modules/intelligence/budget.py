"""Budget intelligence: known costs, variance and spend anomalies.

To avoid double counting, every purchase order contributes exactly once:

    paid                payments with status "paid" against its invoices
    invoiced_unpaid     invoice totals (not rejected) minus paid, floor 0
    open_commitment     order total minus invoiced, floor 0 (not cancelled/rejected)
    known_cost          paid + invoiced_unpaid + open_commitment

`known_cost` is a floor for the final cost: BuildTrack holds no cost estimates
for remaining work. A separate trend projection (constant spend rate) is
labelled as an assumption. Flags are prompts for investigation, never
conclusions about fraud.
"""

from collections import defaultdict
from statistics import median

from app.modules.intelligence.common import iso, norm_text, parse_dt, to_float, utcnow
from app.modules.intelligence.data import AccessDenied, Scope

EXCLUDED_PO = {"cancelled", "rejected"}


def po_total(order: dict) -> float:
    total = to_float(order.get("total_cost"))
    if total is not None:
        return total
    subtotal = to_float(order.get("subtotal"))
    if subtotal is None:
        subtotal = (to_float(order.get("quantity")) or 0.0) * (to_float(order.get("unit_price")) or 0.0)
    return subtotal + (to_float(order.get("gst")) or 0.0)


def invoice_total(invoice: dict) -> float:
    return (to_float(invoice.get("amount")) or 0.0) + (to_float(invoice.get("gst")) or 0.0)


async def budget_overview(db, scope: Scope, project_id: str | None = None) -> dict:
    scope.require("budget.forecast.read")
    now = utcnow()
    projects = [p for p in scope.projects if project_id is None or str(p["_id"]) == str(project_id)]
    if project_id and not projects:
        raise AccessDenied("That project does not exist or you are not assigned to it.")

    orders = await db.purchase_orders.find({}).to_list(20000)
    invoices = await db.invoices.find({}).to_list(20000)
    payments = await db.payments.find({}).to_list(50000)
    deliveries = await db.deliveries.find({}).to_list(50000)

    invoices_by_po = defaultdict(list)
    for invoice in invoices:
        invoices_by_po[str(invoice.get("purchase_order_id"))].append(invoice)
    paid_by_invoice = defaultdict(float)
    for payment in payments:
        if norm_text(payment.get("status")) == "paid":
            paid_by_invoice[str(payment.get("invoice_id"))] += to_float(payment.get("amount")) or 0.0
    received_by_po = defaultdict(float)
    for delivery in deliveries:
        if norm_text(delivery.get("status")) in {"delivered", "received", "accepted"}:
            received_by_po[str(delivery.get("purchase_order_id"))] += to_float(delivery.get("quantity_received")) or 0.0

    results, reconciliation = [], []
    for project in projects:
        pid, name = str(project["_id"]), project.get("name")
        mine = [o for o in orders if str(o.get("project_id") or "") == pid or (not o.get("project_id") and norm_text(o.get("project")) == norm_text(name))]
        paid = invoiced_unpaid = commitment = 0.0
        for order in mine:
            if norm_text(order.get("status")) in EXCLUDED_PO:
                continue
            total = po_total(order)
            po_invoices = [i for i in invoices_by_po[str(order["_id"])] if norm_text(i.get("status")) != "rejected"]
            invoiced = sum(invoice_total(i) for i in po_invoices)
            po_paid = sum(min(paid_by_invoice[str(i["_id"])], invoice_total(i)) for i in po_invoices)
            paid += po_paid
            invoiced_unpaid += max(0.0, invoiced - po_paid)
            commitment += max(0.0, total - invoiced)

            ordered_qty = to_float(order.get("quantity")) or 0.0
            unit_price = to_float(order.get("unit_price")) or 0.0
            received_qty = received_by_po[str(order["_id"])]
            invoiced_net = sum(to_float(i.get("amount")) or 0.0 for i in po_invoices)
            invoiced_qty = round(invoiced_net / unit_price, 3) if unit_price else None
            flags = []
            if received_qty > ordered_qty * 1.01:
                flags.append(f"received {received_qty:g} exceeds ordered {ordered_qty:g}")
            if invoiced_qty is not None and invoiced_qty > received_qty * 1.01 and invoiced_qty > 0:
                flags.append(f"invoiced for about {invoiced_qty:g} units but {received_qty:g} recorded as received")
            if invoiced > total * 1.01 and total > 0:
                flags.append(f"invoiced total {invoiced:,.2f} exceeds order total {total:,.2f}")
            if flags:
                reconciliation.append({"project": name, "po_number": order.get("po_number"), "purchase_order_id": str(order["_id"]), "ordered": ordered_qty,
                                       "received": received_qty, "invoiced_quantity_estimate": invoiced_qty, "flags": flags})

        budget = to_float(project.get("budget"))
        known = paid + invoiced_unpaid + commitment
        start, end = parse_dt(project.get("start_date") or project.get("startDate")), parse_dt(project.get("end_date") or project.get("endDate"))
        trend = None
        if start and end and end > start and now > start and paid > 0:
            elapsed = (min(now, end) - start).days or 1
            trend = round(paid / elapsed * (end - start).days, 2)
        results.append({
            "project_id": pid,
            "project": name,
            "approved_budget": budget,
            "paid": round(paid, 2),
            "invoiced_unpaid": round(invoiced_unpaid, 2),
            "open_commitments": round(commitment, 2),
            "known_cost": round(known, 2),
            "remaining_budget": round(budget - known, 2) if budget is not None else None,
            "known_cost_percent_of_budget": round(known / budget * 100, 1) if budget else None,
            "over_budget": bool(budget) and known > budget,
            "trend_projection": trend,
            "trend_basis": "paid amount extrapolated at a constant daily rate over the scheduled duration" if trend is not None else "not enough data (needs start/end dates and recorded payments)",
            "purchase_orders": len(mine),
        })

    project_names = {norm_text(p.get("name")) for p in projects}
    project_ids = {str(p["_id"]) for p in projects}
    in_view = [o for o in orders if str(o.get("project_id") or "") in project_ids or norm_text(o.get("project")) in project_names]
    in_view_ids = {str(o["_id"]) for o in in_view}
    return {
        "as_of": now.isoformat(),
        "projects": results,
        "duplicate_invoice_flags": _duplicate_invoices([i for i in invoices if str(i.get("purchase_order_id")) in in_view_ids and norm_text(i.get("status")) != "rejected"]),
        "price_change_flags": _price_changes(in_view, orders),
        "quantity_reconciliation_flags": reconciliation,
        "method": "known_cost = paid + invoiced_unpaid + open_commitments, each purchase order counted once.",
        "limitations": [
            "known_cost is a floor: BuildTrack has no cost estimates for remaining work.",
            "Labour and equipment costs are not linked to project budgets.",
            "Flags are prompts for review by an authorized person, not findings of wrongdoing.",
        ],
    }


def _duplicate_invoices(invoices: list[dict]) -> list[dict]:
    flags = []
    by_number = defaultdict(list)
    for invoice in invoices:
        by_number[(str(invoice.get("vendor_id") or ""), norm_text(invoice.get("invoice_number")))].append(invoice)
    for (vendor, number), group in by_number.items():
        if number and len(group) > 1:
            flags.append({"reason": f"Invoice number '{group[0].get('invoice_number')}' recorded {len(group)} times for the same vendor",
                          "invoice_ids": [str(i["_id"]) for i in group], "vendor_id": vendor})
    ordered = sorted(invoices, key=lambda i: (str(i.get("vendor_id") or ""), parse_dt(i.get("invoice_date")) or utcnow()))
    for a, b in zip(ordered, ordered[1:]):
        if str(a.get("vendor_id") or "") != str(b.get("vendor_id") or "") or norm_text(a.get("invoice_number")) == norm_text(b.get("invoice_number")):
            continue
        da, dbt = parse_dt(a.get("invoice_date")), parse_dt(b.get("invoice_date"))
        if da and dbt and abs((dbt - da).days) <= 7 and abs(invoice_total(a) - invoice_total(b)) < 0.01 and invoice_total(a) > 0:
            flags.append({"reason": f"Same vendor and amount ({invoice_total(a):,.2f}) within 7 days under different numbers",
                          "invoice_ids": [str(a["_id"]), str(b["_id"])], "vendor_id": a.get("vendor_id")})
    return flags


def _price_changes(in_view: list[dict], all_orders: list[dict], threshold: float = 0.2) -> list[dict]:
    flags = []
    history = defaultdict(list)
    for order in all_orders:
        price = to_float(order.get("unit_price"))
        if price and price > 0:
            history[norm_text(order.get("materials"))].append((parse_dt(order.get("created_at")), price, str(order["_id"])))
    for order in in_view:
        price = to_float(order.get("unit_price"))
        material = norm_text(order.get("materials"))
        others = [p for _, p, oid in history[material] if oid != str(order["_id"])]
        if not price or len(others) < 2:
            continue
        typical = median(others)
        change = (price - typical) / typical
        if abs(change) >= threshold:
            flags.append({"po_number": order.get("po_number"), "purchase_order_id": str(order["_id"]), "material": order.get("materials"),
                          "unit_price": price, "median_of_other_orders": round(typical, 2), "change_percent": round(change * 100, 1),
                          "based_on_orders": len(others), "date": iso(order.get("created_at"))})
    return flags
