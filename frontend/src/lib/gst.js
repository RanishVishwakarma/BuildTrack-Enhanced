// Mirrors backend app/modules/procurement/gst.py for a live preview. The
// backend recalculates on save, so its figures are the ones stored.
export const GST_SLABS = [0, 5, 12, 18, 28];

export function gstStateCode(gstin) {
  const match = /^(\d{2})[A-Z0-9]{13}$/.exec(String(gstin || "").trim().toUpperCase());
  return match ? match[1] : null;
}

const round2 = (value) => Math.round(value * 100) / 100;

export function previewGst(subtotal, rate, companyStateCode, vendorGstin) {
  if (rate === "" || rate === null || rate === undefined) return null;
  const gst = round2((Number(subtotal) || 0) * Number(rate) / 100);
  const vendorState = gstStateCode(vendorGstin);
  if (companyStateCode && vendorState) {
    if (companyStateCode === vendorState) {
      const cgst = round2(gst / 2);
      return { gst, cgst, sgst: round2(gst - cgst), igst: 0, supplyType: "intra_state" };
    }
    return { gst, cgst: 0, sgst: 0, igst: gst, supplyType: "inter_state" };
  }
  return { gst, cgst: null, sgst: null, igst: null, supplyType: "undetermined" };
}

export function describeSupply(supplyType) {
  return {
    intra_state: "Same state: CGST + SGST",
    inter_state: "Different states: IGST",
    undetermined: "Tax split needs your company GSTIN (COMPANY_GSTIN) and the vendor's GST number",
    manual: "Amount entered manually (no rate recorded)",
  }[supplyType] || "";
}
