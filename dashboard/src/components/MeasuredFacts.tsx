import { useState } from "react";

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(object) : [];
}
function text(value: unknown): string {
  return value === null || value === undefined ? "unavailable" : String(value);
}

/** Display retained calculations verbatim; this component never computes a score. */
export default function MeasuredFacts({kind, document}: {kind: string; document: Record<string, unknown>}): React.ReactElement {
  const [filter, setFilter] = useState("");
  if (kind === "maintenance_health") {
    const aggregate = object(document.aggregate);
    const scorer = object(document.scorer);
    return <section className="space-y-2 text-sm"><h3 className="font-semibold">Measured maintenance health</h3>
      <p>Method: {text(scorer.id ?? scorer.method)}; profile: {text(scorer.profile)}</p>
      {scorer.id === "analyzed-kloc-context-v3" && <p>Historical v3 result: parsed source and header byte verification was not required.</p>}
      {scorer.id === "analyzed-kloc-context-v4" && <p>v4 requires checked source/header buffer identities. Inferred parse opt-in does not waive them.</p>}
      <p>Full-scope health: {text(aggregate.overall)}</p><p>Status: {text(aggregate.availability ?? aggregate.status)}</p>
      {Array.isArray(aggregate.incomplete_required_context_ids) && aggregate.incomplete_required_context_ids.length > 0 && <p>Missing required contexts: {aggregate.incomplete_required_context_ids.map(text).join(", ")}</p>}
      {Array.isArray(aggregate.limitations) && aggregate.limitations.map((value,index) => <p key={index}>{text(value)}</p>)}
      <p>Selected worst required context: {text(aggregate.selected_context_id ?? aggregate.worst_context_id)}</p>
      {rows(document.contexts).map((context, index) => <div key={index} className="border p-2"><p>Context: {text(context.job_context_id)}; stored health: {text(context.overall)}; {text(context.availability ?? context.status)}</p>
        <p>Physical LOC: {text(context.physical_loc)}; code LOC: {text(context.code_loc)}; declared files: {text(context.declared_files)}; analyzed files: {text(context.analyzed_files)}</p>
        {rows(context.category_calculations).map((category,index) => <p key={index}>{text(category.category)}: stored score {text(category.score)}; findings {text(category.count)}; density {text(category.density)}; cap {text(rows(scorer.categories).find(row => row.category === category.category)?.density_cap)}; weight {text(rows(scorer.categories).find(row => row.category === category.category)?.weight)}</p>)}
        {Array.isArray(context.limitations) && context.limitations.map((value,index) => <p key={index}>{text(value)}</p>)}
      </div>)}
      {Array.isArray(document.limitations) && <ul className="list-disc pl-5">{document.limitations.map((value, index) => <li key={index}>{text(value)}</li>)}</ul>}
      <p>Stored calculations describe their selected scope. A health score is separate from a policy gate or calibrated defect probability.</p>
    </section>;
  }
  if (kind !== "analysis_metrics") return <></>;
  const selected = rows(document.items).filter(row => `${text(row.file)} ${text(row.symbol)}`.toLowerCase().includes(filter.toLowerCase()));
  return <section className="space-y-2 text-sm"><h3 className="font-semibold">Measured file and function metrics</h3>
    <p>Job context: {text(document.job_context_id)}</p>
    <label className="block">Filter measured file or symbol <input className="border p-1" value={filter} onChange={event => setFilter(event.target.value)}/></label>
    <p>{selected.length} matching retained measurements; showing at most 200.</p>
    <div className="overflow-auto"><table className="w-full text-left"><thead><tr><th>File / symbol</th><th>Metric</th><th>Stored value</th><th>Availability</th></tr></thead><tbody>{selected.slice(0,200).map((row,index) => <tr key={String(row.id ?? index)} className="border-t align-top"><td className="p-2 break-all">{text(row.file)}{row.symbol !== undefined && row.symbol !== null && <p>{text(row.symbol)}</p>}</td><td className="p-2">{text(row.metric)}<p className="text-xs">{row.metric_version === undefined ? "" : text(row.metric_version)}</p></td><td className="p-2">{row.value === null || row.value === undefined ? "unavailable" : `${text(row.value)} ${text(row.units)}`}</td><td className="p-2">{text(row.availability)}{Array.isArray(row.limitations) && row.limitations.map((value,index) => <p key={index}>{text(value)}</p>)}</td></tr>)}</tbody></table></div>
  </section>;
}
