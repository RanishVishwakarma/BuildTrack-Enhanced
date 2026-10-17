import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { addDays, dateInputToIso, getId, projectName, toDateInput } from "../../../lib/utils.js";
import { MILESTONE_STATUSES, recordProjectId, saveMilestoneRecord } from "../services/projectService.js";

// Same fields and rules as Angular's milestone form.
const milestoneSchema = z.object({
  project_id: z.string().min(1, "Select a project."),
  title: z.string().trim().min(2, "Title must be at least 2 characters."),
  description: z.string().optional(),
  due_date: z.string().min(1, "Due date is required."),
  status: z.enum(MILESTONE_STATUSES),
  progress: z.coerce.number({ invalid_type_error: "Enter progress." }).min(0, "0-100 only.").max(100, "0-100 only."),
});

export function MilestoneFormModal({ open, milestone, projectId, projects = [], onClose, onSaved }) {
  const editing = Boolean(milestone);
  const { run, pending } = useAction();
  const form = useForm({
    resolver: zodResolver(milestoneSchema),
    values: open
      ? {
          project_id: recordProjectId(milestone) || projectId || "",
          title: milestone?.title || "",
          description: milestone?.description || "",
          due_date: milestone ? toDateInput(milestone.due_date || milestone.dueDate) : addDays(30),
          status: MILESTONE_STATUSES.includes(milestone?.status) ? milestone.status : "Not Started",
          progress: milestone?.progress ?? 0,
        }
      : undefined,
  });
  const errors = form.formState.errors;
  const status = form.watch("status");

  const submit = form.handleSubmit(async (values) => {
    const payload = {
      projectId: values.project_id,
      title: values.title.trim(),
      description: values.description || undefined,
      dueDate: dateInputToIso(values.due_date),
      status: values.status,
      progress: values.status === "Completed" ? 100 : values.progress,
    };
    const result = await run("save", () => saveMilestoneRecord(getId(milestone), payload), {
      success: editing ? "Milestone updated." : "Milestone added.",
      error: editing ? "Unable to update milestone." : "Unable to add milestone.",
    });
    if (result) onSaved();
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="milestone-form" type="submit">{pending ? "Saving..." : editing ? "Save milestone" : "Add milestone"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      title={editing ? `Edit ${milestone.title}` : "Add milestone"}
    >
      <form className="grid gap-4 sm:grid-cols-2" id="milestone-form" noValidate onSubmit={submit}>
        {projectId ? (
          <input type="hidden" {...form.register("project_id")} />
        ) : (
          <div className="sm:col-span-2">
            <Select label="Project" {...form.register("project_id")} error={errors.project_id?.message}>
              <option value="">Select project</option>
              {projects.map((project) => <option key={getId(project)} value={getId(project)}>{projectName(project)}</option>)}
            </Select>
          </div>
        )}
        <div className="sm:col-span-2"><Input label="Title" {...form.register("title")} error={errors.title?.message} /></div>
        <Input label="Due date" type="date" {...form.register("due_date")} error={errors.due_date?.message} />
        <Select label="Status" {...form.register("status")}>
          {MILESTONE_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
        </Select>
        <Input disabled={status === "Completed"} label="Progress (%)" max="100" min="0" type="number" {...form.register("progress")} error={errors.progress?.message} />
        <div className="sm:col-span-2"><Textarea label="Description" {...form.register("description")} /></div>
      </form>
    </Modal>
  );
}
