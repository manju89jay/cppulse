"""Unavailable file rankings stay explicit without invented numeric clean ranks."""

from __future__ import annotations

from copy import deepcopy

import pytest

from cppulse.compatibility import export_legacy_risk_scores, read_risk_scores
from cppulse.contracts import validate, validate_bundle
from cppulse.errors import CompatibilityError, ContractError
from tests.test_compatibility_v2 import legacy_risk
from tests.test_contracts_v2 import manifest_document, risk_document


def unavailable_file() -> dict:
    """Return a partial file that has no experimental rank."""
    return {
        "file": "include/cpp20.h",
        "availability": "partial",
        "reason_codes": ["partial_analysis"],
        "reasons": ["Native parsing reported 20 errors in the selected context."],
    }


def scoped_risk() -> dict:
    """Keep a complete rank and a distinct explicitly unavailable file."""
    result = risk_document()
    result["unranked_files"] = [unavailable_file()]
    result["metadata"]["ranking_scope"] = {
        "version": "file-eligibility-1",
        "declared_files": 2,
        "ranked_files": 1,
        "unranked_files": 1,
    }
    return result


def test_explicit_unranked_file_has_no_score_and_preserves_old_rank() -> None:
    result = scoped_risk()
    validate("risk_scores", result)
    assert read_risk_scores(result) == result
    assert result["file_risks"][0]["score"] == 0.2
    assert "score" not in result["unranked_files"][0]


@pytest.mark.parametrize("channel", ["v2", "prototype_v1"])
@pytest.mark.parametrize(
    "mutation",
    [
        "numeric_score",
        "low_label",
        "no_reason",
        "no_reason_code",
        "duplicate",
        "ranked_and_unranked",
        "unsafe_path",
        "wrong_total",
        "wrong_ranked_count",
        "wrong_unranked_count",
        "no_scope",
    ],
)
def test_unranked_inventory_cannot_hide_or_contradict_a_rank(
    mutation: str, channel: str
) -> None:
    result = scoped_risk()
    if channel == "prototype_v1":
        original = legacy_risk()
        original["metadata"]["ranking_scope"] = result["metadata"]["ranking_scope"]
        original["unranked_files"] = result["unranked_files"]
        result = original
    entry = result["unranked_files"][0]
    if mutation == "numeric_score":
        entry["score"] = 0.0
    elif mutation == "low_label":
        entry["risk_level"] = "low"
    elif mutation == "no_reason":
        entry["reasons"] = []
    elif mutation == "no_reason_code":
        entry["reason_codes"] = []
    elif mutation == "duplicate":
        result["unranked_files"].append(deepcopy(entry))
    elif mutation == "ranked_and_unranked":
        entry["file"] = result["file_risks"][0]["file"]
    elif mutation == "unsafe_path":
        entry["file"] = "../outside.h"
    elif mutation == "wrong_total":
        result["metadata"]["ranking_scope"]["declared_files"] = 1
    elif mutation == "wrong_ranked_count":
        result["metadata"]["ranking_scope"]["ranked_files"] = 0
    elif mutation == "wrong_unranked_count":
        result["metadata"]["ranking_scope"]["unranked_files"] = 0
    else:
        del result["metadata"]["ranking_scope"]
    with pytest.raises(ContractError):
        validate("risk_scores", result, version=channel if channel != "v2" else None)


def test_prototype_migration_preserves_explicit_unavailable_scope() -> None:
    original = legacy_risk()
    original["unranked_files"] = [unavailable_file()]
    original["metadata"]["ranking_scope"] = scoped_risk()["metadata"]["ranking_scope"]
    validate("risk_scores", original, version="prototype_v1")
    result = read_risk_scores(original, allow_prototype_v1=True)
    assert result["unranked_files"] == original["unranked_files"]
    assert result["metadata"]["ranking_scope"] == original["metadata"]["ranking_scope"]
    assert result["file_risks"][0]["score"] == 0.2


def test_previous_v2_without_inventory_remains_readable() -> None:
    original = risk_document()
    validate("risk_scores", original)
    assert read_risk_scores(original) == original


def test_original_legacy_schema_is_not_redefined_by_new_availability() -> None:
    original = legacy_risk()
    original["file_risks"][0]["bug_probability"] = None
    with pytest.raises(ContractError):
        read_risk_scores(original)


def test_prototype_migration_preserves_scope_with_no_unranked_files() -> None:
    original = legacy_risk()
    original["metadata"]["ranking_scope"] = {
        "version": "file-eligibility-1",
        "declared_files": 1,
        "ranked_files": 1,
        "unranked_files": 0,
    }
    result = read_risk_scores(original, allow_prototype_v1=True)
    assert result["metadata"]["ranking_scope"] == original["metadata"]["ranking_scope"]


def test_unranked_files_are_bound_to_the_bundle_source_inventory() -> None:
    result = scoped_risk()
    with pytest.raises(ContractError, match="source inventory"):
        validate_bundle({"run_manifest": manifest_document(), "risk_scores": result})


def test_prototype_availability_is_not_silently_exported_as_original_legacy() -> None:
    original = legacy_risk()
    original["unranked_files"] = [unavailable_file()]
    original["metadata"]["ranking_scope"] = scoped_risk()["metadata"]["ranking_scope"]
    with pytest.raises(CompatibilityError, match="availability"):
        export_legacy_risk_scores(original)


def test_prototype_availability_requires_the_explicit_prototype_reader() -> None:
    original = legacy_risk()
    original["unranked_files"] = [unavailable_file()]
    original["metadata"]["ranking_scope"] = scoped_risk()["metadata"]["ranking_scope"]
    with pytest.raises(ContractError, match="prototype"):
        read_risk_scores(original)
