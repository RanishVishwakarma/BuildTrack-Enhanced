import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { DetailList } from "../../../components/common/DetailList.jsx";
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
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useWorkerOptions } from "../../../hooks/useLookups.js";
import { can } from "../../../lib/roles.js";
import { cn, dateInputToIso, formatCurrency, formatDate, formatStatus, getId, normalizeList, projectName, toDateInput, workerName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getProjectResources } from "../../resources/services/resourceService.js";
import { createTask, deleteTask, getTasksForProject, updateTask } from "../../tasks/services/taskService.js";
import { getProjectAllocations } from "../../workforce/services/workforceService.js";
import { WORKER_CATEGORIES } from "../../workforce/constants.js";
import { MilestoneFormModal } from "../components/MilestoneFormModal.jsx";
import { ProjectFormModal } from "../components/ProjectFormModal.jsx";
import {
  createDocumentRecord,
  deleteDocumentRecord,
  deleteMilestoneRecord,
  deleteProject,
  getDocumentRecords,
  getMilestoneRecords,
  getProject,
  projectStatusLabel,
  recordProjectId,
} from "../services/projectService.js";

const SECTIONS = ["overview", "milestones", "tasks", "team", "resources", "documents"];

const taskSchema = z.object({
  title: z.string().trim().min(2, "Title must be at least 2 characters."),
  description: z.string().optional(),
  assigned_worker_id: z.string().optional(),
  assigned_category: z.string().optional(),
  due_date: z.string().optional(),
  status: z.enum(["pending", "completed"]),
});

function TaskFormModal({ open, task, projectId, workers, onClose, onSaved }) {
  const editing = Boolean(task);
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(taskSchema),
    values: open
      ? {
          title: task?.title || "",
          description: task?.description || "",
          assigned_worker_id: task?.assigned_worker_id || "",
          assigned_category: task?.assigned_category || "",
          due_date: task?.due_date ? toDateInput(task.due_date) : "",
          status: task?.status === "completed" ? "completed" : "pending",
        }
      : undefined,
  });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    const payload = {
      ...values,
      description: values.description || undefined,
      assigned_worker_id: values.assigned_worker_id || undefined,
      assigned_category: values.assigned_category || undefined,
      due_date: dateInputToIso(values.due_date),
    };
    const result = await run("save", () => (editing ? updateTask(getId(task), payload) : createTask({ ...payload, project_id: projectId })), {
      success: editing ? "Task updated." : "Task created.",
      error: editing ? "Unable to update task." : "Unable to create task.",
    });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="task-form" type="submit">{pending ? "Saving..." : "Save task"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? "Edit task" : "New task"}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="task-form" noValidate onSubmit={submit}>
        <div className="sm:col-span-2"><Input label="Title" {...form.register("title")} error={errors.title?.message} /></div>
        <Select label="Assign to worker" {...form.register("assigned_worker_id")}>
          <option value="">Unassigned</option>
          {workers.map((worker) => <option key={getId(worker)} value={getId(worker)}>{workerName(worker)}</option>)}
        </Select>
        <Select label="Worker category" {...form.register("assigned_category")}>
          <option value="">Any</option>
          {WORKER_CATEGORIES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Input label="Due date" type="date" {...form.register("due_date")} />
        <Select label="Status" {...form.register("status")}>
          <option value="pending">Pending</option>
          <option value="completed">Completed</option>
        </Select>
        <div className="sm:col-span-2"><Textarea label="Description" {...form.register("description")} /></div>
      </form>
    </Modal>
  );
}

