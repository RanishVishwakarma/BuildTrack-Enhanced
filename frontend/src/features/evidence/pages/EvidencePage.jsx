import { Camera, ImageIcon, ScanSearch, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState } from "../../../components/common/EmptyState.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { Textarea } from "../../../components/ui/Textarea.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { hasPermission } from "../../../lib/roles.js";
import { formatDateTime, getId, projectName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getAiStatus } from "../../ai-assistant/services/aiService.js";
import { getTasksForProject } from "../../tasks/services/taskService.js";
import { analyzeEvidence, getEvidence, getEvidenceFlags, getEvidenceUrl, reviewEvidence, uploadEvidence } from "../services/evidenceService.js";

const ACCEPT = "image/jpeg,image/png,image/webp";

function Thumbnail({ item }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getEvidenceUrl(item._id).then((link) => { if (!cancelled) setUrl(link); }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [item._id]);
  if (failed) return <div className="flex aspect-video items-center justify-center bg-subtle text-xs text-muted">Not available</div>;
  if (!url) return <div className="aspect-video animate-pulse bg-subtle" />;
  return <img alt={item.description} className="aspect-video w-full object-cover" loading="lazy" src={url} />;
}

export function EvidencePage() {
  const { user } = useAuth();
  const { projects } = useProjectOptions();
  const [projectId, setProjectId] = useState("");
  const evidence = useAsyncData(() => getEvidence({ projectId }), [projectId], { initialData: [] });
  const canReview = hasPermission(user, "evidence.review");
  const flags = useAsyncData(() => (canReview ? getEvidenceFlags(projectId) : null), [projectId, canReview]);
  const status = useAsyncData(getAiStatus, []);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [form, setForm] = useState({ projectId: "", taskId: "", location: "", description: "", file: null });
  const tasks = useAsyncData(() => (form.projectId ? getTasksForProject(form.projectId) : []), [form.projectId], { initialData: [] });
  const [reviewing, setReviewing] = useState(null);
  const [review, setReview] = useState({ status: "accepted", note: "" });
  const { run, pending, isPending } = useAction();

  async function submitUpload(event) {
    event.preventDefault();
    const result = await run("upload", () => uploadEvidence(form), { success: "Evidence uploaded." });
    if (result) {
      setUploadOpen(false);
      setForm({ projectId: "", taskId: "", location: "", description: "", file: null });
      evidence.reload();
      flags.reload();
    }
  }

  async function saveReview() {
    const result = await run("review", () => reviewEvidence(reviewing._id, review.status, review.note), { success: "Review saved." });
    if (result) {
      setReviewing(null);
      evidence.reload();
      flags.reload();
    }
  }

  return (
    <>
      <PageHeader
        action={hasPermission(user, "evidence.upload") ? <Button onClick={() => setUploadOpen(true)}><Upload className="h-4 w-4" /> Upload photo</Button> : null}
        description="Site photographs linked to projects and tasks. AI observations are prompts for review, not proof."
        eyebrow="Progress"
        onRefresh={evidence.reload}
        title="Progress evidence"
      />
      <div className="mb-4 w-64">
        <Select aria-label="Project" onChange={(event) => setProjectId(event.target.value)} value={projectId}>
          <option value="">All my projects</option>
          {projects.map((p) => <option key={getId(p)} value={getId(p)}>{projectName(p)}</option>)}
        </Select>
      </div>

      {canReview && flags.data?.completed_without_evidence?.length ? (
        <section className="mb-5 rounded-lg border border-warning/30 bg-warning/5 p-4">
          <h3 className="text-sm font-semibold text-warning">Completed tasks without evidence ({flags.data.completed_without_evidence.length})</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">{flags.data.completed_without_evidence.slice(0, 12).map((f) => <li key={f.task_id}>{f.title}</li>)}</ul>
        </section>
      ) : null}

      {evidence.loading && !evidence.data?.length ? <LoadingState label="Loading evidence..." /> : null}
      {evidence.error ? <ErrorState message={getApiErrorMessage(evidence.error)} onRetry={evidence.reload} /> : null}
      {!evidence.loading && !evidence.error && !evidence.data?.length ? <EmptyState title="No evidence yet" description="Upload site photos to record progress against tasks and milestones." /> : null}

      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {(evidence.data || []).map((item) => (
          <li className="card overflow-hidden p-0" key={item._id}>
            <Thumbnail item={item} />
            <div className="space-y-2 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={item.review_status} />
                <span className="text-xs text-muted">{formatDateTime(item.created_at)}{item.location ? ` · ${item.location}` : ""}</span>
              </div>
              <p className="text-sm text-foreground">{item.description}</p>
              {item.flags?.length ? (
                <ul className="space-y-1">{item.flags.map((f, i) => <li className="rounded bg-warning/10 px-2 py-1 text-xs text-warning" key={i}>{f.message}</li>)}</ul>
              ) : null}
              {item.analysis ? (
                <details className="text-xs">
                  <summary className="cursor-pointer font-semibold text-foreground">AI observation</summary>
                  <p className="mt-1 text-foreground">{item.analysis.visible_work}</p>
                  <p className="mt-1 text-muted">Stage: {item.analysis.apparent_stage} · Match with report: {item.analysis.consistency_with_report.replace(/_/g, " ")}</p>
                  <p className="mt-1 text-muted">{item.analysis.label}</p>
                </details>
              ) : null}
              <div className="flex flex-wrap gap-2 pt-1">
                {status.data?.configured && (canReview || item.uploaded_by === String(user?.id)) ? (
                  <Button disabled={isPending(item._id)} onClick={() => run(item._id, () => analyzeEvidence(item._id), { success: "Observation added for review.", onSuccess: evidence.reload })} size="sm" variant="secondary">
                    <ScanSearch className="h-4 w-4" /> {isPending(item._id) ? "Analysing..." : item.analysis ? "Re-analyse" : "AI observe"}
                  </Button>
                ) : null}
                {canReview && item.uploaded_by !== String(user?.id) ? (
                  <Button onClick={() => { setReviewing(item); setReview({ status: "accepted", note: "" }); }} size="sm" variant="secondary">Review</Button>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>

      <Modal
        footer={<><Button onClick={() => setUploadOpen(false)} variant="secondary">Cancel</Button><Button disabled={pending === "upload"} form="evidence-upload" type="submit">{pending === "upload" ? "Uploading..." : "Upload"}</Button></>}
        onClose={() => setUploadOpen(false)}
        open={uploadOpen}
        title="Upload progress photo"
        description="JPEG, PNG or WebP up to 10 MB. Stored privately; only people with access to the project can view it."
      >
        <form className="grid gap-3 sm:grid-cols-2" id="evidence-upload" onSubmit={submitUpload}>
          <Select label="Project" onChange={(event) => setForm({ ...form, projectId: event.target.value, taskId: "" })} required value={form.projectId}>
            <option value="">Choose a project</option>
            {projects.map((p) => <option key={getId(p)} value={getId(p)}>{projectName(p)}</option>)}
          </Select>
          <Select label="Task (optional)" onChange={(event) => setForm({ ...form, taskId: event.target.value })} value={form.taskId}>
            <option value="">No specific task</option>
            {(Array.isArray(tasks.data) ? tasks.data : []).map((t) => <option key={getId(t)} value={getId(t)}>{t.title}</option>)}
          </Select>
          <Input label="Location on site (optional)" maxLength={200} onChange={(event) => setForm({ ...form, location: event.target.value })} value={form.location} />
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="evidence-file">Photo</label>
            <label className="flex h-11 cursor-pointer items-center gap-2 rounded-md border border-dashed border-input px-3 text-sm text-muted hover:bg-subtle" htmlFor="evidence-file">
              {form.file ? <ImageIcon className="h-4 w-4" /> : <Camera className="h-4 w-4" />} <span className="truncate">{form.file ? form.file.name : "Choose or take a photo"}</span>
            </label>
            <input accept={ACCEPT} capture="environment" className="sr-only" id="evidence-file" onChange={(event) => setForm({ ...form, file: event.target.files?.[0] || null })} required type="file" />
          </div>
          <div className="sm:col-span-2">
            <Textarea label="What does it show?" maxLength={1000} minLength={3} onChange={(event) => setForm({ ...form, description: event.target.value })} required value={form.description} />
          </div>
        </form>
      </Modal>

      <Modal
        footer={<><Button onClick={() => setReviewing(null)} variant="secondary">Cancel</Button><Button disabled={pending === "review" || review.note.trim().length < 3} onClick={saveReview}>Save review</Button></>}
        onClose={() => setReviewing(null)}
        open={Boolean(reviewing)}
        size="sm"
        title="Review evidence"
      >
        <div className="space-y-3">
          <Select label="Decision" onChange={(event) => setReview({ ...review, status: event.target.value })} value={review.status}>
            <option value="accepted">Accepted</option>
            <option value="needs_more_evidence">Needs more evidence</option>
            <option value="rejected">Rejected</option>
          </Select>
          <Textarea label="Note" onChange={(event) => setReview({ ...review, note: event.target.value })} value={review.note} />
          {reviewing?.flags?.length ? <p className="text-xs text-muted">Flags are prompts to check; decide based on the photo and site knowledge.</p> : null}
        </div>
      </Modal>
    </>
  );
}

