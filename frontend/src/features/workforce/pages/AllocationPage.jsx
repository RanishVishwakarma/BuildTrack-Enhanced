import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { EmptyState } from "../../../components/common/EmptyState.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions, useWorkerOptions } from "../../../hooks/useLookups.js";
import { can } from "../../../lib/roles.js";
import { dateInputToIso, formatDate, formatStatus, getId, normalizeList, projectName, toDateInput, workerName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { ALLOCATION_STATUSES } from "../constants.js";
import { createAllocation, deleteAllocation, getProjectAllocations, updateAllocation } from "../services/workforceService.js";

const allocationSchema = z
  .object({
    worker_id: z.string().min(1, "Select a worker."),
    role: z.string().optional(),
    start_date: z.string().min(1, "Start date is required."),
    end_date: z.string().optional(),
    status: z.enum(ALLOCATION_STATUSES),
  })
  .refine((values) => !values.end_date || values.end_date >= values.start_date, { message: "End date cannot be before the start date.", path: ["end_date"] });

function AllocationFormModal({ open, allocation, projectId, workers, onClose, onSaved }) {
  const editing = Boolean(allocation);
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(allocationSchema),
    values: open
      ? {
          worker_id: allocation?.worker_id || "",
          role: allocation?.role || "",
          start_date: toDateInput(allocation?.start_date),
          end_date: allocation?.end_date ? toDateInput(allocation.end_date) : "",
          status: allocation?.status || "ACTIVE",
        }
      : undefined,
  });
  const errors = form.formState.errors;

  function onWorkerChange(event) {
    const worker = workers.find((item) => getId(item) === event.target.value);
    if (worker && !form.getValues("role")) form.setValue("role", worker.designation || worker.skill_type || "");
  }

  const submit = form.handleSubmit(async (values) => {
    const common = { role: values.role || undefined, start_date: dateInputToIso(values.start_date), end_date: dateInputToIso(values.end_date), status: values.status };
    const result = await run(
      "save",
      () => (editing ? updateAllocation(getId(allocation), common) : createAllocation({ ...common, worker_id: values.worker_id, project_id: projectId })),
      { success: editing ? "Allocation updated." : "Worker allocated.", error: editing ? "Unable to update allocation." : "Unable to allocate worker." },
    );
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="allocation-form" type="submit">{pending ? "Saving..." : "Save allocation"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? "Edit allocation" : "Allocate worker"}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="allocation-form" noValidate onSubmit={submit}>
        <Select disabled={editing} label="Worker" {...form.register("worker_id", { onChange: onWorkerChange })} error={errors.worker_id?.message}>
          <option value="">Select worker</option>
          {workers.map((worker) => <option key={getId(worker)} value={getId(worker)}>{workerName(worker)} · {formatStatus(worker.status)}</option>)}
        </Select>
        <Input label="Role on project" placeholder="Mason, supervisor..." {...form.register("role")} />
        <Input label="Start date" type="date" {...form.register("start_date")} error={errors.start_date?.message} />
        <Input label="End date" type="date" {...form.register("end_date")} error={errors.end_date?.message} />
        <Select label="Status" {...form.register("status")}>
          {ALLOCATION_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
      </form>
    </Modal>
  );
}

export function AllocationPage() {
  const { user } = useAuth();
  const projectLookup = useProjectOptions();
  const workerLookup = useWorkerOptions();
  const { run } = useAction();
  const [projectId, setProjectId] = useState("");
  const [form, setForm] = useState({ open: false, allocation: null });
  const isManager = can.manage(user);

  // The backend has no unfiltered allocation list, so a project must be chosen first.
  const allocations = useAsyncData(async () => normalizeList(await getProjectAllocations(projectId)).items, [projectId], { initialData: [], enabled: Boolean(projectId) });

  async function remove(allocation) {
    if (!confirmAction(`Remove ${workerLookup.nameOf(allocation.worker_id)} from this project?`)) return;
    await run("delete", () => deleteAllocation(getId(allocation)), { success: "Allocation removed.", error: "Unable to remove allocation.", onSuccess: allocations.reload });
  }

  const selectedProject = projectLookup.projects.find((project) => getId(project) === projectId);

  return (
    <>
      <PageHeader
        onRefresh={projectId ? allocations.reload : undefined}
        title="Worker Allocation"
        description="Assign workers to projects with a role and date range."
        action={
          <div className="flex flex-wrap gap-2">
            {isManager ? <Button disabled={!projectId} onClick={() => setForm({ open: true, allocation: null })}><Plus className="h-4 w-4" /> Allocate worker</Button> : null}
          </div>
        }
      />
      <div className="mb-6 max-w-md">
        <Select label="Project" value={projectId} onChange={(event) => setProjectId(event.target.value)}>
          <option value="">{projectLookup.loading ? "Loading projects..." : "Select a project"}</option>
          {projectLookup.projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
      </div>
      {!projectId ? <EmptyState title="Choose a project" description="Allocations are listed per project." /> : null}
      {projectId && allocations.loading ? <LoadingState label="Loading allocations..." /> : null}
      {projectId && !allocations.loading && allocations.error ? <ErrorState message={getApiErrorMessage(allocations.error)} onRetry={allocations.reload} /> : null}
      {projectId && !allocations.loading && !allocations.error ? (
        <DataTable
          columns={[
            { key: "worker", header: "Worker", render: (row) => <span className="font-semibold">{workerLookup.nameOf(row.worker_id)}</span> },
            { key: "role", header: "Role" },
            { key: "start_date", header: "Start", render: (row) => formatDate(row.start_date) },
            { key: "end_date", header: "End", render: (row) => (row.end_date ? formatDate(row.end_date) : "Open") },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            ...(isManager
              ? [{
                  key: "actions",
                  header: "Actions",
                  render: (row) => (
                    <div className="flex flex-wrap gap-2">
                      <Button onClick={() => setForm({ open: true, allocation: row })} size="sm" variant="secondary">Edit</Button>
                      <Button onClick={() => remove(row)} size="sm" variant="danger">Remove</Button>
                    </div>
                  ),
                }]
              : []),
          ]}
          emptyDescription={`No workers are allocated to ${selectedProject ? projectName(selectedProject) : "this project"} yet.`}
          emptyTitle="No allocations"
          getRowId={getId}
          rows={allocations.data || []}
        />
      ) : null}
      <AllocationFormModal
        allocation={form.allocation}
        onClose={() => setForm({ open: false, allocation: null })}
        onSaved={() => { setForm({ open: false, allocation: null }); allocations.reload(); }}
        open={form.open}
        projectId={projectId}
        workers={workerLookup.workers}
      />
    </>
  );
}
