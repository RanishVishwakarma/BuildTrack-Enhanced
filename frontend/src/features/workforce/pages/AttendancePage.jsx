import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { SearchInput } from "../../../components/common/SearchInput.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { TabNav } from "../../../components/common/TabNav.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions, useWorkerOptions } from "../../../hooks/useLookups.js";
import { ROLE, can, hasAnyRole } from "../../../lib/roles.js";
import { addDays, formatDate, formatStatus, getId, matchesSearch, normalizeList, projectName, toDateInput, workerName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { ATTENDANCE_STATUSES } from "../constants.js";
import { createAttendance, deleteAttendance, getAttendance, getLowAttendanceWorkers, notifyLowAttendance, updateAttendance } from "../services/workforceService.js";

const dayKey = (value) => (value ? toDateInput(value) : "");
const timeOf = (value) => (value ? new Date(value).toTimeString().slice(0, 5) : "");
function combine(date, time) {
  if (!date || !time) return undefined;
  const value = new Date(`${date}T${time}:00`);
  return Number.isNaN(value.getTime()) ? undefined : value.toISOString();
}

function EditAttendanceModal({ record, onClose, onSaved }) {
  const { run, pending } = useAction();
  const date = dayKey(record?.date);
  const [values, setValues] = useState({
    status: record?.status || "present",
    check_in: timeOf(record?.check_in_time),
    check_out: timeOf(record?.check_out_time),
    hours_worked: record?.hours_worked ?? "",
    overtime_hours: record?.overtime_hours ?? 0,
    remarks: record?.remarks || "",
  });
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (values.check_in && values.check_out && values.check_out <= values.check_in) {
      setError("Check-out must be after check-in.");
      return;
    }
    const payload = {
      status: values.status,
      check_in_time: combine(date, values.check_in),
      check_out_time: combine(date, values.check_out),
      hours_worked: values.hours_worked === "" ? undefined : Number(values.hours_worked),
      overtime_hours: Number(values.overtime_hours || 0),
      remarks: values.remarks || undefined,
    };
    const result = await run("save", () => updateAttendance(getId(record), payload), { success: "Attendance updated.", error: "Unable to update attendance." });
    if (result) onSaved();
  }

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="attendance-form" type="submit">{pending ? "Saving..." : "Save"}</Button>
        </>
      }
      onClose={onClose}
      open={Boolean(record)}
      title={`Attendance · ${formatDate(record?.date)}`}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="attendance-form" noValidate onSubmit={submit}>
        <Select label="Status" value={values.status} onChange={(event) => setValues({ ...values, status: event.target.value })}>
          {ATTENDANCE_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input label="Hours worked" min="0" step="0.25" type="number" value={values.hours_worked} onChange={(event) => setValues({ ...values, hours_worked: event.target.value })} />
        <Input label="Check-in" type="time" value={values.check_in} onChange={(event) => { setValues({ ...values, check_in: event.target.value }); setError(""); }} />
        <Input error={error} label="Check-out" type="time" value={values.check_out} onChange={(event) => { setValues({ ...values, check_out: event.target.value }); setError(""); }} />
        <Input label="Overtime hours" min="0" step="0.25" type="number" value={values.overtime_hours} onChange={(event) => setValues({ ...values, overtime_hours: event.target.value })} />
        <div className="sm:col-span-2"><Textarea label="Remarks" value={values.remarks} onChange={(event) => setValues({ ...values, remarks: event.target.value })} /></div>
      </form>
    </Modal>
  );
}

