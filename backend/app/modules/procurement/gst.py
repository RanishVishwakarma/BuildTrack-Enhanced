"""GST pricing for purchase orders.

The rate is chosen from the standard slabs; the amount is always calculated
here from the subtotal, never typed. The tax is split by place of supply:

* company and vendor GSTINs in the same state  -> CGST + SGST (half each)
* different states                              -> IGST
* either GSTIN missing or invalid               -> "undetermined" (amount only)

Orders created before rates existed keep their stored GST amount ("manual").
Exact rates for each material should be checked against current GST
notifications; nothing here assigns a rate to a material on its own.
"""

import re

from app.core.config import settings

GST_SLABS = (0.0, 5.0, 12.0, 18.0, 28.0)
GSTIN_PATTERN = re.compile(r"^(\d{2})[A-Z0-9]{13}$")


class GSTError(ValueError):
    pass


def validate_rate(rate) -> float | None:
    if rate is None or rate == "":
        return None
    try:
        value = float(rate)
    except (TypeError, ValueError) as error:
        raise GSTError("GST rate must be a number") from error
    if value not in GST_SLABS:
        raise GSTError(f"GST rate must be one of {', '.join(f'{s:g}%' for s in GST_SLABS)}")
    return value


def state_code(gstin) -> str | None:
    """First two digits of a well-formed GSTIN (the state code)."""
    match = GSTIN_PATTERN.match(str(gstin or "").strip().upper())
    return match.group(1) if match else None


def price_order(quantity, unit_price, *, gst_rate=None, gst_amount=None, vendor_gstin=None) -> dict:
    """Subtotal, GST and total for an order line, with the tax split."""
    subtotal = round(float(quantity or 0) * float(unit_price or 0), 2)
    rate = validate_rate(gst_rate)
    if rate is None:
        gst = round(float(gst_amount or 0), 2)
        return {"subtotal": subtotal, "gst_rate": None, "gst": gst, "cgst": None, "sgst": None, "igst": None,
                "supply_type": "manual", "total_cost": round(subtotal + gst, 2)}

    gst = round(subtotal * rate / 100, 2)
    company, vendor = state_code(settings.company_gstin), state_code(vendor_gstin)
    if company and vendor and company == vendor:
        cgst = round(gst / 2, 2)
        split = {"cgst": cgst, "sgst": round(gst - cgst, 2), "igst": 0.0, "supply_type": "intra_state"}
    elif company and vendor:
        split = {"cgst": 0.0, "sgst": 0.0, "igst": gst, "supply_type": "inter_state"}
    else:
        split = {"cgst": None, "sgst": None, "igst": None, "supply_type": "undetermined"}
    return {"subtotal": subtotal, "gst_rate": rate, "gst": gst, **split, "total_cost": round(subtotal + gst, 2)}


def config() -> dict:
    return {"slabs": list(GST_SLABS), "company_state_code": state_code(settings.company_gstin),
            "company_gstin_configured": bool(state_code(settings.company_gstin))}
