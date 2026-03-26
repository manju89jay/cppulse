"""Tests for src/health_scorer.py — HealthScorer."""

from __future__ import annotations

import pandas as pd
import pytest

from src.health_scorer import (
    CATEGORY_COLUMN_MAP,
    PENALTY_WEIGHTS,
    HealthScore,
    HealthScorer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_df(**kwargs: int) -> pd.DataFrame:
    """Create a single-row feature DataFrame.

    Keyword args are column names; all unspecified finding columns default to 0.

    Args:
        **kwargs: Column name -> integer value overrides.

    Returns:
        Single-row DataFrame.
    """
    defaults = {
        "file": "src/a.cpp",
        "memory_findings": 0,
        "modernization_findings": 0,
        "complexity_findings": 0,
        "misra_findings": 0,
        "finding_count": 0,
        "max_severity": 0,
        "change_frequency": 0,
        "unique_contributors": 1,
        "churn_rate": 0.0,
        "bug_fix_commits": 0,
        "age_days": 365,
        "is_knowledge_silo": 0,
    }
    defaults.update(kwargs)
    return pd.DataFrame([defaults])


# ---------------------------------------------------------------------------
# Perfect score tests
# ---------------------------------------------------------------------------


class TestPerfectScore:
    """Tests for the zero-findings (perfect) case."""

    def test_perfect_score_overall(self) -> None:
        """No findings should yield an overall score of 100.0."""
        scorer = HealthScorer()
        df = _make_df()
        result = scorer.compute(df)
        assert result.overall == pytest.approx(100.0)

    def test_perfect_score_all_categories(self) -> None:
        """No findings should yield 100.0 for every category."""
        scorer = HealthScorer()
        df = _make_df()
        result = scorer.compute(df)
        for cat in CATEGORY_COLUMN_MAP:
            assert result.by_category[cat] == pytest.approx(100.0), f"Failed for {cat}"

    def test_empty_dataframe_returns_perfect(self) -> None:
        """Empty input DataFrame should return HealthScore(100, all-100)."""
        scorer = HealthScorer()
        df = pd.DataFrame(
            columns=[
                "file",
                "memory_findings",
                "modernization_findings",
                "complexity_findings",
                "misra_findings",
            ]
        )
        result = scorer.compute(df)
        assert result.overall == pytest.approx(100.0)
        for cat in CATEGORY_COLUMN_MAP:
            assert result.by_category[cat] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Penalty tests
# ---------------------------------------------------------------------------


class TestPenalties:
    """Tests that verify penalty calculations."""

    def test_single_memory_finding_reduces_score(self) -> None:
        """One memory finding should subtract 3.0 * 1 / 1 = 3 penalty points."""
        scorer = HealthScorer()
        df = _make_df(memory_findings=1)
        result = scorer.compute(df)
        expected = 100.0 - PENALTY_WEIGHTS["memory_findings"] * 1
        assert result.overall == pytest.approx(expected)

    def test_single_misra_finding_reduces_score(self) -> None:
        """One MISRA finding should subtract 2.5 penalty points."""
        scorer = HealthScorer()
        df = _make_df(misra_findings=1)
        result = scorer.compute(df)
        expected = 100.0 - PENALTY_WEIGHTS["misra_findings"] * 1
        assert result.overall == pytest.approx(expected)

    def test_multiple_finding_types_accumulate(self) -> None:
        """Mixed findings across categories accumulate correctly."""
        scorer = HealthScorer()
        df = _make_df(memory_findings=2, misra_findings=1, complexity_findings=1)
        result = scorer.compute(df)
        expected = (
            100.0
            - PENALTY_WEIGHTS["memory_findings"] * 2
            - PENALTY_WEIGHTS["misra_findings"] * 1
            - PENALTY_WEIGHTS["complexity_findings"] * 1
        )
        assert result.overall == pytest.approx(expected)

    def test_penalty_divided_by_file_count(self) -> None:
        """With 2 files and 2 total memory findings, penalty is (3*2)/2 = 3."""
        scorer = HealthScorer()
        rows = [
            {
                "file": "src/a.cpp",
                "memory_findings": 1,
                "modernization_findings": 0,
                "complexity_findings": 0,
                "misra_findings": 0,
            },
            {
                "file": "src/b.cpp",
                "memory_findings": 1,
                "modernization_findings": 0,
                "complexity_findings": 0,
                "misra_findings": 0,
            },
        ]
        df = pd.DataFrame(rows)
        result = scorer.compute(df)
        expected = 100.0 - (PENALTY_WEIGHTS["memory_findings"] * 2) / 2
        assert result.overall == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Clamping tests
# ---------------------------------------------------------------------------


class TestClamping:
    """Tests for score clamping to [0, 100]."""

    def test_excessive_findings_clamp_to_zero(self) -> None:
        """Very many findings should clamp overall score to 0.0, not negative."""
        scorer = HealthScorer()
        df = _make_df(memory_findings=1000, misra_findings=500)
        result = scorer.compute(df)
        assert result.overall == pytest.approx(0.0)

    def test_category_score_clamps_to_zero(self) -> None:
        """Category score must not drop below 0.0 regardless of finding count."""
        scorer = HealthScorer()
        df = _make_df(memory_findings=500)
        result = scorer.compute(df)
        assert result.by_category["memory_safety"] >= 0.0

    def test_overall_never_exceeds_100(self) -> None:
        """Overall score must never exceed 100.0."""
        scorer = HealthScorer()
        df = _make_df()
        result = scorer.compute(df)
        assert result.overall <= 100.0

    def test_category_scores_never_exceed_100(self) -> None:
        """No category score should exceed 100.0."""
        scorer = HealthScorer()
        df = _make_df()
        result = scorer.compute(df)
        for cat, score in result.by_category.items():
            assert score <= 100.0, f"{cat} score {score} exceeds 100"


# ---------------------------------------------------------------------------
# Category score tests
# ---------------------------------------------------------------------------


class TestCategoryScores:
    """Tests for per-category scoring logic."""

    def test_category_scores_exist_for_all_categories(self) -> None:
        """by_category must contain keys for all four expected categories."""
        scorer = HealthScorer()
        df = _make_df()
        result = scorer.compute(df)
        assert set(result.by_category.keys()) == set(CATEGORY_COLUMN_MAP.keys())

    def test_memory_category_drops_with_findings(self) -> None:
        """memory_safety score must decrease when memory_findings > 0."""
        scorer = HealthScorer()
        clean = scorer.compute(_make_df())
        dirty = scorer.compute(_make_df(memory_findings=3))
        assert dirty.by_category["memory_safety"] < clean.by_category["memory_safety"]

    def test_misra_category_drops_with_findings(self) -> None:
        """misra_compliance score must decrease when misra_findings > 0."""
        scorer = HealthScorer()
        clean = scorer.compute(_make_df())
        dirty = scorer.compute(_make_df(misra_findings=2))
        assert (
            dirty.by_category["misra_compliance"]
            < clean.by_category["misra_compliance"]
        )

    def test_independent_category_scores(self) -> None:
        """A finding in one category must not reduce an unrelated category's score."""
        scorer = HealthScorer()
        result = scorer.compute(_make_df(memory_findings=5))
        # Modernization should still be 100 (no modernization findings)
        assert result.by_category["modernization"] == pytest.approx(100.0)

    def test_health_score_is_dataclass(self) -> None:
        """compute() must return a HealthScore instance."""
        scorer = HealthScorer()
        result = scorer.compute(_make_df())
        assert isinstance(result, HealthScore)
