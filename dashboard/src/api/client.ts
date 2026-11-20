import type { Summary, FindingsResponse, Hotspot, RiskScores, KnowledgeSilo, RoadmapItem, HealthScore, FileRisk, Finding, UnrankedFile, RankingScope, GitHistoryStatus } from "../types";
import type { DashboardView, LegacySlots, SnapshotView } from "../types";
const BASE_URL = "/api/v1";
async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) throw new Error(`API error ${response.status}: ${response.statusText}`);
  return response.json() as Promise<T>;
}
interface Envelope<T> { items: T[]; total: number }
interface WireHealth { overall: number | null; status?: HealthScore["status"]; by_category: Record<string, number | null> }
interface WireSummary {
  health_score: WireHealth;
  findings_summary: { total_findings: number };
  metadata: { repo_path: string; analyzed_at: string };
  model_metadata?: Summary["model_metadata"];
}
function healthView(health: WireHealth, limitations: string[] = []): HealthScore {
  return {
    overall: health.overall,
    status: health.status,
    limitations: [...new Set(limitations)],
    memory_safety: health.by_category.memory_safety,
    modernization: health.by_category.modernization,
    complexity: health.by_category.complexity,
    misra_compliance: health.by_category.misra_compliance,
  };
}
export async function fetchSummary(): Promise<Summary> {
  const [data, risks, silos] = await Promise.all([
    apiFetch<WireSummary>("/summary"), apiFetch<Envelope<FileRisk>>("/risks"), apiFetch<Envelope<KnowledgeSilo> & {history_status?: GitHistoryStatus}>("/silos")]);
  return { model_metadata: data.model_metadata, repository: data.metadata.repo_path, analysis_date: data.metadata.analyzed_at,
    health_score: healthView(data.health_score, data.model_metadata?.limitations), total_findings: data.findings_summary.total_findings,
    critical_files: risks.items.filter(r => r.risk_level === "critical").length,
    knowledge_silos: silos.total, knowledge_silos_status: silos.history_status ?? "unverified" };
}
export async function fetchFindings(page?: number, category?: string): Promise<FindingsResponse> {
  const params = new URLSearchParams();
  params.set("per_page", "200");
  if (page !== undefined) params.set("page", String(page));
  if (category) params.set("category", category);
  const data = await apiFetch<Envelope<FindingsResponse["findings"][number]> & { page: number; per_page: number; total_pages?: number }>(`/findings?${params}`);
  const items = [...data.items];
  if (page === undefined) {
    for (let next = 2; next <= (data.total_pages ?? 1); next++) {
      params.set("page", String(next));
      items.push(...(await apiFetch<Envelope<FindingsResponse["findings"][number]>>(`/findings?${params}`)).items);
    }
  }
  return { findings: items, total: data.total, page: data.page, page_size: data.per_page };
}
export async function fetchHotspots(): Promise<Hotspot[]> { return (await apiFetch<Envelope<Hotspot>>("/hotspots")).items; }
export async function fetchRisks(): Promise<RiskScores> {
  const [summary, risks, hotspots] = await Promise.all([apiFetch<WireSummary>("/summary"),
    apiFetch<Envelope<Omit<FileRisk, "top_factors"> & { top_factors: {feature: string; importance: number; value: number}[] }> & {unranked_files?: UnrankedFile[]; ranking_scope?: RankingScope | null}>("/risks"), fetchHotspots()]);
  return { hotspot_method: summary.model_metadata?.hotspot_method, health_score: healthView(summary.health_score, summary.model_metadata?.limitations), hotspots,
    unranked_files: risks.unranked_files ?? [], ranking_scope: risks.ranking_scope,
    file_risks: risks.items.map(r => ({...r, top_factors: r.top_factors.map(f => f.feature)})) };
}
export async function fetchSilos(): Promise<KnowledgeSilo[]> {
  const data = await apiFetch<Envelope<KnowledgeSilo & { last_commit_date: string }>>("/silos");
  return data.items.map(s => ({...s, last_commit: s.last_commit_date}));
}
export async function fetchRoadmap(): Promise<RoadmapItem[]> { return (await apiFetch<Envelope<RoadmapItem>>("/roadmap")).items; }

export interface ViewSelection {
  runId?: string;
  manifestSha256?: string;
  assessmentArtifactId?: string;
  apiKey?: string;
}

