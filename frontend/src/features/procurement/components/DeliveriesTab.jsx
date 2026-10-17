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
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { can } from "../../../lib/roles.js";
import { dateInputToIso, formatDate, formatDateTime, formatNumber, formatStatus, getId, toDateInput } from "../../../lib/utils.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { useProcurementList } from "../hooks/useProcurementList.js";
import { useProcurementLookups } from "../hooks/useProcurementLookups.js";
import { createDelivery, getDeliveries, updateDelivery } from "../services/procurementService.js";
import { ListSection, RowActions } from "./ListSection.jsx";

const DELIVERY_STATUSES = ["pending", "accepted", "processing", "shipped", "delivered", "received", "cancelled", "rejected", "partial"];
const AWAITING_RECEIPT = ["pending", "shipped", "delivered", "processing"];
const QUALITY = ["pending", "passed", "failed"];

const quantity = z.coerce.number({ invalid_type_error: "Enter a quantity." }).gt(0, "Quantity must be greater than 0.");
const createSchema = z.object({
  purchase_order_id: z.string().min(1, "Select a purchase order."),
  material: z.string().trim().min(2, "Material is required."),
  quantity_received: quantity,
  quality_status: z.enum(QUALITY),
  delivery_date: z.string().min(1, "Delivery date is required."),
  status: z.enum(["pending", "partial", "accepted", "rejected"]),
  remarks: z.string().optional(),
});
const inspectSchema = z.object({
  quality_status: z.enum(QUALITY),
  status: z.enum(["accepted", "rejected", "partial", "pending"]),
  quantity_received: quantity,
  remarks: z.string().optional(),
});

