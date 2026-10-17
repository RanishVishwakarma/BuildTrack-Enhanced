import api from "../../../services/api.js";
import { endpoints } from "../../../services/endpoints.js";

// backend/app/modules/inventory/router.py (prefix /inventory)
export async function getInventory() {
  const { data } = await api.get(endpoints.inventory);
  return Array.isArray(data) ? data : [];
}

export async function getLowStockItems() {
  const { data } = await api.get(endpoints.lowStock);
  return Array.isArray(data) ? data : [];
}

export async function createInventoryItem(payload) {
  const { data } = await api.post(endpoints.inventory, payload);
  return data;
}

export async function updateInventoryItem(id, payload) {
  const { data } = await api.put(`${endpoints.inventory}/${id}`, payload);
  return data;
}

export async function deleteInventoryItem(id) {
  const { data } = await api.delete(`${endpoints.inventory}/${id}`);
  return data;
}

// Stock movements. "in" adds to quantity, "out" subtracts; the backend
// recalculates in_stock / low_stock / out_of_stock from reorder_level.
export async function getItemTransactions(id) {
  const { data } = await api.get(`${endpoints.inventory}/${id}/transactions`);
  return Array.isArray(data) ? data : [];
}

export async function recordTransaction(id, payload) {
  const { data } = await api.post(`${endpoints.inventory}/${id}/transactions`, payload);
  return data;
}
