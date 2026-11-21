"""Component priorities retain scope and unknowns across public risk readers."""

from copy import deepcopy

import pytest

from cppulse.compatibility import export_legacy_risk_scores, read_risk_scores
from cppulse.contracts import validate
from cppulse.errors import CompatibilityError, ContractError
from test_compatibility_v2 import legacy_risk


def component_priority() -> dict:
    return {
        "version": "1.0.0",
        "method": "sum-measured-file-hotspots-v1",
        "file_method": "measured-cc-physical-kloc-v1",
        "behavior_configuration_digest": "a" * 64,
        "behavior_input_digest": "b" * 64,
        "history_status": "available",
        "components": [
            {
                "id": "api",
                "files": ["src/a.cpp"],
                "measured_files": [{"file": "src/a.cpp", "score": 0}],
                "unavailable_files": [],
                "availability": "available",
                "score": 0,
                "observed_score": 0,
            }
        ],
        "limitations": [
            "Heuristic priority; historical co-change is not a static dependency."
        ],
    }


def test_v2_component_zero_is_measured_and_round_trips() -> None:
    risk = read_risk_scores(legacy_risk())
    risk["component_hotspots"] = component_priority()
    validate("risk_scores", risk)
    assert read_risk_scores(risk)["component_hotspots"] == component_priority()


@pytest.mark.parametrize(
    "change", ["sum", "missing", "duplicate", "outside", "overlap"]
)
def test_component_contract_rejects_inconsistent_or_out_of_scope_claims(
    change: str,
) -> None:
    risk = read_risk_scores(legacy_risk())
    value = component_priority()
    row = value["components"][0]
    if change == "sum":
        row["score"] = row["observed_score"] = 1
    elif change == "missing":
        row["measured_files"] = []
        row["unavailable_files"] = row["files"][:]
    elif change == "duplicate":
        value["components"].append(deepcopy(row))
    elif change == "outside":
        row["files"] = ["outside.cpp"]
        row["measured_files"] = [{"file": "outside.cpp", "score": 0}]
    else:
        peer = deepcopy(row)
        peer["id"] = "other"
        value["components"].append(peer)
    risk["component_hotspots"] = value
    with pytest.raises(ContractError):
        validate("risk_scores", risk)


def test_missing_member_and_partial_history_cannot_become_complete_score() -> None:
    risk = read_risk_scores(legacy_risk())
    value = component_priority()
    value["history_status"] = "partial"
    value["components"][0].update(availability="partial", score=None)
    risk["component_hotspots"] = value
    validate("risk_scores", risk)
    value["components"][0].update(availability="available", score=0)
    with pytest.raises(ContractError):
        validate("risk_scores", risk)


def test_component_priorities_need_explicit_prototype_reader_and_survive_it() -> None:
    risk = legacy_risk()
    risk["component_hotspots"] = component_priority()
    with pytest.raises(ContractError, match="explicit prototype"):
        read_risk_scores(risk)
    converted = read_risk_scores(risk, allow_prototype_v1=True)
    assert converted["component_hotspots"] == component_priority()
    converted["component_hotspots"]["components"].clear()
    assert risk["component_hotspots"]["components"]
    with pytest.raises(CompatibilityError):
        export_legacy_risk_scores(risk)


def test_measured_zero_cannot_be_imported_as_tiny_positive_priority() -> None:
    risk = read_risk_scores(legacy_risk())
    value = component_priority()
    value["components"][0].update(score=1e-15, observed_score=1e-15)
    risk["component_hotspots"] = value
    with pytest.raises(ContractError):
        validate("risk_scores", risk)


def test_finite_members_with_overflowing_sum_are_invalid_contract_evidence() -> None:
    risk = read_risk_scores(legacy_risk())
    peer = deepcopy(risk["file_risks"][0])
    peer["file"] = "src/b.cpp"
    risk["file_risks"].append(peer)
    value = component_priority()
    row = value["components"][0]
    row["files"].append("src/b.cpp")
    row["measured_files"] = [{"file": name, "score": 1e308} for name in row["files"]]
    row.update(score=1e308, observed_score=1e308)
    risk["component_hotspots"] = value
    with pytest.raises(ContractError):
        validate("risk_scores", risk)


def test_excluded_component_member_stays_outside_attempted_ranking_scope() -> None:
    risk = read_risk_scores(legacy_risk())
    value = component_priority()
    value["excluded_files"] = ["src/b.cpp"]
    row = value["components"][0]
    row["files"].append("src/b.cpp")
    row["unavailable_files"].append("src/b.cpp")
    row.update(availability="partial", score=None)
    risk["component_hotspots"] = value
    validate("risk_scores", risk)
    assert len(risk["file_risks"]) == 1 and not risk.get("unranked_files")
    assert read_risk_scores(risk)["component_hotspots"] == value


@pytest.mark.parametrize("change", ["ranked", "measured", "unmapped"])
def test_excluded_members_cannot_inflate_scores_or_escape_component_mapping(
    change: str,
) -> None:
    risk = read_risk_scores(legacy_risk())
    value = component_priority()
    value["excluded_files"] = ["src/a.cpp" if change != "unmapped" else "src/b.cpp"]
    if change == "measured":
        risk["file_risks"] = []
    risk["component_hotspots"] = value
    with pytest.raises(ContractError):
        validate("risk_scores", risk)
