"""Feature engineering module for cppulse predictor.

Merges findings.json and git_metrics.json into a feature DataFrame
suitable for ML training and prediction.
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from dataclasses import dataclass
from typing import Any

import pandas as pd

SEVERITY_MAP: dict[str, int] = {"error": 3, "warning": 2, "info": 1}

FEATURE_COLUMNS: list[str] = [
    "file",
    "finding_count",
    "memory_findings",
    "modernization_findings",
    "complexity_findings",
    "misra_findings",
    "max_severity",
    "change_frequency",
    "unique_contributors",
    "churn_rate",
    "bug_fix_commits",
    "szz_bug_introductions",
    "age_days",
    "is_knowledge_silo",
]


@dataclass
class FindingsSummary:
    """Aggregated findings for a single file.

    Attributes:
        file: Relative path of the file.
        finding_count: Total number of findings.
        memory_findings: Count of memory_safety category findings.
        modernization_findings: Count of modernization category findings.
        complexity_findings: Count of complexity category findings.
        misra_findings: Count of misra category findings.
        max_severity: Highest severity numeric value (error=3, warning=2, info=1).
    """

    file: str
    finding_count: int = 0
    memory_findings: int = 0
    modernization_findings: int = 0
    complexity_findings: int = 0
    misra_findings: int = 0
    max_severity: int = 0


@dataclass
class GitSummary:
    """Git metrics for a single file.

    Attributes:
        file: Relative path of the file.
        change_frequency: Number of commits touching this file.
        unique_contributors: Number of distinct contributors.
        churn_rate: Code churn ratio (added + removed) / LOC.
        bug_fix_commits: Historical bug-fix commit count.
        szz_bug_introductions: Distinct SZZ bug-introducing commits.
        age_days: File age in days.
        is_knowledge_silo: True if this file is a knowledge silo.
    """

    file: str
    change_frequency: int = 0
    unique_contributors: int = 0
    churn_rate: float = 0.0
    bug_fix_commits: int = 0
    szz_bug_introductions: int = 0
    age_days: int = 0
    is_knowledge_silo: bool = False


@dataclass(frozen=True)
class RankAvailability:
    """Usability of one file's inputs for experimental ranking.

    This does not qualify an observed build or consumer configuration. Inferred
    parse arguments remain inferred in the original analysis inventory.
    """

    file: str
    availability: str
    reason_codes: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        """Whether the declared analysis and history inputs are usable."""
        return self.availability == "available"

    def unranked_record(self) -> dict[str, Any]:
        """Serialize an unavailable file without a score or risk-level claim."""
        if self.eligible:
            raise ValueError("An eligible file is not an unranked observation")
        return {
            "file": self.file,
            "availability": self.availability,
            "reason_codes": list(self.reason_codes),
            "reasons": list(self.reasons),
        }


def relative_identity(file: str, data: dict[str, Any]) -> str:
    """Normalize legacy absolute producer paths to repository-relative paths."""
    if not file:
        return ""
    path = PurePosixPath(file.replace("\\", "/"))
    root = PurePosixPath(
        data.get("metadata", {}).get("repo_path", "").replace("\\", "/")
    )
    if not path.is_absolute() and not PureWindowsPath(file).drive:
        return path.as_posix()
    try:
        return (
            path.relative_to(root).as_posix() if str(root) != "." else path.as_posix()
        )
    except ValueError:
        return path.as_posix()


def coverage_identity(file: str, data: dict[str, Any]) -> str:
    """Normalize legacy root-prefixed coverage paths without rewriting file IDs."""
    path = PurePosixPath(file.replace("\\", "/"))
    root = PurePosixPath(
        data.get("metadata", {}).get("repo_path", "").replace("\\", "/")
    )
    if not path.is_absolute() and not PureWindowsPath(file).drive and str(root) != ".":
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return relative_identity(file, data)


class FeatureEngineer:
    """Merges static analysis findings and git metrics into ML features.

    Produces a pandas DataFrame with one row per file and the feature
    columns required by BugPredictor.
    """

    def build_features(
        self,
        findings_data: dict[str, Any],
        git_metrics_data: dict[str, Any],
    ) -> pd.DataFrame:
        """Merge findings and git metrics into a feature DataFrame.

        Files that appear in only one source receive zero-filled defaults
        for the missing source's features.

        Args:
            findings_data: Parsed contents of findings.json.
            git_metrics_data: Parsed contents of git_metrics.json.

        Returns:
            DataFrame with columns defined in FEATURE_COLUMNS.
        """
        findings_map = self._aggregate_findings(findings_data)
        git_map = self._aggregate_git_metrics(git_metrics_data)

        coverage = findings_data.get("metadata", {}).get("analysis")
        limitations = []
        availability = "scored"
        if coverage is not None:
            entries = coverage.get("files", [])
            if not coverage.get("enabled_rules") and entries:
                availability = "partial"
                limitations.append(
                    "Full-scope health unavailable: no detectors were enabled."
                )
            all_files = {
                coverage_identity(entry["path"], findings_data)
                for entry in entries
                if entry["status"] in {"analyzed", "partial"}
            }
            outside = set(findings_map) - all_files
            if outside:
                raise ValueError(
                    f"Findings outside attempted source scope: {sorted(outside)}"
                )
            if any(
                entry["status"] not in {"analyzed", "excluded"}
                or entry.get("error_count", 0) > 0
                for entry in entries
            ):
                availability = "partial"
                limitations.append(
                    "Full-scope health unavailable: some declared source units were not completely analyzed."
                )
        else:
            all_files = set(findings_map.keys()) | set(git_map.keys())
            if all_files:
                availability = "partial"
                limitations.append(
                    "Full-scope health unavailable: legacy input has no parse-scope inventory."
                )
        ranking = self._ranking_scope(
            findings_data, git_metrics_data, all_files, git_map
        )
        attrs = {
            "health_availability": availability,
            "limitations": limitations,
            "rank_availability": ranking,
        }

        if not all_files:
            empty = pd.DataFrame(columns=FEATURE_COLUMNS)
            empty.attrs.update(attrs)
            return empty

        rows: list[dict[str, Any]] = []
        for file_path in sorted(all_files):
            fs = findings_map.get(file_path, FindingsSummary(file=file_path))
            gs = git_map.get(file_path, GitSummary(file=file_path))
            rows.append(
                {
                    "file": file_path,
                    "finding_count": fs.finding_count,
                    "memory_findings": fs.memory_findings,
                    "modernization_findings": fs.modernization_findings,
                    "complexity_findings": fs.complexity_findings,
                    "misra_findings": fs.misra_findings,
                    "max_severity": fs.max_severity,
                    "change_frequency": gs.change_frequency,
                    "unique_contributors": gs.unique_contributors,
                    "churn_rate": gs.churn_rate,
                    "bug_fix_commits": gs.bug_fix_commits,
                    "szz_bug_introductions": gs.szz_bug_introductions,
                    "age_days": gs.age_days,
                    "is_knowledge_silo": int(gs.is_knowledge_silo),
                }
            )

        df = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
        df.attrs.update(attrs)
        return df

    @staticmethod
    def _ranking_scope(
        findings_data: dict[str, Any],
        git_metrics_data: dict[str, Any],
        feature_paths: set[str],
        git_map: dict[str, GitSummary],
    ) -> dict[str, RankAvailability]:
        """Account for every non-excluded file and missing ranking prerequisite.

        A skipped/failed unit stays in this inventory even when no feature row
        can be engineered. Zero-filled convenience features are never evidence
        that static analysis or Git history was actually observed.
        """
        analysis = findings_data.get("metadata", {}).get("analysis")
        entries: dict[str, list[dict[str, Any]]] = {}
        if analysis is not None:
            for entry in analysis.get("files", []):
                if entry["status"] != "excluded":
                    file = coverage_identity(entry["path"], findings_data)
                    entries.setdefault(file, []).append(entry)
            paths = set(entries)
        else:
            paths = feature_paths
        metadata = git_metrics_data.get("metadata", {})
        history_status = metadata.get("history_status")
        result: dict[str, RankAvailability] = {}
        for file in sorted(paths):
            codes: list[str] = []
            reasons: list[str] = []
            state = "available"
            if analysis is None:
                state = "unverified"
                codes.append("missing_parse_inventory")
                reasons.append(
                    "No parse-scope inventory establishes this file's analysis."
                )
            else:
                if not analysis.get("enabled_rules"):
                    state = "unverified"
                    codes.append("no_enabled_detectors")
                    reasons.append(
                        "No enabled detectors establish static ranking inputs."
                    )
                for entry in entries[file]:
                    errors = entry.get("error_count", 0)
                    if entry["status"] != "analyzed" or errors:
                        state = "partial"
                        if "partial_analysis" not in codes:
                            codes.append("partial_analysis")
                        reasons.append(
                            f"Native analysis status is {entry['status']} with {errors} parse errors."
                        )
            if history_status != "available":
                code = {
                    "partial": "partial_history",
                    "unavailable": "missing_history",
                }.get(history_status, "unverified_history")
                codes.append(code)
                reasons.append(
                    f"Git history is {history_status or 'unverified'}; missing history is not zero change activity."
                )
                if state == "available":
                    state = "unavailable" if history_status else "unverified"
            elif file not in git_map or git_map[file].change_frequency <= 0:
                codes.append("missing_file_history")
                reasons.append("No observed commit history is available for this file.")
                if state == "available":
                    state = "unavailable"
            result[file] = RankAvailability(
                file, state, tuple(dict.fromkeys(codes)), tuple(dict.fromkeys(reasons))
            )
        return result

    def _aggregate_findings(
        self, findings_data: dict[str, Any]
    ) -> dict[str, FindingsSummary]:
        """Aggregate raw findings list into per-file summaries.

        Args:
            findings_data: Parsed findings.json dict.

        Returns:
            Mapping from file path to FindingsSummary.
        """
        summaries: dict[str, FindingsSummary] = {}
        raw_findings: list[dict[str, Any]] = findings_data.get("findings", [])

        for finding in raw_findings:
            file_path = relative_identity(finding.get("file", ""), findings_data)
            if not file_path:
                continue

            if file_path not in summaries:
                summaries[file_path] = FindingsSummary(file=file_path)

            fs = summaries[file_path]
            fs.finding_count += 1

            category: str = finding.get("category", "")
            if category == "memory_safety":
                fs.memory_findings += 1
            elif category == "modernization":
                fs.modernization_findings += 1
            elif category == "complexity":
                fs.complexity_findings += 1
            elif category == "misra":
                fs.misra_findings += 1

            severity_val = SEVERITY_MAP.get(finding.get("severity", "info"), 1)
            if severity_val > fs.max_severity:
                fs.max_severity = severity_val

        return summaries

    def _aggregate_git_metrics(
        self, git_metrics_data: dict[str, Any]
    ) -> dict[str, GitSummary]:
        """Build per-file git summaries from git_metrics.json.

        Args:
            git_metrics_data: Parsed git_metrics.json dict.

        Returns:
            Mapping from file path to GitSummary.
        """
        summaries: dict[str, GitSummary] = {}

        silo_files: set[str] = {
            relative_identity(entry.get("file", ""), git_metrics_data)
            for entry in git_metrics_data.get("knowledge_silos", [])
            if entry.get("file")
        }

        for fm in git_metrics_data.get("file_metrics", []):
            file_path = relative_identity(fm.get("file", ""), git_metrics_data)
            if not file_path:
                continue

            summaries[file_path] = GitSummary(
                file=file_path,
                change_frequency=int(fm.get("change_frequency", 0)),
                unique_contributors=int(fm.get("unique_contributors", 0)),
                churn_rate=float(fm.get("churn_rate", 0.0)),
                bug_fix_commits=int(fm.get("bug_fix_commits", 0)),
                szz_bug_introductions=int(fm.get("szz_bug_introductions", 0)),
                age_days=int(fm.get("age_days", 0)),
                is_knowledge_silo=(file_path in silo_files),
            )

        for silo_file in silo_files:
            if silo_file not in summaries:
                summaries[silo_file] = GitSummary(
                    file=silo_file,
                    is_knowledge_silo=True,
                )

        return summaries
