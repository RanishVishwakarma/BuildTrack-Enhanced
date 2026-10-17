import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { z } from "zod";
import { DetailList } from "../../../components/common/DetailList.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { describeSupply } from "../../../lib/gst.js";
import { can } from "../../../lib/roles.js";
import { dateInputToIso, formatCurrency, formatDate, formatDateTime, getId, toDateInput } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { downloadBlob } from "../../../services/fileDownload.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { useProcurementList } from "../hooks/useProcurementList.js";
import { useProcurementLookups } from "../hooks/useProcurementLookups.js";
import {
  createInvoice,
  deleteInvoice,
  downloadInvoicePdf,
  getInvoiceMatch,
  getInvoicePreview,
  getInvoices,
  invoiceAction,
  uploadInvoiceAttachment,
} from "../services/procurementService.js";
import { InvoicePosition } from "./InvoicePosition.jsx";
import { invoiceWarnings, useInvoicePosition } from "../hooks/useInvoicePosition.js";
import { ListSection, RowActions } from "./ListSection.jsx";
import { PaymentFormModal } from "./PaymentsTab.jsx";

const INVOICE_STATUSES = ["pending", "verified", "approved", "rejected"];
const money = z.coerce.number({ invalid_type_error: "Enter an amount." }).min(0, "Cannot be negative.");
const invoiceSchema = z.object({
  purchase_order_id: z.string().min(1, "Select a purchase order."),
  invoice_number: z.string().trim().min(2, "Invoice number must be at least 2 characters.").max(80),
  amount: money,
  gst: money,
  invoice_date: z.string().min(1, "Invoice date is required."),
});

function InvoiceFormModal({ open, onClose, onSaved }) {
  const lookups = useProcurementLookups({ purchaseOrders: open, vendors: open });
  const { run, pending } = useAction();
  const [attachment, setAttachment] = useState({ url: "", uploading: false });
  const form = useForm({
    resolver: zodResolver(invoiceSchema),
    values: open ? { purchase_order_id: "", invoice_number: "", amount: 0, gst: 0, invoice_date: toDateInput() } : undefined,
  });
  const errors = form.formState.errors;
  const poId = form.watch("purchase_order_id");
  const po = lookups.getPurchaseOrder(poId);
  // Amount and GST are prefilled from what the site accepted, not the PO.
  const position = useInvoicePosition(getInvoicePreview, poId, form);
  const warnings = invoiceWarnings(position.data, form.watch("amount"), form.watch("gst"));

  async function onFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setAttachment({ url: "", uploading: true });
    try {
      const result = await uploadInvoiceAttachment(file);
      setAttachment({ url: result.attachment_url, uploading: false });
      toast.success("Attachment uploaded.");
    } catch (error) {
      setAttachment({ url: "", uploading: false });
      toast.error(getApiErrorMessage(error, "Attachment upload failed."));
    }
  }

  const submit = form.handleSubmit(async (values) => {
    const payload = {
      ...values,
      vendor_id: po?.vendor_id || "",
      invoice_date: dateInputToIso(values.invoice_date),
      attachment_url: attachment.url || undefined,
    };
    const result = await run("save", () => createInvoice(payload), { success: "Invoice recorded.", error: "Unable to record invoice." });
    if (result) {
      setAttachment({ url: "", uploading: false });
      onSaved();
    }
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending) || attachment.uploading || warnings.some((w) => w.blocking)} form="invoice-form" type="submit">{pending ? "Saving..." : "Record invoice"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title="Record vendor invoice"
    >
      <form className="grid gap-4 sm:grid-cols-2" id="invoice-form" noValidate onSubmit={submit}>
        <p className="text-sm text-muted sm:col-span-2">
          Enter the bill the vendor sent you. Vendors with a portal login can submit it themselves.
        </p>
        <div className="sm:col-span-2">
          <Select label="Purchase order" {...form.register("purchase_order_id")} error={errors.purchase_order_id?.message}>
            <option value="">Select purchase order</option>
            {lookups.purchaseOrders.map((item) => (
              <option key={getId(item)} value={getId(item)}>{item.po_number} · {item.materials} · {formatCurrency(item.total_cost)}</option>
            ))}
          </Select>
          {po ? <p className="mt-1 text-sm text-muted">Vendor: {lookups.vendorName(po.vendor_id, po)}</p> : null}
        </div>
        <InvoicePosition loading={position.loading} position={position.data} warnings={warnings} />
        <Input label="Vendor invoice number" placeholder="As printed on the bill" {...form.register("invoice_number")} error={errors.invoice_number?.message} />
        <Input label="Invoice date" type="date" {...form.register("invoice_date")} error={errors.invoice_date?.message} />
        <Input label="Amount before GST (Rs)" min="0" step="any" type="number" {...form.register("amount")} error={errors.amount?.message} />
        <Input label="GST (Rs)" min="0" step="any" type="number" {...form.register("gst")} error={errors.gst?.message} />
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-sm font-medium text-foreground">Copy of the bill (optional)</span>
          <input className="block w-full text-sm" onChange={onFile} type="file" />
          {attachment.uploading ? <span className="mt-1 block text-sm text-muted">Uploading...</span> : null}
          {attachment.url ? <span className="mt-1 block text-sm text-success">Uploaded: {attachment.url}</span> : null}
        </label>
      </form>
    </Modal>
  );
}

