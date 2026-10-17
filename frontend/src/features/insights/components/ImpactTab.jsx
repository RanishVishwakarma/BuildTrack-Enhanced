import { useState } from "react";
import { Button } from "../../../components/ui/Button.jsx";
import { Input } from "../../../components/ui/Input.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { useAction } from "../../../hooks/useAction.js";
import { useAsyncData } from "../../../hooks/useAsyncData.js";
import { hasPermission } from "../../../lib/roles.js";
import { getId } from "../../../lib/utils.js";
import { useAuth } from "../../auth/context/AuthContext.jsx";
import { getPurchaseOrders } from "../../procurement/services/procurementService.js";
import { getTasksForProject } from "../../tasks/services/taskService.js";
import { analyzeImpact } from "../services/insightsService.js";

function Section({ title, items, tone = "" }) {
  if (!items?.length) return null;
  return (
    <section className={`card ${tone}`}>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{items.map((item, i) => <li key={i}>{typeof item === "string" ? item : <><span className="font-semibold">{item.label}</span>: {item.effect}</>}</li>)}</ul>
    </section>
  );
}

// "What happens if X is delayed by N days?" Analysis only; nothing changes.
export function ImpactTab({ projectId }) {
  const { user } = useAuth();
  const canPo = hasPermission(user, "procurement.read.assigned");
  const [form, setForm] = useState({ kind: canPo ? "purchase_order" : "task", recordId: "", days: 3 });
  const options = useAsyncData(async () => {
    if (form.kind === "purchase_order") return (await getPurchaseOrders({ limit: 200 })).items.map((o) => ({ id: getId(o), label: `${o.po_number} · ${o.materials} · ${o.project}` }));
    if (!projectId) return [];
    const tasks = await getTasksForProject(projectId);
    return (Array.isArray(tasks) ? tasks : []).map((t) => ({ id: getId(t), label: t.title }));
  }, [form.kind, projectId], { initialData: [] });
  const [result, setResult] = useState(null);
  const { run, pending } = useAction();

  async function submit(event) {
    event.preventDefault();
    const data = await run("impact", () => analyzeImpact(form.kind, form.recordId, form.days));
    if (data) setResult(data);
  }

  return (
    <div className="space-y-4">
      <form className="card grid gap-3 md:grid-cols-[1fr_2fr_0.6fr_auto] md:items-end" onSubmit={submit}>
        <Select label="Delayed item" onChange={(event) => setForm({ ...form, kind: event.target.value, recordId: "" })} value={form.kind}>
          {canPo ? <option value="purchase_order">Purchase order / delivery</option> : null}
          <option value="task">Task</option>
        </Select>
        <Select label={form.kind === "task" && !projectId ? "Choose a project above first" : "Which one"} onChange={(event) => setForm({ ...form, recordId: event.target.value })} required value={form.recordId}>
          <option value="">Select</option>
          {(options.data || []).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </Select>
        <Input label="Delay (days)" max={365} min={1} onChange={(event) => setForm({ ...form, days: event.target.value })} required type="number" value={form.days} />
        <Button disabled={pending === "impact" || !form.recordId} type="submit">{pending === "impact" ? "Analysing..." : "Analyse"}</Button>
      </form>
      {result ? (
        <div className="space-y-3">
          <p className="text-sm text-muted">{result.subject.label}: {result.delay_days} day delay. {result.note}</p>
          <Section items={result.calculated_impacts} title="Calculated impacts" />
          {!result.calculated_impacts.length ? <p className="card text-sm">No calculated impacts from the recorded links.</p> : null}
          <Section items={result.possible_impacts} title="Possible impacts (need confirmation)" />
          <Section items={result.data_gaps} title="Data gaps" />
          <Section items={result.assumptions} title="Assumptions" />
        </div>
      ) : null}
    </div>
  );
}
