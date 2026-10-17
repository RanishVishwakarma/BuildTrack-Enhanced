import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { dateInputToIso, getId, toDateInput } from "../../../lib/utils.js";
import { getManagers } from "../../auth/services/authService.js";
import { PROJECT_CATEGORIES, PROJECT_STATUSES, createProject, updateProject } from "../services/projectService.js";

const projectSchema = z
  .object({
    name: z.string().trim().min(2, "Project name must be at least 2 characters."),
    category: z.string().min(1),
    status: z.string().min(1),
    project_manager_id: z.string().optional(),
    start_date: z.string().min(1, "Start date is required."),
    end_date: z.string().optional(),
    budget: z.coerce.number({ invalid_type_error: "Enter a budget." }).min(0, "Budget cannot be negative."),
    progress: z.coerce.number({ invalid_type_error: "Enter progress." }).min(0, "0-100 only.").max(100, "0-100 only."),
    client: z.string().optional(),
    client_email: z.union([z.literal(""), z.string().trim().email("Enter a valid client email.")]).optional(),
    location: z.string().optional(),
    description: z.string().optional(),
  })
  .refine((values) => !values.end_date || values.end_date >= values.start_date, { message: "End date cannot be before the start date.", path: ["end_date"] });

// Angular stored the selected manager's display name in project_manager_id;
// the same convention is kept so existing records render consistently.
const managerLabel = (manager) => (manager.name && manager.name !== "string" ? manager.name : manager.email?.split("@")[0]);

export function ProjectFormModal({ open, project, onClose, onSaved }) {
  const editing = Boolean(project);
  const { run, pending } = useAction();
  const managers = useAsyncData(getManagers, [], { initialData: [], enabled: open });
  const currentManager = project?.project_manager_id && project.project_manager_id !== "unassigned" ? project.project_manager_id : "";
  const form = useForm({
    resolver: zodResolver(projectSchema),
    values: open
      ? {
          name: project?.name || "",
          category: project?.category || "Commercial",
          status: PROJECT_STATUSES.some((item) => item.value === project?.status) ? project.status : "planning",
          project_manager_id: currentManager,
          start_date: project?.start_date ? toDateInput(project.start_date) : toDateInput(),
          end_date: project?.end_date ? toDateInput(project.end_date) : "",
          budget: project?.budget ?? 0,
          progress: project?.progress ?? 0,
          client: project?.client || "",
          client_email: project?.client_email || project?.clientEmail || "",
          location: project?.location || "",
          description: project?.description || "",
        }
      : undefined,
  });
  const errors = form.formState.errors;
  const managerOptions = (managers.data || []).map(managerLabel);

  const submit = form.handleSubmit(async (values) => {
    const payload = {
      ...values,
      project_manager_id: values.project_manager_id || "unassigned",
      start_date: dateInputToIso(values.start_date),
      end_date: dateInputToIso(values.end_date),
      // Matches Angular: completing a project sets progress to 100.
      progress: values.status === "completed" ? 100 : values.progress,
      client: values.client || undefined,
      client_email: values.client_email ? values.client_email.toLowerCase() : undefined,
      location: values.location || undefined,
      description: values.description || undefined,
    };
    const result = await run("save", () => (editing ? updateProject(getId(project), payload) : createProject(payload)), {
      success: editing ? "Project updated." : "Project created.",
      error: editing ? "Unable to update project." : "Unable to create project.",
    });
    if (result) onSaved(result);
  });

  return (
    <Modal
      footer={
        <>
          <Button disabled={Boolean(pending)} onClick={onClose} variant="secondary">Cancel</Button>
          <Button disabled={Boolean(pending)} form="project-form" type="submit">{pending ? "Saving..." : "Save project"}</Button>
        </>
      }
      onClose={onClose}
      open={open}
      size="lg"
      title={editing ? `Edit ${project.name}` : "New project"}
    >
      <form className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" id="project-form" noValidate onSubmit={submit}>
        <div className="sm:col-span-2"><Input label="Project name" {...form.register("name")} error={errors.name?.message} /></div>
        <Select label="Category" {...form.register("category")}>
          {PROJECT_CATEGORIES.map((value) => <option key={value} value={value}>{value}</option>)}
        </Select>
        <Select label="Status" {...form.register("status")}>
          {PROJECT_STATUSES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </Select>
        <Select label="Project manager" {...form.register("project_manager_id")}>
          <option value="">Unassigned</option>
          {currentManager && !managerOptions.includes(currentManager) ? <option value={currentManager}>{currentManager}</option> : null}
          {managerOptions.map((name) => <option key={name} value={name}>{name}</option>)}
        </Select>
        <Input label="Location" {...form.register("location")} />
        <Input label="Start date" type="date" {...form.register("start_date")} error={errors.start_date?.message} />
        <Input label="End date" type="date" {...form.register("end_date")} error={errors.end_date?.message} />
        <Input label="Budget (Rs)" min="0" step="any" type="number" {...form.register("budget")} error={errors.budget?.message} />
        <Input label="Progress (%)" max="100" min="0" type="number" {...form.register("progress")} error={errors.progress?.message} />
        <Input label="Client name" {...form.register("client")} />
        <Input label="Client email" type="email" {...form.register("client_email")} error={errors.client_email?.message} />
        <div className="sm:col-span-2 lg:col-span-3"><Textarea label="Description" {...form.register("description")} /></div>
      </form>
    </Modal>
  );
}
