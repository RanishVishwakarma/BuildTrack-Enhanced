import { useMemo } from "react";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { getId, missingRecord } from "../../../lib/utils.js";
import { getActiveVendors, getInvoices, getMaterialRequests, getPurchaseOrders, getVendors } from "../services/procurementService.js";

// Reference data used to resolve ids to names and fill dropdowns. Failures are
// non-fatal. Names prefer the copy stored on the record itself, then the
// lookup list; a reference that resolves to nothing is labelled, never shown
// as a raw id.
export function useProcurementLookups({ vendors = false, activeVendors = false, purchaseOrders = false, requests = false, invoices = false } = {}) {
  const vendorQuery = useAsyncData(
    async () => (await getVendors({ limit: 500 })).items,
    [],
    { initialData: [], enabled: vendors },
  );
  const activeVendorQuery = useAsyncData(
    async () => (await getActiveVendors({ limit: 500 })).items,
    [],
    { initialData: [], enabled: activeVendors },
  );
  const poQuery = useAsyncData(
    async () => (await getPurchaseOrders({ limit: 500 })).items,
    [],
    { initialData: [], enabled: purchaseOrders },
  );
  const requestQuery = useAsyncData(
    async () => (await getMaterialRequests({ limit: 500 })).items,
    [],
    { initialData: [], enabled: requests },
  );
  const invoiceQuery = useAsyncData(
    async () => (await getInvoices({ limit: 500 })).items,
    [],
    { initialData: [], enabled: invoices },
  );

  const vendorMap = useMemo(() => {
    const map = new Map();
    for (const vendor of [...(vendorQuery.data || []), ...(activeVendorQuery.data || [])]) {
      map.set(getId(vendor), vendor);
      if (vendor.user_id) map.set(String(vendor.user_id), vendor);
    }
    return map;
  }, [vendorQuery.data, activeVendorQuery.data]);
  const poMap = useMemo(() => new Map((poQuery.data || []).map((po) => [getId(po), po])), [poQuery.data]);
  const invoiceMap = useMemo(() => new Map((invoiceQuery.data || []).map((invoice) => [getId(invoice), invoice])), [invoiceQuery.data]);

  function vendorName(vendorId, item) {
    if (item?.vendor_name) return item.vendor_name;
    const id = vendorId || (item?.purchase_order_id && poMap.get(item.purchase_order_id)?.vendor_id);
    if (!id) return "Not assigned";
    const vendorLookup = vendors ? vendorQuery : activeVendorQuery;
    return vendorMap.get(String(id))?.vendor_name || missingRecord("Vendor", vendorLookup);
  }

  return {
    vendors: vendorQuery.data || [],
    activeVendors: activeVendorQuery.data || [],
    purchaseOrders: poQuery.data || [],
    requests: requestQuery.data || [],
    invoices: invoiceQuery.data || [],
    vendorName,
    poNumber: (id, item) => item?.po_number || (id ? poMap.get(id)?.po_number || missingRecord("Purchase order", poQuery) : "Not set"),
    invoiceNumber: (id, item) => item?.invoice_number || (id ? invoiceMap.get(id)?.invoice_number || missingRecord("Invoice", invoiceQuery) : "Not set"),
    getPurchaseOrder: (id) => poMap.get(id),
    getInvoice: (id) => invoiceMap.get(id),
    reload: () =>
      Promise.all(
        [
          [vendors, vendorQuery],
          [activeVendors, activeVendorQuery],
          [purchaseOrders, poQuery],
          [requests, requestQuery],
          [invoices, invoiceQuery],
        ]
          .filter(([enabled]) => enabled)
          .map(([, query]) => query.reload()),
      ),
  };
}
