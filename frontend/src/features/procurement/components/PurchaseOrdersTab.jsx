import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { DetailList } from "../../../components/common/DetailList.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { can } from "../../../lib/roles.js";
import { dateInputToIso, formatCurrency, formatDate, formatDateTime, formatNumber, formatStatus, getId, toDateInput } from "../../../lib/utils.js";
import { downloadBlob } from "../../../services/fileDownload.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { useProcurementList } from "../hooks/useProcurementList.js";
import { useProcurementLookups } from "../hooks/useProcurementLookups.js";
import {
  createPurchaseOrder,
  deletePurchaseOrder,
  downloadPurchaseOrderPdf,
  getPurchaseOrders,
  sendPurchaseOrder,
  updatePurchaseOrder,
} from "../services/procurementService.js";
import { ListSection, RowActions } from "./ListSection.jsx";

const PO_STATUSES = ["created", "sent", "accepted", "rejected", "processing", "shipped", "delivered", "received", "cancelled"];

const money = z.coerce.number({ invalid_type_error: "Enter an amount." }).min(0, "Cannot be negative.");
const createSchema = z.object({
  request_id: z.string().min(1, "Select a vendor-accepted material request."),
  unit_price: money,
  gst: money,
  expected_delivery_date: z.string().min(1, "Expected delivery date is required."),
});
const editSchema = z.object({
  quantity: z.coerce.number({ invalid_type_error: "Enter a quantity." }).gt(0, "Quantity must be greater than 0."),
  unit_price: money,
  gst: money,
  expected_delivery_date: z.string().min(1, "Expected delivery date is required."),
  status: z.enum(PO_STATUSES),
});

// Backend create_purchase_order_from_request only accepts requests the
// assigned vendor has accepted and that do not already have a PO.
const canGeneratePo = (request) => request.status === "vendor_accepted" && !request.purchase_order_id;

