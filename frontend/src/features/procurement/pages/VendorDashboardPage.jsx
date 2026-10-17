import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { TabNav } from "../../../components/common/TabNav.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { dateInputToIso, formatCurrency, formatDate, formatDateTime, formatNumber, formatStatus, getId, toDateInput } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { downloadBlob } from "../../../services/fileDownload.js";
import { changePassword } from "../../auth/services/authService.js";
import { InvoicePosition } from "../components/InvoicePosition.jsx";
import { invoiceWarnings, useInvoicePosition } from "../hooks/useInvoicePosition.js";
import { RowActions } from "../components/ListSection.jsx";
import {
  createVendorDelivery,
  createVendorInvoice,
  getVendorInvoicePreview,
  downloadInvoicePdf,
  downloadPurchaseOrderPdf,
  getVendorDashboard,
  updateVendorDelivery,
  updateVendorProfile,
  uploadInvoiceAttachment,
  vendorAcceptMaterialRequest,
  vendorAcceptPurchaseOrder,
  vendorRejectMaterialRequest,
  vendorRejectPurchaseOrder,
} from "../services/procurementService.js";

const TABS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "requests", label: "Assigned Requests" },
  { key: "orders", label: "Purchase Orders" },
  { key: "deliveries", label: "Deliveries" },
  { key: "invoices", label: "Invoices" },
  { key: "profile", label: "Profile & Security" },
].map((tab) => ({ ...tab, to: `/procurement/vendor-dashboard?tab=${tab.key}` }));

const AWAITING_RESPONSE = ["sent_to_vendor", "vendor_assigned"];
const PO_PENDING = ["created", "sent", "pending"];
const PO_ACCEPTED = ["accepted", "processing", "shipped"];
const VENDOR_DELIVERY_STATUSES = ["processing", "shipped", "delivered", "cancelled"];

function RejectModal({ target, onClose, onSaved }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const { run, pending } = useAction();

  async function submit(event) {
    event.preventDefault();
    if (reason.trim().length < 2) {
      setError("Give a reason of at least 2 characters.");
      return;
    }
    const action = target.kind === "request" ? () => vendorRejectMaterialRequest(getId(target.item), reason.trim()) : () => vendorRejectPurchaseOrder(getId(target.item), reason.trim());
    const result = await run("reject", action, { success: "Rejection sent to procurement.", error: "Unable to reject." });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="vendor-reject-form" type="submit" variant="danger">{pending ? "Sending..." : "Reject"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(target)}
      size="sm"
      title={target?.kind === "request" ? `Reject request ${target?.item?.request_id || ""}` : `Reject ${target?.item?.po_number || "purchase order"}`}
    >
      <form id="vendor-reject-form" onSubmit={submit}>
        <Textarea error={error} label="Reason" value={reason} onChange={(event) => { setReason(event.target.value); setError(""); }} />
      </form>
    </Modal>
  );
}

const deliverySchema = z.object({
  purchase_order_id: z.string().min(1, "Select an accepted purchase order."),
  quantity: z.coerce.number({ invalid_type_error: "Enter a quantity." }).gt(0, "Quantity must be greater than 0."),
  dispatch_date: z.string().min(1, "Dispatch date is required."),
  vehicle_number: z.string().max(60).optional(),
  tracking_number: z.string().max(100).optional(),
  remarks: z.string().optional(),
  status: z.enum(VENDOR_DELIVERY_STATUSES),
});

