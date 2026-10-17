import { Download, FileText, Share2 } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions } from "../../../hooks/useLookups.js";
import { hasPermission } from "../../../lib/roles.js";
import { formatDateTime, getId, projectName } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { createReport, exportReport, getGeneratedReport, getGeneratedReports, getReportTypes, publishReport } from "../../insights/services/insightsService.js";
import { ReportView } from "./ReportView.jsx";

const CLIENT_SHAREABLE = ["daily_site", "weekly_project"];

export function ReportsTab({ status }) {
  const { user } = useAuth();
  const types = useAsyncData(getReportTypes, [], { initialData: [] });
  const reports = useAsyncData(getGeneratedReports, [], { initialData: [] });
  const { projects } = useProjectOptions();
  const [form, setForm] = useState({ reportType: "", projectId: "", days: "", aiSummary: false });
  const [viewing, setViewing] = useState(null);
  const { run, pending } = useAction();
  const selected = types.data?.find((t) => t.type === form.reportType);
  const canSummarize = hasPermission(user, "ai.report.generate") && status?.configured;
  const canExport = hasPermission(user, "reports.export.assigned");
  const canPublish = hasPermission(user, "reports.publish");

  async function generate(event) {
    event.preventDefault();
    const result = await run("generate", () => createReport({ ...form, days: form.days === "" ? "" : Number(form.days) }), { success: "Report generated." });
    if (result) {
      if (result.ai_summary_error) toast.error(`AI summary not added: ${result.ai_summary_error}`);
      setViewing(result);
      reports.reload();
    }
  }

  async function open(id) {
    try {
      setViewing(await getGeneratedReport(id));
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Unable to open the report."));
    }
  }

  const projectLabel = (id) => {
    const project = projects.find((p) => getId(p) === id);
    return project ? projectName(project) : id ? "Project" : "All my projects";
  };

  return (
    <div className="space-y-6">
      {types.data?.length ? (
        <form className="card grid gap-3 md:grid-cols-[1.4fr_1.4fr_0.7fr_auto] md:items-end" onSubmit={generate}>
          <Select label="Report" onChange={(event) => setForm({ ...form, reportType: event.target.value })} required value={form.reportType}>
            <option value="">Choose a report</option>
            {types.data.map((t) => <option key={t.type} value={t.type}>{t.title}</option>)}
          </Select>
          <Select label={selected?.needs_project ? "Project (required)" : "Project (optional)"} onChange={(event) => setForm({ ...form, projectId: event.target.value })} required={Boolean(selected?.needs_project)} value={form.projectId}>
            <option value="">{selected?.needs_project ? "Choose a project" : "All my projects"}</option>
            {projects.map((p) => <option key={getId(p)} value={getId(p)}>{projectName(p)}</option>)}
          </Select>
          <Input label="Days" max={366} min={0} onChange={(event) => setForm({ ...form, days: event.target.value })} placeholder={selected ? String(selected.default_days) : ""} type="number" value={form.days} />
          <Button disabled={pending === "generate" || !form.reportType} type="submit"><FileText className="h-4 w-4" /> {pending === "generate" ? "Building..." : "Generate"}</Button>
          {canSummarize ? (
            <label className="flex items-center gap-2 text-sm text-foreground md:col-span-4">
              <input checked={form.aiSummary} onChange={(event) => setForm({ ...form, aiSummary: event.target.checked })} type="checkbox" />
              Add an AI-written summary (labelled; the figures always come from records)
            </label>
          ) : null}
        </form>
      ) : null}

      {reports.loading && !reports.data?.length ? <LoadingState label="Loading reports..." /> : null}
      {reports.error ? <ErrorState message={getApiErrorMessage(reports.error)} onRetry={reports.reload} /> : null}
      {!reports.loading && !reports.error ? (
        <DataTable
          columns={[
            { key: "title", header: "Report", render: (row) => <button className="font-semibold text-foreground underline-offset-2 hover:underline" onClick={() => open(row._id)} type="button">{row.title}</button> },
            { key: "project", header: "Project", render: (row) => projectLabel(row.project_id) },
            { key: "created_at", header: "Generated", render: (row) => formatDateTime(row.created_at) },
            { key: "client_visible", header: "Client", render: (row) => (row.client_visible ? <StatusBadge status="Shared" /> : "Internal") },
          ]}
          emptyDescription={types.data?.length ? "Generate a report above." : "Reports shared with you will appear here."}
          emptyTitle="No reports yet"
          getRowId={(row) => row._id}
          rows={reports.data || []}
        />
      ) : null}

      <Modal
        footer={viewing ? (
          <>
            {canPublish && CLIENT_SHAREABLE.includes(viewing.type) && viewing.project_id && !viewing.client_visible ? (
              <Button disabled={pending === "publish"} onClick={() => run("publish", () => publishReport(viewing._id), { success: "Shared with the client (progress and milestones only).", onSuccess: () => { setViewing({ ...viewing, client_visible: true }); reports.reload(); } })} variant="secondary">
                <Share2 className="h-4 w-4" /> Share with client
              </Button>
            ) : null}
            {canExport ? (
              <>
                <Button onClick={() => run("csv", () => exportReport(viewing._id, "csv", viewing.type))} variant="secondary"><Download className="h-4 w-4" /> CSV</Button>
                <Button onClick={() => run("json", () => exportReport(viewing._id, "json", viewing.type))} variant="secondary"><Download className="h-4 w-4" /> JSON</Button>
              </>
            ) : null}
            <Button onClick={() => setViewing(null)}>Close</Button>
          </>
        ) : null}
        onClose={() => setViewing(null)}
        open={Boolean(viewing)}
        size="lg"
        title="Report"
      >
        {viewing ? <ReportView aiSummary={viewing.ai_summary} report={viewing.report} /> : null}
      </Modal>
    </div>
  );
}
