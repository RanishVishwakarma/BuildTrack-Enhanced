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
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions, useWorkerOptions } from "../../../hooks/useLookups.js";
import { can } from "../../../lib/roles.js";
import { addDays, dateInputToIso, formatCurrency, formatDate, formatStatus, getId, normalizeList, projectName, toDateInput, workerName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { PAYROLL_STATUSES } from "../constants.js";
import { createPayroll, deletePayroll, getPayroll, updatePayroll } from "../services/workforceService.js";

const amount = z.coerce.number({ invalid_type_error: "Enter an amount." }).min(0, "Cannot be negative.");
const payrollSchema = z
  .object({
    worker_id: z.string().min(1, "Select a worker."),
    project_id: z.string().optional(),
    pay_period_start: z.string().min(1, "Period start is required."),
    pay_period_end: z.string().min(1, "Period end is required."),
    basic_amount: amount,
    overtime_hours: amount,
    overtime_amount: amount,
    bonus: amount,
    deductions: amount,
    status: z.enum(PAYROLL_STATUSES),
  })
  .refine((values) => values.pay_period_end >= values.pay_period_start, { message: "Period end cannot be before the start.", path: ["pay_period_end"] });

// Same formula the backend applies on create: basic + overtime + bonus - deductions.
const netOf = (values) =>
  Number(values.basic_amount || 0) + Number(values.overtime_amount || 0) + Number(values.bonus || 0) - Number(values.deductions || 0);

function PayrollFormModal({ open, record, workers, projects, onClose, onSaved }) {
  const editing = Boolean(record);
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(payrollSchema),
    values: open
      ? {
          worker_id: record?.worker_id || "",
          project_id: record?.project_id || "",
          pay_period_start: record ? toDateInput(record.pay_period_start) : addDays(-30),
          pay_period_end: record ? toDateInput(record.pay_period_end) : toDateInput(),
          basic_amount: record?.basic_amount ?? 0,
          overtime_hours: record?.overtime_hours ?? 0,
          overtime_amount: record?.overtime_amount ?? 0,
          bonus: record?.bonus ?? 0,
          deductions: record?.deductions ?? 0,
          status: record?.status || "DRAFT",
        }
      : undefined,
  });
  const errors = form.formState.errors;
  const net = netOf(form.watch());

  function onWorkerChange(event) {
    const worker = workers.find((item) => getId(item) === event.target.value);
    if (!worker) return;
    if (worker.project_id && !form.getValues("project_id")) form.setValue("project_id", worker.project_id);
    if (worker.salary_type === "MONTHLY" && worker.salary_amount && !Number(form.getValues("basic_amount"))) form.setValue("basic_amount", worker.salary_amount);
  }

  const submit = form.handleSubmit(async (values) => {
    if (netOf(values) < 0) {
      form.setError("deductions", { message: "Deductions cannot exceed total earnings." });
      return;
    }
    const figures = {
      basic_amount: values.basic_amount,
      overtime_hours: values.overtime_hours,
      overtime_amount: values.overtime_amount,
      bonus: values.bonus,
      deductions: values.deductions,
      net_amount: netOf(values),
      status: values.status,
    };
    const action = editing
      ? () => updatePayroll(getId(record), figures)
      : () =>
          createPayroll({
            ...figures,
            worker_id: values.worker_id,
            project_id: values.project_id || undefined,
            pay_period_start: dateInputToIso(values.pay_period_start),
            pay_period_end: dateInputToIso(values.pay_period_end),
          });
    const result = await run("save", action, { success: editing ? "Payroll updated." : "Payroll created.", error: editing ? "Unable to update payroll." : "Unable to create payroll." });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="payroll-form" type="submit">{pending ? "Saving..." : "Save payroll"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? `Edit payroll · ${workers.find((worker) => getId(worker) === record.worker_id) ? workerName(workers.find((worker) => getId(worker) === record.worker_id)) : ""}` : "New payroll record"}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="payroll-form" noValidate onSubmit={submit}>
        <Select disabled={editing} label="Worker" {...form.register("worker_id", { onChange: onWorkerChange })} error={errors.worker_id?.message}>
          <option value="">Select worker</option>
          {workers.map((worker) => <option key={getId(worker)} value={getId(worker)}>{workerName(worker)}</option>)}
        </Select>
        <Select disabled={editing} label="Project" {...form.register("project_id")}>
          <option value="">Not set</option>
          {projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
        <Input disabled={editing} label="Period start" type="date" {...form.register("pay_period_start")} error={errors.pay_period_start?.message} />
        <Input disabled={editing} label="Period end" type="date" {...form.register("pay_period_end")} error={errors.pay_period_end?.message} />
        <Input label="Basic (Rs)" min="0" step="any" type="number" {...form.register("basic_amount")} error={errors.basic_amount?.message} />
        <Input label="Overtime hours" min="0" step="any" type="number" {...form.register("overtime_hours")} error={errors.overtime_hours?.message} />
        <Input label="Overtime amount (Rs)" min="0" step="any" type="number" {...form.register("overtime_amount")} error={errors.overtime_amount?.message} />
        <Input label="Bonus (Rs)" min="0" step="any" type="number" {...form.register("bonus")} error={errors.bonus?.message} />
        <Input label="Deductions (Rs)" min="0" step="any" type="number" {...form.register("deductions")} error={errors.deductions?.message} />
        <Select label="Status" {...form.register("status")}>
          {PAYROLL_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <p className="text-sm font-semibold sm:col-span-2">Net pay: {formatCurrency(net)}</p>
      </form>
    </Modal>
  );
}

export function PayrollPage() {
  const { user } = useAuth();
  const projectLookup = useProjectOptions();
  const workerLookup = useWorkerOptions();
  const { run } = useAction();
  const [filters, setFilters] = useState({ worker: "", project: "", status: "" });
  const [form, setForm] = useState({ open: false, record: null });
  const isManager = can.manage(user);

  const payroll = useAsyncData(
    async () => normalizeList(await getPayroll({ workerId: filters.worker || undefined, projectId: filters.project || undefined })).items,
    [filters.worker, filters.project],
    { initialData: [] },
  );
  const rows = (payroll.data || []).filter((row) => !filters.status || row.status === filters.status);
  const total = (status) => rows.filter((row) => !status || row.status === status).reduce((sum, row) => sum + Number(row.net_amount || 0), 0);

  async function remove(record) {
    if (!confirmAction("Delete this payroll record? This cannot be undone.")) return;
    await run("delete", () => deletePayroll(getId(record)), { success: "Payroll record deleted.", error: "Unable to delete payroll record.", onSuccess: payroll.reload });
  }

  async function setStatus(record, status) {
    await run(`status-${getId(record)}`, () => updatePayroll(getId(record), { status }), { success: `Payroll marked ${formatStatus(status).toLowerCase()}.`, error: "Unable to update payroll status.", onSuccess: payroll.reload });
  }

  const nextStatus = { DRAFT: "PENDING", PENDING: "APPROVED", APPROVED: "PAID" };

  return (
    <>
      <PageHeader
        onRefresh={payroll.reload}
        title="Payroll"
        description="Worker pay periods, overtime, deductions and payment status."
        action={
          <div className="flex flex-wrap gap-2">
            {isManager ? <Button onClick={() => setForm({ open: true, record: null })}><Plus className="h-4 w-4" /> New payroll</Button> : null}
          </div>
        }
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Records" value={rows.length} />
        <StatCard label="Total net" value={formatCurrency(total())} />
        <StatCard label="Awaiting payment" value={formatCurrency(total("APPROVED") + total("PENDING"))} />
        <StatCard label="Paid" value={formatCurrency(total("PAID"))} />
      </section>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Select aria-label="Filter by worker" className="h-10" value={filters.worker} onChange={(event) => setFilters({ ...filters, worker: event.target.value })}>
          <option value="">All workers</option>
          {workerLookup.workers.map((worker) => <option key={getId(worker)} value={getId(worker)}>{workerName(worker)}</option>)}
        </Select>
        <Select aria-label="Filter by project" className="h-10" value={filters.project} onChange={(event) => setFilters({ ...filters, project: event.target.value })}>
          <option value="">All projects</option>
          {projectLookup.projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
        <Select aria-label="Filter by status" className="h-10" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">All statuses</option>
          {PAYROLL_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
      </div>
      {payroll.loading ? <LoadingState label="Loading payroll..." /> : null}
      {!payroll.loading && payroll.error ? <ErrorState message={getApiErrorMessage(payroll.error)} onRetry={payroll.reload} /> : null}
      {!payroll.loading && !payroll.error ? (
        <DataTable
          columns={[
            { key: "worker", header: "Worker", render: (row) => <span className="font-semibold">{workerLookup.nameOf(row.worker_id)}</span> },
            { key: "project", header: "Project", render: (row) => (row.project_id ? projectLookup.nameOf(row.project_id) : "Not set") },
            { key: "period", header: "Period", render: (row) => `${formatDate(row.pay_period_start)} - ${formatDate(row.pay_period_end)}` },
            { key: "basic_amount", header: "Basic", render: (row) => formatCurrency(row.basic_amount) },
            { key: "extras", header: "OT + bonus", render: (row) => formatCurrency(Number(row.overtime_amount || 0) + Number(row.bonus || 0)) },
            { key: "deductions", header: "Deductions", render: (row) => formatCurrency(row.deductions) },
            { key: "net_amount", header: "Net", render: (row) => <span className="font-semibold">{formatCurrency(row.net_amount)}</span> },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            ...(isManager
              ? [{
                  key: "actions",
                  header: "Actions",
                  render: (row) => (
                    <div className="flex flex-wrap gap-2">
                      {nextStatus[row.status] ? <Button onClick={() => setStatus(row, nextStatus[row.status])} size="sm">Mark {formatStatus(nextStatus[row.status]).toLowerCase()}</Button> : null}
                      <Button onClick={() => setForm({ open: true, record: row })} size="sm" variant="secondary">Edit</Button>
                      {can.adminOnly(user) ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
                    </div>
                  ),
                }]
              : []),
          ]}
          emptyDescription="Create payroll records for each pay period."
          emptyTitle="No payroll records"
          getRowId={getId}
          rows={rows}
        />
      ) : null}
      <PayrollFormModal
        onClose={() => setForm({ open: false, record: null })}
        onSaved={() => { setForm({ open: false, record: null }); payroll.reload(); }}
        open={form.open}
        projects={projectLookup.projects}
        record={form.record}
        workers={workerLookup.workers}
      />
    </>
  );
}