function DispatchModal({ open, purchaseOrders, initialPo, onClose, onSaved }) {
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(deliverySchema),
    values: open
      ? { purchase_order_id: getId(initialPo) || "", quantity: initialPo?.quantity || 1, dispatch_date: toDateInput(), vehicle_number: "", tracking_number: "", remarks: initialPo ? `Delivery for ${initialPo.materials}` : "", status: "shipped" }
      : undefined,
  });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    const payload = { ...values, dispatch_date: dateInputToIso(values.dispatch_date), vehicle_number: values.vehicle_number || undefined, tracking_number: values.tracking_number || undefined, remarks: values.remarks || undefined };
    const result = await run("save", () => createVendorDelivery(payload), { success: "Dispatch recorded.", error: "Unable to record dispatch." });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="dispatch-form" type="submit">{pending ? "Saving..." : "Record dispatch"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title="Dispatch delivery"
    >
      <form className="grid gap-4 sm:grid-cols-2" id="dispatch-form" noValidate onSubmit={submit}>
        <div className="sm:col-span-2">
          <Select label="Purchase order" {...form.register("purchase_order_id")} error={errors.purchase_order_id?.message}>
            <option value="">Select accepted purchase order</option>
            {purchaseOrders.map((po) => <option key={getId(po)} value={getId(po)}>{po.po_number} · {po.materials} · {formatNumber(po.quantity)}</option>)}
          </Select>
        </div>
        <Input label="Quantity" min="0" step="any" type="number" {...form.register("quantity")} error={errors.quantity?.message} />
        <Input label="Dispatch date" type="date" {...form.register("dispatch_date")} error={errors.dispatch_date?.message} />
        <Input label="Vehicle number" {...form.register("vehicle_number")} />
        <Input label="Tracking number" {...form.register("tracking_number")} />
        <Select label="Status" {...form.register("status")}>
          {VENDOR_DELIVERY_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <div className="sm:col-span-2"><Textarea label="Remarks" {...form.register("remarks")} /></div>
      </form>
    </Modal>
  );
}

