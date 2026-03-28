"""Tests for src/health_scorer.py — HealthScorer with profile support."""

from __future__ import annotations

import pandas as pd
import pytest

from src.health_scorer import PROFILES, HealthScore, HealthScorer


def _make_df(**kwargs: int) -> pd.DataFrame:
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


class TestDefaultProfile:
    """Tests for the default profile (MISRA excluded)."""

    def test_perfect_score(self) -> None:
        scorer = HealthScorer(profile="default")
        result = scorer.compute(_make_df())
        assert result.overall == pytest.approx(100.0)

    def test_default_excludes_misra(self) -> None:
        scorer = HealthScorer(profile="default")
        result = scorer.compute(_make_df())
        assert "misra_compliance" not in result.by_category

    def test_default_has_three_categories(self) -> None:
        scorer = HealthScorer(profile="default")
        result = scorer.compute(_make_df())
        assert set(result.by_category.keys()) == {
            "memory_safety",
            "modernization",
            "complexity",
        }

    def test_misra_findings_dont_affect_default_score(self) -> None:
        scorer = HealthScorer(profile="default")
        clean = scorer.compute(_make_df())
        with_misra = scorer.compute(_make_df(misra_findings=100))
        assert with_misra.overall == clean.overall

    def test_memory_finding_reduces_score(self) -> None:
        scorer = HealthScorer(profile="default")
        result = scorer.compute(_make_df(memory_findings=1))
        assert result.overall < 100.0

    def test_empty_dataframe_returns_perfect(self) -> None:
        scorer = HealthScorer(profile="default")
        df = pd.DataFrame(columns=["file", "memory_findings"])
        result = scorer.compute(df)
        assert result.overall == pytest.approx(100.0)


class TestSafetyCriticalProfile:
    """Tests for the safety-critical profile (MISRA included)."""

    def test_includes_misra(self) -> None:
        scorer = HealthScorer(profile="safety-critical")
        result = scorer.compute(_make_df())
        assert "misra_compliance" in result.by_category

    def test_has_four_categories(self) -> None:
        scorer = HealthScorer(profile="safety-critical")
        result = scorer.compute(_make_df())
        assert set(result.by_category.keys()) == {
            "memory_safety",
            "modernization",
            "complexity",
            "misra_compliance",
        }

    def test_misra_findings_reduce_score(self) -> None:
        scorer = HealthScorer(profile="safety-critical")
        clean = scorer.compute(_make_df())
        dirty = scorer.compute(_make_df(misra_findings=1))
        assert dirty.overall < clean.overall

    def test_misra_category_drops_with_findings(self) -> None:
        scorer = HealthScorer(profile="safety-critical")
        clean = scorer.compute(_make_df())
        dirty = scorer.compute(_make_df(misra_findings=2))
        assert (
            dirty.by_category["misra_compliance"]
            < clean.by_category["misra_compliance"]
        )


class TestClamping:
    """Tests for score clamping to [0, 100]."""

    def test_excessive_findings_clamp_to_zero(self) -> None:
        scorer = HealthScorer()
        df = _make_df(memory_findings=1000)
        assert scorer.compute(df).overall == pytest.approx(0.0)

    def test_category_score_clamps_to_zero(self) -> None:
        scorer = HealthScorer()
        df = _make_df(memory_findings=500)
        assert scorer.compute(df).by_category["memory_safety"] >= 0.0

    def test_overall_never_exceeds_100(self) -> None:
        scorer = HealthScorer()
        assert scorer.compute(_make_df()).overall <= 100.0

    def test_category_scores_never_exceed_100(self) -> None:
        scorer = HealthScorer()
        for score in scorer.compute(_make_df()).by_category.values():
            assert score <= 100.0


class TestProfileValidation:
    """Tests for invalid profile handling."""

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown profile"):
            HealthScorer(profile="nonexistent")

    def test_default_is_default(self) -> None:
        scorer = HealthScorer()
        result = scorer.compute(_make_df())
        assert "misra_compliance" not in result.by_category

    def test_health_score_is_dataclass(self) -> None:
        scorer = HealthScorer()
        assert isinstance(scorer.compute(_make_df()), HealthScore)

    def test_penalty_divided_by_file_count(self) -> None:
        scorer = HealthScorer()
        rows = [
            {
                "file": "a.cpp",
                "memory_findings": 1,
                "modernization_findings": 0,
                "complexity_findings": 0,
                "misra_findings": 0,
            },
            {
                "file": "b.cpp",
                "memory_findings": 1,
                "modernization_findings": 0,
                "complexity_findings": 0,
                "misra_findings": 0,
            },
        ]
        df = pd.DataFrame(rows)
        result = scorer.compute(df)
        weight = PROFILES["default"]["weights"]["memory_findings"]
        expected = 100.0 - (weight * 2) / 2
        assert result.overall == pytest.approx(expected)

    def test_independent_category_scores(self) -> None:
        scorer = HealthScorer()
        result = scorer.compute(_make_df(memory_findings=5))
        assert result.by_category["modernization"] == pytest.approx(100.0)
