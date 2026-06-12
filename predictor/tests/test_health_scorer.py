"""Tests for src/health_scorer.py — density-based HealthScorer (ADR-007)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.health_scorer import PROFILES, HealthScore, HealthScorer

_TOTAL_LOC = 10_000  # 10 KLOC baseline for most tests


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
        result = scorer.compute(_make_df(), _TOTAL_LOC)
        assert result.overall == pytest.approx(100.0)

    def test_default_excludes_misra(self) -> None:
        scorer = HealthScorer(profile="default")
        result = scorer.compute(_make_df(), _TOTAL_LOC)
        assert "misra_compliance" not in result.by_category

    def test_default_has_three_categories(self) -> None:
        scorer = HealthScorer(profile="default")
        result = scorer.compute(_make_df(), _TOTAL_LOC)
        assert set(result.by_category.keys()) == {
            "memory_safety",
            "modernization",
            "complexity",
        }

    def test_misra_findings_dont_affect_default_score(self) -> None:
        scorer = HealthScorer(profile="default")
        clean = scorer.compute(_make_df(), _TOTAL_LOC)
        with_misra = scorer.compute(_make_df(misra_findings=100), _TOTAL_LOC)
        assert with_misra.overall == clean.overall

    def test_memory_finding_reduces_score(self) -> None:
        scorer = HealthScorer(profile="default")
        result = scorer.compute(_make_df(memory_findings=1), _TOTAL_LOC)
        assert result.overall < 100.0

    def test_empty_dataframe_returns_perfect(self) -> None:
        scorer = HealthScorer(profile="default")
        df = pd.DataFrame(columns=["file", "memory_findings"])
        result = scorer.compute(df, _TOTAL_LOC)
        assert result.overall == pytest.approx(100.0)


class TestDensityNormalization:
    """The score depends on findings per KLOC, not repo or file count."""

    def test_same_density_same_score_regardless_of_size(self) -> None:
        """10 findings in 10 KLOC scores the same as 100 findings in 100 KLOC."""
        scorer = HealthScorer()
        small = scorer.compute(_make_df(memory_findings=10), 10_000)
        large = scorer.compute(_make_df(memory_findings=100), 100_000)
        assert small.overall == pytest.approx(large.overall)

    def test_score_independent_of_file_count(self) -> None:
        """Spreading the same findings over more rows changes nothing."""
        scorer = HealthScorer()
        one_file = scorer.compute(_make_df(memory_findings=10), 10_000)
        rows = [_make_df(memory_findings=1).iloc[0] for _ in range(10)]
        many_files = scorer.compute(pd.DataFrame(rows), 10_000)
        assert one_file.overall == pytest.approx(many_files.overall)

    def test_known_density_produces_documented_score(self) -> None:
        """Worked example: memory density at half its cap, others clean.

        density = 25 findings / 10 KLOC = 2.5/KLOC; cap 5.0 -> penalty 0.5.
        overall = (1 - (0.5 * 3.0) / (3.0 + 1.5 + 1.0)) * 100 = 72.7
        """
        scorer = HealthScorer()
        result = scorer.compute(_make_df(memory_findings=25), 10_000)
        assert result.overall == pytest.approx(72.7)
        assert result.by_category["memory_safety"] == pytest.approx(50.0)

    def test_zero_total_loc_is_guarded(self) -> None:
        """total_loc <= 0 must not divide by zero."""
        scorer = HealthScorer()
        result = scorer.compute(_make_df(memory_findings=1), 0)
        assert 0.0 <= result.overall <= 100.0


class TestSafetyCriticalProfile:
    """Tests for the safety-critical profile (MISRA included)."""

    def test_includes_misra(self) -> None:
        scorer = HealthScorer(profile="safety-critical")
        result = scorer.compute(_make_df(), _TOTAL_LOC)
        assert "misra_compliance" in result.by_category

    def test_has_four_categories(self) -> None:
        scorer = HealthScorer(profile="safety-critical")
        result = scorer.compute(_make_df(), _TOTAL_LOC)
        assert set(result.by_category.keys()) == {
            "memory_safety",
            "modernization",
            "complexity",
            "misra_compliance",
        }

    def test_misra_findings_reduce_score(self) -> None:
        scorer = HealthScorer(profile="safety-critical")
        clean = scorer.compute(_make_df(), _TOTAL_LOC)
        dirty = scorer.compute(_make_df(misra_findings=10), _TOTAL_LOC)
        assert dirty.overall < clean.overall

    def test_misra_category_drops_with_findings(self) -> None:
        scorer = HealthScorer(profile="safety-critical")
        clean = scorer.compute(_make_df(), _TOTAL_LOC)
        dirty = scorer.compute(_make_df(misra_findings=20), _TOTAL_LOC)
        assert (
            dirty.by_category["misra_compliance"]
            < clean.by_category["misra_compliance"]
        )


class TestClamping:
    """Tests for penalty caps and score clamping to [0, 100]."""

    def test_all_categories_at_cap_scores_zero(self) -> None:
        scorer = HealthScorer()
        df = _make_df(
            memory_findings=100_000,
            complexity_findings=100_000,
            modernization_findings=1_000_000,
        )
        assert scorer.compute(df, _TOTAL_LOC).overall == pytest.approx(0.0)

    def test_single_category_beyond_cap_saturates(self) -> None:
        """Beyond the cap, more findings in one category change nothing."""
        scorer = HealthScorer()
        at_cap = scorer.compute(_make_df(memory_findings=100_000), _TOTAL_LOC)
        beyond = scorer.compute(_make_df(memory_findings=900_000), _TOTAL_LOC)
        assert at_cap.overall == pytest.approx(beyond.overall)
        assert at_cap.by_category["memory_safety"] == pytest.approx(0.0)

    def test_overall_never_exceeds_100(self) -> None:
        scorer = HealthScorer()
        assert scorer.compute(_make_df(), _TOTAL_LOC).overall <= 100.0

    def test_category_scores_never_exceed_100(self) -> None:
        scorer = HealthScorer()
        for score in scorer.compute(_make_df(), _TOTAL_LOC).by_category.values():
            assert score <= 100.0


class TestProfileValidation:
    """Tests for invalid profile handling and result shape."""

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown profile"):
            HealthScorer(profile="nonexistent")

    def test_default_is_default(self) -> None:
        scorer = HealthScorer()
        result = scorer.compute(_make_df(), _TOTAL_LOC)
        assert "misra_compliance" not in result.by_category

    def test_health_score_is_dataclass(self) -> None:
        scorer = HealthScorer()
        assert isinstance(scorer.compute(_make_df(), _TOTAL_LOC), HealthScore)

    def test_independent_category_scores(self) -> None:
        scorer = HealthScorer()
        result = scorer.compute(_make_df(memory_findings=5), _TOTAL_LOC)
        assert result.by_category["modernization"] == pytest.approx(100.0)

    def test_profiles_expose_weights_and_caps(self) -> None:
        """Every profile entry is (column, weight, cap) with positive values."""
        for profile in PROFILES.values():
            for column, weight, cap in profile.values():
                assert column.endswith("_findings")
                assert weight > 0
                assert cap > 0
