import React, { useEffect, useRef, useState } from "react";
import { Layout } from "./components/Layout";
import { HealthScore } from "./components/HealthScore";
import { CategoryBreakdown } from "./components/CategoryBreakdown";
import { HotspotTable } from "./components/HotspotTable";
import { FindingsList } from "./components/FindingsList";
import { SiloAlerts } from "./components/SiloAlerts";
import { RiskPrediction } from "./components/RiskPrediction";
import { Roadmap } from "./components/Roadmap";
import { fetchArtifact, fetchSnapshotReport, fetchSnapshotView, legacySections } from "./api/client";
import type { DashboardView, SnapshotView, Summary } from "./types";
import { displayJson, objectValue } from "./api/displayJson";

type NavSection = "overview" | "evidence" | "artifacts" | "findings" | "hotspots" | "silos" | "risks" | "roadmap";

function ErrorCard({ message }: { message: string }): React.ReactElement {
  return <div role="alert" className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">{message}</div>;
}

function RawJson({ value }: { value: string }): React.ReactElement {
  return <details className="mt-3"><summary className="cursor-pointer text-sm text-blue-700">Original retained JSON</summary><pre className="mt-2 p-3 bg-gray-100 text-xs overflow-auto max-h-96 whitespace-pre-wrap break-all">{value}</pre></details>;
}

function Limitations({ values }: { values: string[] }): React.ReactElement {
  return <ul className="list-disc pl-5 text-sm text-amber-800 space-y-1">{values.map((value, index) => <li key={index}>{value}</li>)}</ul>;
}

function SummaryBanner({ summary }: { summary: Summary }): React.ReactElement {
  return <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 my-4">{[
    ["Repository", summary.repository], ["Total findings", summary.total_findings],
    ["Critical ranked files", summary.critical_files], ["Knowledge silos", summary.knowledge_silos],
  ].map(([label, value]) => <div key={label} className="bg-white rounded-lg shadow p-4"><p className="text-xs text-gray-500 uppercase">{label}</p><p className="text-sm font-semibold mt-2 break-all">{value}</p></div>)}</div>;
}

function StoredAssessment({ view }: { view: SnapshotView }): React.ReactElement {
  const selected = view.assessment;
  if (!selected) return <section className="bg-white p-5 rounded-lg shadow"><h2 className="text-lg font-semibold mb-2">Stored assessment</h2><p>No stored assessment selected.</p><p className="text-sm mt-2">Policy gate and scores are unavailable.</p></section>;
  const assessment = selected.display;
  return <section className="bg-white p-5 rounded-lg shadow space-y-4">
    <h2 className="text-lg font-semibold">Stored assessment</h2>
    <p>Stored policy gate: <strong role="status" aria-label="Stored policy gate" className="font-mono">{assessment.gate}</strong></p>
    <p className="text-sm break-all">Policy: {assessment.policy.id} / {assessment.policy.policy_version}; generated {assessment.generated_at}</p>
    <p className="text-sm">These are stored values. The dashboard does not recalculate a gate or score.</p>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <dl className="space-y-2">{Object.entries(assessment.scores).map(([key, value]) => <div key={key}><dt className="text-xs text-gray-500">{key}</dt><dd className="font-mono break-all">{value ?? "unavailable"}</dd></div>)}</dl>
      <dl className="space-y-2">{Object.entries(assessment.weights).map(([key, value]) => <div key={key}><dt className="text-xs text-gray-500">Stored {key} weight</dt><dd className="font-mono break-all">{value}</dd></div>)}</dl>
    </div>
    <div className="overflow-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Control</th><th className="p-2">Stored status</th><th className="p-2">Weight</th><th className="p-2">Reason / references</th></tr></thead><tbody>{assessment.controls.map(control => <tr key={control.id} className="border-t align-top"><td className="p-2">{control.title}<br/><code>{control.id}</code>{control.required && <p>Required</p>}</td><td className="p-2 font-mono">{control.status}{control.incomplete && <p>incomplete</p>}</td><td className="p-2 font-mono break-all">{control.weight}</td><td className="p-2"><p>{control.reason}</p><p className="text-xs break-all">{control.evidence_ids.join(", ")}</p><p className="text-xs break-all">{control.references.join(", ")}</p></td></tr>)}</tbody></table></div>
    <Limitations values={assessment.limitations}/>
    {assessment.deviations.length > 0 && <details><summary>Stored deviations</summary><pre className="text-xs overflow-auto whitespace-pre-wrap">{JSON.stringify(assessment.deviations, null, 2)}</pre></details>}
    <RawJson value={selected.raw_json}/>
  </section>;
}

