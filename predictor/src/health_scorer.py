"""Health scoring module for cppulse predictor.

Converts raw finding counts into a 0–100 health score for the overall
codebase and per category. Supports profiles: "default" excludes MISRA
rules (designed for safety-critical embedded, not general C++).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PROFILES: dict[str, dict] = {
    "default": {
        "weights": {
            "memory_findings": 3.0,
            "complexity_findings": 1.5,
            "modernization_findings": 1.0,
        },
        "categories": {
            "memory_safety": ("memory_findings", 15.0),
            "modernization": ("modernization_findings", 5.0),
            "complexity": ("complexity_findings", 10.0),
        },
    },
    "safety-critical": {
        "weights": {
            "memory_findings": 3.0,
            "misra_findings": 2.5,
            "complexity_findings": 1.5,
            "modernization_findings": 1.0,
        },
        "categories": {
            "memory_safety": ("memory_findings", 15.0),
            "modernization": ("modernization_findings", 5.0),
            "complexity": ("complexity_findings", 10.0),
            "misra_compliance": ("misra_findings", 12.0),
        },
    },
}


@dataclass
class HealthScore:
    """Aggregated health scores for the codebase.

    Attributes:
        overall: Overall health score clamped to [0, 100].
        by_category: Mapping of category name to score [0, 100].
    """

    overall: float
    by_category: dict[str, float]


class HealthScorer:
    """Computes codebase health scores from feature data.

    The overall health score penalizes findings weighted by category severity.
    Category scores reflect per-file average finding density scaled to [0, 100].

    Args:
        profile: Analysis profile name. "default" excludes MISRA rules,
            "safety-critical" includes them with 2.5x weight.
    """

    def __init__(self, profile: str = "default") -> None:
        if profile not in PROFILES:
            raise ValueError(f"Unknown profile: {profile!r}. Choose from {list(PROFILES)}")
        self._profile = PROFILES[profile]

    def compute(self, features_df: pd.DataFrame) -> HealthScore:
        """Compute the overall and per-category health scores.

        Args:
            features_df: DataFrame produced by FeatureEngineer.build_features().

        Returns:
            HealthScore with overall score and by_category breakdown.
        """
        if features_df.empty:
            return HealthScore(
                overall=100.0,
                by_category={cat: 100.0 for cat in self._profile["categories"]},
            )

        overall = self._compute_overall(features_df)
        by_category = self._compute_by_category(features_df)
        return HealthScore(overall=overall, by_category=by_category)

    def _compute_overall(self, features_df: pd.DataFrame) -> float:
        """Compute overall health score using the active profile weights."""
        total_penalty = 0.0
        file_count = len(features_df)

        for col, weight in self._profile["weights"].items():
            if col in features_df.columns:
                total_penalty += float(features_df[col].sum()) * weight

        normalized_penalty = total_penalty / max(file_count, 1)
        score = 100.0 - normalized_penalty
        return float(max(0.0, min(100.0, score)))

    def _compute_by_category(self, features_df: pd.DataFrame) -> dict[str, float]:
        """Compute per-category health scores for the active profile."""
        file_count = len(features_df)
        scores: dict[str, float] = {}

        for category, (col, scale) in self._profile["categories"].items():
            if col in features_df.columns:
                avg_findings = float(features_df[col].sum()) / max(file_count, 1)
            else:
                avg_findings = 0.0
            raw = 100.0 - avg_findings * scale
            scores[category] = float(max(0.0, min(100.0, raw)))

        return scores
