"""Material intelligence: stock position, shortfalls, consumption and wastage.

Figures per inventory item:

    physical    stock on hand (inventory.stock_quantity / quantity)
    reserved    active inventory_reservations against the item
    available   physical - reserved
    incoming    open purchase-order quantity not yet received; "confirmed"
                only once the vendor accepted, is processing or has shipped
    required    approved, not yet delivered material requests
    shortfall   max(0, required - available - incoming_confirmed)

Requests and orders whose unit differs from the item's unit are excluded and
reported as warnings rather than converted. Nothing here changes stock.
"""

from collections import defaultdict
from datetime import timedelta
from statistics import median

from app.modules.intelligence.common import iso, norm_text, parse_dt, to_float, utcnow
from app.modules.intelligence.data import Scope, stock_quantity

CONFIRMED_PO = {"accepted", "processing", "shipped"}
UNCONFIRMED_PO = {"created", "sent"}
APPROVED_DEMAND = {
    "approved", "vendor_assigned", "sent_to_vendor", "vendor_accepted", "po_generated",
    "po_sent", "po_accepted", "partially_delivered",
}
WASTE_WORDS = ("waste", "wastage", "damage", "damaged", "scrap", "spoil", "broken", "loss", "theft")
UNIT_ALIASES = {
    "nos": "piece", "no": "piece", "pcs": "piece", "pc": "piece", "piece": "piece", "pieces": "piece", "unit": "piece", "units": "piece",
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "t": "tonne", "ton": "tonne", "tons": "tonne", "tonne": "tonne", "tonnes": "tonne", "mt": "tonne",
    "bag": "bag", "bags": "bag",
    "m": "metre", "meter": "metre", "meters": "metre", "metre": "metre", "metres": "metre",
    "m3": "cubic metre", "cum": "cubic metre", "cu m": "cubic metre", "cubic meter": "cubic metre", "cubic metre": "cubic metre",
    "l": "litre", "litre": "litre", "liter": "litre", "litres": "litre", "liters": "litre",
}


def norm_unit(unit) -> str | None:
    key = norm_text(unit)
    if not key:
        return None
    return UNIT_ALIASES.get(key, key)


def _units_compatible(item_unit, other_unit) -> bool:
    a, b = norm_unit(item_unit), norm_unit(other_unit)
    return a is None or b is None or a == b


def _item_name(item: dict) -> str:
    return item.get("material") or item.get("material_name") or item.get("itemName") or "Unnamed item"


def _matches(item: dict, material_id, material_name) -> bool:
    if material_id and str(material_id) == str(item["_id"]):
        return True
    return bool(material_name) and norm_text(material_name) == norm_text(_item_name(item))