// Angular kept project documents as records (name and type) in
// project_documents; the file itself was never uploaded, and the backend has
// no project-linked file storage. React keeps those records, labelled as such.
function DocumentRecordModal({ open, projectId, onClose, onSaved }) {
  const { run, pending } = useAction();
  const [values, setValues] = useState({ name: "", type: "" });
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (values.name.trim().length < 2) {
      setError("Enter the document name.");
      return;
    }
    const result = await run("save", () => createDocumentRecord({ projectId, name: values.name.trim(), type: values.type.trim() || "Document" }), {
      success: "Document record added.",
      error: "Unable to add document record.",
    });
    if (result) {
      setValues({ name: "", type: "" });
      onSaved();
    }
  }

  return (
    <Modal
      description="Records the document name and type in the project register. The file itself is not stored."
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="document-form" type="submit">{pending ? "Saving..." : "Add record"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      size="sm"
      title="Add document record"
    >
      <form className="space-y-4" id="document-form" noValidate onSubmit={submit}>
        <Input error={error} label="Document name" placeholder="Structural drawings rev B.pdf" value={values.name} onChange={(event) => { setValues({ ...values, name: event.target.value }); setError(""); }} />
        <Input label="Type" placeholder="PDF, Drawing, Permit..." value={values.type} onChange={(event) => setValues({ ...values, type: event.target.value })} />
      </form>
    </Modal>
  );
}