function DailyRoster({ records, workers, reload, canMark }) {
  const [date, setDate] = useState(toDateInput());
  const [query, setQuery] = useState("");
  const { run, pending } = useAction();
  const isFuture = date > toDateInput();

  const rows = useMemo(() => {
    const byWorker = new Map(records.filter((record) => dayKey(record.date) === date).map((record) => [String(record.worker_id), record]));
    return workers
      .filter((worker) => matchesSearch([workerName(worker), worker.worker_code, worker.designation, worker.category], query))
      .map((worker) => ({ worker, record: byWorker.get(String(getId(worker))) }));
  }, [records, workers, date, query]);

  async function mark(row, status) {
    if (isFuture) return;
    const action = row.record
      ? () => updateAttendance(getId(row.record), { status })
      : () => createAttendance({ worker_id: getId(row.worker), project_id: row.worker.project_id || undefined, date: new Date(`${date}T00:00:00`).toISOString(), status });
    await run(`mark-${getId(row.worker)}`, action, { error: `Unable to mark ${workerName(row.worker)}.`, onSuccess: reload });
  }

  async function markAllPresent() {
    const pendingRows = rows.filter((row) => row.record?.status !== "present");
    if (!pendingRows.length || !confirmAction(`Mark ${pendingRows.length} worker(s) present for ${formatDate(date)}?`)) return;
    await run("all", async () => {
      for (const row of pendingRows) {
        if (row.record) await updateAttendance(getId(row.record), { status: "present" });
        else await createAttendance({ worker_id: getId(row.worker), project_id: row.worker.project_id || undefined, date: new Date(`${date}T00:00:00`).toISOString(), status: "present" });
      }
    }, { success: "Attendance marked.", error: "Some attendance records could not be saved.", onSuccess: reload });
  }

  const marked = rows.filter((row) => row.record);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Button aria-label="Previous day" onClick={() => setDate(addDays(-1, new Date(`${date}T00:00:00`)))} size="icon" variant="secondary"><ChevronLeft className="h-4 w-4" /></Button>
        <div className="w-44"><Input aria-label="Attendance date" type="date" value={date} onChange={(event) => setDate(event.target.value || toDateInput())} /></div>
        <Button aria-label="Next day" onClick={() => setDate(addDays(1, new Date(`${date}T00:00:00`)))} size="icon" variant="secondary"><ChevronRight className="h-4 w-4" /></Button>
        <Button onClick={() => setDate(toDateInput())} variant="secondary">Today</Button>
        <div className="min-w-[220px] flex-1"><SearchInput aria-label="Search roster" placeholder="Search worker..." value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        {canMark ? <Button disabled={isFuture || Boolean(pending)} onClick={markAllPresent}>Mark all present</Button> : null}
      </div>
      <section className="mb-4 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Workers" value={rows.length} />
        <StatCard label="Present" value={marked.filter((row) => row.record.status === "present").length} />
        <StatCard label="Absent / leave" value={marked.filter((row) => row.record.status !== "present").length} />
        <StatCard label="Not marked" value={rows.length - marked.length} />
      </section>
      {isFuture ? <p className="mb-4 rounded-md bg-warning/10 p-3 text-sm text-warning">Attendance cannot be recorded for a future date.</p> : null}
      <DataTable
        columns={[
          { key: "worker", header: "Worker", render: (row) => <span className="font-semibold">{workerName(row.worker)}</span> },
          { key: "code", header: "Code", render: (row) => row.worker.worker_code || "Not set" },
          { key: "role", header: "Role", render: (row) => row.worker.designation || formatStatus(row.worker.category) },
          { key: "status", header: "Status", render: (row) => (row.record ? <StatusBadge status={row.record.status} /> : <span className="text-sm text-muted">Not marked</span>) },
          {
            key: "actions",
            header: "Mark",
            render: (row) =>
              canMark ? (
                <div className="flex flex-wrap gap-1">
                  {ATTENDANCE_STATUSES.map((status) => (
                    <Button
                      aria-pressed={row.record?.status === status}
                      disabled={isFuture || Boolean(pending)}
                      key={status}
                      onClick={() => mark(row, status)}
                      size="sm"
                      variant={row.record?.status === status ? "primary" : "secondary"}
                    >
                      {formatStatus(status)}
                    </Button>
                  ))}
                </div>
              ) : null,
          },
        ]}
        emptyDescription="Add workers to the roster to record attendance."
        emptyTitle="No workers"
        getRowId={(row) => getId(row.worker)}
        rows={rows}
      />
    </>
  );
}