function RunIdentity({ view }: { view: SnapshotView }): React.ReactElement {
  return <section className="bg-white rounded-lg shadow p-5 mb-5 space-y-2 text-sm">
    <h2 className="text-lg font-semibold">Pinned run</h2>
    <dl className="space-y-1"><div><dt className="inline font-semibold">Run: </dt><dd className="inline font-mono break-all">{view.run.id}</dd></div>
      <div><dt className="inline font-semibold">Manifest SHA-256: </dt><dd className="inline font-mono break-all">{view.run.manifest_sha256}</dd></div>
      <div><dt className="inline font-semibold">Collection status: </dt><dd className="inline font-mono">{view.run.status}</dd></div>
      <div><dt className="inline font-semibold">Stored source verification: </dt><dd className="inline font-mono">{view.run.input_verification}</dd></div>
      <div><dt className="inline font-semibold">Source digest: </dt><dd className="inline font-mono break-all">{view.run.source_digest}</dd></div>
      <div><dt className="inline font-semibold">Inventory complete: </dt><dd className="inline">{String(view.run.inventory_complete)}</dd></div>
    </dl>
    <p>Collection completion does not mean checks or policies passed. This historical view does not recheck current source freshness.</p>
  </section>;
}

function objectRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(objectValue) : [];
}

function FactDetails({ kind, document }: { kind: string; document: Record<string, unknown> }): React.ReactElement {
  if (kind === "consumer_comparison") return <section className="text-sm space-y-2"><h3 className="font-semibold">Consumer applicability cases</h3><p>Import: {String(document.import_origin)}; authentication: {String(document.authentication)}</p><p className="break-all">Upstream source: {String(document.upstream_source_digest)}</p><p className="break-all">Local source: {String(document.local_source_digest)}</p>{objectRows(document.cases).map((item, index) => <div key={index} className="border p-3 rounded"><h4 className="font-semibold">{String(item.case_id)}</h4><p>Configuration compatibility: <strong>{String(item.status)}</strong></p><p>{String(item.reason)}</p><p>Mismatching dimensions: {Array.isArray(item.mismatches) ? item.mismatches.join(", ") || "none recorded" : "not recorded"}</p><p>Local test status: <strong>{String(item.local_test_status)}</strong></p><p>Missing local checks: {Array.isArray(item.missing_local_checks) ? item.missing_local_checks.join(", ") || "none recorded" : "not recorded"}</p></div>)}<p>Configuration correspondence does not replace application tests or authenticate the upstream producer.</p></section>;
  if (kind === "coverage_facts") return <section className="text-sm space-y-2"><h3 className="font-semibold">Stored coverage counts</h3>{objectRows(document.files).map((file, index) => <div key={index} className="border p-3 rounded"><p className="font-semibold">{String(file.file)}</p>{objectRows(file.measurements).map((measurement, cell) => <p key={cell}>{String(measurement.kind)} · {String(measurement.method)}: <span className="font-mono">{String(measurement.covered)} / {String(measurement.total)}</span></p>)}</div>)}<p>Counts and measurement kinds remain separate; the dashboard calculates no percentage.</p></section>;
  if (kind === "sanitizer_facts") return <section className="text-sm space-y-2"><h3 className="font-semibold">Stored sanitizer result</h3><p>{String(document.sanitizer)} outcome: <strong>{String(document.outcome)}</strong></p><p>Requested files: {Array.isArray(document.requested_files) ? document.requested_files.join(", ") : "not recorded"}</p>{objectRows(document.diagnostics).map((diagnostic, index) => <p key={index}>{String(diagnostic.kind)}: {String(diagnostic.message)}{diagnostic.file ? ` (${String(diagnostic.file)}:${String(diagnostic.line ?? "unknown")})` : ""}</p>)}</section>;
  return <></>;
}