function UpdateDeliveryModal({ delivery, onClose, onSaved }) {
  const { run, pending } = useAction();
  const [values, setValues] = useState({
    status: VENDOR_DELIVERY_STATUSES.includes(delivery?.status) ? delivery.status : "shipped",
    vehicle_number: delivery?.vehicle_number || "",
    tracking_number: delivery?.tracking_number || "",
    remarks: delivery?.remarks || "",
  });

  async function submit(event) {
    event.preventDefault();
    const result = await run("save", () => updateVendorDelivery(getId(delivery), values), { success: "Delivery status updated.", error: "Unable to update delivery." });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="vendor-delivery-form" type="submit">{pending ? "Saving..." : "Update"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(delivery)}
      size="sm"
      title={`Update delivery · ${delivery?.material || ""}`}
    >
      <form className="space-y-4" id="vendor-delivery-form" onSubmit={submit}>
        <Select label="Status" value={values.status} onChange={(event) => setValues({ ...values, status: event.target.value })}>
          {VENDOR_DELIVERY_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input label="Vehicle number" value={values.vehicle_number} onChange={(event) => setValues({ ...values, vehicle_number: event.target.value })} />
        <Input label="Tracking number" value={values.tracking_number} onChange={(event) => setValues({ ...values, tracking_number: event.target.value })} />
        <Textarea label="Remarks" value={values.remarks} onChange={(event) => setValues({ ...values, remarks: event.target.value })} />
      </form>
    </Modal>
  );
}

const invoiceSchema = z.object({
  purchase_order_id: z.string().min(1, "Select a purchase order."),
  invoice_number: z.string().trim().min(2, "Invoice number must be at least 2 characters.").max(80),
  invoice_date: z.string().min(1, "Invoice date is required."),
  amount: z.coerce.number({ invalid_type_error: "Enter an amount." }).min(0, "Cannot be negative."),
  gst: z.coerce.number({ invalid_type_error: "Enter GST." }).min(0, "Cannot be negative."),
});

function SubmitInvoiceModal({ open, purchaseOrders, initialPo, onClose, onSaved }) {
  const { run, pending } = useAction();
  const [file, setFile] = useState(null);
  const form = useForm({
    resolver: zodResolver(invoiceSchema),
    values: open
      ? { purchase_order_id: getId(initialPo) || "", invoice_number: "", invoice_date: toDateInput(), amount: 0, gst: 0 }
      : undefined,
  });
  const errors = form.formState.errors;

  // Bill what the site accepted; the backend refuses more than the order.
  const position = useInvoicePosition(getVendorInvoicePreview, form.watch("purchase_order_id"), form);
  const warnings = invoiceWarnings(position.data, form.watch("amount"), form.watch("gst"));

  const submit = form.handleSubmit(async (values) => {
    const result = await run(
      "save",
      async () => {
        let attachmentUrl;
        if (file) {
          try {
            attachmentUrl = (await uploadInvoiceAttachment(file)).attachment_url;
          } catch (error) {
            toast.error(getApiErrorMessage(error, "Attachment upload failed; submitting without it."));
          }
        }
        return createVendorInvoice({ ...values, invoice_date: dateInputToIso(values.invoice_date), attachment_url: attachmentUrl });
      },
      { success: `Invoice ${values.invoice_number} submitted to procurement.`, error: "Unable to submit invoice." },
    );
    if (result) {
      setFile(null);
      onSaved();
    }
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending) || warnings.some((w) => w.blocking)} form="vendor-invoice-form" type="submit">{pending ? "Submitting..." : "Submit invoice"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title="Submit invoice"
    >
      <form className="grid gap-4 sm:grid-cols-2" id="vendor-invoice-form" noValidate onSubmit={submit}>
        <div className="sm:col-span-2">
          <Select label="Purchase order" {...form.register("purchase_order_id")} error={errors.purchase_order_id?.message}>
            <option value="">Select purchase order</option>
            {purchaseOrders.map((po) => <option key={getId(po)} value={getId(po)}>{po.po_number} · {formatCurrency(po.total_cost)}</option>)}
          </Select>
        </div>
        <InvoicePosition loading={position.loading} position={position.data} warnings={warnings} />
        <Input label="Your invoice number" placeholder="e.g. SC/2026/101" {...form.register("invoice_number")} error={errors.invoice_number?.message} />
        <Input label="Invoice date" type="date" {...form.register("invoice_date")} error={errors.invoice_date?.message} />
        <Input label="Amount before GST (Rs)" min="0" step="any" type="number" {...form.register("amount")} error={errors.amount?.message} />
        <Input label="GST (Rs)" min="0" step="any" type="number" {...form.register("gst")} error={errors.gst?.message} />
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-sm font-medium text-foreground">Attachment (optional)</span>
          <input className="block w-full text-sm" onChange={(event) => setFile(event.target.files?.[0] || null)} type="file" />
        </label>
      </form>
    </Modal>
  );
}

const profileSchema = z.object({
  vendor_name: z.string().trim().min(2, "Company name must be at least 2 characters."),
  contact_person: z.string().trim().min(2, "Contact person must be at least 2 characters."),
  phone: z.string().trim().min(7, "Phone must be 7-20 characters.").max(20, "Phone must be 7-20 characters."),
  address: z.string().trim().min(2, "Address is required."),
  gst_number: z.string().max(50).optional(),
  pan_number: z.string().max(50).optional(),
  materials_supplied: z.string().optional(),
});
const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
    new_password: z.string().min(6, "New password must be at least 6 characters."),
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, { message: "Passwords do not match.", path: ["confirm_password"] });

