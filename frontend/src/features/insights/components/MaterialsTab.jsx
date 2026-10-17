import { useState } from "react";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { formatDate } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { getMaterialForecast } from "../services/insightsService.js";

const num = (value) => (value === null || value === undefined ? "-" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 }));

export function MaterialsTab({ projectId }) {
  const [horizon, setHorizon] = useState(30);
  const forecast = useAsyncData(() => getMaterialForecast(projectId, horizon), [projectId, horizon]);
  usePageRefresh(forecast.reload);
  if (forecast.loading && !forecast.data) return <LoadingState label="Forecasting materials..." />;
  if (forecast.error) return <ErrorState message={getApiErrorMessage(forecast.error)} onRetry={forecast.reload} />;
  const data = forecast.data || { items: [] };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Select label="Requirement window" onChange={(event) => setHorizon(Number(event.target.value))} value={horizon}>
            {[14, 30, 60, 90].map((d) => <option key={d} value={d}>Next {d} days</option>)}
          </Select>
        </div>
        <p className="text-xs text-muted">Shortfall = required (approved requests) - available (physical - reserved) - confirmed incoming. Units are not converted.</p>
      </div>
      {data.shortages?.length ? (
        <section className="rounded-lg border border-danger/30 bg-danger/5 p-4">
          <h3 className="text-sm font-semibold text-danger">Projected shortages</h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-foreground">
            {data.shortages.map((r) => <li key={r.item_id}>{r.material}: short {num(r.projected_shortfall)} {r.unit} ({r.shortfall_formula}){r.next_required_date ? `, needed ${formatDate(r.next_required_date)}` : ""}</li>)}
          </ul>
        </section>
      ) : null}
      <DataTable
        columns={[
          { key: "material", header: "Material", render: (r) => <span className="font-semibold">{r.material}</span> },
          { key: "unit", header: "Unit" },
          { key: "physical_stock", header: "Physical", render: (r) => num(r.physical_stock) },
          { key: "reserved", header: "Reserved", render: (r) => num(r.reserved) },
          { key: "available", header: "Available", render: (r) => num(r.available) },
          { key: "incoming_confirmed", header: "Incoming (confirmed)", render: (r) => `${num(r.incoming_confirmed)}${r.incoming_unconfirmed ? ` (+${num(r.incoming_unconfirmed)} unconfirmed)` : ""}` },
          { key: "required_approved", header: "Required", render: (r) => `${num(r.required_approved)}${r.required_pending_approval ? ` (+${num(r.required_pending_approval)} pending)` : ""}` },
          { key: "projected_shortfall", header: "Shortfall", render: (r) => (r.projected_shortfall > 0 ? <span className="font-semibold text-danger">{num(r.projected_shortfall)}</span> : "0") },
          { key: "days_of_cover", header: "Days of cover", render: (r) => (r.days_of_cover === null ? "No usage data" : num(r.days_of_cover)) },
          { key: "warnings", header: "Notes", render: (r) => [...r.warnings, ...r.wastage_anomalies.map((a) => `Unusual issue ${num(a.quantity)}: ${a.flags.join("; ")}`)].join(" · ") || "" },
        ]}
        emptyDescription={projectId ? "This project has no material requests in the window." : "No inventory items recorded."}
        emptyTitle="No materials"
        getRowId={(r) => r.item_id}
        rows={data.items || []}
      />
      {data.transfer_candidates?.length ? (
        <section className="card">
          <h3 className="text-sm font-semibold">Possible transfers between locations</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">{data.transfer_candidates.map((t, i) => <li key={i}>{t.material}: {num(t.suggested_quantity)} {t.unit} from {t.from_location || "unspecified"} to {t.to_location || "unspecified"}. {t.note}</li>)}</ul>
        </section>
      ) : null}
      {data.limitations?.length ? <ul className="list-disc pl-5 text-xs text-muted">{data.limitations.map((l) => <li key={l}>{l}</li>)}</ul> : null}
    </div>
  );
}
