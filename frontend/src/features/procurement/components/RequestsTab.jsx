import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { DetailList } from "../../../components/common/DetailList.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction, confirmAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { can } from "../../../lib/roles.js";
import { addDays, dateInputToIso, formatDate, formatDateTime, formatNumber, getId, projectName, toDateInput } from "../../../lib/utils.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { useProcurementList } from "../hooks/useProcurementList.js";
import { useProcurementLookups } from "../hooks/useProcurementLookups.js";
import {
  approveMaterialRequest,
  assignVendorToMaterialRequest,
  createMaterialRequest,
  deleteMaterialRequest,
  getMaterialRequests,
  getMaterials,
  updateMaterialRequest,
} from "../services/procurementService.js";
import { ListSection, RowActions } from "./ListSection.jsx";
import { PurchaseOrderFormModal } from "./PurchaseOrdersTab.jsx";

const REQUEST_STATUSES = [
  "pending", "approved", "rejected", "sent_to_vendor", "vendor_accepted", "vendor_rejected", "po_generated",
  "po_sent", "po_accepted", "partially_delivered", "delivered", "paid", "completed",
];
// backend assign_vendor_to_material_request accepts these statuses
const ASSIGNABLE = ["approved", "vendor_assigned", "sent_to_vendor"];

const requestSchema = z.object({
  project_id: z.string().min(1, "Select a project."),
  material_name: z.string().trim().min(2, "Material name must be at least 2 characters."),
  quantity: z.coerce.number({ invalid_type_error: "Enter a quantity." }).gt(0, "Quantity must be greater than 0."),
  unit: z.string().trim().optional(),
  required_date: z.string().min(1, "Required date is needed."),
  priority: z.enum(["low", "medium", "high"]),
  remarks: z.string().optional(),
});

