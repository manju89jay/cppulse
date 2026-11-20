"""Negotiate editor contracts without running native or project commands."""

import json
import os
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest

from cppulse import __version__
from cppulse.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_capabilities_is_read_only_machine_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("Capability negotiation must not execute tools")

    monkeypatch.setattr(subprocess, "run", forbid)
    assert main(["capabilities", "--format", "json"]) == 0
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert data["contract_version"] == "1.0.0"
    assert data["tool_version"] == __version__
    assert data["snapshot_view_versions"] == ["2.0.0"]
    assert data["sarif_column_kinds"] == ["unicodeCodePoints"]
    assert data["execution_on_open"] is False
    assert {"explain", "export-sarif", "check", "collect"} <= set(data["commands"])
    assert not output.err


def test_packaged_capabilities_contract_rejects_unsupported_versions() -> None:
    schema = json.loads(
        (
            ROOT
            / "python/cppulse/contracts/schemas/install_v1/client_capabilities.schema.json"
        ).read_bytes()
    )
    process = subprocess.run(
        [sys.executable, "-m", "cppulse", "capabilities", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "python")},
    )
    assert process.returncode == 0, process.stderr
    data = json.loads(process.stdout)
    jsonschema.validate(data, schema)
    data["contract_version"] = "999.0.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