async def _transactions_by_item(db, items: list[dict], since) -> dict[str, list[dict]]:
    """Recent stock transactions for all items in one query (plus any stored
    on the item itself), keyed by item id."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    ids = [str(item["_id"]) for item in items]
    async for row in db.inventory_transactions.find({"item_id": {"$in": ids}, "created_at": {"$gte": since}}):
        grouped[str(row.get("item_id"))].append(row)
    for item in items:
        grouped[str(item["_id"])].extend(t for t in (item.get("transactions") or []) if isinstance(t, dict))
    return grouped


def _consumption(transactions: list[dict], now, days: int = 30) -> tuple[float | None, list[dict]]:
    """Average daily outflow over `days`, and unusual outflows."""
    since = now - timedelta(days=days)
    outs = []
    for t in transactions:
        kind = norm_text(t.get("transaction_type") or t.get("type"))
        at = parse_dt(t.get("created_at") or t.get("date"))
        quantity = abs(to_float(t.get("quantity")) or 0.0)
        if kind in {"out", "issue", "consumption", "usage"} and at and at >= since and quantity > 0:
            outs.append({"quantity": quantity, "at": at, "reason": t.get("reason") or t.get("remarks") or ""})
    if not outs:
        return None, []
    average = round(sum(o["quantity"] for o in outs) / days, 3)
    typical = median(o["quantity"] for o in outs)
    anomalies = []
    for o in outs:
        reasons = []
        if any(word in norm_text(o["reason"]) for word in WASTE_WORDS):
            reasons.append("recorded as waste/damage")
        if len(outs) >= 4 and typical > 0 and o["quantity"] > 3 * typical:
            reasons.append(f"issue {o['quantity']:g} is over 3x the typical issue of {typical:g}")
        if reasons:
            anomalies.append({"quantity": o["quantity"], "date": iso(o["at"]), "reason": o["reason"], "flags": reasons})
    return average, anomalies


async def material_forecast(db, scope: Scope, project_id: str | None = None, horizon_days: int = 30) -> dict:
    scope.require("inventory.read.assigned")
    now = utcnow()
    horizon = now + timedelta(days=max(1, min(horizon_days, 180)))
    project = None
    if project_id:
        project = next((p for p in scope.projects if str(p["_id"]) == str(project_id)), None)
        if project is None:
            from app.modules.intelligence.data import AccessDenied

            raise AccessDenied("That project does not exist or you are not assigned to it.")

    def in_scope(record) -> bool:
        if not scope.includes_project(record.get("project_id"), record.get("project")):
            return False
        if project is not None:
            return str(record.get("project_id") or "") == str(project["_id"]) or norm_text(record.get("project")) == norm_text(project.get("name"))
        return True

    items = await db.inventory.find({}).to_list(5000)
    reservations = await db.inventory_reservations.find({"status": "active"}).to_list(10000)
    requests = await db.material_requests.find({}).to_list(10000)
    orders = await db.purchase_orders.find({}).to_list(10000)
    deliveries = await db.deliveries.find({}).to_list(20000)
    received = defaultdict(float)
    for delivery in deliveries:
        if norm_text(delivery.get("status")) in {"delivered", "received", "accepted"}:
            received[str(delivery.get("purchase_order_id"))] += to_float(delivery.get("quantity_received")) or 0.0

    transactions_by_item = await _transactions_by_item(db, items, now - timedelta(days=30))
    rows, transfer_candidates = [], []
    for item in items:
        name, unit = _item_name(item), item.get("unit")
        warnings = []
        physical = stock_quantity(item)
        reserved = sum(to_float(r.get("quantity")) or 0.0 for r in reservations if str(r.get("item_id")) == str(item["_id"]) and _units_compatible(unit, r.get("unit")))
        available = physical - reserved

        incoming_confirmed = incoming_unconfirmed = 0.0
        incoming_orders = []
        for order in orders:
            if not _matches(item, order.get("material_id"), order.get("materials")):
                continue
            status = norm_text(order.get("status"))
            if status not in CONFIRMED_PO | UNCONFIRMED_PO:
                continue
            if not _units_compatible(unit, order.get("unit")):
                warnings.append(f"PO {order.get('po_number')} uses unit '{order.get('unit')}', item uses '{unit}': excluded")
                continue
            outstanding = max(0.0, (to_float(order.get("quantity")) or 0.0) - received[str(order["_id"])])
            if outstanding <= 0:
                continue
            expected = parse_dt(order.get("expected_delivery_date"))
            if status in CONFIRMED_PO:
                incoming_confirmed += outstanding
            else:
                incoming_unconfirmed += outstanding
            incoming_orders.append({"po_number": order.get("po_number"), "quantity": outstanding, "status": order.get("status"), "expected_delivery_date": iso(expected), "confirmed": status in CONFIRMED_PO})

        required = pending = 0.0
        demand = []
        for request in requests:
            if not in_scope(request) or not _matches(item, request.get("material_id"), request.get("material_name")):
                continue
            status = norm_text(request.get("status"))
            needed = parse_dt(request.get("required_date"))
            if needed and needed > horizon:
                continue
            if not _units_compatible(unit, request.get("unit")):
                warnings.append(f"Request {request.get('request_id')} uses unit '{request.get('unit')}', item uses '{unit}': excluded")
                continue
            quantity = to_float(request.get("quantity")) or 0.0
            if status in APPROVED_DEMAND:
                required += quantity
            elif status == "pending":
                pending += quantity
            else:
                continue
            demand.append({"request_id": request.get("request_id"), "project": request.get("project"), "quantity": quantity, "status": request.get("status"), "required_date": iso(needed)})

        if project is not None and not demand:
            continue  # project view: only materials this project needs

        avg_daily, anomalies = _consumption(transactions_by_item[str(item["_id"])], now)
        shortfall = max(0.0, required - available - incoming_confirmed)
        next_needed = min((parse_dt(d["required_date"]) for d in demand if d["required_date"]), default=None)
        if reserved > physical:
            warnings.append(f"Reservations ({reserved:g}) exceed physical stock ({physical:g}).")
        rows.append({
            "item_id": str(item["_id"]),
            "material": name,
            "unit": unit,
            "location": item.get("location"),
            "physical_stock": physical,
            "reserved": reserved,
            "available": available,
            "incoming_confirmed": incoming_confirmed,
            "incoming_unconfirmed": incoming_unconfirmed,
            "required_approved": required,
            "required_pending_approval": pending,
            "projected_shortfall": round(shortfall, 3),
            "shortfall_formula": f"{required:g} required - {available:g} available - {incoming_confirmed:g} confirmed incoming",
            "next_required_date": iso(next_needed),
            "reorder_level": to_float(item.get("reorder_level")),
            "below_reorder_level": to_float(item.get("reorder_level")) is not None and available <= to_float(item.get("reorder_level")),
            "average_daily_consumption_30d": avg_daily,
            "days_of_cover": round(available / avg_daily, 1) if avg_daily else None,
            "wastage_anomalies": anomalies,
            "incoming_orders": incoming_orders,
            "demand": demand,
            "warnings": warnings,
        })

    # Transfer candidates: same material held at several locations, one short.
    by_material = defaultdict(list)
    for row in rows:
        by_material[(norm_text(row["material"]), norm_unit(row["unit"]))].append(row)
    for (_material, _unit), group in by_material.items():
        short = [r for r in group if r["projected_shortfall"] > 0]
        spare = [r for r in group if r["available"] - r["required_approved"] > 0]
        for need in short:
            for source in spare:
                if source is need:
                    continue
                surplus = source["available"] - source["required_approved"]
                transfer_candidates.append({
                    "material": need["material"], "from_location": source["location"], "to_location": need["location"],
                    "suggested_quantity": round(min(surplus, need["projected_shortfall"]), 3), "unit": need["unit"],
                    "note": "Candidate only: confirm physical stock and approval before any transfer.",
                })

    rows.sort(key=lambda r: (-r["projected_shortfall"], r["next_required_date"] or "9999"))
    return {
        "as_of": now.isoformat(),
        "horizon_days": horizon_days,
        "project": project.get("name") if project else None,
        "items": rows,
        "shortages": [r for r in rows if r["projected_shortfall"] > 0],
        "low_stock": [r for r in rows if r["below_reorder_level"]],
        "transfer_candidates": transfer_candidates,
        "limitations": [
            "Inventory is company-wide; items carry no project, so stock is shared across projects.",
            "Requirements come from material requests; tasks do not record material quantities.",
            "Units are compared as recorded; no conversions are applied.",
        ],
    }