function RequestFormModal({ open, request, onClose, onSaved }) {
  const { projects } = useProjectOptions({ enabled: open });
  const materials = useAsyncData(getMaterials, [], { initialData: [], enabled: open });
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(requestSchema),
    values: open
      ? {
          project_id: request?.project_id || request?.project || "",
          material_name: request?.material_name || "",
          quantity: request?.quantity ?? 1,
          unit: request?.unit || "",
          required_date: request?.required_date ? toDateInput(request.required_date) : addDays(7),
          priority: request?.priority || "medium",
          remarks: request?.remarks || "",
        }
      : undefined,
  });
  const errors = form.formState.errors;
  // Legacy requests may only carry a project name; keep it selectable.
  const legacyProject = request && !request.project_id && request.project ? request.project : null;

  const submit = form.handleSubmit(async (values) => {
    const project = projects.find((item) => getId(item) === values.project_id);
    const material = (materials.data || []).find((item) => (item.material_name || item.material) === values.material_name);
    const payload = {
      project: project ? projectName(project) : legacyProject || values.project_id,
      project_id: project ? values.project_id : request?.project_id,
      material_name: values.material_name.trim(),
      material_id: material ? getId(material) : request?.material_id,
      unit: values.unit || material?.unit || undefined,
      quantity: values.quantity,
      required_date: dateInputToIso(values.required_date),
      priority: values.priority,
      remarks: values.remarks || undefined,
    };
    const id = getId(request);
    const result = await run("save", () => (id ? updateMaterialRequest(id, payload) : createMaterialRequest(payload)), {
      success: id ? "Material request updated." : "Material request created.",
      error: id ? "Unable to update material request." : "Unable to create material request.",
    });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="material-request-form" type="submit">{pending ? "Saving..." : "Save request"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={request ? "Edit material request" : "New material request"}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="material-request-form" noValidate onSubmit={submit}>
        <Select label="Project" {...form.register("project_id")} error={errors.project_id?.message}>
          <option value="">Select project</option>
          {legacyProject ? <option value={legacyProject}>{legacyProject}</option> : null}
          {projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
        <div>
          <Input label="Material" list="procurement-materials" {...form.register("material_name")} error={errors.material_name?.message} />
          <datalist id="procurement-materials">
            {(materials.data || []).map((item) => (
              <option key={getId(item)} value={item.material_name || item.material}>
                {`${formatNumber(item.available_stock)} ${item.unit || ""} in stock`}
              </option>
            ))}
          </datalist>
        </div>
        <Input label="Quantity" min="0" step="any" type="number" {...form.register("quantity")} error={errors.quantity?.message} />
        <Input label="Unit" placeholder="e.g. bags, tonnes" {...form.register("unit")} />
        <Input label="Required by" type="date" {...form.register("required_date")} error={errors.required_date?.message} />
        <Select label="Priority" {...form.register("priority")}>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </Select>
        <div className="sm:col-span-2"><Textarea label="Remarks" {...form.register("remarks")} /></div>
      </form>
    </Modal>
  );
}

function ApprovalModal({ request, onClose, onSaved }) {
  const [decision, setDecision] = useState("approved");
  const [comments, setComments] = useState("");
  const { run, pending } = useAction();

  async function submit(event) {
    event.preventDefault();
    const result = await run("approve", () => approveMaterialRequest(getId(request), { status: decision, comments: comments || undefined }), {
      success: `Material request ${decision}.`,
      error: "Unable to update request approval.",
    });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="approval-form" type="submit" variant={decision === "rejected" ? "danger" : "primary"}>
            {pending ? "Submitting..." : decision === "approved" ? "Approve request" : "Reject request"}
          </Button>
        </>
      }
      onClose={onClose}
      open={Boolean(request)}
      size="sm"
      title={`Review ${request?.request_id || "request"}`}
      description={request ? `${request.material_name} · ${formatNumber(request.quantity)} ${request.unit || ""} for ${request.project}` : undefined}
    >
      <form className="space-y-4" id="approval-form" onSubmit={submit}>
        <Select label="Decision" value={decision} onChange={(event) => setDecision(event.target.value)}>
          <option value="approved">Approve</option>
          <option value="rejected">Reject</option>
        </Select>
        <Textarea label="Comments" value={comments} onChange={(event) => setComments(event.target.value)} />
      </form>
    </Modal>
  );
}

function AssignVendorModal({ request, onClose, onSaved }) {
  const { activeVendors } = useProcurementLookups({ activeVendors: Boolean(request) });
  const [vendorId, setVendorId] = useState(request?.vendor_id || "");
  const [error, setError] = useState("");
  const { run, pending } = useAction();

  async function submit(event) {
    event.preventDefault();
    if (!vendorId) {
      setError("Select an active vendor.");
      return;
    }
    const result = await run("assign", () => assignVendorToMaterialRequest(getId(request), vendorId), {
      success: "Vendor assigned and notified.",
      error: "Unable to assign vendor.",
    });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="assign-vendor-form" type="submit">{pending ? "Assigning..." : "Assign vendor"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(request)}
      size="sm"
      title={`Assign vendor to ${request?.request_id || "request"}`}
    >
      <form className="space-y-3" id="assign-vendor-form" onSubmit={submit}>
        <Select error={error} label="Active vendor" value={vendorId} onChange={(event) => { setVendorId(event.target.value); setError(""); }}>
          <option value="">Select vendor</option>
          {activeVendors.map((vendor) => (
            <option key={getId(vendor)} value={getId(vendor)}>
              {vendor.vendor_name}{vendor.materials_supplied?.length ? ` (${vendor.materials_supplied.join(", ")})` : ""}
            </option>
          ))}
        </Select>
        {!activeVendors.length ? <p className="text-sm text-muted">No active vendors are available. Add one on the Vendors page.</p> : null}
      </form>
    </Modal>
  );
}

export function RequestsTab({ approvalsOnly = false }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const list = useProcurementList(getMaterialRequests, { withPriority: true, fixedStatus: approvalsOnly ? "pending" : undefined });
  const lookups = useProcurementLookups({ vendors: true });
  const { run } = useAction();
  const [formState, setFormState] = useState({ open: false, request: null });
  const [details, setDetails] = useState(null);
  const [reviewing, setReviewing] = useState(null);
  const [assigning, setAssigning] = useState(null);
  const [poRequest, setPoRequest] = useState(null);

  const isPM = can.procurementProjectManager(user);
  const isEngineer = can.procurementSiteEngineer(user);
  const isAdmin = can.adminOnly(user);
  const refresh = () => list.reload();

  async function remove(request) {
    if (!confirmAction(`Delete material request ${request.request_id || request.material_name}? This cannot be undone.`)) return;
    await run("delete", () => deleteMaterialRequest(getId(request)), { success: "Material request deleted.", error: "Unable to delete material request.", onSuccess: refresh });
  }

  // Approvals view only ever lists requests awaiting a decision.
  const rows = approvalsOnly ? list.items.filter((item) => item.status === "pending") : list.items;

  const columns = [
    { key: "request_id", header: "Req ID", render: (row) => <span className="font-semibold">{row.request_id || "Not set"}</span> },
    { key: "project", header: "Project" },
    { key: "material_name", header: "Material" },
    { key: "quantity", header: "Qty", render: (row) => `${formatNumber(row.quantity)} ${row.unit || ""}` },
    { key: "required_date", header: "Required", render: (row) => formatDate(row.required_date) },
    { key: "priority", header: "Priority", render: (row) => <StatusBadge status={row.priority} /> },
    ...(approvalsOnly ? [] : [{ key: "vendor", header: "Vendor", render: (row) => (row.vendor_id ? lookups.vendorName(row.vendor_id, row) : "Not assigned") }]),
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions>
          <Button onClick={() => setDetails(row)} size="sm" variant="secondary">View</Button>
          {isPM && row.status === "pending" ? <Button onClick={() => setReviewing(row)} size="sm">Review</Button> : null}
          {isPM && ASSIGNABLE.includes(row.status) ? <Button onClick={() => setAssigning(row)} size="sm">{row.vendor_id ? "Reassign vendor" : "Assign vendor"}</Button> : null}
          {isPM && row.status === "vendor_accepted" && !row.purchase_order_id ? <Button onClick={() => setPoRequest(row)} size="sm">Generate PO</Button> : null}
          {row.purchase_order_id && !approvalsOnly ? <Button onClick={() => navigate("/procurement/purchase-orders")} size="sm" variant="ghost">View PO {row.po_number || ""}</Button> : null}
          {isEngineer && !approvalsOnly ? <Button onClick={() => setFormState({ open: true, request: row })} size="sm" variant="secondary">Edit</Button> : null}
          {isAdmin && !approvalsOnly ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ListSection
        addLabel="New request"
        columns={columns}
        emptyDescription={approvalsOnly ? "No material requests are waiting for approval." : "Create a material request to start the procurement workflow."}
        emptyTitle={approvalsOnly ? "Nothing to approve" : "No material requests"}
        exportName={approvalsOnly ? undefined : "material_requests"}
        getRowId={getId}
        list={{ ...list, items: rows }}
        onAdd={isEngineer && !approvalsOnly ? () => setFormState({ open: true, request: null }) : undefined}
        priorityOptions={["low", "medium", "high"]}
        searchPlaceholder="Search request ID, project, material..."
        statusOptions={approvalsOnly ? undefined : REQUEST_STATUSES}
        title={approvalsOnly ? "Pending approvals" : "Material requests"}
      />
      <RequestFormModal
        onClose={() => setFormState({ open: false, request: null })}
        onSaved={() => { setFormState({ open: false, request: null }); refresh(); }}
        open={formState.open}
        request={formState.request}
      />
      <ApprovalModal onClose={() => setReviewing(null)} onSaved={() => { setReviewing(null); refresh(); }} request={reviewing} />
      <AssignVendorModal key={getId(assigning) || "none"} onClose={() => setAssigning(null)} onSaved={() => { setAssigning(null); refresh(); lookups.reload(); }} request={assigning} />
      <PurchaseOrderFormModal
        onClose={() => setPoRequest(null)}
        onSaved={() => { setPoRequest(null); refresh(); }}
        open={Boolean(poRequest)}
        request={poRequest}
      />
      <Modal onClose={() => setDetails(null)} open={Boolean(details)} title={`Material request ${details?.request_id || ""}`}>
        {details ? (
          <DetailList
            items={[
              ["Project", details.project],
              ["Material", details.material_name],
              ["Quantity", `${formatNumber(details.quantity)} ${details.unit || ""}`],
              ["Required by", formatDate(details.required_date)],
              ["Priority", <StatusBadge key="p" status={details.priority} />],
              ["Status", <StatusBadge key="s" status={details.status} />],
              ["Vendor", details.vendor_id ? lookups.vendorName(details.vendor_id, details) : null],
              ["Vendor response", details.vendor_comment || details.vendor_response],
              ["Purchase order", details.po_number],
              ["Approved by", details.approved_by],
              ["Approval comments", details.approval_comments],
              ["Remarks", details.remarks],
              ["Created", formatDateTime(details.created_at)],
              ["Updated", formatDateTime(details.updated_at)],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