function RecordsView({ records, workerLookup, projectLookup, reload, canEdit, canDelete, filters, setFilters, showWorkerFilter }) {
  const { run } = useAction();
  const [editing, setEditing] = useState(null);

  async function remove(record) {
    if (!confirmAction(`Delete the attendance record for ${workerLookup.nameOf(record.worker_id)} on ${formatDate(record.date)}?`)) return;
    await run("delete", () => deleteAttendance(getId(record)), { success: "Attendance record deleted.", error: "Unable to delete attendance record.", onSuccess: reload });
  }

  const rows = records
    .filter((record) => (!filters.from || dayKey(record.date) >= filters.from) && (!filters.to || dayKey(record.date) <= filters.to) && (!filters.status || record.status === filters.status))
    .sort((a, b) => String(b.date).localeCompare(String(a.date)));

  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {showWorkerFilter ? (
          <Select aria-label="Filter by worker" className="h-10" value={filters.worker} onChange={(event) => setFilters({ ...filters, worker: event.target.value, project: "" })}>
            <option value="">All workers</option>
            {workerLookup.workers.map((worker) => <option key={getId(worker)} value={getId(worker)}>{workerName(worker)}</option>)}
          </Select>
        ) : null}
        {showWorkerFilter ? (
          <Select aria-label="Filter by project" className="h-10" value={filters.project} onChange={(event) => setFilters({ ...filters, project: event.target.value, worker: "" })}>
            <option value="">All projects</option>
            {projectLookup.projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
          </Select>
        ) : null}
        <Select aria-label="Filter by status" className="h-10" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">All statuses</option>
          {ATTENDANCE_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input aria-label="From date" className="h-10" type="date" value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} />
        <Input aria-label="To date" className="h-10" type="date" value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} />
      </div>
      <DataTable
        columns={[
          { key: "date", header: "Date", render: (row) => formatDate(row.date) },
          { key: "worker", header: "Worker", render: (row) => workerLookup.nameOf(row.worker_id) },
          { key: "project", header: "Project", render: (row) => (row.project_id ? projectLookup.nameOf(row.project_id) : "Not set") },
          { key: "check", header: "In / out", render: (row) => [timeOf(row.check_in_time), timeOf(row.check_out_time)].filter(Boolean).join(" - ") || "Not set" },
          { key: "hours_worked", header: "Hours", render: (row) => row.hours_worked ?? "Not set" },
          { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
          ...(canEdit || canDelete
            ? [{
                key: "actions",
                header: "Actions",
                render: (row) => (
                  <div className="flex flex-wrap gap-2">
                    {canEdit ? <Button onClick={() => setEditing(row)} size="sm" variant="secondary">Edit</Button> : null}
                    {canDelete ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
                  </div>
                ),
              }]
            : []),
        ]}
        emptyDescription="No attendance has been recorded for these filters."
        emptyTitle="No attendance records"
        getRowId={getId}
        rows={rows}
      />
      <EditAttendanceModal key={getId(editing) || "none"} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} record={editing} />
    </>
  );
}

function LowAttendanceView({ projectLookup }) {
  const [params, setParams] = useState({ days: 30, threshold: 75, projectId: "" });
  const { run, isPending } = useAction();
  const [notified, setNotified] = useState(() => new Set());
  const { data, loading, error, reload } = useAsyncData(() => getLowAttendanceWorkers(params), [params.days, params.threshold, params.projectId]);
  const rows = Array.isArray(data) ? data : normalizeList(data).items;

  async function notify(row) {
    const result = await run(`notify-${row.worker_id}`, () => notifyLowAttendance(row.worker_id, params.days), {
      success: `Warning sent to ${row.worker_name}.`,
      error: "Unable to notify worker. They may not have a login yet.",
    });
    if (result) setNotified((current) => new Set(current).add(row.worker_id));
  }

  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Input label="Look-back (days)" min="1" type="number" value={params.days} onChange={(event) => setParams({ ...params, days: Number(event.target.value) || 30 })} />
        <Input label="Threshold (%)" max="100" min="1" type="number" value={params.threshold} onChange={(event) => setParams({ ...params, threshold: Number(event.target.value) || 75 })} />
        <Select label="Project" value={params.projectId} onChange={(event) => setParams({ ...params, projectId: event.target.value })}>
          <option value="">All projects</option>
          {projectLookup.projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
        </Select>
      </div>
      {loading ? <LoadingState label="Checking attendance..." /> : null}
      {!loading && error ? <ErrorState message={getApiErrorMessage(error)} onRetry={reload} /> : null}
      {!loading && !error ? (
        <DataTable
          columns={[
            { key: "worker_name", header: "Worker" },
            { key: "project_id", header: "Project", render: (row) => (row.project_id ? projectLookup.nameOf(row.project_id) : "Not set") },
            { key: "present_days", header: "Present / recorded", render: (row) => `${row.present_days} / ${row.total_days}` },
            { key: "attendance_percentage", header: "Attendance", render: (row) => `${Number(row.attendance_percentage || 0).toFixed(1)}%` },
            {
              key: "actions",
              header: "Action",
              render: (row) => (
                <Button disabled={notified.has(row.worker_id) || isPending(`notify-${row.worker_id}`)} onClick={() => notify(row)} size="sm">
                  {notified.has(row.worker_id) ? "Notified" : "Send warning"}
                </Button>
              ),
            },
          ]}
          emptyDescription={`No workers are below ${params.threshold}% over the last ${params.days} days.`}
          emptyTitle="Attendance is on track"
          getRowId={(row) => row.worker_id}
          rows={rows}
        />
      ) : null}
    </>
  );
}