function ProfileTab({ vendor, onSaved }) {
  const { run, pending } = useAction();
  const profile = useForm({
    resolver: zodResolver(profileSchema),
    values: {
      vendor_name: vendor?.vendor_name || "",
      contact_person: vendor?.contact_person || "",
      phone: vendor?.phone || "",
      address: vendor?.address || "",
      gst_number: vendor?.gst_number || "",
      pan_number: vendor?.pan_number || "",
      materials_supplied: (vendor?.materials_supplied || []).join(", "),
    },
  });
  const password = useForm({ resolver: zodResolver(passwordSchema), defaultValues: { current_password: "", new_password: "", confirm_password: "" } });

  const saveProfile = profile.handleSubmit(async (values) => {
    const payload = {
      ...values,
      gst_number: values.gst_number || undefined,
      pan_number: values.pan_number || undefined,
      materials_supplied: (values.materials_supplied || "").split(",").map((item) => item.trim()).filter(Boolean),
    };
    const result = await run("profile", () => updateVendorProfile(payload), { success: "Company profile updated.", error: "Unable to update profile." });
    if (result) onSaved();
  });

  const savePassword = password.handleSubmit(async (values) => {
    const result = await run("password", () => changePassword(values.current_password, values.new_password), { success: "Password changed.", error: "Unable to change password." });
    if (result) password.reset();
  });

  const pErr = profile.formState.errors;
  const pwErr = password.formState.errors;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form className="card grid gap-4 sm:grid-cols-2" noValidate onSubmit={saveProfile}>
        <h2 className="text-lg font-semibold sm:col-span-2">Company profile</h2>
        <Input label="Company name" {...profile.register("vendor_name")} error={pErr.vendor_name?.message} />
        <Input label="Contact person" {...profile.register("contact_person")} error={pErr.contact_person?.message} />
        <Input label="Phone" {...profile.register("phone")} error={pErr.phone?.message} />
        <Input disabled label="Email" value={vendor?.email || ""} />
        <div className="sm:col-span-2"><Textarea label="Address" rows={2} {...profile.register("address")} error={pErr.address?.message} /></div>
        <Input label="GST number" {...profile.register("gst_number")} />
        <Input label="PAN number" {...profile.register("pan_number")} />
        <div className="sm:col-span-2"><Input label="Materials supplied (comma separated)" {...profile.register("materials_supplied")} /></div>
        <div className="sm:col-span-2"><Button disabled={Boolean(pending)} type="submit">{pending === "profile" ? "Saving..." : "Save profile"}</Button></div>
      </form>
      <form className="card space-y-4" noValidate onSubmit={savePassword}>
        <h2 className="text-lg font-semibold">Change password</h2>
        <Input autoComplete="current-password" label="Current password" type="password" {...password.register("current_password")} error={pwErr.current_password?.message} />
        <Input autoComplete="new-password" label="New password" type="password" {...password.register("new_password")} error={pwErr.new_password?.message} />
        <Input autoComplete="new-password" label="Confirm new password" type="password" {...password.register("confirm_password")} error={pwErr.confirm_password?.message} />
        <Button disabled={Boolean(pending)} type="submit">{pending === "password" ? "Updating..." : "Update password"}</Button>
      </form>
    </div>
  );
}

