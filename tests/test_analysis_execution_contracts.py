"""Contract-first gates for public bounded native orchestration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from cppulse.errors import ContractError
from cppulse.identities import snapshot_inputs
from cppulse.work_units import _check


def plan(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "source"
    root.mkdir()
    (root / "sample.cpp").write_text("int value;\n")
    return {
        "version": "1.0.0",
        "source_root": str(root),
        "work_root": str(tmp_path / "work"),
        "source": snapshot_inputs(root, ["sample.cpp"]),
        "configuration_sha256": "a" * 64,
        "native_sha256": "b" * 64,
        "execution": {
            "mode": "bounded",
            "jobs": 2,
            "wall_seconds": 10,
            "cpu_seconds": 5,
            "address_space_bytes": 1024**3,
            "output_bytes": 1024**2,
            "work_directory": None,
            "resume": False,
        },
        "compilation_database_sha256": None,
        "units": [
            {
                "unit_id": "sample-unit",
                "primary_file": "sample.cpp",
                "context_mode": "fallback",
            }
        ],
        "discovery_gaps": [],
        "limitations": ["Finite selected C++ inventory; no target build executes."],
    }


def test_plan_binds_source_scope_native_configuration_and_finite_budgets(
    tmp_path: Path,
) -> None:
    document = plan(tmp_path)
    _check("analysis_execution_plan", document)
    for field in [
        "source",
        "native_sha256",
        "configuration_sha256",
        "execution",
        "units",
    ]:
        candidate = deepcopy(document)
        del candidate[field]
        with pytest.raises(ContractError):
            _check("analysis_execution_plan", candidate)


@pytest.mark.parametrize(
    "field,value",
    [
        ("jobs", 0),
        ("jobs", True),
        ("wall_seconds", 0),
        ("address_space_bytes", -1),
        ("output_bytes", 0),
        ("mode", "legacy"),
    ],
)
def test_plan_rejects_missing_or_ignored_bounds(
    tmp_path: Path, field: str, value: Any
) -> None:
    document = plan(tmp_path)
    document["execution"][field] = value
    with pytest.raises(ContractError):
        _check("analysis_execution_plan", document)