function StoredFacts({ view }: { view: SnapshotView }): React.ReactElement {
  return <div className="space-y-4"><h1 className="text-2xl font-bold">Stored evidence and facts</h1>
    <p className="text-sm">Recorded status, usability, origin and scope are shown verbatim. Imported claims remain unauthenticated.</p>
    {view.facts.length === 0 && <p>No typed facts were retained in this selected run.</p>}
    {view.facts.map(fact => { const document = objectValue(displayJson(fact.raw_json)); const receipt = objectValue(document.receipt); const label = String(receipt.id ?? document.file ?? document.subject_id ?? fact.id ?? fact.artifact_id); return <article key={fact.artifact_id} className="bg-white p-4 rounded-lg shadow space-y-2"><h2 className="font-semibold">{label.length > 40 ? `${label.slice(0, 28)}…` : label}</h2><p className="text-sm font-mono">{fact.kind}</p>
      <dl className="text-sm grid sm:grid-cols-2 gap-2"><div><dt>Status</dt><dd className="font-mono">{fact.status ?? "not recorded"}</dd></div><div><dt>Usability</dt><dd className="font-mono">{fact.usability ?? "not recorded"}</dd></div><div><dt>Origin</dt><dd>{fact.origin ?? "not recorded"}</dd></div><div><dt>Contexts</dt><dd>{fact.context_ids.join(", ") || "none recorded"}</dd></div></dl>
      {fact.producer && <p className="text-xs">{fact.producer.name} / {fact.producer.version}</p>}
      <FactDetails kind={fact.kind} document={document}/>
      <Limitations values={fact.limitations}/><RawJson value={fact.raw_json}/>
    </article>; })}
  </div>;
}

function shortId(value: unknown): string {
  const text = String(value);
  return text.length > 32 ? `${text.slice(0, 24)}…` : text;
}

function TypedObservations({ view, onDownload }: { view: SnapshotView; onDownload: (id: string) => void }): React.ReactElement {
  const inventories = new Map(view.facts.filter(fact => fact.kind === "analysis_inventory").map(fact => {
    const document = objectValue(displayJson(fact.raw_json));
    return [String(document.id), document] as const;
  }));
  const documents = view.facts.filter(fact => fact.kind === "observations" || fact.kind === "external_analysis_facts");
  return <section className="space-y-4"><h1 className="text-2xl font-bold">Stored observations by job</h1><p className="text-sm">Each retained observation remains in its recorded context. Rows are not deduplicated across jobs or reinterpreted as a policy gate. External producer namespaces remain separate.</p>
    {documents.length === 0 && <p>No typed observation document was retained in this selected run.</p>}
    {documents.map(fact => {
      const document = objectValue(displayJson(fact.raw_json));
      const external = fact.kind === "external_analysis_facts";
      const inventory = inventories.get(String(document.analysis_inventory_id));
      const job = inventory?.job_context_id ?? document.context_id;
      const selected = external ? document.observations : document.items;
      const items = Array.isArray(selected) ? selected.map(objectValue) : [];
      return <article key={fact.artifact_id} className="bg-white p-4 rounded-lg shadow"><h2 className="font-semibold">{external ? `External analysis · ${String(document.producer_namespace)}` : "Native analysis"} · {job ? shortId(job) : shortId(fact.artifact_id)}</h2>
        {items.length === 0 && <p>No observations recorded in this document; analysis completeness must be checked separately.</p>}
        {items.map((item, index) => <div key={index} className="border-t py-3 text-sm"><p className="font-semibold break-all">{String(item.file)}:{String(item.line)}{item.column ? `:${String(item.column)}` : ""}</p><p>{String(external ? item.namespaced_rule_id : item.rule_id)} · {String(item.severity)}</p><p>{String(item.message)}</p><p className="text-xs break-all">Job: {shortId(job ?? item.context_id)}; observation context: {shortId(item.context_id ?? document.context_id)}; observation: {shortId(item.id)}</p></div>)}
        <button className="text-sm text-blue-700 underline" onClick={() => onDownload(fact.artifact_id)}>Download original observations</button><RawJson value={fact.raw_json}/>
      </article>;
    })}
  </section>;
}