function InvoiceActionModal({ state, onClose, onSaved }) {
  const [action, setAction] = useState(state?.action || "verify");
  const [comments, setComments] = useState("");
  const { run, pending } = useAction();
  const invoice = state?.invoice;
  const match = useAsyncData(() => getInvoiceMatch(getId(invoice)), [getId(invoice)], { enabled: Boolean(invoice) });
  const flags = match.data?.flags || [];
  const needsReason = action !== "reject" && flags.length > 0;

  async function submit(event) {
    event.preventDefault();
    if (needsReason && !comments.trim()) {
      toast.error("Explain in the comments why this invoice is accepted despite the differences.");
      return;
    }
    const result = await run("action", () => invoiceAction(getId(invoice), action, { comments: comments || undefined }), {
      success: `Invoice ${invoice.invoice_number} ${action === "verify" ? "verified" : action === "approve" ? "approved" : "rejected"}.`,
      error: "Unable to update invoice.",
    });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="invoice-action-form" type="submit" variant={action === "reject" ? "danger" : "primary"}>{pending ? "Saving..." : "Submit"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(invoice)}
      title={`Review invoice ${invoice?.invoice_number || ""}`}
    >
      <form className="space-y-4" id="invoice-action-form" onSubmit={submit}>
        {match.loading ? <p className="text-sm text-muted">Checking order and deliveries...</p> : null}
        {match.data && !match.data.missing_po ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-1 font-medium" scope="col"></th>
                <th className="py-1 text-right font-medium" scope="col">Order</th>
                <th className="py-1 text-right font-medium" scope="col">Received</th>
                <th className="py-1 text-right font-medium" scope="col">This invoice</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th className="py-1 text-left font-medium" scope="row">Amount</th>
                <td className="text-right">{formatCurrency(match.data.po_subtotal)}</td>
                <td className="text-right">{formatCurrency(match.data.delivered_value)}</td>
                <td className="text-right font-semibold">{formatCurrency(match.data.amount)}</td>
              </tr>
              <tr>
                <th className="py-1 text-left font-medium" scope="row">GST</th>
                <td className="text-right">{match.data.gst_rate != null ? `${match.data.gst_rate}%` : "Not set"}</td>
                <td className="text-right">{match.data.expected_gst != null ? formatCurrency(match.data.expected_gst) : ""}</td>
                <td className="text-right font-semibold">{formatCurrency(match.data.gst)}</td>
              </tr>
              <tr>
                <th className="py-1 text-left font-medium" scope="row">Other invoices</th>
                <td className="text-right" colSpan={3}>{formatCurrency(match.data.previously_invoiced)}</td>
              </tr>
            </tbody>
          </table>
        ) : null}
        {match.data ? (
          flags.length ? (
            <ul className="space-y-1 rounded-md border border-warning p-3 text-sm text-warning">
              {flags.map((flag) => <li key={flag}>{flag}</li>)}
            </ul>
          ) : (
            <p className="text-sm text-success">Matches the order and accepted deliveries.</p>
          )
        ) : null}
        <Select label="Action" value={action} onChange={(event) => setAction(event.target.value)}>
          <option value="verify">Verify</option>
          <option value="approve">Approve</option>
          <option value="reject">Reject</option>
        </Select>
        <Textarea
          label={needsReason ? "Reason for accepting despite the differences" : "Comments"}
          value={comments}
          onChange={(event) => setComments(event.target.value)}
        />
      </form>
    </Modal>
  );
}

