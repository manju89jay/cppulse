"""Real producer reports that cannot fit the legacy embedded SDK proof."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cppulse.analysis_execution import run_analysis
from cppulse.errors import IntegrityError
from cppulse.run_store import RunStore
from cppulse import sdk_inputs
import test_analysis_execution as execution_fixtures
import test_bounded_pipeline as pipeline_fixtures


@pytest.fixture(scope="module")
def sdk_execution(tmp_path_factory: pytest.TempPathFactory) -> Any:
    root = tmp_path_factory.mktemp("sdk-capture-budget")
    config = execution_fixtures.configuration(root, jobs=1)
    source = config.repo / "main.cpp"
    source.write_text(
        "#include <__stddef_size_t.h>\nint value() { return sizeof(size_t); }\n"
    )
    (config.repo / "compile_commands.json").write_text(
        json.dumps([{"directory": str(config.repo), "file": str(source),
                     "arguments": ["clang++", "-std=c++17", "-c", str(source)]}])
    )
    execution = run_analysis(
        config, execution_fixtures.native.__wrapped__(), root / "work", timeout=60
    )
    assert len(execution.results) == 1
    request, result = execution.results[0]
    assert result["outcome"] == "complete", result
    assert request["inputs"]["resource_manifest"] is not None
    return execution


def report(sdk_execution: Any) -> tuple[Path, dict[str, Any]]:
    """Locate the actual producer descriptor and its original on-disk report."""
    request, result = sdk_execution.results[0]
    descriptor = next(
        row for row in result["artifacts"] if row["path"] == "output/findings.json"
    )
    return Path(request["work_root"]) / descriptor["path"], descriptor


def test_unrepresentable_report_is_checked_without_materializing_or_sdk_writes(
    sdk_execution: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, descriptor = report(sdk_execution)
    assert descriptor["size_bytes"] > 2048
    # Only the cap is reduced, not producer bytes, descriptor or wire contract.
    monkeypatch.setattr(sdk_inputs, "MAX_SDK_PROOF_BYTES", 2048)
    original_read = sdk_inputs._read

    def no_report_read(candidate: Path, **kwargs: Any) -> bytes:
        assert candidate != path, "unrepresentable native report was materialized"
        return original_read(candidate, **kwargs)

    monkeypatch.setattr(sdk_inputs, "_read", no_report_read)
    with RunStore(tmp_path / "store").begin() as stage:
        proof = sdk_inputs.retain_used_sdk_inputs(stage, sdk_execution)
        assert proof["units"] == []
        assert proof["captured_bytes"] == 0
        assert not any(row["id"].startswith("sdk-buffer-") for row in stage.artifacts)


@pytest.mark.parametrize("change", ["sha", "size", "growth", "missing", "symlink"])
def test_over_budget_does_not_bypass_original_report_integrity(
    sdk_execution: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    path, descriptor = report(sdk_execution)
    original = path.read_bytes()
    original_descriptor = descriptor.copy()
    monkeypatch.setattr(sdk_inputs, "MAX_SDK_PROOF_BYTES", 2048)
    try:
        if change == "sha":
            descriptor["sha256"] = "0" * 64
        elif change == "size":
            descriptor["size_bytes"] += 1
        elif change == "growth":
            path.write_bytes(original + b" ")
        elif change == "missing":
            path.unlink()
        else:
            peer = tmp_path / "same-report.json"
            peer.write_bytes(original)
            path.unlink()
            path.symlink_to(peer)
        with RunStore(tmp_path / "store").begin() as stage:
            with pytest.raises(IntegrityError):
                sdk_inputs.retain_used_sdk_inputs(stage, sdk_execution)
            assert not any(row["id"].startswith("sdk-buffer-") for row in stage.artifacts)
    finally:
        if path.is_symlink():
            path.unlink()
        path.write_bytes(original)
        descriptor.clear()
        descriptor.update(original_descriptor)


def test_representable_real_report_still_captures_actual_sdk_bytes(
    sdk_execution: Any, tmp_path: Path
) -> None:
    with RunStore(tmp_path / "store").begin() as stage:
        proof = sdk_inputs.retain_used_sdk_inputs(stage, sdk_execution)
        assert len(proof["units"]) == 1
        assert proof["captured_bytes"] > 0
        entries = proof["units"][0]["entries"]
        assert any(row["status"] == "available" for row in entries)


def test_declined_sdk_proof_publishes_unknown_not_qualified_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse.contracts import validate_bundle
    from cppulse.pipeline import analyze
    from cppulse.workflows import read_documents

    config = pipeline_fixtures.config(tmp_path)
    source = config.repo / "main.cpp"
    source.write_text(
        "#include <__stddef_size_t.h>\nint value() { return sizeof(size_t); }\n"
    )
    (config.repo / "compile_commands.json").write_text(
        json.dumps([{"directory": str(config.repo), "file": str(source),
                     "arguments": ["clang++", "-std=c++17", "-c", str(source)]}])
    )
    pipeline_fixtures.select_native(
        monkeypatch, execution_fixtures.native.__wrapped__()
    )
    monkeypatch.setattr(sdk_inputs, "MAX_SDK_PROOF_BYTES", 2048)
    summary = analyze(config, report_format="json", timeout=60)
    snapshot = RunStore(config.output).open_run(
        summary["run_id"], manifest_sha256=summary["manifest_sha256"]
    )
    documents = read_documents(snapshot)
    validate_bundle(documents)
    proof = documents["used_sdk_inputs"][0]
    assert proof["units"] == [] and proof["captured_bytes"] == 0
    assert not any(
        row["id"].startswith("sdk-buffer-") for row in snapshot.manifest["artifacts"]
    )
    assert documents["analysis_inventory"][0]["items"][0]["buffer_coherence"] == "unverified"
    assert all(
        row["aggregate"]["overall"] is None for row in documents["maintenance_health"]
    )