export function ProjectDetailsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { run } = useAction();
  const [section, setSection] = useState("overview");
  const [editing, setEditing] = useState(false);
  const [milestoneForm, setMilestoneForm] = useState({ open: false, milestone: null });
  const [addingDocument, setAddingDocument] = useState(false);
  const [taskForm, setTaskForm] = useState({ open: false, task: null });
  const isManager = can.manage(user);
  const canAssignTasks = can.assignTasks(user);
  const workerLookup = useWorkerOptions();

  const project = useAsyncData(() => getProject(projectId), [projectId]);
  const tasks = useAsyncData(() => getTasksForProject(projectId), [projectId], { initialData: [], enabled: section === "tasks" || section === "overview" });
  const team = useAsyncData(async () => normalizeList(await getProjectAllocations(projectId)).items, [projectId], { initialData: [], enabled: section === "team" || section === "overview" });
  const resources = useAsyncData(() => getProjectResources(projectId), [projectId], { initialData: [], enabled: section === "resources" });
  const milestoneRecords = useAsyncData(
    async () => (await getMilestoneRecords()).filter((milestone) => recordProjectId(milestone) === projectId),
    [projectId],
    { initialData: [], enabled: section === "milestones" || section === "overview" },
  );
  const documents = useAsyncData(
    async () => (await getDocumentRecords()).filter((document) => recordProjectId(document) === projectId),
    [projectId],
    { initialData: [], enabled: section === "documents" },
  );

  if (project.loading) return <LoadingState label="Loading project..." />;
  if (project.error) {
    const notFound = project.error?.response?.status === 404 || project.error?.response?.status === 422;
    return (
      <>
        <Link className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-primary" to="/projects"><ArrowLeft className="h-4 w-4" /> Back to projects</Link>
        <ErrorState message={notFound ? "This project does not exist or was deleted." : getApiErrorMessage(project.error)} onRetry={notFound ? undefined : project.reload} />
      </>
    );
  }

  const record = project.data;
  const milestones = milestoneRecords.data || [];
  // Milestones embedded on the project document drive the backend progress figure.
  const embeddedMilestones = record.milestones || [];
  const taskList = tasks.data || [];

  async function remove() {
    if (!confirmAction(`Delete project ${projectName(record)}? This cannot be undone.`)) return;
    const result = await run("delete", () => deleteProject(getId(record)), { success: "Project deleted.", error: "Unable to delete project." });
    if (result) navigate("/projects", { replace: true });
  }

  async function removeMilestone(milestone) {
    if (!confirmAction(`Delete milestone "${milestone.title}"?`)) return;
    await run("delete-milestone", () => deleteMilestoneRecord(getId(milestone)), { success: "Milestone deleted.", error: "Unable to delete milestone.", onSuccess: milestoneRecords.reload });
  }

  async function removeDocument(document) {
    if (!confirmAction(`Delete the record for ${document.name || document.file_name}?`)) return;
    await run("delete-document", () => deleteDocumentRecord(getId(document)), { success: "Document record deleted.", error: "Unable to delete document record.", onSuccess: documents.reload });
  }

  async function toggleTask(task) {
    const status = task.status === "completed" ? "pending" : "completed";
    await run(`task-${getId(task)}`, () => updateTask(getId(task), { status }), { success: `Task marked ${status}.`, error: "Unable to update task.", onSuccess: tasks.reload });
  }

  async function removeTask(task) {
    if (!confirmAction(`Delete task "${task.title}"?`)) return;
    await run("delete-task", () => deleteTask(getId(task)), { success: "Task deleted.", error: "Unable to delete task.", onSuccess: tasks.reload });
  }

  return (
    <>
      <Link className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-primary" to="/projects"><ArrowLeft className="h-4 w-4" /> Back to projects</Link>
      <PageHeader
        eyebrow={record.category}
        title={projectName(record)}
        description={record.description || record.location}
        action={
          <div className="flex flex-wrap gap-2">
            {isManager ? <Button onClick={() => setEditing(true)} variant="secondary"><Pencil className="h-4 w-4" /> Edit</Button> : null}
            {can.adminOnly(user) ? <Button onClick={remove} variant="danger"><Trash2 className="h-4 w-4" /> Delete</Button> : null}
          </div>
        }
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card"><p className="text-sm font-medium text-muted">Status</p><div className="mt-2"><StatusBadge status={projectStatusLabel(record.status)} /></div></div>
        <StatCard helper={embeddedMilestones.length ? "Calculated by the backend from project milestones" : undefined} label="Progress" value={`${Number(record.progress || 0)}%`} />
        <StatCard label="Budget" value={formatCurrency(record.budget)} />
        <StatCard label="Timeline" value={formatDate(record.start_date)} helper={`to ${formatDate(record.end_date)}`} />
      </section>
      <div className="no-scrollbar mb-6 overflow-x-auto" role="tablist">
        <div className="inline-flex min-w-max gap-1 rounded-lg border border-border/80 bg-surface p-1 shadow-sm">
          {SECTIONS.map((key) => (
            <button
              aria-selected={section === key}
              className={cn("h-9 rounded-md px-3.5 text-sm font-semibold capitalize transition-colors", section === key ? "bg-primary text-primary-foreground shadow-sm" : "text-muted hover:bg-subtle hover:text-foreground")}
              key={key}
              onClick={() => setSection(key)}
              role="tab"
              type="button"
            >
              {key}
            </button>
          ))}
        </div>
      </div>

      {section === "overview" ? (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <section className="card">
            <h2 className="mb-4 text-lg font-semibold">Project information</h2>
            <DetailList
              items={[
                ["Manager", record.project_manager_name || "Unassigned"],
                ["Client", record.client],
                ["Client email", record.client_email || record.clientEmail],
                ["Location", record.location],
                ["Start", formatDate(record.start_date)],
                ["End", formatDate(record.end_date)],
                ["Category", record.category],
                ["Status", projectStatusLabel(record.status)],
              ]}
            />
          </section>
          <section className="card space-y-4">
            <h2 className="text-lg font-semibold">At a glance</h2>
            <p className="text-sm"><span className="font-semibold">{milestones.length}</span> milestones, {milestones.filter((m) => m.status === "Completed").length} completed</p>
            <p className="text-sm"><span className="font-semibold">{taskList.length}</span> tasks, {taskList.filter((t) => t.status !== "completed").length} open</p>
            <p className="text-sm"><span className="font-semibold">{(team.data || []).filter((a) => a.status === "ACTIVE").length}</span> workers actively allocated</p>
          </section>
        </div>
      ) : null}

      {section === "milestones" ? (
        <section className="card">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Milestones</h2>
            {isManager ? <Button onClick={() => setMilestoneForm({ open: true, milestone: null })} size="sm"><Plus className="h-4 w-4" /> Add milestone</Button> : null}
          </div>
          {milestoneRecords.loading ? <LoadingState label="Loading milestones..." /> : null}
          {!milestoneRecords.loading && milestoneRecords.error ? <ErrorState message={getApiErrorMessage(milestoneRecords.error)} onRetry={milestoneRecords.reload} /> : null}
          {!milestoneRecords.loading && !milestoneRecords.error ? (
            <DataTable
              columns={[
                { key: "title", header: "Milestone", render: (row) => <span className="font-semibold">{row.title}</span> },
                { key: "due", header: "Due", render: (row) => formatDate(row.due_date || row.dueDate) },
                { key: "progress", header: "Progress", render: (row) => `${Number(row.progress || 0)}%` },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
                ...(isManager
                  ? [{
                      key: "actions",
                      header: "Actions",
                      render: (row) => (
                        <div className="flex flex-wrap gap-2">
                          <Button onClick={() => setMilestoneForm({ open: true, milestone: row })} size="sm" variant="secondary">Edit</Button>
                          {can.adminOnly(user) ? <Button onClick={() => removeMilestone(row)} size="sm" variant="danger">Delete</Button> : null}
                        </div>
                      ),
                    }]
                  : []),
              ]}
              emptyDescription="No milestones have been added to this project."
              emptyTitle="No milestones"
              getRowId={getId}
              rows={milestones.slice().sort((a, b) => String(a.due_date || a.dueDate).localeCompare(String(b.due_date || b.dueDate)))}
            />
          ) : null}
          {embeddedMilestones.length ? (
            <div className="mt-6">
              <h3 className="font-semibold">Milestones stored on the project record</h3>
              <p className="mb-3 text-xs text-muted">Added through the project milestones API. The backend calculates project progress from these, and the API cannot edit them.</p>
              <DataTable
                columns={[
                  { key: "title", header: "Milestone" },
                  { key: "due_date", header: "Due", render: (row) => formatDate(row.due_date) },
                  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
                ]}
                getRowId={(row) => (typeof row._id === "string" ? row._id : `${row.title}-${row.due_date}`)}
                rows={embeddedMilestones}
              />
            </div>
          ) : null}
        </section>
      ) : null}

      {section === "documents" ? (
        <section className="card">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Document register</h2>
              <p className="text-xs text-muted">Names and types of project documents. Files are not stored by the backend.</p>
            </div>
            {isManager ? <Button onClick={() => setAddingDocument(true)} size="sm"><Plus className="h-4 w-4" /> Add record</Button> : null}
          </div>
          {documents.loading ? <LoadingState label="Loading documents..." /> : null}
          {!documents.loading && documents.error ? <ErrorState message={getApiErrorMessage(documents.error)} onRetry={documents.reload} /> : null}
          {!documents.loading && !documents.error ? (
            <DataTable
              columns={[
                { key: "name", header: "Document", render: (row) => <span className="font-semibold">{row.name || row.file_name}</span> },
                { key: "type", header: "Type", render: (row) => row.type || row.file_type || "Document" },
                { key: "recorded", header: "Recorded", render: (row) => formatDate(row.uploaded_at || row.uploadedAt || row.created_at) },
                ...(can.adminOnly(user) ? [{ key: "actions", header: "Actions", render: (row) => <Button onClick={() => removeDocument(row)} size="sm" variant="danger">Delete</Button> }] : []),
              ]}
              emptyDescription="No documents have been recorded for this project."
              emptyTitle="No documents"
              getRowId={getId}
              rows={documents.data || []}
            />
          ) : null}
        </section>
      ) : null}

      {section === "tasks" ? (
        <section className="card">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Tasks</h2>
            {canAssignTasks ? <Button onClick={() => setTaskForm({ open: true, task: null })} size="sm"><Plus className="h-4 w-4" /> New task</Button> : null}
          </div>
          {tasks.loading ? <LoadingState label="Loading tasks..." /> : null}
          {!tasks.loading && tasks.error ? <ErrorState message={getApiErrorMessage(tasks.error)} onRetry={tasks.reload} /> : null}
          {!tasks.loading && !tasks.error ? (
            <DataTable
              columns={[
                { key: "title", header: "Task", render: (row) => <span className="font-semibold">{row.title}</span> },
                { key: "assigned", header: "Assigned to", render: (row) => (row.assigned_worker_id ? workerLookup.nameOf(row.assigned_worker_id) : row.assigned_category ? formatStatus(row.assigned_category) : "Unassigned") },
                { key: "due_date", header: "Due", render: (row) => formatDate(row.due_date) },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
                ...(canAssignTasks
                  ? [{
                      key: "actions",
                      header: "Actions",
                      render: (row) => (
                        <div className="flex flex-wrap gap-2">
                          <Button onClick={() => toggleTask(row)} size="sm" variant="secondary">{row.status === "completed" ? "Reopen" : "Complete"}</Button>
                          <Button onClick={() => setTaskForm({ open: true, task: row })} size="sm" variant="secondary">Edit</Button>
                          {can.adminOnly(user) ? <Button onClick={() => removeTask(row)} size="sm" variant="danger">Delete</Button> : null}
                        </div>
                      ),
                    }]
                  : []),
              ]}
              emptyDescription="Break the project down into tasks and assign them to workers."
              emptyTitle="No tasks"
              getRowId={getId}
              rows={taskList}
            />
          ) : null}
        </section>
      ) : null}

      {section === "team" ? (
        <section className="card">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Allocated workers</h2>
            {can.manage(user) ? <Link className="text-sm font-semibold text-primary" to="/workers/allocation">Manage allocations</Link> : null}
          </div>
          {team.loading ? <LoadingState label="Loading team..." /> : null}
          {!team.loading && team.error ? <ErrorState message={getApiErrorMessage(team.error)} onRetry={team.reload} /> : null}
          {!team.loading && !team.error ? (
            <DataTable
              columns={[
                { key: "worker", header: "Worker", render: (row) => workerLookup.nameOf(row.worker_id) },
                { key: "role", header: "Role" },
                { key: "start_date", header: "From", render: (row) => formatDate(row.start_date) },
                { key: "end_date", header: "To", render: (row) => (row.end_date ? formatDate(row.end_date) : "Open") },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
              ]}
              emptyDescription="No workers are allocated to this project."
              emptyTitle="No team members"
              getRowId={getId}
              rows={team.data || []}
            />
          ) : null}
        </section>
      ) : null}

      {section === "resources" ? (
        <section className="card">
          <h2 className="mb-4 text-lg font-semibold">Assigned resources</h2>
          {resources.loading ? <LoadingState label="Loading resources..." /> : null}
          {!resources.loading && resources.error ? <ErrorState message={getApiErrorMessage(resources.error)} onRetry={resources.reload} /> : null}
          {!resources.loading && !resources.error ? (
            <DataTable
              columns={[
                { key: "resource_name", header: "Resource" },
                { key: "resource_type", header: "Type", render: (row) => formatStatus(row.resource_type) },
                { key: "quantity", header: "Qty", render: (row) => `${row.quantity} ${row.unit || ""}` },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
              ]}
              emptyDescription="Assign equipment from the Resources page."
              emptyTitle="No resources assigned"
              getRowId={getId}
              rows={resources.data || []}
            />
          ) : null}
        </section>
      ) : null}

      <ProjectFormModal onClose={() => setEditing(false)} onSaved={() => { setEditing(false); project.reload(); }} open={editing} project={record} />
      <MilestoneFormModal
        milestone={milestoneForm.milestone}
        onClose={() => setMilestoneForm({ open: false, milestone: null })}
        onSaved={() => { setMilestoneForm({ open: false, milestone: null }); milestoneRecords.reload(); }}
        open={milestoneForm.open}
        projectId={projectId}
      />
      <DocumentRecordModal onClose={() => setAddingDocument(false)} onSaved={() => { setAddingDocument(false); documents.reload(); }} open={addingDocument} projectId={projectId} />
      <TaskFormModal
        onClose={() => setTaskForm({ open: false, task: null })}
        onSaved={() => { setTaskForm({ open: false, task: null }); tasks.reload(); }}
        open={taskForm.open}
        projectId={projectId}
        task={taskForm.task}
        workers={workerLookup.workers}
      />
    </>
  );
}
