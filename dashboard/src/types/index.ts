// Finding types from analyzer-core output

export interface Finding {
  id: string;
  rule_id: string;
  file: string;
  line: number;
  column: number;
  severity: "error" | "warning" | "info";
  category: string;
  message: string;
  suggestion: string;
}

export interface FindingsResponse {
  total: number;
  page: number;
  page_size: number;
  findings: Finding[];
}

// Git metrics types from git-miner output

export interface FileMetric {
  file: string;
  change_frequency: number;
  unique_authors: number;
  last_modified: string;
  complexity_score: number;
  bug_fix_ratio: number;
  churn_rate: number;
  age_days: number;
  coupling_factor: number;
  review_coverage: number;
}

export interface KnowledgeSilo {
  file: string;
  sole_contributor: string;
  commit_count: number;
  last_commit: string;
  risk_note: string;
}

export interface GitMetrics {
  repository: string;
  analysis_date: string;
  file_metrics: FileMetric[];
  knowledge_silos: KnowledgeSilo[];
}

// Risk scores and health from predictor output

export interface HealthScore {
  overall: number | null;
  status?: "scored" | "partial" | "no_data";
  limitations?: string[];
  memory_safety?: number | null;
  modernization?: number | null;
  complexity?: number | null;
  misra_compliance?: number | null;
}

export interface FileRisk {
  file: string;
  bug_probability: number;
  risk_level: "critical" | "high" | "medium" | "low";
  top_factors: string[];
}

export interface UnrankedFile {
  file: string;
  availability: "partial" | "unverified" | "unavailable";
  reason_codes: string[];
  reasons: string[];
}

export interface RankingScope {
  version: "file-eligibility-1";
  declared_files: number;
  ranked_files: number;
  unranked_files: number;
}

export type GitHistoryStatus = "available" | "partial" | "unavailable" | "unverified";

export interface Hotspot {
  file: string;
  hotspot_score: number;
  change_frequency: number;
  complexity_score: number;
  finding_count: number;
}

export interface RiskScores {
  hotspot_method?: string;
  health_score: HealthScore;
  file_risks: FileRisk[];
  unranked_files?: UnrankedFile[];
  ranking_scope?: RankingScope | null;
  hotspots: Hotspot[];
}

// Roadmap types

export interface RoadmapItem {
  priority: number;
  file: string;
  action: string;
  category: string;
  estimated_hours: number;
  impact_score: number;
}

// Summary type returned by report-engine API

export interface Summary {
  model_metadata?: {hotspot_method?: string; hotspot_scope?: {status?: string}; model_type: string; profile: string; experimental: boolean; limitations?: string[]; ranking_scope?: RankingScope};
  repository: string;
  analysis_date: string;
  health_score: HealthScore;
  total_findings: number;
  critical_files: number;
  knowledge_silos: number;
  knowledge_silos_status?: GitHistoryStatus;
}

export interface ArtifactDescriptor {
  id: string;
  path: string;
  sha256: string;
  size_bytes: number;
  media_type: string;
  contract?: { kind: string; version: string };
}

export interface StoredDocument<T> {
  artifact_id: string;
  sha256: string;
  size_bytes: number;
  raw_json: string;
  document: T;
}

export interface LegacyFindings {
  metadata: { repo_path: string; analyzed_at: string };
  summary: { total_findings: number };
  findings: Finding[];
}

export interface LegacyRisks {
  health_score: {
    overall: number | null;
    status?: HealthScore["status"];
    by_category: Record<string, number | null>;
  };
  metadata?: Summary["model_metadata"];
  file_risks: (Omit<FileRisk, "top_factors"> & {
    top_factors: { feature: string; importance: number; value: number }[];
  })[];
  unranked_files?: UnrankedFile[];
  hotspots: Hotspot[];
}

export interface LegacySlots {
  findings: Pick<StoredDocument<LegacyFindings>, "document"> | null;
  git_metrics: Pick<StoredDocument<{
    metadata?: { history_status?: GitHistoryStatus; limitations?: string[] };
    knowledge_silos: (KnowledgeSilo & { last_commit_date: string })[];
  }>, "document"> | null;
  risk_scores: Pick<StoredDocument<LegacyRisks>, "document"> | null;
  roadmap: Pick<StoredDocument<{ items: RoadmapItem[] }>, "document"> | null;
}

export interface AssessmentDisplay {
  gate: string;
  policy: { id: string; policy_version: string; sha256: string };
  generated_at: string;
  weights: Record<string, string>;
  scores: Record<string, string | null>;
  controls: {
    id: string; title: string; status: string; reason: string; weight: string;
    required: boolean; evidence_ids: string[]; references: string[];
    context_ids?: string[]; fact_ids?: string[]; incomplete?: boolean;
  }[];
  deviations: Record<string, unknown>[];
  limitations: string[];
}

export interface SnapshotView {
  version: "2.0.0";
  run_manifest_json: string;
  run: {
    id: string; manifest_sha256: string; status: string;
    input_verification: string; source_digest: string; inventory_complete: boolean;
    started_at: string; finished_at: string; config_digest: string; limitations: string[];
  };
  source: { files: { path: string }[]; [key: string]: unknown };
  stages: { id: string; status: string; reason?: string; [key: string]: unknown }[];
  contexts: { id: string; [key: string]: unknown }[];
  assessment: { artifact_id: string; sha256: string; size_bytes: number; raw_json: string; display: AssessmentDisplay } | null;
  facts: {
    kind: string; artifact_id: string; sha256: string; size_bytes: number;
    raw_json: string; id: string | null; context_ids: string[];
    origin: string | null; producer: { name: string; version: string } | null;
    status: string | null; usability: string | null; limitations: string[];
  }[];
  artifacts: ArtifactDescriptor[];
  legacy: LegacySlots;
  gaps: { kind: string; id: string | null; message: string; artifact_ids: string[] }[];
  limitations: string[];
}

export interface LegacyFlatView {
  mode: "legacy-flat";
  input_verification: "unverified";
  legacy: LegacySlots;
  limitations: string[];
}

export type DashboardView = SnapshotView | LegacyFlatView;