function DeliveryFormModal({ open, delivery, onClose, onSaved }) {
  const editing = Boolean(delivery);
  const lookups = useProcurementLookups({ purchaseOrders: open });
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(createSchema),
    values: open
      ? {
          purchase_order_id: delivery?.purchase_order_id || "",
          material: delivery?.material || "",
          quantity_received: delivery?.quantity_received ?? 1,
          quality_status: delivery?.quality_status || "passed",
          delivery_date: toDateInput(delivery?.delivery_date),
          status: ["pending", "partial", "accepted", "rejected"].includes(delivery?.status) ? delivery.status : "accepted",
          remarks: delivery?.remarks || "",
        }
      : undefined,
  });
  const errors = form.formState.errors;
  const poId = form.watch("purchase_order_id");
  const po = lookups.getPurchaseOrder(poId);

  function onPoChange(event) {
    const selected = lookups.getPurchaseOrder(event.target.value);
    if (selected) {
      form.setValue("material", selected.materials || "");
      form.setValue("quantity_received", selected.quantity || 1);
    }
  }

  const submit = form.handleSubmit(async (values) => {
    const payload = { ...values, delivery_date: dateInputToIso(values.delivery_date), remarks: values.remarks || undefined };
    if (editing) {
      // DeliveryUpdate does not accept purchase_order_id or material.
      const update = {
        quantity_received: payload.quantity_received,
        quality_status: payload.quality_status,
        delivery_date: payload.delivery_date,
        status: payload.status,
        remarks: payload.remarks,
      };
      const result = await run("save", () => updateDelivery(getId(delivery), update), { success: "Delivery updated and inventory reconciled.", error: "Unable to update delivery." });
      if (result) onSaved();
      return;
    }
    const result = await run("save", () => createDelivery(payload), { success: "Delivery recorded and inventory updated.", error: "Unable to record delivery." });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="delivery-form" type="submit">{pending ? "Saving..." : "Save delivery"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? "Edit delivery" : "Record delivery"}
      description="Accepted quantities are added to inventory by the backend."
    >
      <form className="grid gap-4 sm:grid-cols-2" id="delivery-form" noValidate onSubmit={submit}>
        <div className="sm:col-span-2">
          <Select disabled={editing} label="Purchase order" {...form.register("purchase_order_id", { onChange: onPoChange })} error={errors.purchase_order_id?.message}>
            <option value="">Select purchase order</option>
            {lookups.purchaseOrders.map((item) => (
              <option key={getId(item)} value={getId(item)}>
                {item.po_number} · {item.materials} · {formatStatus(item.status)}
              </option>
            ))}
          </Select>
          {po ? <p className="mt-1 text-sm text-muted">Ordered {formatNumber(po.quantity)} for {po.project}. Receiving less marks the delivery partial.</p> : null}
        </div>
        <Input disabled={editing} label="Material" {...form.register("material")} error={errors.material?.message} />
        <Input label="Quantity received" min="0" step="any" type="number" {...form.register("quantity_received")} error={errors.quantity_received?.message} />
        <Select label="Quality inspection" {...form.register("quality_status")}>
          {QUALITY.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Select label="Delivery status" {...form.register("status")}>
          {["accepted", "partial", "pending", "rejected"].map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input label="Delivery date" type="date" {...form.register("delivery_date")} error={errors.delivery_date?.message} />
        <div className="sm:col-span-2"><Textarea label="Remarks" {...form.register("remarks")} /></div>
      </form>
    </Modal>
  );
}

function InspectionModal({ delivery, onClose, onSaved }) {
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(inspectSchema),
    values: delivery
      ? {
          quality_status: delivery.quality_status === "failed" ? "failed" : "passed",
          status: delivery.quality_status === "failed" ? "rejected" : "accepted",
          quantity_received: delivery.quantity_received || 1,
          remarks: delivery.remarks || "",
        }
      : undefined,
  });
  const quality = form.watch("quality_status");

  const submit = form.handleSubmit(async (values) => {
    // Same mapping as Angular saveQualityInspection: passed -> accepted, failed -> rejected.
    const status = values.quality_status === "passed" ? "accepted" : values.quality_status === "failed" ? "rejected" : values.status;
    const result = await run("inspect", () => updateDelivery(getId(delivery), { ...values, status, remarks: values.remarks || undefined }), {
      success: values.quality_status === "passed" ? "Inspection passed. Stock added to inventory." : `Inspection recorded as ${values.quality_status}.`,
      error: "Unable to record inspection.",
    });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="inspection-form" type="submit">{pending ? "Saving..." : "Record inspection"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(delivery)}
      size="sm"
      title={`Quality inspection · ${delivery?.material || ""}`}
    >
      <form className="space-y-4" id="inspection-form" noValidate onSubmit={submit}>
        <Select label="Result" {...form.register("quality_status")}>
          {QUALITY.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        {quality === "pending" ? (
          <Select label="Delivery status" {...form.register("status")}>
            <option value="partial">Partial</option>
            <option value="pending">Pending</option>
          </Select>
        ) : null}
        <Input label="Quantity received" min="0" step="any" type="number" {...form.register("quantity_received")} error={form.formState.errors.quantity_received?.message} />
        <Textarea label="Remarks" {...form.register("remarks")} />
      </form>
    </Modal>
  );
}

export function DeliveriesTab() {
  const { user } = useAuth();
  const list = useProcurementList(getDeliveries);
  const { run } = useAction();
  const [form, setForm] = useState({ open: false, delivery: null });
  const [inspecting, setInspecting] = useState(null);
  const [details, setDetails] = useState(null);
  const canReceive = can.procurementStoreManager(user);

  async function accept(delivery) {
    await run(
      `accept-${getId(delivery)}`,
      () => updateDelivery(getId(delivery), { status: "accepted", quality_status: "passed", quantity_received: delivery.quantity_received || 1 }),
      { success: `Delivery of ${delivery.material} accepted. Stock added to inventory.`, error: "Unable to accept delivery.", onSuccess: list.reload },
    );
  }

  const columns = [
    { key: "po_number", header: "PO", render: (row) => row.po_number || "Not set" },
    { key: "vendor_name", header: "Vendor", render: (row) => row.vendor_name || "Not set" },
    { key: "material", header: "Material", render: (row) => `${row.material} · ${formatNumber(row.quantity_received)}` },
    { key: "tracking", header: "Tracking / vehicle", render: (row) => [row.tracking_number, row.vehicle_number].filter(Boolean).join(" / ") || "Not set" },
    { key: "delivery_date", header: "Delivered", render: (row) => formatDate(row.delivery_date) },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "quality_status", header: "Quality", render: (row) => <StatusBadge status={row.quality_status} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions>
          <Button onClick={() => setDetails(row)} size="sm" variant="secondary">View</Button>
          {canReceive ? <Button onClick={() => setInspecting(row)} size="sm" variant="secondary">Inspect QA</Button> : null}
          {canReceive && AWAITING_RECEIPT.includes(row.status) ? <Button onClick={() => accept(row)} size="sm">Accept &amp; stock</Button> : null}
          {canReceive ? <Button onClick={() => setForm({ open: true, delivery: row })} size="sm" variant="secondary">Edit</Button> : null}
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ListSection
        addLabel="Record delivery"
        columns={columns}
        emptyDescription="Deliveries appear when vendors dispatch goods or when a receipt is recorded."
        emptyTitle="No deliveries"
        exportName="deliveries"
        getRowId={getId}
        list={list}
        onAdd={canReceive ? () => setForm({ open: true, delivery: null }) : undefined}
        searchPlaceholder="Search material or status..."
        statusOptions={DELIVERY_STATUSES}
        title="Deliveries"
      />
      <DeliveryFormModal
        delivery={form.delivery}
        onClose={() => setForm({ open: false, delivery: null })}
        onSaved={() => { setForm({ open: false, delivery: null }); list.reload(); }}
        open={form.open}
      />
      <InspectionModal delivery={inspecting} onClose={() => setInspecting(null)} onSaved={() => { setInspecting(null); list.reload(); }} />
      <Modal onClose={() => setDetails(null)} open={Boolean(details)} title={`Delivery · ${details?.material || ""}`}>
        {details ? (
          <DetailList
            items={[
              ["Purchase order", details.po_number],
              ["Vendor", details.vendor_name],
              ["Project", details.project],
              ["Quantity received", formatNumber(details.quantity_received)],
              ["Quality", <StatusBadge key="q" status={details.quality_status} />],
              ["Status", <StatusBadge key="s" status={details.status} />],
              ["Dispatch date", formatDate(details.dispatch_date)],
              ["Delivery date", formatDate(details.delivery_date)],
              ["Vehicle", details.vehicle_number],
              ["Tracking", details.tracking_number],
              ["Remarks", details.remarks],
              ["Updated", formatDateTime(details.updated_at)],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
