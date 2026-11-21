"""SDK serialization boundary controls; synthetic units do not attest execution.

The genuine 32-TU native regression is retained separately in SDK91. These small
controls exercise the real producer/store wire boundary, not native execution.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from cppulse import sdk_inputs
from cppulse.identities import canonical_json_bytes
from cppulse.run_store import RunStore
from test_sdk_used_inputs import fixture


def test_sdk_capture_budget_bounds_actual_store_wire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = tmp_path / 'wire-λ-"quoted"'
    case.mkdir()
    execution, _, _, _ = fixture(case)
    request, result = execution.results[0]
    # Authored serialization inputs only: no extra execution/receipt is claimed.
    execution.results = [
        ({**deepcopy(request), "unit_id": f"unit-{index:02}"}, deepcopy(result))
        for index in range(32)
    ]
    with RunStore(tmp_path / "baseline").begin() as stage:
        full = sdk_inputs.retain_used_sdk_inputs(stage, execution)
        descriptor = next(
            row for row in stage.artifacts if row["id"] == "sdk-used-inputs"
        )
        raw = (stage.path / descriptor["path"]).read_bytes()
        assert len(full["units"]) == 32
        assert descriptor["size_bytes"] == len(raw)
    old_compact_estimate = (
        2048
        + sum(len(canonical_json_bytes(row)) + 2 for row in full["units"])
        + sum(
            len(canonical_json_bytes(row)) + 2 for row in full["resource_inventories"]
        )
    )
    cap = len(raw) - 1
    assert old_compact_estimate < cap < sdk_inputs.MAX_SDK_PROOF_BYTES
    monkeypatch.setattr(sdk_inputs, "MAX_SDK_PROOF_BYTES", cap)
    with RunStore(tmp_path / "bounded").begin() as stage:
        bounded = sdk_inputs.retain_used_sdk_inputs(stage, execution)
        descriptor = next(
            row for row in stage.artifacts if row["id"] == "sdk-used-inputs"
        )
        bounded_raw = (stage.path / descriptor["path"]).read_bytes()
        assert 0 < len(bounded["units"]) <= len(full["units"])
        assert len(bounded_raw) == descriptor["size_bytes"]
        assert (
            len(bounded_raw) <= cap
        ), "SDK producer published wire its reader must reject"
        assert bounded["captured_bytes"] == full["captured_bytes"]
