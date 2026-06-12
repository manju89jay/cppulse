"""Health scoring module for cppulse predictor.

Converts raw finding counts into a 0–100 health score for the overall
codebase and per category, using finding density (findings per KLOC)
so the score is independent of repository size and file granularity.

Model (see ADR-007):
    density_cat  = findings_cat / KLOC
    penalty_cat  = min(1.0, density_cat / cap_cat)        # in [0, 1]
    category     = (1 - penalty_cat) * 100
    overall      = (1 - sum(penalty_cat * w_cat) / sum(w_cat)) * 100

The cap is the density at which a category is considered fully degraded
(category score 0). Caps are calibration constants documented in ADR-007.
Supports profiles: "default" excludes MISRA rules (designed for
safety-critical embedded, not general C++).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Per profile: category -> (feature column, weight, density cap in findings/KLOC).
PROFILES: dict[str, dict[str, tuple[str, float, float]]] = {
    "default": {
        "memory_safety": ("memory_findings", 3.0, 5.0),
        "complexity": ("complexity_findings", 1.5, 10.0),
        "modernization": ("modernization_findings", 1.0, 50.0),
    },
    "safety-critical": {
        "memory_safety": ("memory_findings", 3.0, 5.0),
        "misra_compliance": ("misra_findings", 2.5, 10.0),
        "complexity": ("complexity_findings", 1.5, 10.0),
        "modernization": ("modernization_findings", 1.0, 50.0),
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
    """Computes codebase health scores from finding densities.

    Each category's penalty is its finding density (per KLOC) relative to a
    documented cap, weighted and normalized by the sum of weights — the same
    inputs always produce the same score, and a codebase with zero findings
    scores 100 regardless of size.

    Args:
        profile: Analysis profile name. "default" excludes MISRA rules,
            "safety-critical" includes them with 2.5x weight.
    """

    def __init__(self, profile: str = "default") -> None:
        if profile not in PROFILES:
            raise ValueError(
                f"Unknown profile: {profile!r}. Choose from {list(PROFILES)}"
            )
        self._categories = PROFILES[profile]

    def compute(self, features_df: pd.DataFrame, total_loc: int) -> HealthScore:
        """Compute the overall and per-category health scores.

        Args:
            features_df: DataFrame produced by FeatureEngineer.build_features().
            total_loc: Total lines of code analyzed (from findings.json
                metadata). Guarded to at least 1.

        Returns:
            HealthScore with overall score and by_category breakdown.
        """
        if features_df.empty:
            return HealthScore(
                overall=100.0,
                by_category={cat: 100.0 for cat in self._categories},
            )

        kloc = max(int(total_loc), 1) / 1000.0

        penalties: dict[str, float] = {}
        for category, (col, _weight, cap) in self._categories.items():
            count = float(features_df[col].sum()) if col in features_df.columns else 0.0
            density = count / kloc
            penalties[category] = min(1.0, density / cap)

        weight_sum = sum(weight for (_c, weight, _cap) in self._categories.values())
        weighted_penalty = (
            sum(
                penalties[category] * weight
                for category, (_c, weight, _cap) in self._categories.items()
            )
            / weight_sum
        )

        overall = round((1.0 - weighted_penalty) * 100.0, 1)
        by_category = {
            category: round((1.0 - penalty) * 100.0, 1)
            for category, penalty in penalties.items()
        }
        return HealthScore(overall=overall, by_category=by_category)
