import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions, useWorkerOptions } from "../../../hooks/useLookups.js";
import { ROLE, can, hasAnyRole } from "../../../lib/roles.js";
import { formatDate, formatStatus, getId, normalizeList, projectName, toDateInput, workerName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { ALLOCATION_STATUSES, SHIFT_STATUSES } from "../constants.js";
import { createShift, createShiftAssignment, deleteShift, deleteShiftAssignment, getShiftAssignments, getShifts, updateShift } from "../services/workforceService.js";

const shiftSchema = z
  .object({
    name: z.string().trim().min(1, "Shift name is required."),
    start_time: z.string().min(1, "Start time is required."),
    end_time: z.string().min(1, "End time is required."),
    project_id: z.string().optional(),
    description: z.string().optional(),
    status: z.enum(SHIFT_STATUSES),
  })
  .refine((values) => values.start_time !== values.end_time, { message: "End time must differ from start time.", path: ["end_time"] });

const assignmentSchema = z.object({
  shift_id: z.string().min(1, "Select a shift."),
  worker_id: z.string().min(1, "Select a worker."),
  date: z.string().min(1, "Date is required."),
  project_id: z.string().optional(),
});

function ShiftFormModal({ open, shift, projects, onClose, onSaved }) {
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(shiftSchema),
    values: open
      ? { name: shift?.name || "", start_time: shift?.start_time || "09:00", end_time: shift?.end_time || "17:00", project_id: shift?.project_id || "", description: shift?.description || "", status: shift?.status || "ACTIVE" }
      : undefined,
  });
  const errors = form.formState.errors;
  const submit = form.handleSubmit(async (values) => {
    const payload = { ...values, project_id: values.project_id || undefined, description: values.description || undefined };
    const result = await run("save", () => (shift ? updateShift(getId(shift), payload) : createShift(payload)), {
      success: shift ? "Shift updated." : "Shift created.",
      error: shift ? "Unable to update shift." : "Unable to create shift.",
    });
    if (result) onSaved();
  });
  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="shift-form" type="submit">{pending ? "Saving..." : "Save shift"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={shift ? `Edit ${shift.name}` : "New shift"}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="shift-form" noValidate onSubmit={submit}>
        <Input label="Name" placeholder="Morning shift" {...form.register("name")} error={errors.name?.message} />
        <Select label="Project" {...form.register("project_id")}>
          <option value="">All projects</option>
          {projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
        <Input label="Start time" type="time" {...form.register("start_time")} error={errors.start_time?.message} />
        <Input label="End time" type="time" {...form.register("end_time")} error={errors.end_time?.message} />
        <Select label="Status" {...form.register("status")}>
          {SHIFT_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <div className="sm:col-span-2"><Textarea label="Description" {...form.register("description")} /></div>
      </form>
    </Modal>
  );
}

function AssignmentFormModal({ open, shifts, workers, projects, onClose, onSaved }) {
  const { run, pending } = useAction();
  const form = useForm({ resolver: zodResolver(assignmentSchema), values: open ? { shift_id: "", worker_id: "", date: toDateInput(), project_id: "" } : undefined });
  const errors = form.formState.errors;

  function onShiftChange(event) {
    const shift = shifts.find((item) => getId(item) === event.target.value);
    if (shift?.project_id) form.setValue("project_id", shift.project_id);
  }

  const submit = form.handleSubmit(async (values) => {
    const payload = { ...values, date: new Date(`${values.date}T00:00:00`).toISOString(), project_id: values.project_id || undefined, status: "ACTIVE" };
    const result = await run("save", () => createShiftAssignment(payload), { success: "Worker assigned to shift.", error: "Unable to assign shift." });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="assignment-form" type="submit">{pending ? "Saving..." : "Assign"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title="Assign worker to shift"
    >
      <form className="grid gap-4 sm:grid-cols-2" id="assignment-form" noValidate onSubmit={submit}>
        <Select label="Shift" {...form.register("shift_id", { onChange: onShiftChange })} error={errors.shift_id?.message}>
          <option value="">Select shift</option>
          {shifts.filter((shift) => shift.status !== "INACTIVE").map((shift) => <option key={getId(shift)} value={getId(shift)}>{shift.name} ({shift.start_time}-{shift.end_time})</option>)}
        </Select>
        <Select label="Worker" {...form.register("worker_id")} error={errors.worker_id?.message}>
          <option value="">Select worker</option>
          {workers.map((worker) => <option key={getId(worker)} value={getId(worker)}>{workerName(worker)}</option>)}
        </Select>
        <Input label="Date" type="date" {...form.register("date")} error={errors.date?.message} />
        <Select label="Project" {...form.register("project_id")}>
          <option value="">Not set</option>
          {projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
      </form>
    </Modal>
  );
}

export function ShiftSchedulingPage() {
  const { user } = useAuth();
  const isWorker = hasAnyRole(user, [ROLE.WORKER]);
  const isManager = can.manage(user);
  const canAssign = can.assignShifts(user);
  const projectLookup = useProjectOptions();
  const workerLookup = useWorkerOptions({ enabled: !isWorker });
  const { run } = useAction();
  const [projectFilter, setProjectFilter] = useState("");
  const [shiftForm, setShiftForm] = useState({ open: false, shift: null });
  const [assigning, setAssigning] = useState(false);

  // A worker login a manager has not linked to a worker record yet.
  const unlinked = isWorker && !user?.workerId;
  const data = useAsyncData(
    async () => {
      const [shifts, assignments] = await Promise.all([
        getShifts(projectFilter || undefined),
        isWorker
          ? user?.workerId ? getShiftAssignments({ workerId: user.workerId }) : []
          : getShiftAssignments({ projectId: projectFilter || undefined }),
      ]);
      return { shifts: normalizeList(shifts).items, assignments: normalizeList(assignments).items };
    },
    [projectFilter, isWorker, user?.workerId],
    { enabled: !unlinked },
  );
  const shifts = data.data?.shifts || [];
  const assignments = (data.data?.assignments || []).slice().sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const shiftById = new Map(shifts.map((shift) => [getId(shift), shift]));

  async function removeShift(shift) {
    if (!confirmAction(`Delete shift ${shift.name}? This cannot be undone.`)) return;
    await run("delete-shift", () => deleteShift(getId(shift)), { success: "Shift deleted.", error: "Unable to delete shift.", onSuccess: data.reload });
  }
  async function removeAssignment(assignment) {
    if (!confirmAction("Remove this shift assignment?")) return;
    await run("delete-assignment", () => deleteShiftAssignment(getId(assignment)), { success: "Assignment removed.", error: "Unable to remove assignment.", onSuccess: data.reload });
  }

  const shiftLabel = (id) => {
    const shift = shiftById.get(id);
    return shift ? `${shift.name} (${shift.start_time}-${shift.end_time})` : id;
  };

  return (
    <>
      <PageHeader
        onRefresh={data.reload}
        title={isWorker ? "My Schedule" : "Shift Scheduling"}
        description={isWorker ? "Shifts you have been assigned to." : "Define site shifts and assign workers to them."}
        action={
          <div className="flex flex-wrap gap-2">
            {canAssign ? <Button onClick={() => setAssigning(true)} variant="secondary">Assign worker</Button> : null}
            {isManager ? <Button onClick={() => setShiftForm({ open: true, shift: null })}><Plus className="h-4 w-4" /> New shift</Button> : null}
          </div>
        }
      />
      {!isWorker ? (
        <div className="mb-4 max-w-sm">
          <Select aria-label="Filter by project" value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}>
            <option value="">All projects</option>
            {projectLookup.projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
          </Select>
        </div>
      ) : null}
      {unlinked ? <ErrorState message="Your login is not linked to a worker profile, so your schedule cannot be loaded. Ask your project manager to link it on the Workers page." /> : null}
      {!unlinked && data.loading ? <LoadingState label="Loading shifts..." /> : null}
      {!unlinked && !data.loading && data.error ? <ErrorState message={getApiErrorMessage(data.error)} onRetry={data.reload} /> : null}
      {!unlinked && !data.loading && !data.error ? (
        <div className="space-y-6">
          {!isWorker ? (
            <section className="card">
              <h2 className="mb-4 text-lg font-semibold">Shifts</h2>
              <DataTable
                columns={[
                  { key: "name", header: "Shift", render: (row) => <span className="font-semibold">{row.name}</span> },
                  { key: "time", header: "Time", render: (row) => `${row.start_time} - ${row.end_time}` },
                  { key: "project", header: "Project", render: (row) => (row.project_id ? projectLookup.nameOf(row.project_id) : "All projects") },
                  { key: "description", header: "Description" },
                  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
                  ...(isManager
                    ? [{
                        key: "actions",
                        header: "Actions",
                        render: (row) => (
                          <div className="flex flex-wrap gap-2">
                            <Button onClick={() => setShiftForm({ open: true, shift: row })} size="sm" variant="secondary">Edit</Button>
                            {can.adminOnly(user) ? <Button onClick={() => removeShift(row)} size="sm" variant="danger">Delete</Button> : null}
                          </div>
                        ),
                      }]
                    : []),
                ]}
                emptyDescription="Create shifts to start scheduling workers."
                emptyTitle="No shifts"
                getRowId={getId}
                rows={shifts}
              />
            </section>
          ) : null}
          <section className="card">
            <h2 className="mb-4 text-lg font-semibold">{isWorker ? "My assignments" : "Assignments"}</h2>
            <DataTable
              columns={[
                { key: "date", header: "Date", render: (row) => formatDate(row.date) },
                { key: "shift", header: "Shift", render: (row) => shiftLabel(row.shift_id) },
                ...(!isWorker ? [{ key: "worker", header: "Worker", render: (row) => workerLookup.nameOf(row.worker_id) }] : []),
                { key: "project", header: "Project", render: (row) => (row.project_id ? projectLookup.nameOf(row.project_id) : "Not set") },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={ALLOCATION_STATUSES.includes(row.status) ? row.status : row.status || "ACTIVE"} /> },
                ...(canAssign ? [{ key: "actions", header: "Actions", render: (row) => <Button onClick={() => removeAssignment(row)} size="sm" variant="danger">Remove</Button> }] : []),
              ]}
              emptyDescription={isWorker ? "You have no shifts assigned yet." : "Assign workers to shifts to build the schedule."}
              emptyTitle="No assignments"
              getRowId={getId}
              rows={assignments}
            />
          </section>
        </div>
      ) : null}
      <ShiftFormModal onClose={() => setShiftForm({ open: false, shift: null })} onSaved={() => { setShiftForm({ open: false, shift: null }); data.reload(); }} open={shiftForm.open} projects={projectLookup.projects} shift={shiftForm.shift} />
      <AssignmentFormModal onClose={() => setAssigning(false)} onSaved={() => { setAssigning(false); data.reload(); }} open={assigning} projects={projectLookup.projects} shifts={shifts} workers={workerLookup.workers} />
    </>
  );
}
