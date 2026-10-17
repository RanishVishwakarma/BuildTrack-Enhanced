import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { DetailList } from "../../../components/common/DetailList.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { SearchInput } from "../../../components/common/SearchInput.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { can } from "../../../lib/roles.js";
import { dateInputToIso, formatCurrency, formatDate, formatStatus, getId, matchesSearch, normalizeList, projectName, toDateInput, workerName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { createWorker, deleteWorker, getWorkers, updateWorker } from "../services/workforceService.js";
import { EMPLOYMENT_TYPES, SALARY_TYPES, WORKER_CATEGORIES, WORKER_STATUSES } from "../constants.js";

const workerSchema = z.object({
  worker_code: z.string().optional(),
  first_name: z.string().trim().min(1, "First name is required."),
  last_name: z.string().trim().min(1, "Last name is required."),
  email: z.string().trim().email("Enter a valid email."),
  phone: z.string().optional(),
  category: z.enum(WORKER_CATEGORIES),
  skill_type: z.string().trim().min(1, "Skill is required (e.g. mason, electrician)."),
  designation: z.string().optional(),
  experience_years: z.coerce.number().min(0, "Cannot be negative."),
  employment_type: z.enum(EMPLOYMENT_TYPES),
  joining_date: z.string().optional(),
  salary_type: z.enum(SALARY_TYPES),
  hourly_rate: z.coerce.number().min(0, "Cannot be negative."),
  salary_amount: z.coerce.number().min(0, "Cannot be negative."),
  project_id: z.string().optional(),
  status: z.enum(WORKER_STATUSES),
});

function WorkerFormModal({ open, worker, projects, onClose, onSaved }) {
  const editing = Boolean(worker);
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(workerSchema),
    values: open
      ? {
          worker_code: worker?.worker_code || "",
          first_name: worker?.first_name || "",
          last_name: worker?.last_name || "",
          email: worker?.email || "",
          phone: worker?.phone || "",
          category: WORKER_CATEGORIES.includes(worker?.category) ? worker.category : "SKILLED_WORKER",
          skill_type: worker?.skill_type || "",
          designation: worker?.designation || "",
          experience_years: worker?.experience_years ?? 0,
          employment_type: EMPLOYMENT_TYPES.includes(worker?.employment_type) ? worker.employment_type : "FULL_TIME",
          joining_date: toDateInput(worker?.joining_date),
          salary_type: SALARY_TYPES.includes(worker?.salary_type) ? worker.salary_type : "MONTHLY",
          hourly_rate: worker?.hourly_rate ?? 0,
          salary_amount: worker?.salary_amount ?? 0,
          project_id: worker?.project_id || "",
          status: WORKER_STATUSES.includes(worker?.status) ? worker.status : "available",
        }
      : undefined,
  });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    const payload = {
      ...values,
      worker_code: values.worker_code?.trim() || undefined,
      phone: values.phone || undefined,
      designation: values.designation || undefined,
      joining_date: dateInputToIso(values.joining_date),
      project_id: values.project_id || undefined,
    };
    const result = await run("save", () => (editing ? updateWorker(getId(worker), payload) : createWorker(payload)), {
      success: editing ? "Worker updated." : "Worker added.",
      error: editing ? "Unable to update worker." : "Unable to add worker.",
    });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="worker-form" type="submit">{pending ? "Saving..." : "Save worker"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      size="lg"
      title={editing ? `Edit ${workerName(worker)}` : "Add worker"}
    >
      <form className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" id="worker-form" noValidate onSubmit={submit}>
        <Input label="First name" {...form.register("first_name")} error={errors.first_name?.message} />
        <Input label="Last name" {...form.register("last_name")} error={errors.last_name?.message} />
        <Input label="Worker code" placeholder="Auto-generated if empty" {...form.register("worker_code")} />
        <Input label="Email" type="email" {...form.register("email")} error={errors.email?.message} />
        <Input label="Phone" type="tel" {...form.register("phone")} />
        <Select label="Category" {...form.register("category")}>
          {WORKER_CATEGORIES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input label="Skill" placeholder="mason, electrician..." {...form.register("skill_type")} error={errors.skill_type?.message} />
        <Input label="Designation" {...form.register("designation")} />
        <Input label="Experience (years)" min="0" step="any" type="number" {...form.register("experience_years")} error={errors.experience_years?.message} />
        <Select label="Employment" {...form.register("employment_type")}>
          {EMPLOYMENT_TYPES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input label="Joining date" type="date" {...form.register("joining_date")} />
        <Select label="Salary type" {...form.register("salary_type")}>
          {SALARY_TYPES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input label="Hourly rate (Rs)" min="0" step="any" type="number" {...form.register("hourly_rate")} error={errors.hourly_rate?.message} />
        <Input label="Salary amount (Rs)" min="0" step="any" type="number" {...form.register("salary_amount")} error={errors.salary_amount?.message} />
        <Select label="Project" {...form.register("project_id")}>
          <option value="">Not assigned</option>
          {projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
        <Select label="Status" {...form.register("status")}>
          {WORKER_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
      </form>
    </Modal>
  );
}

export function WorkforcePage() {
  const { user } = useAuth();
  const { projects, nameOf } = useProjectOptions();
  const { data, loading, error, reload } = useAsyncData(async () => normalizeList(await getWorkers()).items, [], { initialData: [] });
  const { run } = useAction();
  const [filters, setFilters] = useState({ query: "", category: "", status: "", project: "" });
  const [form, setForm] = useState({ open: false, worker: null });
  const [details, setDetails] = useState(null);
  const workers = data;
  const isManager = can.manage(user);

  const filtered = useMemo(
    () =>
      workers.filter(
        (worker) =>
          matchesSearch([workerName(worker), worker.worker_code, worker.email, worker.phone, worker.skill_type, worker.designation], filters.query) &&
          (!filters.category || worker.category === filters.category) &&
          (!filters.status || worker.status === filters.status) &&
          (!filters.project || worker.project_id === filters.project),
      ),
    [workers, filters],
  );

  async function remove(worker) {
    if (!confirmAction(`Delete ${workerName(worker)}? This cannot be undone.`)) return;
    await run("delete", () => deleteWorker(getId(worker)), { success: "Worker deleted.", error: "Unable to delete worker.", onSuccess: reload });
  }

  const count = (status) => workers.filter((worker) => worker.status === status).length;

  return (
    <>
      <PageHeader
        onRefresh={reload}
        title="Workers"
        description="Site workforce roster, skills and project assignment."
        action={
          <div className="flex flex-wrap gap-2">
            {isManager ? <Button onClick={() => setForm({ open: true, worker: null })}><Plus className="h-4 w-4" /> Add worker</Button> : null}
          </div>
        }
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total workers" value={workers.length} />
        <StatCard label="Available" value={count("available")} />
        <StatCard label="Assigned" value={count("assigned")} />
        <StatCard label="Unavailable" value={count("unavailable")} />
      </section>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SearchInput aria-label="Search workers" placeholder="Search name, code, skill..." value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} />
        <Select aria-label="Filter by category" className="h-10" value={filters.category} onChange={(event) => setFilters({ ...filters, category: event.target.value })}>
          <option value="">All categories</option>
          {WORKER_CATEGORIES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Select aria-label="Filter by status" className="h-10" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">All statuses</option>
          {WORKER_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Select aria-label="Filter by project" className="h-10" value={filters.project} onChange={(event) => setFilters({ ...filters, project: event.target.value })}>
          <option value="">All projects</option>
          {projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
      </div>
      {loading ? <LoadingState label="Loading workers..." /> : null}
      {!loading && error ? <ErrorState message={getApiErrorMessage(error)} onRetry={reload} /> : null}
      {!loading && !error ? (
        <DataTable
          columns={[
            { key: "name", header: "Worker", render: (row) => <button className="text-left font-semibold text-primary" onClick={() => setDetails(row)} type="button">{workerName(row)}</button> },
            { key: "worker_code", header: "Code" },
            { key: "category", header: "Category", render: (row) => formatStatus(row.category) },
            { key: "skill_type", header: "Skill" },
            { key: "phone", header: "Phone" },
            { key: "project_id", header: "Project", render: (row) => (row.project_id ? nameOf(row.project_id) : "Not assigned") },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            {
              key: "actions",
              header: "Actions",
              render: (row) => (
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => setDetails(row)} size="sm" variant="secondary">View</Button>
                  {isManager ? <Button onClick={() => setForm({ open: true, worker: row })} size="sm" variant="secondary">Edit</Button> : null}
                  {can.adminOnly(user) ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
                </div>
              ),
            },
          ]}
          emptyDescription={workers.length ? "No workers match the current filters." : "Add workers to build the site roster."}
          emptyTitle={workers.length ? "No matching workers" : "No workers"}
          getRowId={getId}
          rows={filtered}
        />
      ) : null}
      <WorkerFormModal onClose={() => setForm({ open: false, worker: null })} onSaved={() => { setForm({ open: false, worker: null }); reload(); }} open={form.open} projects={projects} worker={form.worker} />
      <Modal onClose={() => setDetails(null)} open={Boolean(details)} title={workerName(details)}>
        {details ? (
          <DetailList
            items={[
              ["Worker code", details.worker_code],
              ["Email", details.email],
              ["Phone", details.phone],
              ["Category", formatStatus(details.category)],
              ["Skill", details.skill_type],
              ["Designation", details.designation],
              ["Experience", `${details.experience_years ?? 0} years`],
              ["Employment", formatStatus(details.employment_type)],
              ["Joined", formatDate(details.joining_date)],
              ["Salary", `${formatStatus(details.salary_type)} · ${formatCurrency(details.salary_amount)}`],
              ["Hourly rate", formatCurrency(details.hourly_rate)],
              ["Project", details.project_id ? nameOf(details.project_id) : "Not assigned"],
              ["Attendance (30 days)", details.attendance_pct != null ? `${Number(details.attendance_pct).toFixed(0)}%` : null],
              ["Status", <StatusBadge key="s" status={details.status} />],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
