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
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { can } from "../../../lib/roles.js";
import { formatDateTime, getId } from "../../../lib/utils.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { useProcurementList } from "../hooks/useProcurementList.js";
import { createVendor, createVendorWithAccount, deleteVendor, getVendors, updateVendor } from "../services/procurementService.js";
import { ListSection, RowActions } from "./ListSection.jsx";

// Field rules from VendorBase in backend/app/modules/procurement/models.py.
const vendorSchema = z
  .object({
    vendor_name: z.string().trim().min(2, "Vendor name must be at least 2 characters."),
    contact_person: z.string().trim().min(2, "Contact person must be at least 2 characters."),
    phone: z.string().trim().min(7, "Phone must be 7-20 characters.").max(20, "Phone must be 7-20 characters."),
    email: z.string().trim().email("Enter a valid email."),
    address: z.string().trim().min(2, "Address is required."),
    gst_number: z.string().max(50).optional(),
    pan_number: z.string().max(50).optional(),
    materials_supplied: z.string().trim().min(1, "List at least one material."),
    rating: z.coerce.number().min(0, "Rating must be 0-5.").max(5, "Rating must be 0-5."),
    status: z.enum(["active", "inactive"]),
    create_login_account: z.boolean(),
    password: z.string().optional(),
  })
  .refine((values) => !values.create_login_account || (values.password || "").length >= 6, {
    message: "Password must be at least 6 characters to create a login.",
    path: ["password"],
  });

function VendorFormModal({ open, vendor, onClose, onSaved }) {
  const { user } = useAuth();
  const { run, pending } = useAction();
  const editing = Boolean(vendor);
  const form = useForm({
    resolver: zodResolver(vendorSchema),
    values: open
      ? {
          vendor_name: vendor?.vendor_name || "",
          contact_person: vendor?.contact_person || "",
          phone: vendor?.phone || "",
          email: vendor?.email || "",
          address: vendor?.address || "",
          gst_number: vendor?.gst_number || "",
          pan_number: vendor?.pan_number || "",
          materials_supplied: (vendor?.materials_supplied || []).join(", "),
          rating: vendor?.rating ?? 4,
          status: vendor?.status || "active",
          create_login_account: false,
          password: "",
        }
      : undefined,
  });
  const errors = form.formState.errors;
  const createLogin = form.watch("create_login_account");

  const submit = form.handleSubmit(async ({ create_login_account: withLogin, password, ...values }) => {
    const payload = {
      ...values,
      gst_number: values.gst_number || undefined,
      pan_number: values.pan_number || undefined,
      materials_supplied: values.materials_supplied.split(",").map((item) => item.trim()).filter(Boolean),
    };
    const action = editing
      ? () => updateVendor(getId(vendor), payload)
      : withLogin
        ? () => createVendorWithAccount({ ...payload, create_login_account: true, password })
        : () => createVendor(payload);
    const result = await run("save", action, {
      success: (response) => response?.message || (editing ? "Vendor updated." : "Vendor added."),
      error: editing ? "Unable to update vendor." : "Unable to add vendor.",
    });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="vendor-form" type="submit">{pending ? "Saving..." : "Save vendor"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? `Edit ${vendor.vendor_name}` : "Add vendor"}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="vendor-form" noValidate onSubmit={submit}>
        <Input label="Vendor name" {...form.register("vendor_name")} error={errors.vendor_name?.message} />
        <Input label="Contact person" {...form.register("contact_person")} error={errors.contact_person?.message} />
        <Input label="Phone" type="tel" {...form.register("phone")} error={errors.phone?.message} />
        <Input label="Email" type="email" {...form.register("email")} error={errors.email?.message} />
        <div className="sm:col-span-2"><Textarea label="Address" rows={2} {...form.register("address")} error={errors.address?.message} /></div>
        <Input label="GST number" {...form.register("gst_number")} />
        <Input label="PAN number" {...form.register("pan_number")} />
        <div className="sm:col-span-2">
          <Input label="Materials supplied (comma separated)" placeholder="Cement, Steel, Sand" {...form.register("materials_supplied")} error={errors.materials_supplied?.message} />
        </div>
        <Input label="Rating (0-5)" max="5" min="0" step="0.1" type="number" {...form.register("rating")} error={errors.rating?.message} />
        <Select label="Status" {...form.register("status")}>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </Select>
        {!editing && can.adminOnly(user) ? (
          <div className="space-y-3 rounded-md border border-border p-3 sm:col-span-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" {...form.register("create_login_account")} />
              Also create a vendor portal login for this email
            </label>
            {createLogin ? <Input autoComplete="new-password" label="Login password" type="password" {...form.register("password")} error={errors.password?.message} /> : null}
          </div>
        ) : null}
      </form>
    </Modal>
  );
}

export function VendorsTab() {
  const { user } = useAuth();
  const list = useProcurementList(getVendors);
  const { run } = useAction();
  const [form, setForm] = useState({ open: false, vendor: null });
  const [details, setDetails] = useState(null);
  const isPM = can.procurementProjectManager(user);

  async function remove(vendor) {
    if (!confirmAction(`Delete vendor ${vendor.vendor_name}? This cannot be undone.`)) return;
    await run("delete", () => deleteVendor(getId(vendor)), { success: "Vendor deleted.", error: "Unable to delete vendor.", onSuccess: list.reload });
  }

  const columns = [
    { key: "vendor_name", header: "Vendor", render: (row) => <span className="font-semibold">{row.vendor_name}</span> },
    { key: "contact_person", header: "Contact" },
    { key: "phone", header: "Phone" },
    { key: "email", header: "Email" },
    { key: "materials_supplied", header: "Materials", render: (row) => (row.materials_supplied || []).join(", ") || "Not set" },
    { key: "rating", header: "Rating", render: (row) => `${Number(row.rating || 0).toFixed(1)} / 5` },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions>
          <Button onClick={() => setDetails(row)} size="sm" variant="secondary">View</Button>
          {isPM ? <Button onClick={() => setForm({ open: true, vendor: row })} size="sm" variant="secondary">Edit</Button> : null}
          {can.adminOnly(user) ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ListSection
        addLabel="Add vendor"
        columns={columns}
        emptyDescription="Add suppliers so material requests can be assigned to them."
        emptyTitle="No vendors"
        exportName="vendors"
        getRowId={getId}
        list={list}
        onAdd={isPM ? () => setForm({ open: true, vendor: null }) : undefined}
        searchPlaceholder="Search vendors..."
        statusOptions={["active", "inactive"]}
        title="Vendors"
      />
      <VendorFormModal
        onClose={() => setForm({ open: false, vendor: null })}
        onSaved={() => { setForm({ open: false, vendor: null }); list.reload(); }}
        open={form.open}
        vendor={form.vendor}
      />
      <Modal onClose={() => setDetails(null)} open={Boolean(details)} title={details?.vendor_name || "Vendor"}>
        {details ? (
          <DetailList
            items={[
              ["Contact person", details.contact_person],
              ["Phone", details.phone],
              ["Email", details.email],
              ["Address", details.address],
              ["GST number", details.gst_number],
              ["PAN number", details.pan_number],
              ["Materials supplied", (details.materials_supplied || []).join(", ")],
              ["Rating", `${Number(details.rating || 0).toFixed(1)} / 5`],
              ["Status", <StatusBadge key="s" status={details.status} />],
              ["Created", formatDateTime(details.created_at)],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
