"""Finite-example safety and real public C++/CTest acceptance controls.

The integration test requires the actual supported producer; missing tools or
another CTest version are prerequisite failures, never successful skipped proof.
The same test can run outside checkout against an installed candidate by setting
CPPULSE_FIRST_TRIAL_CLI to its actual console command (shell words only).
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

import pytest

from cppulse.run_store import RunStore

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "first-trial"


def preparation() -> Any:
    """Load the actual checked-in script without assuming the caller's cwd."""
    spec = importlib.util.spec_from_file_location(
        "first_trial_prepare", EXAMPLE / "prepare.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_workspace_is_rejected_before_probes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = preparation()
    sentinel = tmp_path / "preserved"
    sentinel.write_bytes(b"original private work")
    monkeypatch.setattr(sys, "argv", ["prepare.py", "--workspace", str(tmp_path)])

    def reject_probe(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("An existing workspace must be rejected before any probe")

    monkeypatch.setattr(module, "executable", reject_probe)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert sentinel.read_bytes() == b"original private work"


def test_unsupported_ctest_never_creates_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = preparation()
    workspace = tmp_path / "uncreated"
    monkeypatch.setattr(sys, "argv", ["prepare.py", "--workspace", str(workspace)])
    monkeypatch.setattr(module, "executable", lambda name: Path("/declared") / name)
    versions = {
        "c++": "declared compiler test double",
        "cmake": "cmake version 4.4.5",
        "ctest": "ctest version 4.4.5",
    }
    monkeypatch.setattr(module, "version", lambda tool: versions[tool.name])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert not workspace.exists()


def test_real_public_first_trial_pass_missing_and_stale(tmp_path: Path) -> None:
    """Build actual C++, bind actual CTest output, then reject missing/stale proof."""
    cli = (
        shlex.split(os.environ["CPPULSE_FIRST_TRIAL_CLI"])
        if os.environ.get("CPPULSE_FIRST_TRIAL_CLI")
        else [sys.executable, "-m", "cppulse"]
    )
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def invoke(argv: list[str], expected: int) -> dict[str, Any]:
        result = subprocess.run(
            argv,
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == expected, (
            argv,
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return json.loads(result.stdout)

    def collect(
        name: str, *, missing: bool = False
    ) -> tuple[Path, Path, dict[str, Any]]:
        workspace, store = tmp_path / name, tmp_path / (name + "-store")
        prepare = [
            sys.executable,
            str(EXAMPLE / "prepare.py"),
            "--workspace",
            str(workspace),
        ]
        if missing:
            prepare.append("--omit-tests")
        invoke(prepare, 0)
        result = invoke(
            [
                *cli,
                "collect",
                "--request",
                str(workspace / "collection-request.json"),
                "--workspace",
                str(workspace),
                "--store",
                str(store),
            ],
            0,
        )
        assert result["status"] == "completed"
        return workspace, store, result["final_run"]

    def check(
        workspace: Path, store: Path, pin: dict[str, Any], expected: int
    ) -> dict[str, Any]:
        return invoke(
            [
                *cli,
                "check",
                "--store",
                str(store),
                "--workspace",
                str(workspace),
                "--run-id",
                pin["run_id"],
                "--manifest-sha256",
                pin["manifest_sha256"],
                "--policy",
                str(workspace / "policy.json"),
            ],
            expected,
        )

    workspace, store, pin = collect("positive")
    passed = check(workspace, store, pin, 0)
    assert passed["status"] == "passed"
    snapshot = RunStore.open_existing(store).open_run(
        pin["run_id"], manifest_sha256=pin["manifest_sha256"]
    )
    records = [
        row
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == "evidence"
        for row in snapshot.read_json(entry["id"])["records"]
    ]
    test = next(row for row in records if row["id"] == "trial-tests")
    assert test["origin"] == "execution" and test["status"] == "passed"
    receipts = [
        snapshot.read_json(entry["id"])
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == "execution_receipt"
    ]
    receipt = next(row for row in receipts if row["id"] == test["receipt_id"])
    assert receipt["tests"] == {
        "total": 3,
        "passed": 3,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }
    report = tmp_path / "report.html"
    invoke(
        [
            *cli,
            "report",
            "--input",
            str(store),
            "--evidence",
            "--format",
            "html",
            "--output",
            str(report),
        ],
        0,
    )
    assert "<!doctype html>" in report.read_text().lower()
    missing_workspace, missing_store, missing_pin = collect("missing", missing=True)
    missing = check(missing_workspace, missing_store, missing_pin, 3)
    assert missing["status"] == "insufficient_evidence"
    with (workspace / "checks.cpp").open("a") as stream:
        stream.write("\n// Explicit stale-source negative control.\n")
    stale = check(workspace, store, pin, 3)
    assert stale["error"]["code"] == "STALE_SOURCE"
