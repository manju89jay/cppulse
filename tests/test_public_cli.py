"""Installed dispatcher paths preserve machine output and explicit gate semantics."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from cppulse.cli import main
from cppulse.run_store import RunStore
from test_assessment_workflows import selected_policy
from test_public_workflows import request_for


def request_file(tmp_path: Path) -> Path:
    request = request_for(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('observed fixture material')",
    )
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    return path


def test_collect_assess_repeat_check_and_historical_explain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = request_file(tmp_path)
    common = ["--store", str(tmp_path / "store"), "--workspace", str(tmp_path)]
    assert main(["collect", *common, "--request", str(request)]) == 0
    capture = json.loads(capsys.readouterr().out)
    assert (
        capture["status"] == "completed" and capture["raw_run"] and capture["final_run"]
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(selected_policy()))
    assert main(["assess", *common, "--policy", str(policy)]) == 0
    assessed = json.loads(capsys.readouterr().out)
    assert assessed["policy_gate"] == "passed"
    assert main(["check", *common, "--policy", str(policy)]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["status"] == "passed"
    (tmp_path / "build/app").write_text("different current binary")
    assert main(["check", *common, "--policy", str(policy)]) == 3
    stale = json.loads(capsys.readouterr().out)
    assert stale["error"]["code"] == "STALE_OUTPUT"
    assert main(["explain", "--store", str(tmp_path / "store")]) == 0
    latest = json.loads(capsys.readouterr().out)
    assert latest["run"]["status"] == "partial" and latest["assessment"] is None
    assert (
        main(
            [
                "explain",
                "--store",
                str(tmp_path / "store"),
                "--run-id",
                assessed["final_run"]["run_id"],
                "--manifest-sha256",
                assessed["final_run"]["manifest_sha256"],
            ]
        )
        == 0
    )
    historical = json.loads(capsys.readouterr().out)
    assert json.loads(historical["assessment"]["raw_json"])["gate"] == "passed"


def test_invalid_request_and_duplicate_json_keys_never_execute_or_create_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = request_file(tmp_path)
    data = json.loads(request.read_text())
    data["normalizers"] = [
        {"id": "fake", "kind": "python_module", "normalizer_version": "1.0.0"}
    ]
    request.write_text(json.dumps(data))
    arguments = [
        "collect",
        "--request",
        str(request),
        "--workspace",
        str(tmp_path),
        "--store",
        str(tmp_path / "missing"),
    ]
    assert main(arguments) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "invalid" and result["error"]
    assert not (tmp_path / "build").exists() and not (tmp_path / "missing").exists()
    request.write_text('{"version":"2.0.0","version":"9.0.0"}')
    assert main(arguments) == 2
    assert (
        "duplicate" in json.loads(capsys.readouterr().out)["error"]["message"].lower()
    )


def test_check_modes_are_exclusive_and_pins_are_a_pair(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "check",
                "--store",
                str(tmp_path),
                "--workspace",
                str(tmp_path),
                "--policy",
                "policy.json",
                "--findings",
                "findings.json",
            ]
        )
    assert raised.value.code == 2
    with pytest.raises(SystemExit) as raised:
        main(["explain", "--store", str(tmp_path / "absent"), "--run-id", "one-pin"])
    assert raised.value.code == 2 and not (tmp_path / "absent").exists()


def test_explain_missing_store_is_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["explain", "--store", str(tmp_path / "absent")]) != 0
    capsys.readouterr()
    assert not (tmp_path / "absent").exists()


def test_baseline_finding_check_and_readonly_sarif(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from test_findings import normalized, SCOPE

    snapshot = normalized(tmp_path)
    store = snapshot.path.parents[1]
    request = tmp_path / "baseline-request.json"
    request.write_text(
        json.dumps(
            {
                "version": "2.0.0",
                "baseline_id": "reviewed",
                **SCOPE,
                "reason": "Synthetic public command regression",
            }
        )
    )
    common = ["--store", str(store), "--workspace", str(tmp_path)]
    assert main(["baseline", "create", *common, "--request", str(request)]) == 0
    baseline = json.loads(capsys.readouterr().out)
    assert baseline["policy_gate"] is None
    request.write_text(
        json.dumps(
            {
                "version": "2.0.0",
                **SCOPE,
                "max_new": 0,
                "baseline": {
                    "source": "local_run",
                    "store": str(store),
                    "run_id": baseline["final_run"]["run_id"],
                    "manifest_sha256": baseline["final_run"]["manifest_sha256"],
                    "artifact_id": baseline["baseline_artifact_id"],
                },
            }
        )
    )
    assert main(["check", *common, "--findings", str(request)]) == 0
    compared = json.loads(capsys.readouterr().out)
    assert compared["mode"] == "findings" and compared["policy_sha256"] is None
    before = RunStore.open_existing(store).resolve_latest_attempt().manifest_sha256
    assert (
        main(
            [
                "export-sarif",
                "--store",
                str(store),
                "--comparison-artifact-id",
                compared["comparison_artifact_id"],
            ]
        )
        == 0
    )
    sarif = json.loads(capsys.readouterr().out)
    assert sarif["version"] == "2.1.0" and len(sarif["runs"][0]["results"]) == 1
    assert sarif["runs"][0]["results"][0]["baselineState"] == "unchanged"
    assert (
        RunStore.open_existing(store).resolve_latest_attempt().manifest_sha256 == before
    )


def test_package_module_dispatcher_is_installed_entry_alias() -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "python")
    result = subprocess.run(
        [sys.executable, "-m", "cppulse", "--version"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    from cppulse import __version__

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == __version__


def test_collect_sigint_publishes_cancelled_observed_attempt(tmp_path: Path) -> None:
    request = request_for(
        tmp_path,
        "from pathlib import Path\nimport time\nPath('RUNNING').write_text('actual worker started')\ntime.sleep(30)\nPath('AFTER').write_text('should be terminated')",
    )
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "python")
    command = [
        sys.executable,
        "-m",
        "cppulse.cli",
        "collect",
        "--request",
        str(path),
        "--workspace",
        str(tmp_path),
        "--store",
        str(tmp_path / "store"),
    ]
    process = subprocess.Popen(
        command,
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not (tmp_path / "RUNNING").exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.03)
        assert (tmp_path / "RUNNING").exists(), process.communicate(timeout=2)
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 130, (stdout, stderr)
        result = json.loads(stdout)
        assert (
            result["status"] == "cancelled"
            and result["raw_run"]["status"] == "cancelled"
        )
        assert not (tmp_path / "AFTER").exists()
        assert (
            RunStore.open_existing(tmp_path / "store")
            .resolve_latest_attempt()
            .manifest["status"]
            == "cancelled"
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
