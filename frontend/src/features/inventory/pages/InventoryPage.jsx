import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { SearchInput } from "../../../components/common/SearchInput.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { can } from "../../../lib/roles.js";
import { formatCurrency, formatDateTime, formatNumber, formatStatus, getId, matchesSearch } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import {
  createInventoryItem,
  deleteInventoryItem,
  getInventory,
  getItemTransactions,
  recordTransaction,
  updateInventoryItem,
} from "../services/inventoryService.js";

const STOCK_STATUSES = ["in_stock", "low_stock", "out_of_stock"];

const itemSchema = (editing) =>
  z.object({
    material_name: z.string().trim().min(1, "Material name is required."),
    // InventoryItemUpdate.quantity is an int on the backend.
    quantity: editing
      ? z.coerce.number({ invalid_type_error: "Enter a quantity." }).int("Quantity must be a whole number.").min(0, "Quantity cannot be negative.")
      : z.coerce.number({ invalid_type_error: "Enter a quantity." }).min(0, "Quantity cannot be negative."),
    unit: z.string().trim().min(1, "Unit is required."),
    unit_cost: z.coerce.number({ invalid_type_error: "Enter a cost." }).min(0, "Cost cannot be negative."),
    reorder_level: z.coerce.number({ invalid_type_error: "Enter a reorder level." }).int("Whole number only.").min(0, "Cannot be negative."),
    location: z.string().optional(),
  });

function ItemFormModal({ open, item, onClose, onSaved }) {
  const editing = Boolean(item);
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(itemSchema(editing)),
    values: open
      ? {
          material_name: item?.material_name || "",
          quantity: item?.quantity ?? 0,
          unit: item?.unit || "Nos",
          unit_cost: item?.unit_cost ?? 0,
          reorder_level: item?.reorder_level ?? 10,
          location: item?.location || "",
        }
      : undefined,
  });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    const payload = { ...values, location: values.location || undefined };
    const result = await run("save", () => (editing ? updateInventoryItem(getId(item), payload) : createInventoryItem(payload)), {
      success: editing ? "Inventory item updated." : "Inventory item added.",
      error: editing ? "Unable to update inventory item." : "Unable to add inventory item.",
    });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="inventory-form" type="submit">{pending ? "Saving..." : "Save item"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? `Edit ${item.material_name}` : "Add inventory item"}
      description="Stock status is calculated by the backend from quantity and reorder level."
    >
      <form className="grid gap-4 sm:grid-cols-2" id="inventory-form" noValidate onSubmit={submit}>
        <Input label="Material name" {...form.register("material_name")} error={errors.material_name?.message} />
        <Input label="Unit" placeholder="Nos, kg, bags" {...form.register("unit")} error={errors.unit?.message} />
        <Input label={editing ? "Quantity (whole number)" : "Opening quantity"} min="0" step={editing ? "1" : "any"} type="number" {...form.register("quantity")} error={errors.quantity?.message} />
        <Input label="Reorder level" min="0" step="1" type="number" {...form.register("reorder_level")} error={errors.reorder_level?.message} />
        <Input label="Unit cost (Rs)" min="0" step="any" type="number" {...form.register("unit_cost")} error={errors.unit_cost?.message} />
        <Input label="Location" placeholder="Main Warehouse" {...form.register("location")} />
      </form>
    </Modal>
  );
}

function StockMovementModal({ item, onClose, onSaved }) {
  const { user } = useAuth();
  const { run, pending } = useAction();
  const history = useAsyncData(() => getItemTransactions(getId(item)), [item], { initialData: [], enabled: Boolean(item) });
  const [values, setValues] = useState({ transaction_type: "in", quantity: "", reason: "" });
  const [error, setError] = useState("");
  const canRecord = can.manage(user);

  async function submit(event) {
    event.preventDefault();
    const quantity = Number(values.quantity);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setError("Enter a whole number greater than 0.");
      return;
    }
    // The backend clamps stock at zero silently; refuse to issue more than is on hand.
    if (values.transaction_type === "out" && quantity > Number(item.quantity || 0)) {
      setError(`Only ${formatNumber(item.quantity)} ${item.unit} in stock.`);
      return;
    }
    const result = await run(
      "move",
      () => recordTransaction(getId(item), { transaction_type: values.transaction_type, quantity, reason: values.reason || undefined, created_by: user?.name || user?.email || "BuildTrack user" }),
      { success: values.transaction_type === "in" ? "Stock received." : "Stock issued.", error: "Unable to record stock movement." },
    );
    if (result) onSaved();
  }

  return (
    <Modal onClose={onClose} open={Boolean(item)} size="lg" title={`Stock · ${item?.material_name || ""}`} description={item ? `On hand: ${formatNumber(item.quantity)} ${item.unit} · Reorder level ${item.reorder_level}` : undefined}>
      {canRecord ? (
        <form className="mb-6 grid gap-4 rounded-md border border-border p-4 sm:grid-cols-4" noValidate onSubmit={submit}>
          <Select label="Movement" value={values.transaction_type} onChange={(event) => { setValues({ ...values, transaction_type: event.target.value }); setError(""); }}>
            <option value="in">Receive (in)</option>
            <option value="out">Issue (out)</option>
          </Select>
          <Input error={error} label="Quantity" min="1" step="1" type="number" value={values.quantity} onChange={(event) => { setValues({ ...values, quantity: event.target.value }); setError(""); }} />
          <Input label="Reason" value={values.reason} onChange={(event) => setValues({ ...values, reason: event.target.value })} />
          <div className="flex items-end"><Button className="w-full" disabled={Boolean(pending)} type="submit">{pending ? "Saving..." : "Record"}</Button></div>
        </form>
      ) : null}
      <h3 className="mb-3 font-semibold">Movement history</h3>
      {history.loading ? <LoadingState label="Loading history..." /> : null}
      {history.error ? <ErrorState message={getApiErrorMessage(history.error)} onRetry={history.reload} /> : null}
      {!history.loading && !history.error ? (
        <DataTable
          columns={[
            { key: "transaction_type", header: "Type", render: (row) => <StatusBadge status={row.transaction_type} /> },
            { key: "quantity", header: "Quantity", render: (row) => formatNumber(row.quantity) },
            { key: "reason", header: "Reason" },
            { key: "created_by", header: "By" },
            { key: "created_at", header: "Date", render: (row) => formatDateTime(row.created_at) },
          ]}
          emptyDescription="No stock movements have been recorded for this item."
          emptyTitle="No movements"
          getRowId={getId}
          rows={history.data || []}
        />
      ) : null}
    </Modal>
  );
}