function authorization(apiKey?: string): HeadersInit {
  return apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
}

export async function fetchSnapshotView(selection: ViewSelection = {}): Promise<DashboardView> {
  if ((selection.runId === undefined) !== (selection.manifestSha256 === undefined)) {
    throw new Error("Select both run_id and manifest_sha256.");
  }
  const params = new URLSearchParams();
  if (selection.runId !== undefined) params.set("run_id", selection.runId);
  if (selection.manifestSha256 !== undefined) params.set("manifest_sha256", selection.manifestSha256);
  if (selection.assessmentArtifactId !== undefined) params.set("assessment_artifact_id", selection.assessmentArtifactId);
  const suffix = params.size ? `?${params}` : "";
  const response = await fetch(`${BASE_URL}/view${suffix}`, { headers: authorization(selection.apiKey), cache: "no-store" });
  if (!response.ok) throw new Error(`API error ${response.status}: ${response.statusText}`);
  const value = await response.json() as DashboardView;
  if (!("run" in value) && !("mode" in value && value.mode === "legacy-flat")) {
    throw new Error("The API did not return a snapshot view or explicit legacy flat mode.");
  }
  return value;
}

export function artifactUrl(view: SnapshotView, artifactId: string): string {
  return `${BASE_URL}/runs/${encodeURIComponent(view.run.id)}/artifacts/${encodeURIComponent(artifactId)}?manifest_sha256=${encodeURIComponent(view.run.manifest_sha256)}`;
}

export async function fetchArtifact(view: SnapshotView, artifactId: string, apiKey?: string): Promise<Blob> {
  const response = await fetch(artifactUrl(view, artifactId), { headers: authorization(apiKey), cache: "no-store" });
  if (!response.ok) throw new Error(`Artifact download failed: ${response.status} ${response.statusText}`);
  return response.blob();
}

export async function fetchSnapshotReport(view: SnapshotView, format: "pdf" | "html", apiKey?: string): Promise<Blob> {
  const params = new URLSearchParams({run_id:view.run.id, manifest_sha256:view.run.manifest_sha256});
  if (view.assessment) params.set("assessment_artifact_id", view.assessment.artifact_id);
  const response = await fetch(`${BASE_URL}/report.${format}?${params}`, {headers:authorization(apiKey), cache:"no-store"});
  if (!response.ok) throw new Error(`Snapshot ${format.toUpperCase()} unavailable: ${response.status} ${response.statusText}`);
  return response.blob();
}

export function legacySections(slots: LegacySlots): {
  summary: Summary | null; findings: Finding[] | null; risks: RiskScores | null;
  hotspots: Hotspot[] | null; silos: KnowledgeSilo[] | null; roadmap: RoadmapItem[] | null;
  historyStatus: GitHistoryStatus; historyLimitations: string[];
} {
  const findings = slots.findings?.document ?? null;
  const risk = slots.risk_scores?.document ?? null;
  const git = slots.git_metrics?.document ?? null;
  const historyStatus = git?.metadata?.history_status ?? "unverified";
  const historyLimitations = git?.metadata?.limitations ?? [];
  const silos = git?.knowledge_silos.map(item => ({ ...item, last_commit: item.last_commit_date })) ?? null;
  const risks = risk ? {
    hotspot_method: risk.metadata?.hotspot_method,
    health_score: healthView(risk.health_score, risk.metadata?.limitations),
    hotspots: risk.hotspots,
    unranked_files: risk.unranked_files ?? [], ranking_scope: risk.metadata?.ranking_scope,
    file_risks: risk.file_risks.map(item => ({ ...item, top_factors: item.top_factors.map(factor => factor.feature) })),
  } : null;
  const summary = findings && risk && git ? {
    model_metadata: risk.metadata, repository: findings.metadata.repo_path,
    analysis_date: findings.metadata.analyzed_at,
    health_score: healthView(risk.health_score, risk.metadata?.limitations),
    total_findings: findings.summary.total_findings,
    critical_files: risk.file_risks.filter(item => item.risk_level === "critical").length,
    knowledge_silos: git.knowledge_silos.length,
    knowledge_silos_status: historyStatus,
  } : null;
  return { summary, findings: findings?.findings ?? null, risks, historyStatus, historyLimitations,
    hotspots: risk?.hotspots ?? null, silos, roadmap: slots.roadmap?.document.items ?? null };
}
