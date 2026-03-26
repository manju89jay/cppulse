"""Roadmap generation module for cppulse predictor.

Generates a prioritized refactoring roadmap from findings, git metrics,
and risk scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


RISK_LEVEL_WEIGHTS: dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}

SEVERITY_WEIGHTS: dict[str, float] = {
    "error": 3.0,
    "warning": 2.0,
    "info": 1.0,
}

CATEGORY_HOURS: dict[str, float] = {
    "memory_safety": 4.0,
    "misra": 2.0,
    "complexity": 3.0,
    "modernization": 1.0,
    "knowledge_silo": 8.0,
}

CATEGORY_ACTIONS: dict[str, str] = {
    "memory_safety": "Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks",
    "misra": "Address MISRA C++ compliance violations to meet safety standards",
    "complexity": "Reduce cyclomatic complexity by extracting methods and simplifying control flow",
    "modernization": "Modernize C++ code: apply C++11/14/17 idioms and remove deprecated constructs",
    "knowledge_silo": "Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions",
}


@dataclass
class RoadmapItem:
    """A single refactoring roadmap item.

    Attributes:
        priority: Rank starting at 1 (lower is higher priority).
        file: File path this item applies to.
        action: Human-readable refactoring recommendation.
        category: One of memory_safety, modernization, complexity, misra, knowledge_silo.
        estimated_hours: Estimated effort in hours.
        impact_score: Expected health score improvement (0–100).
        finding_ids: List of related rule IDs from findings.
    """

    priority: int
    file: str
    action: str
    category: str
    estimated_hours: float
    impact_score: float
    finding_ids: list[str] = field(default_factory=list)


class RoadmapGenerator:
    """Generates a prioritized refactoring roadmap.

    Takes findings, git metrics, and risk scores to produce ranked
    refactoring items sorted by impact score descending.
    """

    def generate(
        self,
        findings_data: dict[str, Any],
        git_metrics_data: dict[str, Any],
        risk_scores_data: dict[str, Any],
    ) -> list[RoadmapItem]:
        """Generate a prioritized list of refactoring items.

        Items are generated per file per category where findings exist or
        a knowledge silo is detected. Each item is scored by:
            impact_score = risk_level_weight * severity_weight * (1 + is_hotspot)

        Items are sorted by impact_score descending and assigned priority ranks.

        Args:
            findings_data: Parsed findings.json dict.
            git_metrics_data: Parsed git_metrics.json dict.
            risk_scores_data: Parsed risk_scores.json dict (output of predictor).

        Returns:
            List of RoadmapItem sorted by priority (highest impact first).
        """
        file_risk_map = self._build_risk_map(risk_scores_data)
        hotspot_files = self._build_hotspot_set(risk_scores_data)
        silo_files = self._build_silo_set(git_metrics_data)
        file_findings_map = self._group_findings_by_file(findings_data)

        raw_items: list[tuple[float, RoadmapItem]] = []

        # Process findings-based items
        for file_path, findings in file_findings_map.items():
            risk_level = file_risk_map.get(file_path, "low")
            risk_weight = RISK_LEVEL_WEIGHTS[risk_level]
            is_hotspot = 1 if file_path in hotspot_files else 0

            by_category: dict[str, list[dict[str, Any]]] = {}
            for f in findings:
                cat = f.get("category", "")
                if cat:
                    by_category.setdefault(cat, []).append(f)

            for category, cat_findings in by_category.items():
                max_sev = max(
                    SEVERITY_WEIGHTS.get(f.get("severity", "info"), 1.0)
                    for f in cat_findings
                )
                impact = risk_weight * max_sev * (1.0 + is_hotspot)
                impact = min(100.0, impact)

                rule_ids = list(
                    dict.fromkeys(f.get("rule_id", "") for f in cat_findings if f.get("rule_id"))
                )

                action = CATEGORY_ACTIONS.get(
                    category,
                    f"Address {category} findings in this file",
                )
                estimated_hours = CATEGORY_HOURS.get(category, 2.0) * max(
                    1, len(cat_findings)
                )

                item = RoadmapItem(
                    priority=0,
                    file=file_path,
                    action=action,
                    category=category,
                    estimated_hours=float(estimated_hours),
                    impact_score=float(impact),
                    finding_ids=rule_ids,
                )
                raw_items.append((impact, item))

        # Process knowledge silo items
        for silo_file in silo_files:
            risk_level = file_risk_map.get(silo_file, "low")
            risk_weight = RISK_LEVEL_WEIGHTS[risk_level]
            is_hotspot = 1 if silo_file in hotspot_files else 0

            impact = risk_weight * 2.0 * (1.0 + is_hotspot)
            impact = min(100.0, impact)

            item = RoadmapItem(
                priority=0,
                file=silo_file,
                action=CATEGORY_ACTIONS["knowledge_silo"],
                category="knowledge_silo",
                estimated_hours=CATEGORY_HOURS["knowledge_silo"],
                impact_score=float(impact),
                finding_ids=[],
            )
            raw_items.append((impact, item))

        # Sort by impact descending, assign priorities
        raw_items.sort(key=lambda x: x[0], reverse=True)
        result: list[RoadmapItem] = []
        for idx, (_, item) in enumerate(raw_items, start=1):
            item.priority = idx
            result.append(item)

        return result

    def _build_risk_map(self, risk_scores_data: dict[str, Any]) -> dict[str, str]:
        """Build a file -> risk_level mapping from risk_scores output.

        Args:
            risk_scores_data: Parsed risk_scores.json.

        Returns:
            Dict mapping file path to risk level string.
        """
        return {
            entry["file"]: entry.get("risk_level", "low")
            for entry in risk_scores_data.get("file_risks", [])
            if entry.get("file")
        }

    def _build_hotspot_set(self, risk_scores_data: dict[str, Any]) -> set[str]:
        """Build the set of hotspot file paths from risk_scores output.

        Args:
            risk_scores_data: Parsed risk_scores.json.

        Returns:
            Set of file path strings identified as hotspots.
        """
        return {
            entry["file"]
            for entry in risk_scores_data.get("hotspots", [])
            if entry.get("file")
        }

    def _build_silo_set(self, git_metrics_data: dict[str, Any]) -> set[str]:
        """Build the set of knowledge silo file paths.

        Args:
            git_metrics_data: Parsed git_metrics.json.

        Returns:
            Set of file path strings that are knowledge silos.
        """
        return {
            entry["file"]
            for entry in git_metrics_data.get("knowledge_silos", [])
            if entry.get("file")
        }

    def _group_findings_by_file(
        self, findings_data: dict[str, Any]
    ) -> dict[str, list[dict[str, Any]]]:
        """Group raw findings by file path.

        Args:
            findings_data: Parsed findings.json.

        Returns:
            Dict mapping file path to list of finding dicts.
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        for finding in findings_data.get("findings", []):
            file_path = finding.get("file", "")
            if file_path:
                grouped.setdefault(file_path, []).append(finding)
        return grouped