export function AttendancePage() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const isWorker = hasAnyRole(user, [ROLE.WORKER]);
  const isManager = can.manage(user);
  const workerLookup = useWorkerOptions({ enabled: !isWorker });
  const projectLookup = useProjectOptions();
  const [filters, setFilters] = useState({ worker: "", project: "", status: "", from: "", to: "" });

  // Workers only ever see their own records (GET /attendance/worker/{id}).
  const records = useAsyncData(
    async () => {
      if (isWorker) return user?.workerId ? getAttendance({ workerId: user.workerId }) : [];
      return getAttendance({ workerId: filters.worker || undefined, projectId: filters.project || undefined });
    },
    [isWorker, user?.workerId, filters.worker, filters.project],
    { initialData: [] },
  );
  const list = Array.isArray(records.data) ? records.data : normalizeList(records.data).items;

  const views = isWorker
    ? [{ key: "records", label: "My attendance", to: "/attendance" }]
    : [
        { key: "roster", label: "Daily roster", to: "/attendance?view=roster" },
        { key: "records", label: "All records", to: "/attendance?view=records" },
        ...(isManager ? [{ key: "low", label: "Low attendance", to: "/attendance?view=low" }] : []),
      ];
  const view = views.some((item) => item.key === searchParams.get("view")) ? searchParams.get("view") : views[0].key;

  return (
    <>
      <PageHeader
        title={isWorker ? "My Attendance" : "Attendance"}
        description={isWorker ? "Your attendance as recorded by site management." : "Daily attendance roster, history and low-attendance follow-up."}
        onRefresh={records.reload}
      />
      <TabNav active={view} label="Attendance views" tabs={views} />
      {isWorker && !user?.workerId ? (
        <ErrorState message="Your login is not linked to a worker profile, so attendance cannot be loaded. Ask an administrator to link it." />
      ) : null}
      {view === "low" ? <LowAttendanceView projectLookup={projectLookup} /> : null}
      {view !== "low" && records.loading ? <LoadingState label="Loading attendance..." /> : null}
      {view !== "low" && !records.loading && records.error ? <ErrorState message={getApiErrorMessage(records.error)} onRetry={records.reload} /> : null}
      {view !== "low" && !records.loading && !records.error ? (
        view === "roster" ? (
          workerLookup.loading ? <LoadingState label="Loading workers..." /> : <DailyRoster canMark={isManager} records={list} reload={records.reload} workers={workerLookup.workers} />
        ) : (
          <RecordsView
            canDelete={can.adminOnly(user)}
            canEdit={isManager}
            filters={filters}
            projectLookup={projectLookup}
            records={list}
            reload={records.reload}
            setFilters={setFilters}
            showWorkerFilter={!isWorker}
            workerLookup={isWorker ? { workers: [], nameOf: () => user?.name || "Me" } : workerLookup}
          />
        )
      ) : null}
    </>
  );
}
