import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { can } from "../../../lib/roles.js";
import { dateInputToIso, formatCurrency, formatDate, formatStatus, getId, projectName, toDateInput, workerName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import {
  RESOURCE_STATUSES,
  RESOURCE_TYPES,
  assignResource,
  createResource,
  getMaintenanceLogs,
  recordMaintenance,
  updateResource,
} from "../services/resourceService.js";

const resourceSchema = z.object({
  resource_name: z.string().trim().min(1, "Name is required."),
  resource_type: z.string().min(1),
  description: z.string().optional(),
  quantity: z.coerce.number({ invalid_type_error: "Enter a quantity." }).gt(0, "Quantity must be greater than 0."),
  unit: z.string().optional(),
  acquisition_cost: z.coerce.number().min(0, "Cannot be negative."),
  acquisition_date: z.string().optional(),
  status: z.string().min(1),
  maintenance_schedule: z.string().optional(),
});

export function ResourceFormModal({ open, resource, onClose, onSaved }) {
  const editing = Boolean(resource);
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(resourceSchema),
    values: open
      ? {
          resource_name: resource?.resource_name || "",
          resource_type: resource?.resource_type || "equipment",
          description: resource?.description || "",
          quantity: resource?.quantity ?? 1,
          unit: resource?.unit || "Nos",
          acquisition_cost: resource?.acquisition_cost ?? 0,
          acquisition_date: resource?.acquisition_date ? toDateInput(resource.acquisition_date) : toDateInput(),
          status: resource?.status || "available",
          maintenance_schedule: resource?.maintenance_schedule || "",
        }
      : undefined,
  });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    // ResourceUpdate does not accept cost, acquisition date or schedule.
    const payload = editing
      ? { resource_name: values.resource_name, resource_type: values.resource_type, description: values.description || undefined, quantity: values.quantity, unit: values.unit || undefined, status: values.status }
      : { ...values, description: values.description || undefined, acquisition_date: dateInputToIso(values.acquisition_date), maintenance_schedule: values.maintenance_schedule || undefined };
    const result = await run("save", () => (editing ? updateResource(getId(resource), payload) : createResource(payload)), {
      success: editing ? "Resource updated." : "Resource added.",
      error: editing ? "Unable to update resource." : "Unable to add resource.",
    });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="resource-form" type="submit">{pending ? "Saving..." : "Save resource"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? `Edit ${resource.resource_name}` : "Add resource"}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="resource-form" noValidate onSubmit={submit}>
        <Input label="Name" {...form.register("resource_name")} error={errors.resource_name?.message} />
        <Select label="Type" {...form.register("resource_type")}>
          {RESOURCE_TYPES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input label="Quantity" min="0" step="any" type="number" {...form.register("quantity")} error={errors.quantity?.message} />
        <Input label="Unit" {...form.register("unit")} />
        <Select label="Status" {...form.register("status")}>
          {RESOURCE_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        {!editing ? <Input label="Acquisition cost (Rs)" min="0" step="any" type="number" {...form.register("acquisition_cost")} error={errors.acquisition_cost?.message} /> : null}
        {!editing ? <Input label="Acquired on" type="date" {...form.register("acquisition_date")} /> : null}
        {!editing ? <Input label="Maintenance schedule" placeholder="e.g. every 250 hours" {...form.register("maintenance_schedule")} /> : null}
        <div className="sm:col-span-2"><Textarea label="Description" {...form.register("description")} /></div>
      </form>
    </Modal>
  );
}

