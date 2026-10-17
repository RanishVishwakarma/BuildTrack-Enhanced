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
import { formatCurrency, formatDateTime, formatStatus, getId } from "../../../lib/utils.js";
import { API_BASE_URL } from "../../../services/api.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { useProcurementList } from "../hooks/useProcurementList.js";
import { useProcurementLookups } from "../hooks/useProcurementLookups.js";
import { createPayment, getPayments, quickPayInvoice, updatePayment } from "../services/procurementService.js";
import { ListSection, RowActions } from "./ListSection.jsx";

const PAYMENT_STATUSES = ["pending", "approved", "paid"];
const paymentSchema = z.object({
  invoice_id: z.string().min(1, "Select an invoice."),
  amount: z.coerce.number({ invalid_type_error: "Enter an amount." }).min(0, "Cannot be negative."),
  status: z.enum(PAYMENT_STATUSES),
  remarks: z.string().optional(),
});

const invoiceTotal = (invoice) => Number(invoice?.amount || 0) + Number(invoice?.gst || 0);

// Records a payment against an invoice. When opened from an invoice row it
// also offers the backend's UPI QR code and quick-pay confirmation.
export function PaymentFormModal({ open, invoice, onClose, onSaved }) {
  const lookups = useProcurementLookups({ invoices: open && !invoice, vendors: open });
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(paymentSchema),
    values: open
      ? { invoice_id: getId(invoice) || "", amount: invoice ? invoiceTotal(invoice) : 0, status: "paid", remarks: invoice ? `Payment for invoice ${invoice.invoice_number}` : "" }
      : undefined,
  });
  const errors = form.formState.errors;
  const unpaid = lookups.invoices.filter((item) => item.payment_status !== "paid");
  const selected = invoice || lookups.getInvoice(form.watch("invoice_id"));

  function onInvoiceChange(event) {
    const chosen = lookups.getInvoice(event.target.value);
    if (chosen) {
      form.setValue("amount", invoiceTotal(chosen));
      form.setValue("remarks", `Payment for invoice ${chosen.invoice_number}`);
    }
  }

  const submit = form.handleSubmit(async (values) => {
    const payload = {
      ...values,
      vendor_id: selected?.vendor_id || "",
      purchase_order_id: selected?.purchase_order_id || "",
      remarks: values.remarks || undefined,
    };
    const result = await run("save", () => createPayment(payload), { success: "Payment recorded.", error: "Unable to record payment." });
    if (result) onSaved();
  });

  async function quickPay() {
    const result = await run("quick", () => quickPayInvoice(getId(invoice)), { success: `Invoice ${invoice.invoice_number} marked paid via QR.`, error: "QR payment failed." });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="payment-form" type="submit">{pending === "save" ? "Saving..." : "Record payment"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      size={invoice ? "lg" : "md"}
      title={invoice ? `Pay invoice ${invoice.invoice_number}` : "Record payment"}
    >
      <div className={invoice ? "grid gap-6 md:grid-cols-[220px_1fr]" : ""}>
        {invoice ? (
          <div className="text-center">
            <img
              alt={`UPI payment QR code for invoice ${invoice.invoice_number}`}
              className="mx-auto h-48 w-48 rounded-md border border-border"
              src={`${API_BASE_URL}/procurement/invoices/${getId(invoice)}/qr`}
            />
            <p className="mt-2 text-sm font-semibold">{formatCurrency(invoiceTotal(invoice))}</p>
            <p className="text-xs text-muted">Scan with any UPI app, then confirm below once paid.</p>
            <Button className="mt-3 w-full" disabled={Boolean(pending)} onClick={quickPay} size="sm" variant="secondary">
              {pending === "quick" ? "Confirming..." : "Confirm QR payment received"}
            </Button>
          </div>
        ) : null}
        <form className="grid gap-4 sm:grid-cols-2" id="payment-form" noValidate onSubmit={submit}>
          <div className="sm:col-span-2">
            {invoice ? (
              <p className="text-sm text-muted">Vendor: {lookups.vendorName(invoice.vendor_id, invoice)}</p>
            ) : (
              <Select label="Invoice" {...form.register("invoice_id", { onChange: onInvoiceChange })} error={errors.invoice_id?.message}>
                <option value="">Select unpaid invoice</option>
                {unpaid.map((item) => (
                  <option key={getId(item)} value={getId(item)}>{item.invoice_number} · {formatCurrency(invoiceTotal(item))}</option>
                ))}
              </Select>
            )}
          </div>
          <Input label="Amount (Rs)" min="0" step="any" type="number" {...form.register("amount")} error={errors.amount?.message} />
          <Select label="Status" {...form.register("status")}>
            {PAYMENT_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
          </Select>
          <div className="sm:col-span-2"><Textarea label="Remarks" {...form.register("remarks")} /></div>
        </form>
      </div>
    </Modal>
  );
}

function EditPaymentModal({ payment, onClose, onSaved }) {
  const [status, setStatus] = useState(payment?.status || "pending");
  const [remarks, setRemarks] = useState(payment?.remarks || "");
  const { run, pending } = useAction();

  async function submit(event) {
    event.preventDefault();
    const result = await run("save", () => updatePayment(getId(payment), { status, remarks: remarks || undefined }), {
      success: status === "paid" ? "Payment marked paid; invoice updated." : "Payment updated.",
      error: "Unable to update payment.",
    });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="edit-payment-form" type="submit">{pending ? "Saving..." : "Save"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(payment)}
      size="sm"
      title="Update payment"
    >
      <form className="space-y-4" id="edit-payment-form" onSubmit={submit}>
        <Select label="Status" value={status} onChange={(event) => setStatus(event.target.value)}>
          {PAYMENT_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Textarea label="Remarks" value={remarks} onChange={(event) => setRemarks(event.target.value)} />
      </form>
    </Modal>
  );
}

export function PaymentsTab() {
  const { user } = useAuth();
  const list = useProcurementList(getPayments);
  const lookups = useProcurementLookups({ vendors: true, purchaseOrders: true, invoices: true });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [details, setDetails] = useState(null);
  const isFinance = can.procurementFinance(user);

  const columns = [
    { key: "invoice", header: "Invoice", render: (row) => lookups.invoiceNumber(row.invoice_id, row) },
    { key: "vendor", header: "Vendor", render: (row) => lookups.vendorName(row.vendor_id, row) },
    { key: "po", header: "PO", render: (row) => lookups.poNumber(row.purchase_order_id, row) },
    { key: "amount", header: "Amount", render: (row) => formatCurrency(row.amount) },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "paid_at", header: "Paid at", render: (row) => (row.paid_at ? formatDateTime(row.paid_at) : "Not paid") },
    { key: "remarks", header: "Remarks" },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions>
          <Button onClick={() => setDetails(row)} size="sm" variant="secondary">View</Button>
          {isFinance ? <Button onClick={() => setEditing(row)} size="sm" variant="secondary">Edit</Button> : null}
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ListSection
        addLabel="Record payment"
        columns={columns}
        emptyDescription="Payments recorded against invoices appear here."
        emptyTitle="No payments"
        exportName="payments"
        getRowId={getId}
        list={list}
        onAdd={isFinance ? () => setCreating(true) : undefined}
        searchPlaceholder="Search status or remarks..."
        statusOptions={PAYMENT_STATUSES}
        title="Payments"
      />
      <PaymentFormModal onClose={() => setCreating(false)} onSaved={() => { setCreating(false); list.reload(); lookups.reload(); }} open={creating} />
      <EditPaymentModal key={getId(editing) || "none"} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); }} payment={editing} />
      <Modal onClose={() => setDetails(null)} open={Boolean(details)} title="Payment">
        {details ? (
          <DetailList
            items={[
              ["Invoice", lookups.invoiceNumber(details.invoice_id, details)],
              ["Vendor", lookups.vendorName(details.vendor_id, details)],
              ["Purchase order", lookups.poNumber(details.purchase_order_id, details)],
              ["Amount", formatCurrency(details.amount)],
              ["Status", <StatusBadge key="s" status={details.status} />],
              ["Paid at", formatDateTime(details.paid_at)],
              ["Remarks", details.remarks],
              ["Created", formatDateTime(details.created_at)],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