export function InventoryPage() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useAsyncData(getInventory, [], { initialData: [] });
  const { run } = useAction();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [form, setForm] = useState({ open: false, item: null });
  const [moving, setMoving] = useState(null);
  const items = data;
  const isManager = can.manage(user);

  const filtered = useMemo(
    () => items.filter((item) => matchesSearch([item.material_name, item.location, item.unit], query) && (!status || item.status === status)),
    [items, query, status],
  );
  const lowStock = items.filter((item) => item.status === "low_stock").length;
  const outOfStock = items.filter((item) => item.status === "out_of_stock").length;
  const value = items.reduce((sum, item) => sum + Number(item.quantity || 0) * Number(item.unit_cost || 0), 0);

  async function remove(item) {
    if (!confirmAction(`Delete ${item.material_name} from inventory? This cannot be undone.`)) return;
    await run("delete", () => deleteInventoryItem(getId(item)), { success: "Inventory item deleted.", error: "Unable to delete inventory item.", onSuccess: reload });
  }

  return (
    <>
      <PageHeader
        onRefresh={reload}
        title="Inventory"
        description="Materials on hand, reorder levels and stock movements."
        action={
          <div className="flex flex-wrap gap-2">
            {isManager ? <Button onClick={() => setForm({ open: true, item: null })}><Plus className="h-4 w-4" /> Add item</Button> : null}
          </div>
        }
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Materials" value={items.length} />
        <StatCard label="Low stock" value={lowStock} helper="At or below reorder level" />
        <StatCard label="Out of stock" value={outOfStock} />
        <StatCard label="Stock value" value={formatCurrency(value)} helper="Quantity x unit cost" />
      </section>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="sm:col-span-2"><SearchInput aria-label="Search inventory" placeholder="Search material or location..." value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <Select aria-label="Filter by stock status" className="h-10" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">All stock levels</option>
          {STOCK_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
      </div>
      {loading ? <LoadingState label="Loading inventory..." /> : null}
      {!loading && error ? <ErrorState message={getApiErrorMessage(error)} onRetry={reload} /> : null}
      {!loading && !error ? (
        <DataTable
          columns={[
            { key: "material_name", header: "Material", render: (row) => <span className="font-semibold">{row.material_name}</span> },
            { key: "quantity", header: "On hand", render: (row) => `${formatNumber(row.quantity)} ${row.unit}` },
            { key: "reorder_level", header: "Reorder at", render: (row) => formatNumber(row.reorder_level) },
            { key: "unit_cost", header: "Unit cost", render: (row) => formatCurrency(row.unit_cost) },
            { key: "location", header: "Location" },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            {
              key: "actions",
              header: "Actions",
              render: (row) => (
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => setMoving(row)} size="sm" variant="secondary">{isManager ? "Stock in/out" : "History"}</Button>
                  {isManager ? <Button onClick={() => setForm({ open: true, item: row })} size="sm" variant="secondary">Edit</Button> : null}
                  {can.adminOnly(user) ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
                </div>
              ),
            },
          ]}
          emptyDescription={items.length ? "No items match the current filters." : "Add materials to start tracking stock."}
          emptyTitle={items.length ? "No matching items" : "No inventory items"}
          getRowId={getId}
          rows={filtered}
        />
      ) : null}
      <ItemFormModal item={form.item} onClose={() => setForm({ open: false, item: null })} onSaved={() => { setForm({ open: false, item: null }); reload(); }} open={form.open} />
      <StockMovementModal item={moving} key={getId(moving) || "none"} onClose={() => setMoving(null)} onSaved={() => { setMoving(null); reload(); }} />
    </>
  );
}
