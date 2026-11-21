"""Literal architectural priorities, complete scope, and meaningful unknowns."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import jsonschema
import pytest

from cppulse.component_hotspots import aggregate_component_hotspots
from cppulse.contracts import load_schema
from cppulse.contracts.component_hotspots import validate_component_hotspots
from cppulse.errors import ContractError
from cppulse.git_miner.behavior import analyze_behavior
from cppulse.identities import digest_json
from test_git_behavior import CUTOFF, config, record


def behavior(*, files: list[str] | None = None, **settings: Any) -> dict[str, Any]:
    """Declare real producer mapping/denominators, separate from hotspot math."""
    files = files if files is not None else ["a.cpp", "b.cpp", "zero.cpp"]
    cfg = config(components={"api": ["a.cpp", "b.cpp"]}, **settings)
    return analyze_behavior(
        [record(1, files=tuple(files), total_files=len(files))],
        files,
        cfg,
        cutoff=CUTOFF,
    )


def scores() -> list[dict[str, Any]]:
    """Hand-calculated priorities 120, 30 and a genuinely measured zero."""
    return [
        {
            "file": "a.cpp",
            "change_frequency": 3,
            "complexity_score": 2,
            "finding_count": 2,
            "physical_loc": 100,
            "debt_density": 20,
            "hotspot_score": 120,
        },
        {
            "file": "b.cpp",
            "change_frequency": 2,
            "complexity_score": 3,
            "finding_count": 1,
            "physical_loc": 200,
            "debt_density": 5,
            "hotspot_score": 30,
        },
        {
            "file": "zero.cpp",
            "change_frequency": 2,
            "complexity_score": 3,
            "finding_count": 0,
            "physical_loc": 200,
            "debt_density": 0,
            "hotspot_score": 0,
        },
    ]


def aggregate(report: dict[str, Any], values: list[dict[str, Any]]) -> dict[str, Any]:
    """Use the complete behavior file census as declared predictor scope."""
    return aggregate_component_hotspots(
        behavior=report,
        declared_files=[row["file"] for row in report["files"]],
        hotspot_scores=values,
    )


def test_complete_component_and_known_zero_have_exact_literal_priorities() -> None:
    report = behavior()
    original = deepcopy(report)
    inputs = scores()
    original_inputs = deepcopy(inputs)
    result = aggregate(report, inputs)
    rows = {row["id"]: row for row in result["components"]}
    assert rows["api"] == {
        "id": "api",
        "files": ["a.cpp", "b.cpp"],
        "measured_files": [
            {"file": "a.cpp", "score": 120},
            {"file": "b.cpp", "score": 30},
        ],
        "unavailable_files": [],
        "availability": "available",
        "score": 150,
        "observed_score": 150,
    }
    assert rows["__unassigned__"]["availability"] == "available"
    assert rows["__unassigned__"]["score"] == 0
    assert result["behavior_configuration_digest"] == report["configuration_digest"]
    assert result["behavior_input_digest"] == report["input_digest"]
    assert report == original and inputs == original_inputs
    jsonschema.validate(
        result, load_schema("risk_scores", "2.0.0")["properties"]["component_hotspots"]
    )
    validate_component_hotspots(
        {
            "component_hotspots": result,
            "file_risks": [{"file": name} for name in ["a.cpp", "b.cpp", "zero.cpp"]],
        }
    )
    assert any("static include/call" in text for text in result["limitations"])
    assert any("not producer authentication" in text for text in result["limitations"])


def test_missing_member_is_partial_without_complete_score_or_invented_zero() -> None:
    result = aggregate(behavior(), [scores()[0], scores()[2]])
    row = next(row for row in result["components"] if row["id"] == "api")
    assert row["availability"] == "partial"
    assert row["score"] is None and row["observed_score"] == 120
    assert row["unavailable_files"] == ["b.cpp"]
    assert aggregate(behavior(), [])["components"][0]["observed_score"] is None


def test_explicit_excluded_member_is_not_an_attempted_or_measured_file() -> None:
    result = aggregate_component_hotspots(
        behavior=behavior(),
        declared_files=["a.cpp", "zero.cpp"],
        excluded_files=["b.cpp"],
        hotspot_scores=[scores()[0], scores()[2]],
    )
    assert result["excluded_files"] == ["b.cpp"]
    row = next(row for row in result["components"] if row["id"] == "api")
    assert row["files"] == ["a.cpp", "b.cpp"]
    assert row["score"] is None and row["observed_score"] == 120
    assert row["availability"] == "partial" and row["unavailable_files"] == ["b.cpp"]
    validate_component_hotspots(
        {
            "component_hotspots": result,
            "file_risks": [{"file": "a.cpp"}, {"file": "zero.cpp"}],
        }
    )


@pytest.mark.parametrize(
    "excluded", [None, "b.cpp", ["b.cpp", "b.cpp"], ["a.cpp"], ["outside.cpp"]]
)
def test_invalid_excluded_inventory_cannot_expand_or_overlap_scope(
    excluded: Any,
) -> None:
    with pytest.raises(ContractError):
        aggregate_component_hotspots(
            behavior=behavior(),
            declared_files=["a.cpp", "zero.cpp"],
            excluded_files=excluded,
            hotspot_scores=[scores()[0], scores()[2]],
        )


def test_excluded_file_cannot_keep_its_former_measured_priority() -> None:
    with pytest.raises(ContractError):
        aggregate_component_hotspots(
            behavior=behavior(),
            declared_files=["a.cpp", "zero.cpp"],
            excluded_files=["b.cpp"],
            hotspot_scores=scores(),
        )


def test_all_excluded_architectural_members_have_no_attempted_score() -> None:
    result = aggregate_component_hotspots(
        behavior=behavior(),
        declared_files=[],
        excluded_files=["a.cpp", "b.cpp", "zero.cpp"],
        hotspot_scores=[],
    )
    assert all(row["availability"] == "unavailable" for row in result["components"])
    assert all(
        row["score"] is row["observed_score"] is None for row in result["components"]
    )
    validate_component_hotspots({"component_hotspots": result, "file_risks": []})


def test_partial_history_cannot_supply_complete_component_score() -> None:
    report = analyze_behavior(
        [record(1, files=("a.cpp", "b.cpp", "zero.cpp"))],
        ["a.cpp", "b.cpp", "zero.cpp"],
        config(components={"api": ["a.cpp", "b.cpp"]}),
        cutoff=CUTOFF,
        history_limitations=["Selected history was truncated by actual collection."],
    )
    result = aggregate(report, scores())
    assert result["history_status"] == "partial"
    row = next(row for row in result["components"] if row["id"] == "api")
    assert row["availability"] == "partial"
    assert row["score"] is None and row["observed_score"] == 150


def test_unavailable_history_retains_no_measured_claim_but_checks_supplied_rows() -> (
    None
):
    report = analyze_behavior(
        [],
        ["a.cpp", "b.cpp", "zero.cpp"],
        config(components={"api": ["a.cpp", "b.cpp"]}),
        cutoff=CUTOFF,
    )
    result = aggregate(report, scores())
    assert all(row["availability"] == "unavailable" for row in result["components"])
    assert all(
        row["score"] is row["observed_score"] is None and row["measured_files"] == []
        for row in result["components"]
    )
    forged = scores()
    forged[0]["hotspot_score"] = 121
    with pytest.raises(ContractError, match="calculation"):
        aggregate(report, forged)


def test_behavior_exclusions_do_not_silently_redefine_legacy_hotspot_activity() -> None:
    report = behavior(exclude_paths=["b.cpp"])
    assert (
        next(row for row in report["files"] if row["file"] == "b.cpp")["touches"] == 0
    )
    result = aggregate(report, scores())
    row = next(row for row in result["components"] if row["id"] == "api")
    assert row["score"] == 150
    assert any(
        "retained legacy history" in text and "exclusions" in text
        for text in result["limitations"]
    )


@pytest.mark.parametrize(
    "pair_limit,expected_score,expected_status,expected_drops",
    [(1000, 25, "available", 0), (100, None, "partial", 200)],
)
def test_all_twenty_five_measured_files_are_aggregated_before_display_limit(
    pair_limit: int,
    expected_score: int | None,
    expected_status: str,
    expected_drops: int,
) -> None:
    files = [f"src/f{number:02d}.cpp" for number in range(25)]
    report = analyze_behavior(
        [record(1, files=tuple(files), total_files=25)],
        files,
        config(
            components={"library": ["src/**"]},
            max_files_per_commit=30,
            max_pair_records=pair_limit,
        ),
        cutoff=CUTOFF,
    )
    values = [
        {
            "file": name,
            "change_frequency": 1,
            "complexity_score": 1,
            "finding_count": 1,
            "physical_loc": 1000,
            "debt_density": 1,
            "hotspot_score": 1,
        }
        for name in files
    ]
    result = aggregate(report, values)
    row = result["components"][0]
    assert report["counts"]["dropped_pair_updates"] == expected_drops
    assert row["score"] == expected_score and row["availability"] == expected_status
    assert row["observed_score"] == 25
    assert row["measured_files"][-1] == {"file": "src/f24.cpp", "score": 1}
    assert len(row["measured_files"]) == 25


@pytest.mark.parametrize(
    "field,value",
    [
        ("hotspot_score", 121),
        ("debt_density", 21),
        ("hotspot_score", True),
        ("hotspot_score", float("nan")),
        ("debt_density", float("inf")),
        ("hotspot_score", 10**400),
        ("hotspot_score", -1),
        ("change_frequency", -1),
        ("complexity_score", 0),
        ("physical_loc", 0),
        ("finding_count", True),
        ("finding_count", 0.5),
        ("complexity_score", float("inf")),
        ("physical_loc", "100"),
    ],
)
def test_invalid_counts_and_forged_or_nonfinite_calculations_reject(
    field: str,
    value: Any,
) -> None:
    values = scores()
    values[0][field] = value
    with pytest.raises(ContractError):
        aggregate(behavior(), values)


@pytest.mark.parametrize(
    "change", ["duplicate", "outside", "unsafe", "missing", "nondict"]
)
def test_invalid_score_inventory_never_becomes_a_component_result(change: str) -> None:
    values = scores()
    if change == "duplicate":
        values.append(dict(values[0]))
    elif change in {"outside", "unsafe"}:
        values[0]["file"] = "outside.cpp" if change == "outside" else "../a.cpp"
    elif change == "missing":
        del values[0]["physical_loc"]
    else:
        values.append(None)
    with pytest.raises(ContractError):
        aggregate(behavior(), values)


def test_measured_zero_cannot_be_inflated_by_absolute_comparison_tolerance() -> None:
    values = scores()
    values[2]["hotspot_score"] = 1e-15
    with pytest.raises(ContractError, match="calculation"):
        aggregate(behavior(), values)


@pytest.mark.parametrize(
    "files",
    [
        ["a.cpp", "b.cpp"],
        ["a.cpp", "b.cpp", "zero.cpp", "a.cpp"],
        ["a.cpp", "b.cpp", "zero.cpp", "outside.cpp"],
        "a.cpp",
        [None],
    ],
)
def test_declared_and_component_mapping_scope_must_match_exactly(files: Any) -> None:
    with pytest.raises(ContractError):
        aggregate_component_hotspots(
            behavior=behavior(), declared_files=files, hotspot_scores=scores()
        )


def test_overlapping_mapping_or_forged_component_membership_is_rejected() -> None:
    report = behavior()
    report["configuration"]["components"]["overlap"] = ["a.cpp"]
    report["configuration_digest"] = digest_json(report["configuration"])
    with pytest.raises(ContractError, match="Ambiguous"):
        aggregate(report, scores())
    report = behavior()
    report["components"][0]["files"].append("outside.cpp")
    with pytest.raises(ContractError, match="membership"):
        aggregate(report, scores())
