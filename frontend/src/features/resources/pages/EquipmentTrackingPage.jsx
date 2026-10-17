import { useState } from "react";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { PageHeader } from "../../../components/common/PageHeader.jsx";
import { StatusBadge } from "../../../components/common/StatusBadge.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { StatCard } from "../../../components/data-display/StatCard.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { useProjectOptions, useWorkerOptions } from "../../../hooks/useLookups.js";
import { formatCurrency, formatDate, formatStatus, getId } from "../../../lib/utils.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { MaintenanceModal } from "../components/ResourceModals.jsx";
import { RESOURCE_STATUSES, getResources } from "../services/resourceService.js";

// Angular EquipmentTrackingComponent: equipment and vehicles, where they are
// deployed and their maintenance state.
const TRACKED_TYPES = ["equipment", "vehicle"];

export function EquipmentTrackingPage() {
  const { data, loading, error, reload } = useAsyncData(getResources, [], { initialData: [] });
  const projects = useProjectOptions();
  const workers = useWorkerOptions();
  const [status, setStatus] = useState("");
  const [maintaining, setMaintaining] = useState(null);

  if (loading) return <LoadingState label="Loading equipment..." />;
  if (error) return <ErrorState message={getApiErrorMessage(error)} onRetry={reload} />;

  const equipment = (data || []).filter((resource) => TRACKED_TYPES.includes(String(resource.resource_type).toLowerCase()));
  const rows = equipment.filter((resource) => !status || resource.status === status);
  const count = (value) => equipment.filter((resource) => resource.status === value).length;

  return (
    <>
      <PageHeader
        title="Equipment Tracking"
        description="Where each machine and vehicle is deployed and its maintenance state."
        onRefresh={reload}
      />
      <section className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Equipment & vehicles" value={equipment.length} />
        <StatCard label="Deployed" value={count("in_use")} />
        <StatCard label="Available" value={count("available")} />
        <StatCard label="Under maintenance" value={count("maintenance")} />
      </section>
      <div className="mb-4 max-w-xs">
        <Select aria-label="Filter by status" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">All statuses</option>
          {RESOURCE_STATUSES.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
        </Select>
      </div>
      <DataTable
        columns={[
          { key: "resource_name", header: "Equipment", render: (row) => <span className="font-semibold">{row.resource_name}</span> },
          { key: "resource_type", header: "Type", render: (row) => formatStatus(row.resource_type) },
          { key: "assigned_project", header: "Deployed at", render: (row) => (row.assigned_project ? projects.nameOf(row.assigned_project) : "Yard") },
          { key: "assigned_to", header: "Operator", render: (row) => (row.assigned_to ? workers.nameOf(row.assigned_to) : "Not set") },
          { key: "maintenance_schedule", header: "Maintenance plan" },
          { key: "acquisition", header: "Acquired", render: (row) => `${formatDate(row.acquisition_date)} · ${formatCurrency(row.acquisition_cost)}` },
          { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
          { key: "actions", header: "Actions", render: (row) => <Button onClick={() => setMaintaining(row)} size="sm" variant="secondary">Maintenance</Button> },
        ]}
        emptyDescription="Add resources of type equipment or vehicle on the Resources page."
        emptyTitle="No equipment"
        getRowId={getId}
        rows={rows}
      />
      <MaintenanceModal key={getId(maintaining) || "none"} onClose={() => setMaintaining(null)} onSaved={reload} resource={maintaining} />
    </>
  );
}
