"""Tests for label derivation in src/main.py and leakage guards."""

from __future__ import annotations

import pandas as pd

from src.main import _derive_labels
from src.model import NUMERIC_FEATURES


def _frame(**overrides: list) -> pd.DataFrame:
    """Build a 3-file feature frame with zero defaults and given overrides."""
    base: dict[str, list] = {
        "file": ["a.cpp", "b.cpp", "c.cpp"],
        "memory_findings": [0, 0, 0],
        "misra_findings": [0, 0, 0],
        "bug_fix_commits": [0, 0, 0],
        "szz_bug_introductions": [0, 0, 0],
    }
    base.update(overrides)
    frame = pd.DataFrame(base)
    if "szz_bug_introductions" not in overrides:
        # Match FeatureEngineer's distinction between convenience defaults and
        # raw SZZ observations. An explicitly supplied zero remains observed.
        frame.attrs["szz_observed_files"] = []
    return frame


class TestDeriveLabelsFromSZZ:
    """SZZ bug introductions are the primary label source."""

    def test_szz_counts_drive_labels(self) -> None:
        """Files with >= 1 SZZ bug introduction are labeled buggy."""
        df = _frame(szz_bug_introductions=[2, 0, 1])
        assert _derive_labels(df).tolist() == [1, 0, 1]

    def test_szz_labels_ignore_heuristic_columns(self) -> None:
        """With SZZ data present, memory findings and fix commits are ignored."""
        df = _frame(
            szz_bug_introductions=[1, 0, 0],
            memory_findings=[0, 5, 0],
            bug_fix_commits=[0, 0, 9],
        )
        assert _derive_labels(df).tolist() == [1, 0, 0]


class TestDeriveLabelsFallback:
    """Without SZZ data the legacy heuristic applies."""

    def test_fallback_uses_memory_and_fix_commits(self) -> None:
        """Absent SZZ observations use heuristics despite zero-filled defaults."""
        df = _frame(memory_findings=[1, 0, 0], bug_fix_commits=[0, 3, 2])
        assert _derive_labels(df).tolist() == [1, 1, 0]

    def test_fallback_safety_critical_includes_misra(self) -> None:
        """MISRA findings label files buggy on the safety-critical profile."""
        df = _frame(misra_findings=[0, 1, 0])
        assert _derive_labels(df, profile="safety-critical").tolist() == [0, 1, 0]


class TestLeakageGuards:
    """Label-adjacent columns must never be model features."""

    def test_label_sources_excluded_from_model_features(self) -> None:
        """bug_fix_commits and szz_bug_introductions are not trained on."""
        assert "bug_fix_commits" not in NUMERIC_FEATURES
        assert "szz_bug_introductions" not in NUMERIC_FEATURES