export function InvoicesTab() {
  const { user } = useAuth();
  const list = useProcurementList(getInvoices);
  const lookups = useProcurementLookups({ vendors: true, purchaseOrders: true });
  const { run } = useAction();
  const [creating, setCreating] = useState(false);
  const [reviewing, setReviewing] = useState(null);
  const [paying, setPaying] = useState(null);
  const [details, setDetails] = useState(null);
  const isFinance = can.procurementFinance(user);
  // Angular allowed Finance and Project Managers to raise invoices; POST /invoices has no role check.
  const canCreate = isFinance || can.procurementProjectManager(user);

  async function pdf(invoice) {
    await run(`pdf-${getId(invoice)}`, async () => downloadBlob(await downloadInvoicePdf(getId(invoice)), `${invoice.invoice_number || "invoice"}.pdf`), { error: "Unable to download invoice PDF." });
  }

  async function remove(invoice) {
    if (!confirmAction(`Delete invoice ${invoice.invoice_number}? This cannot be undone.`)) return;
    await run("delete", () => deleteInvoice(getId(invoice)), { success: "Invoice deleted.", error: "Unable to delete invoice.", onSuccess: list.reload });
  }

  const columns = [
    { key: "invoice_number", header: "Invoice", render: (row) => <span className="font-semibold">{row.invoice_number}</span> },
    { key: "vendor", header: "Vendor", render: (row) => lookups.vendorName(row.vendor_id, row) },
    { key: "po", header: "PO", render: (row) => lookups.poNumber(row.purchase_order_id, row) },
    { key: "amount", header: "Amount", render: (row) => formatCurrency(row.amount) },
    { key: "gst", header: "GST", render: (row) => formatCurrency(row.gst) },
    { key: "total", header: "Total", render: (row) => formatCurrency(Number(row.amount || 0) + Number(row.gst || 0)) },
    { key: "invoice_date", header: "Date", render: (row) => formatDate(row.invoice_date) },
    { key: "payment_status", header: "Payment", render: (row) => <StatusBadge status={row.payment_status} /> },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions>
          <Button onClick={() => setDetails(row)} size="sm" variant="secondary">View</Button>
          <Button onClick={() => pdf(row)} size="sm" variant="secondary">PDF</Button>
          {isFinance && !["approved", "rejected"].includes(row.status) ? (
            <Button onClick={() => setReviewing({ invoice: row, action: row.status === "verified" ? "approve" : "verify" })} size="sm" variant="secondary">Review</Button>
          ) : null}
          {isFinance && row.payment_status !== "paid" ? <Button onClick={() => setPaying(row)} size="sm">Pay</Button> : null}
          {can.adminOnly(user) ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ListSection
        addLabel="Record invoice"
        columns={columns}
        emptyDescription="Vendors submit invoices from their portal, or you record the bills they send."
        emptyTitle="No invoices"
        exportName="invoices"
        getRowId={getId}
        list={list}
        onAdd={canCreate ? () => setCreating(true) : undefined}
        searchPlaceholder="Search invoices..."
        statusOptions={INVOICE_STATUSES}
        title="Invoices"
      />
      <InvoiceFormModal onClose={() => setCreating(false)} onSaved={() => { setCreating(false); list.reload(); }} open={creating} />
      <InvoiceActionModal key={getId(reviewing?.invoice) || "none"} onClose={() => setReviewing(null)} onSaved={() => { setReviewing(null); list.reload(); }} state={reviewing} />
      <PaymentFormModal invoice={paying} onClose={() => setPaying(null)} onSaved={() => { setPaying(null); list.reload(); }} open={Boolean(paying)} />
      <Modal onClose={() => setDetails(null)} open={Boolean(details)} title={`Invoice ${details?.invoice_number || ""}`}>
        {details ? (
          <DetailList
            items={[
              ["Vendor", lookups.vendorName(details.vendor_id, details)],
              ["Purchase order", lookups.poNumber(details.purchase_order_id, details)],
              ["Amount", formatCurrency(details.amount)],
              ["GST", details.gst_rate != null ? `${formatCurrency(details.gst)} (${details.gst_rate}%)` : formatCurrency(details.gst)],
              ...(details.supply_type === "intra_state"
                ? [["CGST + SGST", `${formatCurrency(details.cgst)} + ${formatCurrency(details.sgst)}`]]
                : details.supply_type === "inter_state"
                  ? [["IGST", formatCurrency(details.igst)]]
                  : []),
              ["Tax type", describeSupply(details.supply_type)],
              ["Total", formatCurrency(Number(details.amount || 0) + Number(details.gst || 0))],
              ["Invoice date", formatDate(details.invoice_date)],
              ["Status", <StatusBadge key="s" status={details.status} />],
              ["Payment", <StatusBadge key="p" status={details.payment_status} />],
              ["Verification comments", details.verification_comments],
              ["Attachment", details.attachment_url],
              ["Created", formatDateTime(details.created_at)],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
