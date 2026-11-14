"""Regressions for legacy identities and truthful result metadata."""

from pathlib import Path

import numpy as np
import pandas as pd
from src.feature_engineer import FeatureEngineer
from src.health_scorer import HealthScorer
from src.main import build_risk_scores, parse_args
from src.model import BugPredictor


def test_absolute_findings_join_relative_history() -> None:
    """Static and history signals must describe the same file."""
    features = FeatureEngineer().build_features(
        {
            "metadata": {"repo_path": "/repo"},
            "findings": [{"file": "/repo/src/a.cpp", "category": "memory_safety"}],
        },
        {"file_metrics": [{"file": "src/a.cpp", "change_frequency": 3}]},
    )
    assert len(features) == 1
    assert features.iloc[0]["file"] == "src/a.cpp"
    assert features.iloc[0]["change_frequency"] == 3
    assert features.iloc[0]["finding_count"] == 1


def test_empty_output_is_unscored_heuristic() -> None:
    """No files cannot imply perfect health or a trained model."""
    features = FeatureEngineer().build_features({}, {})
    model = BugPredictor()
    model.train(features, pd.Series(dtype=int))
    result = build_risk_scores(features, np.array([]), model, HealthScorer())
    assert result["health_score"]["overall"] is None
    assert result["health_score"]["status"] == "no_data"
    assert result["metadata"]["model_type"] == "heuristic"
    assert result["metadata"]["experimental"] is True
    assert result["metadata"]["feature_count"] == 5
    assert set(result["metadata"]["active_features"]) == {
        "memory_findings",
        "complexity_findings",
        "modernization_findings",
        "churn_rate",
        "bug_fix_commits",
    }
    assert result["hotspots"] == []


def test_explicit_default_is_distinct_from_omitted_profile() -> None:
    """Explicit default overrides a config profile."""
    assert parse_args(["--input", "."]).profile is None
    assert parse_args(["--input", ".", "--profile", "default"]).profile == "default"


def test_run_writes_valid_profile_specific_outputs(tmp_path: Path) -> None:
    """Exercise schema inputs, training fallback, roadmap and result serialization."""
    import json
    from tests.test_feature_engineer import SAMPLE_FINDINGS, SAMPLE_GIT_METRICS
    from src.main import run

    for name, data in [
        ("findings", SAMPLE_FINDINGS),
        ("git_metrics", SAMPLE_GIT_METRICS),
    ]:
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    for profile in ["default", "safety-critical"]:
        output = tmp_path / profile
        run(tmp_path, output, profile)
        result = json.loads((output / "risk_scores.json").read_text())
        roadmap = json.loads((output / "roadmap.json").read_text())
        assert result["metadata"]["profile"] == profile
        assert result["metadata"]["f1_score"] is None
        assert result["file_risks"]
        assert all(item["hotspot_score"] > 0 for item in result["hotspots"])
        assert roadmap["items"]
        assert (
            all(item["category"] != "misra" for item in roadmap["items"])
            if profile == "default"
            else any(item["category"] == "misra" for item in roadmap["items"])
        )
