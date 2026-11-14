"""Thin public consumer-comparison integration over the accepted actual fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from cppulse.cli import main
from cppulse.contracts import validate
from cppulse.errors import IntegrityError
from cppulse.run_store import RunSnapshot, RunStore, StagedRun
import cppulse.workflows as workflows
from test_consumer_comparison import applicable


@pytest.fixture(scope="module")
def consumer_capture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Reuse one real archive/consumer capture; comparison launches no commands."""
    return applicable.__wrapped__(tmp_path_factory)


def arguments(data: dict[str, Any], store: Path) -> dict[str, Any]:
    """Select explicit local and read-only transferred manifest/subject pins."""
    return {
        "upstream_bundle": data["workspace"] / "foreign-transfer",
        "upstream_root_id": "upstream",
        "upstream_manifest_sha256": data["upstream"].manifest_sha256,
        "upstream_subject_id": data["subject"]["id"],
        "local_subject_id": data["subject"]["id"],
        "upstream_matrix_id": "selected-matrix",
        "local_matrix_id": "selected-matrix",
        "workspace": data["workspace"],
        "store": store,
    }


def bundle_bytes(directory: Path) -> dict[str, str]:
    """Detect any imported file addition, removal or content mutation."""
    return {
        path.relative_to(directory)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def no_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make a metadata-only contract observable at the public API boundary."""

    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Consumer comparison must not execute any project or tool")

    monkeypatch.setattr("subprocess.run", reject)
    monkeypatch.setattr("subprocess.Popen", reject)


def open_final(result: dict[str, Any], store: Path) -> RunSnapshot:
    """Open the exact returned immutable final pin, never current/latest again."""
    reference = result["final_run"]
    snapshot = RunStore.open_existing(store).open_run(
        reference["run_id"], manifest_sha256=reference["manifest_sha256"]
    )
    snapshot.verify()
    return snapshot


def test_public_compare_retains_imported_namespace_and_missing_local_tests(
    consumer_capture: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = consumer_capture
    local = data["local"]
    store = tmp_path / "results"
    selected = arguments(data, store)
    before = bundle_bytes(selected["upstream_bundle"])
    no_commands(monkeypatch)
    result = workflows.compare_runs(local, **selected)
    validate("workflow_result", result)
    assert (result["operation"], result["status"], result["exit_code"]) == (
        "compare",
        "completed",
        0,
    )
    assert result["policy_gate"] is None
    assert result["upstream_run"]["manifest_sha256"] == data["upstream"].manifest_sha256
    assert result["raw_run"]["manifest_sha256"] == local.manifest_sha256
    final = open_final(result, store)
    document = final.read_json(result["comparison_artifact_id"])
    assert (
        document["import_origin"] == "import"
        and document["authentication"] == "unverified"
    )
    assert document["cases"][0]["status"] == "compatible"
    assert document["cases"][0]["local_test_status"] == "unknown"
    assert document["cases"][0]["missing_local_checks"] == [
        "required-application-workload"
    ]
    assert final.manifest["source"] == local.manifest["source"]
    assert final.manifest["contexts"] == local.manifest["contexts"]
    original = {row["id"]: row for row in local.manifest["artifacts"]}
    assert all(row in final.manifest["artifacts"] for row in original.values())
    extra = [row for row in final.manifest["artifacts"] if row["id"] not in original]
    assert [row["contract"]["kind"] for row in extra if "contract" in row] == [
        "consumer_comparison"
    ]
    assert any("contract" not in row for row in extra)
    assert bundle_bytes(selected["upstream_bundle"]) == before


def test_wrong_upstream_pin_rejects_before_a_writer_or_commands(
    consumer_capture: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = arguments(consumer_capture, tmp_path / "must-not-exist")
    selected["upstream_manifest_sha256"] = "0" * 64
    before = bundle_bytes(selected["upstream_bundle"])
    no_commands(monkeypatch)
    with pytest.raises(IntegrityError, match="pin"):
        workflows.compare_runs(consumer_capture["local"], **selected)
    assert not selected["store"].exists()
    assert bundle_bytes(selected["upstream_bundle"]) == before


@pytest.mark.parametrize(
    "relative,code", [("main.cpp", "STALE_SOURCE"), ("build/consumer", "STALE_OUTPUT")]
)
def test_stale_source_or_binary_records_latest_gap_and_preserves_completed_pin(
    consumer_capture: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    code: str,
) -> None:
    data = consumer_capture
    selected = arguments(data, tmp_path / "results")
    no_commands(monkeypatch)
    completed = workflows.compare_runs(data["local"], **selected)
    path = data["workspace"] / relative
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\nexplicit stale-output test marker\n")
        result = workflows.compare_runs(data["local"], **selected)
    finally:
        path.write_bytes(original)
    validate("workflow_result", result)
    assert result["status"] == "insufficient_evidence" and result["exit_code"] == 3
    assert result["error"]["code"] == code
    assert result["comparison_artifact_id"] is None
    final = open_final(result, selected["store"])
    assert final.manifest["status"] == "partial"
    assert final.manifest["input_verification"] == "unverified"
    assert not any("contract" in row for row in final.manifest["artifacts"])
    runtime = RunStore.open_existing(selected["store"])
    assert (
        runtime.resolve_latest().manifest_sha256
        == completed["final_run"]["manifest_sha256"]
    )
    assert runtime.resolve_latest_attempt().manifest_sha256 == final.manifest_sha256


def test_final_publication_rechecks_binary_before_promoting_new_comparison(
    consumer_capture: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = consumer_capture
    selected = arguments(data, tmp_path / "results")
    path = data["workspace"] / "build/consumer"
    content = path.read_bytes()
    original_publish = StagedRun.publish
    changed = False

    def race(self: StagedRun, manifest: dict[str, Any], **kwargs: Any) -> RunSnapshot:
        nonlocal changed
        if not changed and any(
            row.get("contract", {}).get("kind") == "consumer_comparison"
            for row in manifest["artifacts"]
        ):
            changed = True
            path.write_bytes(content + b"\nexplicit final publication race marker\n")
        return original_publish(self, manifest, **kwargs)

    no_commands(monkeypatch)
    monkeypatch.setattr(StagedRun, "publish", race)
    try:
        result = workflows.compare_runs(data["local"], **selected)
    finally:
        path.write_bytes(content)
    assert changed
    assert result["status"] == "insufficient_evidence" and result["exit_code"] == 3
    assert result["error"]["code"] == "STALE_OUTPUT"
    assert result["comparison_artifact_id"] is None
    final = open_final(result, selected["store"])
    assert final.manifest["status"] == "partial"
    assert not (selected["store"] / "latest.json").exists()


def test_cli_compare_completes_metadata_without_claiming_missing_application_tests(
    consumer_capture: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = consumer_capture
    local = data["local"]
    selected = arguments(data, local._root)
    no_commands(monkeypatch)
    result = main(
        [
            "compare",
            "--store",
            str(local._root),
            "--workspace",
            str(data["workspace"]),
            "--run-id",
            local.run_id,
            "--manifest-sha256",
            local.manifest_sha256,
            *[
                argument
                for key, value in selected.items()
                if key not in {"workspace", "store"}
                for argument in ["--" + key.replace("_", "-"), str(value)]
            ],
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert result == 0 and output["status"] == "completed"
    assert output["policy_gate"] is None
    final = open_final(output, local._root)
    comparison = final.read_json(output["comparison_artifact_id"])
    assert comparison["cases"][0]["local_test_status"] == "unknown"
    assert comparison["cases"][0]["missing_local_checks"] == [
        "required-application-workload"
    ]