export function AssignResourceModal({ resource, projects, workers, onClose, onSaved }) {
  const { run, pending } = useAction();
  const [values, setValues] = useState({ workerId: "", projectId: "" });
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (!values.workerId || !values.projectId) {
      setError("Select both a worker and a project.");
      return;
    }
    const result = await run("assign", () => assignResource(getId(resource), values.workerId, values.projectId), { success: `${resource.resource_name} assigned.`, error: "Unable to assign resource." });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="assign-resource-form" type="submit">{pending ? "Assigning..." : "Assign"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(resource)}
      size="sm"
      title={`Assign ${resource?.resource_name || "resource"}`}
    >
      <form className="space-y-4" id="assign-resource-form" onSubmit={submit}>
        <Select label="Project" value={values.projectId} onChange={(event) => { setValues({ ...values, projectId: event.target.value }); setError(""); }}>
          <option value="">Select project</option>
          {projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
        <Select error={error} label="Responsible worker" value={values.workerId} onChange={(event) => { setValues({ ...values, workerId: event.target.value }); setError(""); }}>
          <option value="">Select worker</option>
          {workers.map((worker) => <option key={getId(worker)} value={getId(worker)}>{workerName(worker)}</option>)}
        </Select>
      </form>
    </Modal>
  );
}

const maintenanceSchema = z.object({
  maintenance_date: z.string().min(1, "Date is required."),
  maintenance_type: z.enum(["routine", "repair", "inspection"]),
  description: z.string().trim().min(1, "Describe the work done."),
  cost: z.coerce.number().min(0, "Cannot be negative."),
  performed_by: z.string().trim().min(1, "Who performed it?"),
});

export function MaintenanceModal({ resource, onClose, onSaved }) {
  const { user } = useAuth();
  const { run, pending } = useAction();
  const logs = useAsyncData(() => getMaintenanceLogs(getId(resource)), [resource], { initialData: [], enabled: Boolean(resource) });
  const form = useForm({
    resolver: zodResolver(maintenanceSchema),
    values: resource ? { maintenance_date: toDateInput(), maintenance_type: "routine", description: "", cost: 0, performed_by: user?.name || "" } : undefined,
  });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    const result = await run("save", () => recordMaintenance(getId(resource), { ...values, maintenance_date: dateInputToIso(values.maintenance_date) }), {
      success: "Maintenance recorded.",
      error: "Unable to record maintenance.",
    });
    if (result) {
      form.reset();
      logs.reload();
      onSaved?.();
    }
  });

  return (
    <Modal onClose={onClose} open={Boolean(resource)} size="lg" title={`Maintenance · ${resource?.resource_name || ""}`}>
      {can.manage(user) ? (
        <form className="mb-6 grid gap-4 rounded-md border border-border p-4 sm:grid-cols-3" noValidate onSubmit={submit}>
          <Input label="Date" type="date" {...form.register("maintenance_date")} error={errors.maintenance_date?.message} />
          <Select label="Type" {...form.register("maintenance_type")}>
            <option value="routine">Routine</option>
            <option value="repair">Repair</option>
            <option value="inspection">Inspection</option>
          </Select>
          <Input label="Cost (Rs)" min="0" step="any" type="number" {...form.register("cost")} error={errors.cost?.message} />
          <div className="sm:col-span-2"><Input label="Work done" {...form.register("description")} error={errors.description?.message} /></div>
          <Input label="Performed by" {...form.register("performed_by")} error={errors.performed_by?.message} />
          <div className="sm:col-span-3"><Button disabled={Boolean(pending)} type="submit">{pending ? "Saving..." : "Record maintenance"}</Button></div>
        </form>
      ) : null}
      {logs.loading ? <LoadingState label="Loading maintenance history..." /> : null}
      {!logs.loading && logs.error ? <ErrorState message={getApiErrorMessage(logs.error)} onRetry={logs.reload} /> : null}
      {!logs.loading && !logs.error ? (
        <DataTable
          columns={[
            { key: "maintenance_date", header: "Date", render: (row) => formatDate(row.maintenance_date) },
            { key: "maintenance_type", header: "Type", render: (row) => formatStatus(row.maintenance_type) },
            { key: "description", header: "Work done" },
            { key: "cost", header: "Cost", render: (row) => formatCurrency(row.cost) },
            { key: "performed_by", header: "By" },
          ]}
          emptyDescription="No maintenance has been recorded for this resource."
          emptyTitle="No maintenance history"
          getRowId={getId}
          rows={logs.data || []}
        />
      ) : null}
    </Modal>
  );
}
