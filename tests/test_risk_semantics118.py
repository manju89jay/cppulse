"""Authored identity controls; these fixtures do not authenticate producers."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from cppulse.predictor.feature_engineer import FeatureEngineer
from cppulse.predictor.health_scorer import HealthScorer
from cppulse.predictor.main import build_risk_scores
from cppulse.predictor.model import BugPredictor


def inputs(
    findings_root: str | None, history_root: str | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """One observed clean file and explicitly declared available Git history."""
    findings = {
        "metadata": {
            "analysis": {
                "enabled_rules": ["CPP-MEM-001"],
                "files": [{"path": "a.cpp", "status": "analyzed", "error_count": 0}],
            }
        },
        "findings": [],
    }
    history = {
        "metadata": {"history_status": "available"},
        "file_metrics": [{"file": "a.cpp", "change_frequency": 3,
                          "unique_contributors": 2, "age_days": 30,
                          "lines_of_code": 10}],
    }
    if findings_root is not None:
        findings["metadata"]["repo_path"] = findings_root
    if history_root is not None:
        history["metadata"]["repo_path"] = history_root
    return findings, history


@pytest.mark.parametrize("roots", [
    ("/repo", "/repo"), ("/repo/", "/repo//."),
    ("C:\\repo\\", "c:/repo/"),
    ("//server/share/repo", "\\\\server\\share\\repo\\"),
])
def test_consistent_lexical_roots_preserve_observed_join(roots: tuple[str, str]) -> None:
    frame = FeatureEngineer().build_features(*inputs(*roots))
    assert frame.iloc[0]["file"] == "a.cpp"
    assert frame.iloc[0]["change_frequency"] == 3
    assert frame.attrs["rank_availability"]["a.cpp"].eligible


@pytest.mark.parametrize("roots", [
    ("/repo-A", "/repo-B"), ("/repo", "repo"),
    ("C:/repo", "D:/repo"), ("/repo", "C:/repo"),
])
def test_conflicting_origins_cannot_borrow_same_relative_file_history(
    roots: tuple[str, str],
) -> None:
    with pytest.raises(ValueError, match="conflicting repository roots"):
        FeatureEngineer().build_features(*inputs(*roots))


def test_empty_history_cannot_constrain_independent_static_features() -> None:
    findings, history = inputs("/repo-A", "/unrelated-empty-history")
    history["file_metrics"] = []
    frame = FeatureEngineer().build_features(findings, history)
    assert frame["file"].tolist() == ["a.cpp"]
    assert not frame.attrs["rank_availability"]["a.cpp"].eligible
    assert "missing_file_history" in frame.attrs["rank_availability"]["a.cpp"].reason_codes


@pytest.mark.parametrize("roots", [(None, "/repo"), ("/repo", None), (None, None)])
def test_missing_identity_keeps_public_ranking_unverified(
    roots: tuple[str | None, str | None],
) -> None:
    frame = FeatureEngineer().build_features(*inputs(*roots))
    availability = frame.attrs["rank_availability"]["a.cpp"]
    assert not availability.eligible
    assert "missing_repository_identity" in availability.reason_codes
    model = BugPredictor()
    model.train(frame, pd.Series([0], dtype=int))
    result = build_risk_scores(frame, np.array([0.0]), model, HealthScorer())
    assert result["file_risks"] == []
    assert result["health_score"]["overall"] is None
    assert result["unranked_files"][0]["file"] == "a.cpp"
    assert "missing_repository_identity" in result["unranked_files"][0]["reason_codes"]
