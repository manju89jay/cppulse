"""Public predictor component integration; literal fixtures do not attest native execution."""

from copy import deepcopy

import pandas as pd

from cppulse.compatibility import read_risk_scores
from cppulse.contracts import validate
from cppulse.git_miner.behavior import analyze_behavior
from cppulse.predictor.feature_engineer import FeatureEngineer
from cppulse.predictor.health_scorer import HealthScorer
from cppulse.predictor.main import build_risk_scores
from cppulse.predictor.model import BugPredictor
from test_git_behavior import CUTOFF, config, record
from tests.test_maintenance_metrics_contract import native_metric_report


def test_public_build_and_normalization_preserve_component_priority() -> None:
    findings = deepcopy(native_metric_report())
    findings["findings"] = [{
        "file": "a.cpp", "rule_id": "CPP-MOD-001", "category": "modernization",
        "severity": "warning", "line": 1, "column": 1, "message": "Declared fixture",
    }]
    findings["summary"] = {
        "total_findings": 1, "by_category": {"modernization": 1},
        "by_severity": {"warning": 1},
    }
    findings["metadata"]["analysis"]["native_metrics"]["files"][0]["source_content_sha256"] = "a" * 64
    history = {
        "version": "1.0.0",
        "metadata": {"repo_path": "/repo", "history_status": "available", "total_commits": 2},
        "file_metrics": [{"file": "a.cpp", "change_frequency": 2,
                          "unique_contributors": 1, "age_days": 1, "lines_of_code": 9999}],
        "knowledge_silos": [],
    }
    frame = FeatureEngineer().build_features(findings, history)
    predictor = BugPredictor()
    predictor.train(frame, pd.Series([0]))
    behavior = analyze_behavior(
        [record(1), record(2)], ["a.cpp"], config(components={"api": ["a.cpp"]}),
        cutoff=CUTOFF, head="a" * 40,
    )
    result = build_risk_scores(
        frame, predictor.predict(frame), predictor, HealthScorer(), behavior=behavior
    )
    validate("risk_scores", result, version="prototype_v1")
    row = result["component_hotspots"]["components"][0]
    assert row["id"] == "api" and row["files"] == ["a.cpp"]
    assert row["availability"] == "available"
    assert row["score"] == result["hotspots"][0]["hotspot_score"] > 0
    converted = read_risk_scores(result, allow_prototype_v1=True)
    assert converted["component_hotspots"] == result["component_hotspots"]


def test_feature_exclusion_is_explicit_without_changing_attempted_denominator() -> None:
    findings = deepcopy(native_metric_report())
    del findings["metadata"]["analysis"]["native_metrics"]
    findings["metadata"]["file_count"] = 2
    findings["metadata"]["analysis"]["files"].append({
        "path": "/repo/b.cpp", "status": "excluded", "compile_context": "database",
        "error_count": 0,
    })
    history = {
        "version": "1.0.0", "metadata": {"repo_path": "/repo", "history_status": "available", "total_commits": 2},
        "file_metrics": [{"file": name, "change_frequency": 2, "unique_contributors": 1,
                          "age_days": 1, "lines_of_code": 10} for name in ["a.cpp", "b.cpp"]],
        "knowledge_silos": [],
    }
    frame = FeatureEngineer().build_features(findings, history)
    assert list(frame["file"]) == ["a.cpp"]
    assert set(frame.attrs["rank_availability"]) == {"a.cpp"}
    assert frame.attrs["component_excluded_files"] == ["b.cpp"]
    predictor = BugPredictor()
    predictor.train(frame, pd.Series([0]))
    behavior = analyze_behavior(
        [record(1, files=("a.cpp", "b.cpp"))], ["a.cpp", "b.cpp"],
        config(components={"api": ["*.cpp"]}), cutoff=CUTOFF,
    )
    risk = build_risk_scores(
        frame, predictor.predict(frame), predictor, HealthScorer(), behavior=behavior
    )
    validate("risk_scores", risk, version="prototype_v1")
    assert risk["metadata"]["ranking_scope"]["declared_files"] == 1
    assert risk["component_hotspots"]["excluded_files"] == ["b.cpp"]
    row = risk["component_hotspots"]["components"][0]
    assert row["files"] == ["a.cpp", "b.cpp"]
    assert row["score"] is row["observed_score"] is None
