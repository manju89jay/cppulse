"""Risk migration preserves observations without fabricating supported claims."""

from __future__ import annotations

import pytest

from cppulse.compatibility import (
    export_legacy_risk_scores,
    read_prototype_document,
    read_risk_scores,
)
from cppulse.contracts import validate
from cppulse.errors import CompatibilityError, ContractError, UnsupportedVersion


def legacy_risk() -> dict:
    """Return a structurally valid original v1 fixture, not claimed execution."""
    return {
        "version": "1.0.0",
        "metadata": {
            "generated_at": "2026-11-13T10:00:00Z",
            "model_type": "xgboost",
            "feature_count": 10,
            "training_samples": 60,
            "f1_score": 0.8,
        },
        "health_score": {"overall": 95, "by_category": {"modernization": 90}},
        "file_risks": [
            {
                "file": "src/a.cpp",
                "bug_probability": 0.2,
                "risk_level": "low",
                "top_factors": [],
            }
        ],
        "hotspots": [],
    }


def test_original_legacy_claims_become_unverified_ranks() -> None:
    original = legacy_risk()
    result = read_risk_scores(original)
    assert result["version"] == "2.0.0"
    assert result["metadata"]["method"] == "legacy_claim_unverified"
    assert result["metadata"]["evaluation_status"] == "not_evaluated"
    assert result["metadata"]["f1_score"] is None
    assert result["metadata"]["feature_count"] is None
    assert result["health_score"]["overall"] is None
    assert result["health_score"]["availability"] == "unverified"
    assert result["legacy_observed_health"] == 95
    assert result["file_risks"][0]["score"] == 0.2
    assert "bug_probability" not in result["file_risks"][0]
    assert original == legacy_risk()
    validate("risk_scores", result)


def test_prototype_extension_requires_explicit_reader() -> None:
    original = legacy_risk()
    original["metadata"].update(
        {
            "model_type": "heuristic",
            "evaluation_status": "not_evaluated",
            "active_features": ["memory_findings"],
            "feature_count": 1,
            "f1_score": None,
        }
    )
    original["health_score"].update(
        {"overall": None, "status": "partial", "by_category": {"modernization": None}}
    )
    with pytest.raises(ContractError):
        read_risk_scores(original)
    result = read_risk_scores(original, allow_prototype_v1=True)
    assert result["metadata"]["method"] == "heuristic"
    assert result["metadata"]["score_kind"] == "heuristic_rank"
    assert result["metadata"]["active_features"] == ["memory_findings"]
    assert result["metadata"]["feature_count"] == 1
    assert result["health_score"]["availability"] == "partial"
    assert read_prototype_document("risk_scores", original) == original


def test_v2_round_trip_and_copy_isolation() -> None:
    result = read_risk_scores(legacy_risk())
    other = read_risk_scores(result)
    assert result == other and result is not other
    other["file_risks"].clear()
    assert result["file_risks"]


def test_new_major_is_actionable_not_best_effort() -> None:
    document = legacy_risk()
    document["version"] = "3.0.0"
    with pytest.raises(UnsupportedVersion):
        read_risk_scores(document)


def test_unrepresentable_legacy_export_is_explicit() -> None:
    result = read_risk_scores(legacy_risk())
    with pytest.raises(CompatibilityError) as caught:
        export_legacy_risk_scores(result)
    assert caught.value.code == "LEGACY_EXPORT_NOT_REPRESENTABLE"


def test_original_v1_round_trip_is_retained_without_rewrite() -> None:
    original = legacy_risk()
    assert export_legacy_risk_scores(original) == original
    original["health_score"]["overall"] = None
    with pytest.raises(ContractError):
        export_legacy_risk_scores(original)


def test_bad_original_v1_does_not_sneak_through_migration() -> None:
    original = legacy_risk()
    original["metadata"]["model_type"] = "invented"
    with pytest.raises(ContractError):
        read_risk_scores(original)
