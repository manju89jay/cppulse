"""Measured snapshot comparison must break at method/context/scope changes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from cppulse.identities import digest_json
from cppulse.maintenance import (
    compare_maintenance_snapshots,
    compute_maintenance_health,
    measured_hotspots,
    measured_roadmap,
)
from tests.test_measured_maintenance import inputs


def snapshot() -> dict[str, Any]:
    data = inputs()
    return {
        "health": compute_maintenance_health(**data),
        "metrics": data["metrics"],
        "observations": data["observations"],
        "inventories": data["inventories"],
    }


def test_comparable_same_method_retains_raw_delta_and_metric_evidence() -> None:
    before = snapshot()
    after = deepcopy(before)
    assert compare_maintenance_snapshots(before, after)["comparable"]
    assert compare_maintenance_snapshots(before, after)["overall_delta"] == 0


def test_changed_method_does_not_silently_rebaseline_history() -> None:
    before = snapshot()
    after = deepcopy(before)
    after["health"]["scorer"]["allow_inferred_parse"] = True
    after["health"]["scorer"]["configuration_digest"] = digest_json(
        {
            key: value
            for key, value in after["health"]["scorer"].items()
            if key != "configuration_digest"
        }
    )
    result = compare_maintenance_snapshots(before, after)
    assert not result["comparable"]
    assert result["overall_delta"] is None
    assert result["limitations"]


def test_changed_required_context_or_source_scope_breaks_trend() -> None:
    for mutation in ["context", "scope"]:
        before = snapshot()
        after = deepcopy(before)
        if mutation == "context":
            after["health"]["required_context_ids"].append("another-consumer")
        else:
            after["inventories"][0]["items"][0]["file"] = "different.cpp"
        result = compare_maintenance_snapshots(before, after)
        assert not result["comparable"]
        assert result["overall_delta"] is None


def test_missing_measurement_is_a_gap_not_a_zero_delta() -> None:
    before = snapshot()
    after = deepcopy(before)
    after["metrics"][0]["items"][0].update(
        value=None, availability="unavailable", limitations=["Missing"]
    )
    result = compare_maintenance_snapshots(before, after)
    physical = next(row for row in result["metrics"] if row["metric"] == "physical_loc")
    assert physical["delta"] is None
    assert physical["availability"] == "unavailable"


def test_hotspot_requires_measured_complexity_not_severity() -> None:
    data = inputs()
    history = {"file_metrics": [{"file": "src/main.cpp", "change_frequency": 10}]}
    result = measured_hotspots(
        metrics=data["metrics"],
        observations=data["observations"],
        registry=data["registry"],
        git_metrics=history,
        job_context_id="native",
    )
    assert result["items"] == []
    assert result["unavailable_files"][0]["file"] == "src/main.cpp"


def test_hotspot_formula_and_roadmap_links_reproduce_measured_inputs() -> None:
    data = inputs()
    document = data["metrics"][0]
    document["items"][2]["value"] = 1
    metric = deepcopy(document["items"][0])
    metric.update(
        id="cx-f",
        symbol="c:@F@f#",
        metric="cyclomatic_complexity",
        units="count",
        value=4,
        location={"line": 1, "column": 1, "end_line": 10, "end_column": 1},
    )
    document["items"].append(metric)
    history = {"file_metrics": [{"file": "src/main.cpp", "change_frequency": 10}]}
    result = measured_hotspots(
        metrics=data["metrics"],
        observations=data["observations"],
        registry=data["registry"],
        git_metrics=history,
        job_context_id="native",
    )
    item = result["items"][0]
    assert item["complexity_score"] == 4
    assert item["hotspot_score"] == 320
    assert item["metric_ids"] and item["observation_ids"]
    roadmap = measured_roadmap(
        observations=data["observations"], registry=data["registry"], hotspots=result
    )
    assert roadmap["items"]
    assert all(row["effort_basis"] == "heuristic_estimate" for row in roadmap["items"])
    assert all(row["observation_ids"] for row in roadmap["items"])


def test_changed_effective_parse_context_breaks_comparison() -> None:
    before = snapshot()
    after = deepcopy(before)
    after["inventories"][0]["items"][0][
        "parse_context_id"
    ] = "different-compiler-or-macros"
    result = compare_maintenance_snapshots(before, after)
    assert not result["comparable"]
    assert result["overall_delta"] is None
    assert result["limitations"]
