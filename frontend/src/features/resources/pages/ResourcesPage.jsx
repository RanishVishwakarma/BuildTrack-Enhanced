import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { SearchInput } from "../../../components/common/SearchInput.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { confirmAction, useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions, useWorkerOptions } from "../../../hooks/useLookups.js";
import { can } from "../../../lib/roles.js";
import { formatStatus, getId, matchesSearch } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { AssignResourceModal, MaintenanceModal, ResourceFormModal } from "../components/ResourceModals.jsx";
import { RESOURCE_STATUSES, RESOURCE_TYPES, deleteResource, getResources, unassignResource } from "../services/resourceService.js";

export function ResourcesPage() {
  const { user } = useAuth();
  const isManager = can.manage(user);
  const { data, loading, error, reload } = useAsyncData(getResources, [], { initialData: [] });
  const projectLookup = useProjectOptions();
  const workerLookup = useWorkerOptions({ enabled: isManager });
  const { run } = useAction();
  const [filters, setFilters] = useState({ query: "", type: "", status: "" });
  const [form, setForm] = useState({ open: false, resource: null });
  const [assigning, setAssigning] = useState(null);
  const [maintaining, setMaintaining] = useState(null);
  const resources = data;

  const filtered = useMemo(
    () =>
      resources.filter(
        (resource) =>
          matchesSearch([resource.resource_name, resource.description, resource.unit], filters.query) &&
          (!filters.type || resource.resource_type === filters.type) &&
          (!filters.status || resource.status === filters.status),
      ),
    [resources, filters],
  );

  async function remove(resource) {
    if (!confirmAction(`Delete ${resource.resource_name}? This cannot be undone.`)) return;
    await run("delete", () => deleteResource(getId(resource)), { success: "Resource deleted.", error: "Unable to delete resource.", onSuccess: reload });
  }

  async function release(resource) {
    await run(`release-${getId(resource)}`, () => unassignResource(getId(resource)), { success: `${resource.resource_name} returned to available.`, error: "Unable to release resource.", onSuccess: reload });
  }

  const count = (status) => resources.filter((resource) => resource.status === status).length;

  return (
    <>
      <PageHeader
        onRefresh={reload}
        title="Resources"
        description="Equipment, tools, vehicles and materials, with project assignment and maintenance."
        action={
          <div className="flex flex-wrap gap-2">
            {isManager ? <Button onClick={() => setForm({ open: true, resource: null })}><Plus className="h-4 w-4" /> Add resource</Button> : null}
          </div>
        }
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total resources" value={resources.length} />
        <StatCard label="Available" value={count("available")} />
        <StatCard label="In use" value={count("in_use")} />
        <StatCard label="Under maintenance" value={count("maintenance")} />
      </section>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="lg:col-span-2"><SearchInput aria-label="Search resources" placeholder="Search resources..." value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} /></div>
        <Select aria-label="Filter by type" className="h-10" value={filters.type} onChange={(event) => setFilters({ ...filters, type: event.target.value })}>
          <option value="">All types</option>
          {RESOURCE_TYPES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
        <Select aria-label="Filter by status" className="h-10" value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">All statuses</option>
          {RESOURCE_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
      </div>
      {loading ? <LoadingState label="Loading resources..." /> : null}
      {!loading && error ? <ErrorState message={getApiErrorMessage(error)} onRetry={reload} /> : null}
      {!loading && !error ? (
        <DataTable
          columns={[
            { key: "resource_name", header: "Resource", render: (row) => <span className="font-semibold">{row.resource_name}</span> },
            { key: "resource_type", header: "Type", render: (row) => formatStatus(row.resource_type) },
            { key: "quantity", header: "Qty", render: (row) => `${row.quantity} ${row.unit || ""}` },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "assigned_project", header: "Project", render: (row) => (row.assigned_project ? projectLookup.nameOf(row.assigned_project) : "Not assigned") },
            {
              key: "actions",
              header: "Actions",
              render: (row) => (
                <div className="flex flex-wrap gap-2">
                  {isManager && row.status === "available" ? <Button onClick={() => setAssigning(row)} size="sm">Assign</Button> : null}
                  {isManager && ["in_use", "maintenance"].includes(row.status) ? (
                    <Button onClick={() => release(row)} size="sm" variant="secondary">{row.status === "maintenance" ? "Mark available" : "Release"}</Button>
                  ) : null}
                  <Button onClick={() => setMaintaining(row)} size="sm" variant="secondary">Maintenance</Button>
                  {isManager ? <Button onClick={() => setForm({ open: true, resource: row })} size="sm" variant="secondary">Edit</Button> : null}
                  {can.adminOnly(user) ? <Button onClick={() => remove(row)} size="sm" variant="danger">Delete</Button> : null}
                </div>
              ),
            },
          ]}
          emptyDescription={resources.length ? "No resources match the current filters." : "Add equipment and tools to track their use."}
          emptyTitle={resources.length ? "No matching resources" : "No resources"}
          getRowId={getId}
          rows={filtered}
        />
      ) : null}
      <ResourceFormModal onClose={() => setForm({ open: false, resource: null })} onSaved={() => { setForm({ open: false, resource: null }); reload(); }} open={form.open} resource={form.resource} />
      <AssignResourceModal
        key={getId(assigning) || "none"}
        onClose={() => setAssigning(null)}
        onSaved={() => { setAssigning(null); reload(); }}
        projects={projectLookup.projects}
        resource={assigning}
        workers={workerLookup.workers}
      />
      <MaintenanceModal key={getId(maintaining) || "none-m"} onClose={() => setMaintaining(null)} onSaved={reload} resource={maintaining} />
    </>
  );
}
