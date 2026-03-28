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
  overall: number;
  memory_safety: number;
  modernization: number;
  complexity: number;
  misra_compliance: number;
}

export interface FileRisk {
  file: string;
  bug_probability: number;
  risk_level: "critical" | "high" | "medium" | "low";
  top_factors: string[];
}

export interface Hotspot {
  file: string;
  hotspot_score: number;
  change_frequency: number;
  complexity_score: number;
  finding_count: number;
}

export interface RiskScores {
  health_score: HealthScore;
  file_risks: FileRisk[];
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
  repository: string;
  analysis_date: string;
  health_score: HealthScore;
  total_findings: number;
  critical_files: number;
  knowledge_silos: number;
}