export default function App(): React.ReactElement {
  const [activeSection, setActiveSection] = useState<NavSection>("overview");
  const [view, setView] = useState<DashboardView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const request = useRef(0);

  function load(key = apiKey): void {
    const sequence = ++request.current;
    setView(null); setLoading(true); setError(null); setDownloadError(null);
    const params = new URLSearchParams(window.location.search);
    fetchSnapshotView({ runId: params.get("run_id") ?? undefined, manifestSha256: params.get("manifest_sha256") ?? undefined,
      assessmentArtifactId: params.get("assessment_artifact_id") ?? undefined, apiKey: key })
      .then(value => { if (sequence === request.current) { setView(value); setLoading(false); } })
      .catch((failure: unknown) => { if (sequence === request.current) { setError(failure instanceof Error ? failure.message : "View unavailable"); setLoading(false); } });
  }

  useEffect(() => { load(""); return () => { request.current++; }; }, []);

  const snapshot = view && "run" in view ? view : null;
  const legacy = view ? legacySections(view.legacy) : null;

  async function download(artifactId: string): Promise<void> {
    if (!snapshot) return;
    setDownloadError(null);
    try {
      const blob = await fetchArtifact(snapshot, artifactId, apiKey);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `cppulse-${snapshot.run.id}-${artifactId}.bin`;
      anchor.click(); URL.revokeObjectURL(url);
    } catch (failure: unknown) { setDownloadError(failure instanceof Error ? failure.message : "Download unavailable"); }
  }

  async function downloadReport(format: "pdf" | "html"): Promise<void> {
    if (!snapshot) return;
    setDownloadError(null);
    try {
      const blob = await fetchSnapshotReport(snapshot, format, apiKey);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `cppulse-${snapshot.run.id}.${format}`;
      anchor.click(); URL.revokeObjectURL(url);
    } catch (failure: unknown) { setDownloadError(failure instanceof Error ? failure.message : "Report unavailable"); }
  }

  function missing(name: string): React.ReactElement {
    return <p className="bg-white p-5 rounded-lg">No {name} document in this selected view.</p>;
  }

  function section(): React.ReactElement {
    if (!view || !legacy) return <></>;
    if (activeSection === "overview") return <div className="space-y-5"><h1 className="text-2xl font-bold">Overview</h1>
      {snapshot ? <><RunIdentity view={snapshot}/><StoredAssessment view={snapshot}/>
        <section className="bg-white p-5 rounded-lg shadow"><h2 className="font-semibold mb-2">Recorded stages</h2>{snapshot.stages.map(stage => <div key={stage.id} className="border-t py-2"><code>{stage.id}: {stage.status}</code><p className="text-sm">{stage.reason}</p></div>)}</section>
        <section className="bg-white p-5 rounded-lg shadow"><h2 className="font-semibold mb-2">Gaps in this selected view</h2>{snapshot.gaps.length ? <ul className="list-disc pl-5 text-sm">{snapshot.gaps.map((gap, index) => <li key={index}>{gap.message}</li>)}</ul> : <p className="text-sm">No additional view gaps were recorded. This is not a release assurance.</p>}</section>
        <details className="bg-white p-5 rounded-lg shadow"><summary>Source, contexts and original manifest</summary><pre className="text-xs whitespace-pre-wrap break-all mt-3">{JSON.stringify({ source: snapshot.source, contexts: snapshot.contexts }, null, 2)}</pre><RawJson value={snapshot.run_manifest_json}/></details>
      </> : <section className="bg-amber-50 p-5 rounded-lg"><h2 className="font-semibold">Legacy flat compatibility</h2><p>Unverified files; no stored policy gate or immutable run pin.</p></section>}
      <Limitations values={view.limitations}/>
      {legacy.risks && <section className="space-y-4"><h2 className="text-lg font-semibold">Experimental legacy ranking</h2>{legacy.summary && <SummaryBanner summary={legacy.summary}/>}<p className="text-sm">Profile: {legacy.summary?.model_metadata?.profile ?? "not recorded"}; model: {legacy.summary?.model_metadata?.model_type ?? "not recorded"} (experimental)</p><div className="grid lg:grid-cols-2 gap-6"><HealthScore healthScore={legacy.risks.health_score}/>{legacy.risks.health_score.overall !== null && <CategoryBreakdown healthScore={legacy.risks.health_score}/>}</div></section>}
    </div>;
    if (activeSection === "evidence") return snapshot ? <StoredFacts view={snapshot}/> : <p>Legacy flat compatibility has no inventoried typed evidence.</p>;
    if (activeSection === "artifacts") return snapshot ? <section><h1 className="text-2xl font-bold mb-4">Pinned raw artifacts</h1><p className="text-sm mb-4">Each download selects this exact run and manifest hash. Raw files can contain source, paths or logs.</p><div className="space-y-3">{snapshot.artifacts.map(artifact => <article key={artifact.id} className="bg-white p-4 rounded-lg shadow"><h2 className="font-semibold break-all">{artifact.path}</h2><p className="text-xs break-all" title={artifact.id}>{shortId(artifact.id)}</p><p className="text-xs break-all font-mono">{artifact.sha256}</p><p className="text-xs">{artifact.size_bytes} bytes; {artifact.media_type}</p><button className="mt-2 text-blue-700 underline text-sm" onClick={() => { void download(artifact.id); }}>Download {artifact.path}</button></article>)}</div></section> : <p>Legacy flat compatibility has no pinned artifact downloads.</p>;
    if (activeSection === "findings") return <div className="space-y-6">{snapshot && <TypedObservations view={snapshot} onDownload={id => { void download(id); }}/>} {legacy.findings && <section><h2 className="text-lg font-semibold mb-3">Legacy static findings</h2><FindingsList findings={legacy.findings}/></section>}{!snapshot && !legacy.findings && missing("findings")}</div>;
    if (activeSection === "hotspots") return legacy.hotspots ? <HotspotTable hotspots={legacy.hotspots}/> : missing("risk scores");
    if (activeSection === "silos") return legacy.silos ? <SiloAlerts silos={legacy.silos}/> : missing("git metrics");
    if (activeSection === "risks") return legacy.risks ? <RiskPrediction fileRisks={legacy.risks.file_risks}/> : missing("risk scores");
    return legacy.roadmap ? <Roadmap items={legacy.roadmap}/> : missing("roadmap");
  }

  return <Layout activeSection={activeSection} onNavigate={setActiveSection}>
    <div className="flex flex-wrap items-end gap-3 mb-5"><button className="px-4 py-2 bg-blue-700 text-white rounded" onClick={() => load()}>Refresh snapshot</button><form className="flex flex-wrap gap-2 items-end" onSubmit={event => { event.preventDefault(); load(); }}><label className="text-xs">API key (optional)<input type="password" autoComplete="off" className="block border rounded p-2 text-sm" value={apiKey} onChange={event => setApiKey(event.target.value)}/></label><button className="px-3 py-2 border rounded text-sm" type="submit">Load with key</button></form></div>
    <p className="text-sm text-amber-800 mb-4">Experimental ranking and scoped stored evidence; scores do not establish production readiness or safety.</p>
    {snapshot && <div className="flex gap-4 mb-4"><button className="text-blue-700 underline" onClick={() => { void downloadReport("pdf"); }}>Download snapshot PDF</button><button className="text-blue-700 underline" onClick={() => { void downloadReport("html"); }}>Download snapshot HTML</button></div>}
    {downloadError && <ErrorCard message={downloadError}/>}
    {loading && <p role="status">Loading selected view…</p>}{error && <ErrorCard message={error}/>} {view && section()}
  </Layout>;
}