export function VendorDashboardPage() {
  const [params] = useSearchParams();
  const tab = TABS.some((item) => item.key === params.get("tab")) ? params.get("tab") : "dashboard";
  const { data, loading, error, reload } = useAsyncData(getVendorDashboard, []);
  const { run } = useAction();
  const [rejecting, setRejecting] = useState(null);
  const [dispatch, setDispatch] = useState({ open: false, po: null });
  const [invoice, setInvoice] = useState({ open: false, po: null });
  const [updatingDelivery, setUpdatingDelivery] = useState(null);

  if (loading) return <LoadingState label="Loading vendor portal..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error, "Unable to load vendor data.")} onRetry={reload} />;

  const requests = data?.requests || [];
  const orders = data?.purchase_orders || [];
  const deliveries = data?.deliveries || [];
  const invoices = data?.invoices || [];
  const acceptedOrders = orders.filter((po) => PO_ACCEPTED.includes(String(po.status).toLowerCase()));
  const invoiceableOrders = orders.filter((po) => [...PO_ACCEPTED, "delivered", "received"].includes(String(po.status).toLowerCase()));
  const done = () => reload();

  const accept = (kind, item) =>
    run(`accept-${getId(item)}`, () => (kind === "request" ? vendorAcceptMaterialRequest(getId(item)) : vendorAcceptPurchaseOrder(getId(item))), {
      success: kind === "request" ? "Request accepted. Procurement can now raise a purchase order." : "Purchase order accepted.",
      error: "Unable to accept.",
      onSuccess: done,
    });
  const poPdf = (po) => run(`pdf-${getId(po)}`, async () => downloadBlob(await downloadPurchaseOrderPdf(getId(po)), `${po.po_number}.pdf`), { error: "Unable to download PDF." });
  const invoicePdf = (inv) => run(`ipdf-${getId(inv)}`, async () => downloadBlob(await downloadInvoicePdf(getId(inv)), `${inv.invoice_number}.pdf`), { error: "Unable to download PDF." });

  const stats = [
    ["Assigned requests", data?.total_assigned, "requests"],
    ["Awaiting your response", data?.pending_responses, "requests"],
    ["Purchase orders", data?.total_purchase_orders, "orders"],
    ["Pending orders", data?.pending_orders, "orders"],
    ["Pending deliveries", data?.pending_deliveries, "deliveries"],
    ["Pending invoices", data?.pending_invoices, "invoices"],
    ["Pending payments", data?.pending_payments, "invoices"],
    ["Delivered orders", data?.delivered_orders, "orders"],
  ];

  return (
    <>
      <PageHeader eyebrow="Vendor portal" onRefresh={reload} title={data?.vendor?.vendor_name || "Vendor Portal"} description="Respond to assigned requests, fulfil purchase orders and submit invoices." />
      <TabNav active={tab} label="Vendor portal sections" tabs={TABS} />

      {tab === "dashboard" ? (
        <>
          <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {stats.map(([label, value]) => <StatCard key={label} label={label} value={value ?? 0} />)}
          </section>
          <section className="card mt-6">
            <h2 className="mb-3 text-lg font-semibold">Recent notifications</h2>
            {(data?.recent_notifications || []).length ? (
              <ul className="space-y-3">
                {data.recent_notifications.map((item, index) => (
                  <li className="rounded-md border border-border p-3" key={item._id || item.id || index}>
                    <p className="font-semibold">{item.title}</p>
                    <p className="text-sm text-muted">{item.message}</p>
                    <p className="mt-1 text-xs text-muted">{formatDateTime(item.created_at)}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No recent notifications.</p>}
          </section>
        </>
      ) : null}

      {tab === "requests" ? (
        <DataTable
          columns={[
            { key: "request_id", header: "Req ID" },
            { key: "project", header: "Project" },
            { key: "material_name", header: "Material" },
            { key: "quantity", header: "Qty", render: (row) => `${formatNumber(row.quantity)} ${row.unit || ""}` },
            { key: "required_date", header: "Required", render: (row) => formatDate(row.required_date) },
            { key: "priority", header: "Priority", render: (row) => <StatusBadge status={row.priority} /> },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            {
              key: "actions",
              header: "Actions",
              render: (row) =>
                AWAITING_RESPONSE.includes(row.status) ? (
                  <RowActions>
                    <Button onClick={() => accept("request", row)} size="sm">Accept</Button>
                    <Button onClick={() => setRejecting({ kind: "request", item: row })} size="sm" variant="danger">Reject</Button>
                  </RowActions>
                ) : <span className="text-sm text-muted">{row.vendor_comment || "Responded"}</span>,
            },
          ]}
          emptyDescription="Requests assigned to you by procurement appear here."
          emptyTitle="No assigned requests"
          getRowId={getId}
          rows={requests}
        />
      ) : null}

      {tab === "orders" ? (
        <DataTable
          columns={[
            { key: "po_number", header: "PO" },
            { key: "project", header: "Project" },
            { key: "materials", header: "Materials" },
            { key: "quantity", header: "Qty", render: (row) => formatNumber(row.quantity) },
            { key: "total_cost", header: "Total", render: (row) => formatCurrency(row.total_cost) },
            { key: "expected_delivery_date", header: "Expected", render: (row) => formatDate(row.expected_delivery_date) },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            {
              key: "actions",
              header: "Actions",
              render: (row) => {
                const status = String(row.status).toLowerCase();
                return (
                  <RowActions>
                    <Button onClick={() => poPdf(row)} size="sm" variant="secondary">PDF</Button>
                    {PO_PENDING.includes(status) ? <Button onClick={() => accept("po", row)} size="sm">Accept</Button> : null}
                    {PO_PENDING.includes(status) ? <Button onClick={() => setRejecting({ kind: "po", item: row })} size="sm" variant="danger">Reject</Button> : null}
                    {PO_ACCEPTED.includes(status) ? <Button onClick={() => setDispatch({ open: true, po: row })} size="sm">Dispatch</Button> : null}
                    {invoiceableOrders.includes(row) ? <Button onClick={() => setInvoice({ open: true, po: row })} size="sm" variant="secondary">Invoice</Button> : null}
                  </RowActions>
                );
              },
            },
          ]}
          emptyDescription="Purchase orders sent to you appear here."
          emptyTitle="No purchase orders"
          getRowId={getId}
          rows={orders}
        />
      ) : null}

      {tab === "deliveries" ? (
        <>
          <div className="mb-4 flex justify-end">
            <Button disabled={!acceptedOrders.length} onClick={() => setDispatch({ open: true, po: null })}>Dispatch delivery</Button>
          </div>
          <DataTable
            columns={[
              { key: "po_number", header: "PO" },
              { key: "material", header: "Material", render: (row) => `${row.material} · ${formatNumber(row.quantity_received)}` },
              { key: "dispatch_date", header: "Dispatched", render: (row) => formatDate(row.dispatch_date) },
              { key: "tracking", header: "Tracking / vehicle", render: (row) => [row.tracking_number, row.vehicle_number].filter(Boolean).join(" / ") || "Not set" },
              { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
              { key: "quality_status", header: "Quality", render: (row) => <StatusBadge status={row.quality_status} /> },
              {
                key: "actions",
                header: "Actions",
                render: (row) => (["accepted", "rejected", "received", "cancelled"].includes(row.status) ? null : <Button onClick={() => setUpdatingDelivery(row)} size="sm" variant="secondary">Update status</Button>),
              },
            ]}
            emptyDescription="Dispatch goods against an accepted purchase order to create a delivery."
            emptyTitle="No deliveries"
            getRowId={getId}
            rows={deliveries}
          />
        </>
      ) : null}

      {tab === "invoices" ? (
        <>
          <div className="mb-4 flex justify-end">
            <Button disabled={!invoiceableOrders.length} onClick={() => setInvoice({ open: true, po: null })}>Submit invoice</Button>
          </div>
          <DataTable
            columns={[
              { key: "invoice_number", header: "Invoice" },
              { key: "amount", header: "Amount", render: (row) => formatCurrency(row.amount) },
              { key: "gst", header: "GST", render: (row) => formatCurrency(row.gst) },
              { key: "invoice_date", header: "Date", render: (row) => formatDate(row.invoice_date) },
              { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
              { key: "payment_status", header: "Payment", render: (row) => <StatusBadge status={row.payment_status} /> },
              { key: "actions", header: "Actions", render: (row) => <Button onClick={() => invoicePdf(row)} size="sm" variant="secondary">PDF</Button> },
            ]}
            emptyDescription="Invoices you submit against purchase orders appear here."
            emptyTitle="No invoices"
            getRowId={getId}
            rows={invoices}
          />
        </>
      ) : null}

      {tab === "profile" ? <ProfileTab onSaved={done} vendor={data?.vendor} /> : null}

      <RejectModal key={getId(rejecting?.item) || "none"} onClose={() => setRejecting(null)} onSaved={() => { setRejecting(null); done(); }} target={rejecting} />
      <DispatchModal
        initialPo={dispatch.po}
        onClose={() => setDispatch({ open: false, po: null })}
        onSaved={() => { setDispatch({ open: false, po: null }); done(); }}
        open={dispatch.open}
        purchaseOrders={acceptedOrders}
      />
      <SubmitInvoiceModal
        initialPo={invoice.po}
        onClose={() => setInvoice({ open: false, po: null })}
        onSaved={() => { setInvoice({ open: false, po: null }); done(); }}
        open={invoice.open}
        purchaseOrders={invoiceableOrders}
      />
      <UpdateDeliveryModal key={getId(updatingDelivery) || "none"} delivery={updatingDelivery} onClose={() => setUpdatingDelivery(null)} onSaved={() => { setUpdatingDelivery(null); done(); }} />
    </>
  );
}
