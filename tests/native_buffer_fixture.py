"""Explicit synthetic parsed-buffer declarations without invented measurements.

This helper supports finding/repair consumer tests. Actual producer evidence is
separate. The shared legacy native_snapshot fixture remains legacy by default.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

from cppulse.analysis import _physical_loc
from tests.test_maintenance_metrics_contract import native_metric_report


def add_parsed_buffer_fixture(report: dict[str, Any], root: Path) -> None:
    """Declare only the fixture's parsed source identity and unknown metrics."""
    raw = deepcopy(native_metric_report()["metadata"]["analysis"]["native_metrics"])
    observed = report["metadata"]["analysis"]["files"][0]
    source = (root / "main.cpp").read_bytes()
    row = raw["files"][0]
    row.update(
        path=str(root / "main.cpp"),
        status=observed["status"],
        error_count=observed["error_count"],
        measurement_complete=False,
        source_content_sha256=hashlib.sha256(source).hexdigest(),
        physical_loc=_physical_loc(source),
        code_loc=None,
        function_count=None,
        functions=[],
        includes=[],
        limitations=[
            "Synthetic parsed-buffer declaration; numerical measurements unavailable."
        ],
    )
    row["token_stream"].update(
        availability="unavailable",
        complete=False,
        total_tokens=None,
        retained_tokens=0,
        records=[],
        limitations=["No token measurement is asserted by this consumer fixture."],
    )
    report["metadata"]["analysis"]["native_metrics"] = raw
