"""Health scoring module for cppulse predictor.

Converts raw finding counts into a 0–100 health score for the overall
codebase and per category.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PENALTY_WEIGHTS: dict[str, float] = {
    "memory_findings": 3.0,
    "misra_findings": 2.5,
    "complexity_findings": 1.5,
    "modernization_findings": 1.0,
}

CATEGORY_SCALE_FACTORS: dict[str, float] = {
    "memory_safety": 15.0,
    "modernization": 5.0,
    "complexity": 10.0,
    "misra_compliance": 12.0,
}

CATEGORY_COLUMN_MAP: dict[str, str] = {
    "memory_safety": "memory_findings",
    "modernization": "modernization_findings",
    "complexity": "complexity_findings",
    "misra_compliance": "misra_findings",
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
    """

    def compute(self, features_df: pd.DataFrame) -> HealthScore:
        """Compute the overall and per-category health scores.

        Args:
            features_df: DataFrame produced by FeatureEngineer.build_features().
                Must contain columns: memory_findings, modernization_findings,
                complexity_findings, misra_findings.

        Returns:
            HealthScore with overall score and by_category breakdown.
        """
        if features_df.empty:
            return HealthScore(
                overall=100.0,
                by_category={cat: 100.0 for cat in CATEGORY_SCALE_FACTORS},
            )

        overall = self._compute_overall(features_df)
        by_category = self._compute_by_category(features_df)
        return HealthScore(overall=overall, by_category=by_category)

    def _compute_overall(self, features_df: pd.DataFrame) -> float:
        """Compute overall health score.

        overall_health = 100 - weighted_penalty, clamped to [0, 100].
        weighted_penalty = sum of (count * weight) across all findings.

        Args:
            features_df: Feature DataFrame.

        Returns:
            Float health score in [0.0, 100.0].
        """
        total_penalty = 0.0
        file_count = len(features_df)

        for col, weight in PENALTY_WEIGHTS.items():
            if col in features_df.columns:
                total_penalty += float(features_df[col].sum()) * weight

        normalized_penalty = total_penalty / max(file_count, 1)
        score = 100.0 - normalized_penalty
        return float(max(0.0, min(100.0, score)))

    def _compute_by_category(self, features_df: pd.DataFrame) -> dict[str, float]:
        """Compute per-category health scores.

        Category score = 100 - (category_findings / file_count * scale_factor),
        clamped to [0, 100].

        Args:
            features_df: Feature DataFrame.

        Returns:
            Dict mapping category name to score in [0.0, 100.0].
        """
        file_count = len(features_df)
        scores: dict[str, float] = {}

        for category, col in CATEGORY_COLUMN_MAP.items():
            scale = CATEGORY_SCALE_FACTORS[category]
            if col in features_df.columns:
                avg_findings = float(features_df[col].sum()) / max(file_count, 1)
            else:
                avg_findings = 0.0
            raw = 100.0 - avg_findings * scale
            scores[category] = float(max(0.0, min(100.0, raw)))

        return scores
