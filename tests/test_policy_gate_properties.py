"""Bounded exhaustive policy properties independent of score formulas."""

from __future__ import annotations

from copy import deepcopy
from itertools import permutations, product
from typing import Any

import pytest

from cppulse.contracts import policy_gate

STATES = ("passed", "failed", "unknown", "not_applicable")


def inputs(states: tuple[str, ...]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Construct explicitly synthetic gate inputs, not executed evidence."""
    controls = [
        {
            "id": f"c{index}",
            "status": state,
            "weight": index + 1,
            "required": False,
            "incomplete": state == "unknown",
        }
        for index, state in enumerate(states)
    ]
    policy = {
        "controls": [{"id": row["id"], "allow_deviation": False} for row in controls],
        "gates": {"minimum_readiness": 50, "minimum_completeness": 50},
    }
    return policy, controls


@pytest.mark.parametrize("states", list(product(STATES, repeat=3)))
def test_order_and_common_weight_scale_do_not_change_gate(
    states: tuple[str, ...],
) -> None:
    policy, controls = inputs(states)
    expected = policy_gate(policy, controls, source_scope_empty=False)
    for ordering in permutations(controls):
        assert policy_gate(policy, ordering, source_scope_empty=False) == expected
    for scale in (10**-12, 10**12, 10**308):
        scaled = [{**row, "weight": row["weight"] * scale} for row in controls]
        assert policy_gate(policy, scaled, source_scope_empty=False) == expected


@pytest.mark.parametrize("states", list(product(STATES, repeat=2)))
@pytest.mark.parametrize("threshold", [0, 50, 100])
def test_required_failed_and_unknown_cannot_be_hidden_by_other_controls(
    states: tuple[str, ...], threshold: int
) -> None:
    for required_status in ("failed", "unknown"):
        policy, controls = inputs((required_status, *states))
        controls[0]["required"] = True
        policy["gates"] = {
            "minimum_readiness": threshold,
            "minimum_completeness": threshold,
        }
        gate = policy_gate(policy, controls, source_scope_empty=False)
        assert gate != "passed"
        if required_status == "failed":
            assert gate == "failed"


@pytest.mark.parametrize("states", list(product(STATES, repeat=3)))
def test_tightening_thresholds_never_creates_a_pass(states: tuple[str, ...]) -> None:
    policy, controls = inputs(states)
    for readiness, completeness in product((0, 25, 50, 75, 100), repeat=2):
        policy["gates"] = {
            "minimum_readiness": readiness,
            "minimum_completeness": completeness,
        }
        gate = policy_gate(policy, controls, source_scope_empty=False)
        stricter = deepcopy(policy)
        stricter["gates"] = {
            "minimum_readiness": min(100, readiness + 25),
            "minimum_completeness": min(100, completeness + 25),
        }
        if gate != "passed":
            assert policy_gate(stricter, controls, source_scope_empty=False) != "passed"


@pytest.mark.parametrize("states", list(product(STATES, repeat=2)))
@pytest.mark.parametrize("threshold", [0, 25, 50, 75, 100])
def test_resolving_unknown_to_complete_pass_cannot_break_a_passing_gate(
    states: tuple[str, ...], threshold: int
) -> None:
    policy, controls = inputs(("unknown", *states))
    policy["gates"] = {
        "minimum_readiness": threshold,
        "minimum_completeness": threshold,
    }
    before = policy_gate(policy, controls, source_scope_empty=False)
    controls[0].update(status="passed", incomplete=False)
    after = policy_gate(policy, controls, source_scope_empty=False)
    if before == "passed":
        assert after == "passed"
