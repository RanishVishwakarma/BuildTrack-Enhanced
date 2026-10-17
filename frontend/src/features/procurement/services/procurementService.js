import api from "../../../services/api.js";
import { endpoints } from "../../../services/endpoints.js";
import { normalizeList } from "../../../lib/utils.js";

// Endpoints mirror frontend/src/app/core/services/procurement.service.ts and
// backend/app/modules/procurement/router.py (prefix /procurement).
const base = "/procurement";
const { materialRequests, purchaseOrders, vendors, deliveries, invoices, payments } = endpoints.procurement;

// Drop empty filter values so the backend never receives `status_filter=`.
function cleanParams(params = {}) {
  return Object.fromEntries(Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== ""));
}

async function list(url, params) {
  const { data } = await api.get(url, { params: cleanParams(params) });
  return normalizeList(data);
}

async function send(method, url, payload, config) {
  const { data } = await api[method](url, payload, config);
  return data;
}

// Dashboard
export async function getProcurementDashboard() {
  const { data } = await api.get(endpoints.procurement.dashboard);
  return data;
}

// Vendors
export const getVendors = (params) => list(vendors, params);
export const getActiveVendors = (params) => list(`${vendors}/active`, params);
export const createVendor = (payload) => send("post", vendors, payload);
export const createVendorWithAccount = (payload) => send("post", `${vendors}/create-account`, payload);
export const updateVendor = (id, payload) => send("put", `${vendors}/${id}`, payload);
export const deleteVendor = (id) => send("delete", `${vendors}/${id}`);
export const createVendorLogin = (id, payload) => send("post", `${vendors}/${id}/login`, payload);
export const resetVendorPassword = (id, password) => send("put", `${vendors}/${id}/login/password`, { password });

// Material requests
export const getMaterialRequests = (params) => list(materialRequests, params);
export const createMaterialRequest = (payload) => send("post", materialRequests, payload);
export const updateMaterialRequest = (id, payload) => send("put", `${materialRequests}/${id}`, payload);
export const deleteMaterialRequest = (id) => send("delete", `${materialRequests}/${id}`);
export const approveMaterialRequest = (id, action) => send("patch", `${materialRequests}/${id}/approval`, action);
export const assignVendorToMaterialRequest = (id, vendorId) => send("put", `${materialRequests}/${id}/assign-vendor`, { vendor_id: vendorId });

export async function getMaterials() {
  const { data } = await api.get(`${base}/materials`);
  return Array.isArray(data) ? data : [];
}

// GST slabs and the company's state code, for previewing PO tax.
export async function getGstConfig() {
  const { data } = await api.get(`${base}/gst-config`);
  return data;
}

// Purchase orders
export const getPurchaseOrders = (params) => list(purchaseOrders, params);
export const createPurchaseOrder = (payload) => send("post", purchaseOrders, payload);
export const updatePurchaseOrder = (id, payload) => send("put", `${purchaseOrders}/${id}`, payload);
export const sendPurchaseOrder = (id) => send("put", `${purchaseOrders}/${id}/send`, {});
export const deletePurchaseOrder = (id) => send("delete", `${purchaseOrders}/${id}`);
export const downloadPurchaseOrderPdf = (id) => api.get(`${purchaseOrders}/${id}/pdf`, { responseType: "blob" });

// Deliveries (creating/updating a delivery updates inventory server-side)
export const getDeliveries = (params) => list(deliveries, params);
export const createDelivery = (payload) => send("post", deliveries, payload);
export const updateDelivery = (id, payload) => send("put", `${deliveries}/${id}`, payload);

// Procurement inventory view and history
export const getProcurementInventory = (params) => list(`${base}/inventory`, params);
export async function getInventoryHistory(materialId) {
  const { data } = await api.get(`${base}/inventory/history`, { params: cleanParams({ material_id: materialId }) });
  return Array.isArray(data) ? data : normalizeList(data).items;
}

// Invoices
export const getInvoices = (params) => list(invoices, params);
export const createInvoice = (payload) => send("post", invoices, payload);
export const updateInvoice = (id, payload) => send("put", `${invoices}/${id}`, payload);
export const deleteInvoice = (id) => send("delete", `${invoices}/${id}`);
export const invoiceAction = (id, action, payload) => send("patch", `${invoices}/${id}/${action}`, payload);
export const downloadInvoicePdf = (id) => api.get(`${invoices}/${id}/pdf`, { responseType: "blob" });
export const quickPayInvoice = (id) => send("post", `${invoices}/${id}/quick-pay`, {});

export async function uploadInvoiceAttachment(file) {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post(`${invoices}/upload`, formData, { headers: { "Content-Type": "multipart/form-data" } });
  return data;
}

// Payments
export const getPayments = (params) => list(payments, params);
export const createPayment = (payload) => send("post", payments, payload);
export const updatePayment = (id, payload) => send("put", `${payments}/${id}`, payload);

// CSV export of a procurement collection
export const exportCollection = (collection) => api.get(`${base}/export/${collection}`, { responseType: "blob" });

// Vendor portal (role: vendor)
export async function getVendorDashboard() {
  const { data } = await api.get(`${base}/vendor/dashboard`);
  return data;
}
export const getVendorMaterialRequests = (params) => list(`${base}/vendor/material-requests`, params);
export const vendorAcceptMaterialRequest = (id) => send("post", `${base}/vendor/material-requests/${id}/accept`, {});
export const vendorRejectMaterialRequest = (id, reason) => send("post", `${base}/vendor/material-requests/${id}/reject`, { reason });
export const getVendorPurchaseOrders = (params) => list(`${base}/vendor/purchase-orders`, params);
export const vendorAcceptPurchaseOrder = (id) => send("post", `${base}/vendor/purchase-orders/${id}/accept`, {});
export const vendorRejectPurchaseOrder = (id, reason) => send("post", `${base}/vendor/purchase-orders/${id}/reject`, { reason });
export const getVendorDeliveries = (params) => list(`${base}/vendor/deliveries`, params);
export const createVendorDelivery = (payload) => send("post", `${base}/vendor/deliveries`, payload);
export const updateVendorDelivery = (id, payload) => send("put", `${base}/vendor/deliveries/${id}`, payload);
export const getVendorInvoices = (params) => list(`${base}/vendor/invoices`, params);
export const createVendorInvoice = (payload) => send("post", `${base}/vendor/invoices`, payload);
export async function getVendorProfile() {
  const { data } = await api.get(`${base}/vendor/profile`);
  return data;
}
export const updateVendorProfile = (payload) => send("put", `${base}/vendor/profile`, payload);
