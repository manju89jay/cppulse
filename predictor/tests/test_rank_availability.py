"""Per-file ranking requires observed analysis and usable history inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import jsonschema

from src.feature_engineer import FeatureEngineer
from src.health_scorer import HealthScorer
from src.main import build_risk_scores, run
from src.model import BugPredictor
from src.schema_validator import SchemaValidator


def scoped_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    """Declare complete, partial, skipped and intentionally excluded files."""
    files = [
        ("clean.cpp", "analyzed", 0),
        ("partial.hpp", "partial", 20),
        ("large.hpp", "skipped", 0),
        ("vendor.hpp", "excluded", 0),
    ]
    findings = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/repo",
            "analyzed_at": "2026-11-14T10:00:00Z",
            "file_count": 2,
            "total_loc": 20,
            "analysis": {
                "enabled_rules": ["CPP-MEM-001"],
                "files": [
                    {
                        "path": "/repo/" + file,
                        "status": status,
                        "error_count": errors,
                        "compile_context": (
                            "inferred" if status in {"analyzed", "partial"} else "none"
                        ),
                    }
                    for file, status, errors in files
                ],
            },
        },
        "findings": [
            {
                "file": "partial.hpp",
                "rule_id": "CPP-MEM-001",
                "category": "memory_safety",
                "severity": "error",
                "line": 1,
                "message": "An observed pattern survives incomplete parsing.",
            }
        ],
        "summary": {
            "total_findings": 1,
            "by_category": {"memory_safety": 1},
            "by_severity": {"error": 1},
        },
    }
    history = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/repo",
            "analyzed_at": "2026-11-14T10:00:00Z",
            "commit_range": "first..last",
            "total_commits": 3,
            "history_status": "available",
            "limitations": [],
        },
        "file_metrics": [
            {
                "file": file,
                "change_frequency": 3,
                "unique_contributors": 2,
                "age_days": 30,
                "lines_of_code": 10,
            }
            for file, _, _ in files
        ],
        "knowledge_silos": [],
    }
    return findings, history


def build(findings: dict, history: dict, scores: list[float] | None = None) -> dict:
    """Build actual predictor output from a declared scope."""
    features = FeatureEngineer().build_features(findings, history)
    model = BugPredictor()
    model.train(features, pd.Series([0] * len(features), dtype=int))
    probabilities = model.predict(features) if scores is None else np.array(scores)
    return build_risk_scores(features, probabilities, model, HealthScorer())


def test_partial_and_skipped_files_never_receive_numeric_low_rank() -> None:
    findings, history = scoped_inputs()
    result = build(findings, history)
    assert [entry["file"] for entry in result["file_risks"]] == ["clean.cpp"]
    assert result["file_risks"][0]["bug_probability"] == 0.0
    assert result["file_risks"][0]["risk_level"] == "low"
    unranked = {entry["file"]: entry for entry in result["unranked_files"]}
    assert set(unranked) == {"partial.hpp", "large.hpp"}
    assert "partial_analysis" in unranked["partial.hpp"]["reason_codes"]
    assert "20" in " ".join(unranked["partial.hpp"]["reasons"])
    assert all(
        "bug_probability" not in entry and "risk_level" not in entry
        for entry in unranked.values()
    )
    assert result["metadata"]["ranking_scope"] == {
        "version": "file-eligibility-1",
        "declared_files": 3,
        "ranked_files": 1,
        "unranked_files": 2,
    }
    assert result["health_score"]["overall"] is None
    assert result["hotspots"] == []


@pytest.mark.parametrize("history_status", ["unavailable", "partial", None])
def test_missing_or_partial_history_is_unavailable_not_zero_history(
    history_status: str | None,
) -> None:
    findings, history = scoped_inputs()
    if history_status is None:
        del history["metadata"]["history_status"]
    else:
        history["metadata"]["history_status"] = history_status
    result = build(findings, history)
    assert result["file_risks"] == []
    assert result["hotspots"] == []
    clean = next(
        entry for entry in result["unranked_files"] if entry["file"] == "clean.cpp"
    )
    assert any(
        code in clean["reason_codes"]
        for code in ["partial_history", "missing_history", "unverified_history"]
    )


def test_file_without_history_does_not_inherit_zero_filled_rank() -> None:
    findings, history = scoped_inputs()
    history["file_metrics"] = [
        row for row in history["file_metrics"] if row["file"] != "clean.cpp"
    ]
    result = build(findings, history)
    assert result["file_risks"] == []
    clean = next(
        entry for entry in result["unranked_files"] if entry["file"] == "clean.cpp"
    )
    assert "missing_file_history" in clean["reason_codes"]


def test_missing_parse_inventory_is_explicitly_unverified() -> None:
    findings, history = scoped_inputs()
    del findings["metadata"]["analysis"]
    result = build(findings, history)
    assert result["file_risks"] == []
    assert all(
        "missing_parse_inventory" in row["reason_codes"]
        for row in result["unranked_files"]
    )


def test_no_enabled_detectors_cannot_produce_a_clean_rank() -> None:
    findings, history = scoped_inputs()
    findings["metadata"]["analysis"]["enabled_rules"] = []
    result = build(findings, history)
    assert result["file_risks"] == []
    assert all(
        "no_enabled_detectors" in row["reason_codes"]
        for row in result["unranked_files"]
    )


def test_missing_or_nonfinite_prediction_is_explicitly_unavailable() -> None:
    findings, history = scoped_inputs()
    for scores in [[], [float("nan"), 0.0]]:
        result = build(findings, history, scores)
        assert result["file_risks"] == []
        clean = next(
            entry for entry in result["unranked_files"] if entry["file"] == "clean.cpp"
        )
        assert "unavailable_model_output" in clean["reason_codes"]


def test_run_trains_only_on_eligible_observations(
    tmp_path: Path, monkeypatch: Any
) -> None:
    findings, history = scoped_inputs()
    for name, data in [("findings", findings), ("git_metrics", history)]:
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    trained_files: list[list[str]] = []
    original = BugPredictor.train

    def observe(self: BugPredictor, features: pd.DataFrame, labels: pd.Series) -> Any:
        trained_files.append(features["file"].tolist())
        return original(self, features, labels)

    monkeypatch.setattr(BugPredictor, "train", observe)
    run(tmp_path, tmp_path)
    assert trained_files == [["clean.cpp"]]
    result = json.loads((tmp_path / "risk_scores.json").read_text())
    assert [row["file"] for row in result["file_risks"]] == ["clean.cpp"]


def test_component_validator_rejects_misleading_scope_counts() -> None:
    findings, history = scoped_inputs()
    result = build(findings, history)
    result["metadata"]["ranking_scope"]["unranked_files"] = 0
    with pytest.raises(jsonschema.ValidationError, match="scope count"):
        SchemaValidator().validate_risk_scores(result)


@pytest.mark.parametrize("skipped", [False, True])
def test_run_with_no_feature_rows_preserves_unavailable_scope(
    tmp_path: Path, skipped: bool
) -> None:
    findings, history = scoped_inputs()
    findings["findings"] = []
    findings["summary"] = {"total_findings": 0, "by_category": {}, "by_severity": {}}
    findings["metadata"]["file_count"] = 0
    findings["metadata"]["total_loc"] = 0
    findings["metadata"]["analysis"]["files"] = (
        [
            {
                "path": "/repo/large.hpp",
                "status": "skipped",
                "error_count": 0,
                "compile_context": "none",
            }
        ]
        if skipped
        else []
    )
    for name, data in [("findings", findings), ("git_metrics", history)]:
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    run(tmp_path, tmp_path)
    result = json.loads((tmp_path / "risk_scores.json").read_text())
    assert result["file_risks"] == []
    assert result["hotspots"] == []
    assert result["health_score"]["overall"] is None
    assert result["health_score"]["status"] == ("partial" if skipped else "no_data")
    assert len(result["unranked_files"]) == int(skipped)
    assert result["metadata"]["ranking_scope"]["declared_files"] == int(skipped)
