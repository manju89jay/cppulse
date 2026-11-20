"""Public legacy-compatible reports must never call severity measured complexity."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pandas as pd

from cppulse.predictor.feature_engineer import FeatureEngineer
from cppulse.predictor.health_scorer import HealthScorer
from cppulse.predictor.main import build_risk_scores
from cppulse.predictor.model import BugPredictor
from tests.test_maintenance_metrics_contract import native_metric_report


def output(
    *, measured: bool = True, severity: str = "warning", no_functions: bool = False
) -> dict[str, Any]:
    """Use declared synthetic native facts; actual executable validation is separate."""
    findings = deepcopy(native_metric_report())
    findings["findings"] = [
        {
            "file": "a.cpp",
            "rule_id": "CPP-MOD-001",
            "category": "modernization",
            "severity": severity,
            "line": 1,
            "column": 1,
            "message": "Synthetic cast fixture",
        }
    ]
    findings["summary"] = {
        "total_findings": 1,
        "by_category": {"modernization": 1},
        "by_severity": {severity: 1},
    }
    raw = findings["metadata"]["analysis"]["native_metrics"]["files"][0]
    raw["source_content_sha256"] = "a" * 64
    raw["functions"][0]["cyclomatic_complexity"] = 4
    if no_functions:
        raw["function_count"] = 0
        raw["functions"] = []
    if not measured:
        del findings["metadata"]["analysis"]["native_metrics"]
    history = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/repo",
            "history_status": "available",
            "total_commits": 2,
        },
        "file_metrics": [
            {
                "file": "a.cpp",
                "change_frequency": 2,
                "unique_contributors": 1,
                "age_days": 1,
                "lines_of_code": 9999,
            }
        ],
        "knowledge_silos": [],
    }
    frame = FeatureEngineer().build_features(findings, history)
    predictor = BugPredictor()
    predictor.train(frame, pd.Series([0]))
    return build_risk_scores(frame, predictor.predict(frame), predictor, HealthScorer())


def test_absent_metrics_never_get_severity_as_complexity() -> None:
    result = output(measured=False, severity="error")
    assert result["file_risks"]  # descriptive ranking availability is separate
    assert result["hotspots"] == []
    assert (
        result["metadata"]["hotspot_scope"]["unavailable_files"][0]["file"] == "a.cpp"
    )


def test_actual_cc_and_physical_loc_replace_severity_and_git_loc() -> None:
    result = output()
    hotspot = result["hotspots"][0]
    assert hotspot["complexity_score"] == 4
    assert hotspot["physical_loc"] == 1
    assert hotspot["hotspot_score"] == 8000  # 2 changes * 4 CC * 1 finding / .001 KLOC
    assert result["metadata"]["hotspot_method"] == "measured-cc-physical-kloc-v1"


def test_severity_does_not_change_measured_hotspot_complexity_or_score() -> None:
    assert output(severity="error")["hotspots"] == output(severity="info")["hotspots"]


def test_known_no_function_scope_has_no_invented_complexity() -> None:
    result = output(no_functions=True)
    assert result["hotspots"] == []
    assert result["metadata"]["hotspot_scope"]["unavailable_files"]


def test_shared_formula_rejects_nonfinite_fractional_or_unbounded_counts() -> None:
    import pytest
    from cppulse.errors import ContractError
    from cppulse.maintenance import measured_hotspot_calculation

    for value in [True, -1, 0.5, float("nan"), float("inf"), 2**63]:
        with pytest.raises(ContractError):
            measured_hotspot_calculation(
                change_frequency=value, complexity=2, finding_count=1, physical_loc=1
            )
    for key in ("complexity", "physical_loc"):
        counts = dict(change_frequency=1, complexity=2, finding_count=1, physical_loc=1)
        counts[key] = 0
        with pytest.raises(ContractError):
            measured_hotspot_calculation(**counts)


def test_partial_or_unhashed_native_claim_cannot_supply_hotspot_metrics() -> None:
    from cppulse.predictor.measured_hotspots import native_hotspot_metrics

    report = deepcopy(native_metric_report())
    raw = report["metadata"]["analysis"]["native_metrics"]["files"][0]
    raw["source_content_sha256"] = "a" * 64
    assert native_hotspot_metrics(report)["a.cpp"]["complexity_score"] == 1
    raw["measurement_complete"] = False
    raw["function_count"] = None
    assert native_hotspot_metrics(report) == {}
    raw["measurement_complete"] = True
    raw["function_count"] = 1
    del raw["source_content_sha256"]
    assert native_hotspot_metrics(report) == {}