export function PurchaseOrderFormModal({ open, request, purchaseOrder, onClose, onSaved }) {
  const editing = Boolean(purchaseOrder);
  const lookups = useProcurementLookups({ requests: open && !editing, vendors: open });
  const { run, pending } = useAction();
  const eligible = lookups.requests.filter(canGeneratePo);
  const form = useForm({
    resolver: zodResolver(editing ? editSchema : createSchema),
    values: open
      ? editing
        ? {
            quantity: purchaseOrder.quantity,
            unit_price: purchaseOrder.unit_price ?? 0,
            gst: purchaseOrder.gst ?? 0,
            expected_delivery_date: toDateInput(purchaseOrder.expected_delivery_date),
            status: purchaseOrder.status || "created",
          }
        : { request_id: getId(request) || "", unit_price: 0, gst: 0, expected_delivery_date: request?.required_date ? toDateInput(request.required_date) : "" }
      : undefined,
  });
  const errors = form.formState.errors;
  const requestId = form.watch("request_id");
  const selected = editing ? null : request && getId(request) === requestId ? request : eligible.find((item) => getId(item) === requestId);
  const quantity = Number(editing ? form.watch("quantity") : selected?.quantity) || 0;
  const subtotal = quantity * (Number(form.watch("unit_price")) || 0);
  const total = subtotal + (Number(form.watch("gst")) || 0);

  const submit = form.handleSubmit(async (values) => {
    if (editing) {
      const payload = { ...values, expected_delivery_date: dateInputToIso(values.expected_delivery_date) };
      const result = await run("save", () => updatePurchaseOrder(getId(purchaseOrder), payload), { success: "Purchase order updated.", error: "Unable to update purchase order." });
      if (result) onSaved();
      return;
    }
    if (!selected) return;
    // Project, materials, quantity and vendor are re-read from the request by
    // the backend; they are sent because the schema requires them.
    const payload = {
      request_id: values.request_id,
      vendor_id: selected.vendor_id,
      project: selected.project,
      project_id: selected.project_id || undefined,
      materials: selected.material_name,
      material_id: selected.material_id || undefined,
      quantity: selected.quantity,
      unit_price: values.unit_price,
      gst: values.gst,
      expected_delivery_date: dateInputToIso(values.expected_delivery_date),
      status: "created",
    };
    const result = await run("save", () => createPurchaseOrder(payload), {
      success: (po) => `Purchase order ${po?.po_number || ""} created.`,
      error: "Unable to create purchase order.",
    });
    if (result) onSaved(result);
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="po-form" type="submit">{pending ? "Saving..." : editing ? "Save changes" : "Generate PO"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? `Edit ${purchaseOrder?.po_number || "purchase order"}` : "Generate purchase order"}
      description={editing ? undefined : "Purchase orders are generated from material requests that the assigned vendor has accepted."}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="po-form" noValidate onSubmit={submit}>
        {!editing ? (
          <div className="sm:col-span-2">
            <Select label="Material request" {...form.register("request_id")} error={errors.request_id?.message}>
              <option value="">Select request</option>
              {request && !eligible.some((item) => getId(item) === getId(request)) ? (
                <option value={getId(request)}>{request.request_id} · {request.material_name}</option>
              ) : null}
              {eligible.map((item) => (
                <option key={getId(item)} value={getId(item)}>
                  {item.request_id} · {item.material_name} · {item.project}
                </option>
              ))}
            </Select>
            {!request && !eligible.length ? <p className="mt-1 text-sm text-muted">No requests are ready. A vendor must accept an assigned request first.</p> : null}
          </div>
        ) : null}
        {selected ? (
          <div className="rounded-md bg-subtle p-3 text-sm sm:col-span-2">
            <p><span className="font-semibold">Project:</span> {selected.project}</p>
            <p><span className="font-semibold">Material:</span> {selected.material_name} · {formatNumber(selected.quantity)} {selected.unit || ""}</p>
            <p><span className="font-semibold">Vendor:</span> {lookups.vendorName(selected.vendor_id, selected)}</p>
          </div>
        ) : null}
        {editing ? <Input label="Quantity" min="0" step="any" type="number" {...form.register("quantity")} error={errors.quantity?.message} /> : null}
        <Input label="Unit price (Rs)" min="0" step="any" type="number" {...form.register("unit_price")} error={errors.unit_price?.message} />
        <Input label="GST amount (Rs)" min="0" step="any" type="number" {...form.register("gst")} error={errors.gst?.message} />
        <Input label="Expected delivery" type="date" {...form.register("expected_delivery_date")} error={errors.expected_delivery_date?.message} />
        {editing ? (
          <Select label="Status" {...form.register("status")}>
            {PO_STATUSES.map((status) => <option key={status} value={status}>{formatStatus(status)}</option>)}
          </Select>
        ) : null}
        <p className="text-sm text-muted sm:col-span-2">
          Subtotal {formatCurrency(subtotal)} · Total {formatCurrency(total)}
        </p>
      </form>
    </Modal>
  );
}

export function PurchaseOrdersTab() {
  const { user } = useAuth();
  const list = useProcurementList(getPurchaseOrders);
  const lookups = useProcurementLookups({ vendors: true });
  const { run } = useAction();
  const [form, setForm] = useState({ open: false, purchaseOrder: null });
  const [details, setDetails] = useState(null);
  const isPM = can.procurementProjectManager(user);

  async function send(po) {
    await run(`send-${getId(po)}`, () => sendPurchaseOrder(getId(po)), { success: `${po.po_number} sent to vendor.`, error: "Unable to send purchase order.", onSuccess: list.reload });
  }

  async function remove(po) {
    if (!confirmAction(`Delete ${po.po_number || "this purchase order"}? This cannot be undone.`)) return;
    await run("delete", () => deletePurchaseOrder(getId(po)), { success: "Purchase order deleted.", error: "Unable to delete purchase order.", onSuccess: list.reload });
  }

  async function pdf(po) {
    await run(`pdf-${getId(po)}`, async () => downloadBlob(await downloadPurchaseOrderPdf(getId(po)), `${po.po_number || "purchase-order"}.pdf`), { error: "Unable to download PDF." });
  }

  const columns = [
    { key: "po_number", header: "PO", render: (row) => <span className="font-semibold">{row.po_number}</span> },
    { key: "vendor", header: "Vendor", render: (row) => lookups.vendorName(row.vendor_id, row) },
    { key: "project", header: "Project" },
    { key: "materials", header: "Materials" },
    { key: "quantity", header: "Qty", render: (row) => formatNumber(row.quantity) },
    { key: "unit_price", header: "Unit price", render: (row) => formatCurrency(row.unit_price) },
    { key: "total_cost", header: "Total", render: (row) => formatCurrency(row.total_cost) },
    { key: "expected_delivery_date", header: "Expected", render: (row) => formatDate(row.expected_delivery_date) },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions>
          <Button onClick={() => setDetails(row)} size="sm" variant="secondary">View</Button>
          <Button onClick={() => pdf(row)} size="sm" variant="secondary">PDF</Button>
          {isPM && row.status === "created" ? <Button onClick={() => send(row)} size="sm">Send</Button> : null}
          {isPM ? <Button onClick={() => setForm({ open: true, purchaseOrder: row })} size="sm" variant="secondary">Edit</Button> : null}
          {isPM ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ListSection
        addLabel="Generate PO"
        columns={columns}
        emptyDescription="Purchase orders appear here once generated from vendor-accepted requests."
        emptyTitle="No purchase orders"
        exportName="purchase_orders"
        getRowId={getId}
        list={list}
        onAdd={isPM ? () => setForm({ open: true, purchaseOrder: null }) : undefined}
        searchPlaceholder="Search PO number, project, material..."
        statusOptions={PO_STATUSES}
        title="Purchase orders"
      />
      <PurchaseOrderFormModal
        onClose={() => setForm({ open: false, purchaseOrder: null })}
        onSaved={() => { setForm({ open: false, purchaseOrder: null }); list.reload(); }}
        open={form.open}
        purchaseOrder={form.purchaseOrder}
      />
      <Modal onClose={() => setDetails(null)} open={Boolean(details)} title={details?.po_number || "Purchase order"}>
        {details ? (
          <DetailList
            items={[
              ["Vendor", lookups.vendorName(details.vendor_id, details)],
              ["Project", details.project],
              ["Materials", details.materials],
              ["Quantity", formatNumber(details.quantity)],
              ["Unit price", formatCurrency(details.unit_price)],
              ["Subtotal", formatCurrency(details.subtotal)],
              ["GST", formatCurrency(details.gst)],
              ["Total", formatCurrency(details.total_cost)],
              ["Expected delivery", formatDate(details.expected_delivery_date)],
              ["Status", <StatusBadge key="s" status={details.status} />],
              ["Rejection reason", details.rejection_reason],
              ["Created", formatDateTime(details.created_at)],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
