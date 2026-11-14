"""Actual finite GCC/CTest coverage plus explicitly rewritten negative fixtures."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import runpy
import shutil
from typing import Any, Callable

import pytest

from cppulse.coverage import (
    normalize_coverage,
    normalize_imported_coverage,
    persist_coverage,
)
from cppulse.errors import CompatibilityError, ContractError, InputChanged
from cppulse.identities import digest_json, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore, StagedRun

ROOT = Path(__file__).resolve().parents[1]
DRIVER = runpy.run_path(str(ROOT / "scripts/demo_coverage.py"))


@pytest.fixture(scope="module")
def actual(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[RunSnapshot, Path, dict[str, Any]]:
    """Run real tools when the optional local verification toolchain is present."""
    gcovr = os.environ.get(
        "CPPULSE_GCOVR", str(ROOT.parent / "tooling/gcovr-8.8/bin/gcovr")
    )
    requested = {
        "compiler": "g++-14",
        "gcov": "gcov-14",
        "gcovr": gcovr,
        "cmake": "cmake",
        "ctest": "ctest",
    }
    if any(shutil.which(tool) is None for tool in requested.values()):
        pytest.skip(
            "Optional GCC14.2/gcovr8.8/CMake3.31.6 verification tools unavailable"
        )
    selected = {name: DRIVER["selected_tool"](tool) for name, tool in requested.items()}
    snapshot, workspace = DRIVER["prepare_collection"](
        tmp_path_factory.mktemp("actual-coverage"), **selected
    )
    assert snapshot.manifest["status"] == "completed"
    return (
        snapshot,
        workspace,
        {kind: DRIVER["roles"](snapshot, kind) for kind in ["lcov", "cobertura"]},
    )


def clone(
    actual: tuple[RunSnapshot, Path, dict[str, Any]],
    directory: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> tuple[RunSnapshot, dict[str, Any]]:
    """Rewrite a checked actual run into a clearly synthetic negative fixture."""
    snapshot, workspace, selections = actual
    manifest = snapshot.manifest
    contents = {
        entry["id"]: snapshot.read_bytes(entry["id"]) for entry in manifest["artifacts"]
    }
    documents = {
        entry["id"]: snapshot.read_json(entry["id"])
        for entry in manifest["artifacts"]
        if entry.get("contract", {}).get("version") == "2.0.0"
    }
    state = {
        "manifest": manifest,
        "contents": contents,
        "documents": documents,
        "selection": deepcopy(selections["lcov"]),
    }
    mutate(state)
    for identifier, content in list(contents.items()):
        if content != snapshot.read_bytes(identifier):
            original = next(
                row for row in manifest["artifacts"] if row["id"] == identifier
            )
            for entry in manifest["artifacts"]:
                if (entry["sha256"], entry["size_bytes"]) == (
                    original["sha256"],
                    original["size_bytes"],
                ):
                    contents[entry["id"]] = content
    # Keep changed raw payload identity consistent with every observed material
    # fact. The negative is semantic, not merely a stale artifact hash.
    for identifier, content in contents.items():
        entry = next(row for row in manifest["artifacts"] if row["id"] == identifier)
        if content == snapshot.read_bytes(identifier):
            continue
        for document in documents.values():
            if "binding" not in document:
                continue
            paths = {
                row["path"]
                for direction in ["input", "output"]
                for row in document["binding"][direction + "_artifacts"]
                if row["artifact_id"] == identifier
            }
            for key in [
                "input_facts",
                "input_after_facts",
                "output_facts",
                "preexisting_output_facts",
            ]:
                for fact in document[key]:
                    if fact["path"] in paths:
                        fact["sha256"] = hashlib.sha256(content).hexdigest()
                        fact["size_bytes"] = len(content)
    store = RunStore(directory / "store")
    with store.begin() as stage:
        for entry in manifest["artifacts"]:
            identifier = entry["id"]
            if identifier in documents:
                stage.write_json(
                    entry["path"],
                    documents[identifier],
                    contract=entry["contract"],
                    artifact_id=identifier,
                )
            else:
                path = directory / "copies" / identifier
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents[identifier])
                stage.copy_artifact(
                    identifier, path, entry["path"], entry["media_type"]
                )
        manifest["run_id"] = stage.run_id
        manifest["artifacts"] = stage.artifacts
        result = stage.publish(
            manifest,
            source_check=lambda: (
                (_ for _ in ()).throw(InputChanged("Fixture source changed"))
                if verify_inputs(workspace, manifest["source"])
                else None
            ),
        )
    return result, state["selection"]


def facts(state: dict[str, Any], receipt_id: str) -> dict[str, Any]:
    return next(
        document
        for document in state["documents"].values()
        if document.get("receipt", {}).get("id") == receipt_id
    )


def test_actual_execution_has_distinct_exact_counts_and_source_hash(
    actual: tuple[RunSnapshot, Path, dict[str, Any]]
) -> None:
    snapshot, _, selections = actual
    for adapter, expected in [
        ("lcov", {"line": (5, 8), "branch": (1, 2), "function": (2, 3)}),
        ("cobertura", {"line": (5, 8), "branch": (1, 2)}),
    ]:
        result = normalize_coverage(snapshot, **selections[adapter])
        assert result["origin"] == "execution" and result["usability"] == "usable"
        assert result["files"][0]["file"] == "main.cpp"
        source = next(
            row
            for row in snapshot.manifest["source"]["files"]
            if row["path"] == "main.cpp"
        )
        assert result["files"][0]["source_sha256"] == source["sha256"]
        assert {
            row["kind"]: (row["covered"], row["total"])
            for row in result["files"][0]["measurements"]
        } == expected
        assert all(
            row["covered"] == sum(unit["covered"] for unit in row["units"])
            and row["total"] == sum(unit["total"] for unit in row["units"])
            for row in result["files"][0]["measurements"]
        )


def test_imported_counts_never_acquire_execution_proof(
    actual: tuple[RunSnapshot, Path, dict[str, Any]]
) -> None:
    snapshot, workspace, selections = actual
    selected = selections["lcov"]
    result = normalize_imported_coverage(
        snapshot,
        report_artifact_id=selected["report_artifact_id"],
        adapter="lcov",
        context_id="gcc-coverage-job",
        source_root=str(workspace),
    )
    assert result["origin"] == "import" and result["usability"] == "usable"
    assert result["receipt_id"] is None and not result["profiles"]
    assert result["files"][0]["source_sha256"] is None


@pytest.mark.parametrize(
    "change", ["stamp", "version", "source", "line", "totals", "empty", "truncated"]
)
def test_changed_retained_payloads_do_not_become_positive_execution(
    actual: tuple[RunSnapshot, Path, dict[str, Any]], tmp_path: Path, change: str
) -> None:
    def mutate(state: dict[str, Any]) -> None:
        selection = state["selection"]
        if change in {"stamp", "version"}:
            identifier = selection["profiles"][0]["artifact_id"]
            content = bytearray(state["contents"][identifier])
            content[8 if change == "stamp" else 4] ^= 1
            state["contents"][identifier] = bytes(content)
        else:
            identifier = selection["report_artifact_id"]
            value = state["contents"][identifier].decode()
            if change == "source":
                value = value.replace("/main.cpp", "/unselected.cpp")
            if change == "line":
                value = value.replace("DA:2,", "DA:9999,")
            if change == "totals":
                value = value.replace("LF:8", "LF:9")
            if change == "empty":
                value = ""
            if change == "truncated":
                value = value.replace("end_of_record", "")
            state["contents"][identifier] = value.encode()

    snapshot, selection = clone(actual, tmp_path, mutate)
    if change in {"stamp", "version", "source", "line"}:
        with pytest.raises((CompatibilityError, ContractError)):
            normalize_coverage(snapshot, **selection)
    else:
        result = normalize_coverage(snapshot, **selection)
        assert result["usability"] != "usable" and result["files"] == []


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "version_prefix",
        "output",
        "config",
        "scan",
        "instrumentation",
        "gcov",
        "compiler",
        "omitted_version",
    ],
)
def test_wrong_tools_or_roles_cannot_label_counts_observed(
    actual: tuple[RunSnapshot, Path, dict[str, Any]], tmp_path: Path, change: str
) -> None:
    def mutate(state: dict[str, Any]) -> None:
        selection = state["selection"]
        if change == "omitted_version":
            selection["proof_receipt_ids"].remove("gcovr-version")
        elif change == "instrumentation":
            selection["instrumentation"][0]["mapping_artifact_id"] = selection[
                "instrumentation"
            ][0]["object_artifact_id"]
        elif change == "gcov":
            selection["gcov_artifact_id"] = selection["configuration_artifact_id"]
        elif change == "compiler":
            selection["compiler_version_receipt_id"] = "gcov-version"
        elif change in {"version", "version_prefix"}:
            version = facts(state, "gcovr-version")
            identifier = version["binding"]["log_artifacts"]["stdout"]
            state["contents"][identifier] = state["contents"][identifier].replace(
                b"8.8", b"8.7" if change == "version" else b"8.80"
            )
            if change == "version_prefix":
                version["stdout_bytes"] += 1
                version["captured_bytes"] += 1
        else:
            report = facts(state, "coverage-report")
            argv = report["receipt"]["argv"]
            if change == "output":
                argv[argv.index("--lcov") + 1] = "unrelated.info"
            if change == "config":
                argv[argv.index("--config") + 1] = "unselected.cfg"
            if change == "scan":
                argv[-1] = "build"
            for document in state["documents"].values():
                if document.get("id") == "coverage-report":
                    document["argv"] = deepcopy(argv)
                if "recipe" in document:
                    next(
                        row
                        for row in document["recipe"]["steps"]
                        if row["id"] == "coverage-report"
                    )["argv"] = deepcopy(argv)
                    state["manifest"]["config_digest"] = digest_json(document)

    snapshot, selection = clone(actual, tmp_path, mutate)
    with pytest.raises((CompatibilityError, ContractError)):
        normalize_coverage(snapshot, **selection)


def test_normalization_uses_frozen_inputs_without_commands_or_live_project(
    actual: tuple[RunSnapshot, Path, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    snapshot, _, selections = actual

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Coverage normalization must not execute commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert normalize_coverage(snapshot, **selections["lcov"])["usability"] == "usable"


def test_derived_snapshot_preserves_parent_and_current_source_guard(
    actual: tuple[RunSnapshot, Path, dict[str, Any]], tmp_path: Path
) -> None:
    snapshot, workspace, selections = actual
    original = snapshot.read_bytes(selections["lcov"]["report_artifact_id"])
    derived = persist_coverage(
        snapshot, workspace=workspace, store=tmp_path / "store", **selections["lcov"]
    )
    derived.verify()
    assert derived.run_id != snapshot.run_id
    assert derived.manifest["config_digest"] == snapshot.manifest["config_digest"]
    assert derived.manifest["source"] == snapshot.manifest["source"]
    assert derived.read_bytes(selections["lcov"]["report_artifact_id"]) == original
    assert all(
        entry in derived.manifest["artifacts"]
        for entry in snapshot.manifest["artifacts"]
    )
    with pytest.raises(ContractError, match="already normalized"):
        normalize_coverage(derived, **selections["lcov"])


def test_source_change_during_publication_does_not_promote_derived_run(
    actual: tuple[RunSnapshot, Path, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, workspace, selections = actual
    store = RunStore(tmp_path / "store")
    source = workspace / "main.cpp"
    original = source.read_bytes()
    method = StagedRun.publish

    def publish(
        stage: StagedRun, manifest: dict[str, Any], **kwargs: Any
    ) -> RunSnapshot:
        source.write_bytes(original + b"\n// actual mutation during publication\n")
        return method(stage, manifest, **kwargs)

    monkeypatch.setattr(StagedRun, "publish", publish)
    try:
        with pytest.raises(InputChanged):
            persist_coverage(
                snapshot, workspace=workspace, store=store, **selections["lcov"]
            )
        assert (
            not list((store.root / "runs").glob("*/run_manifest.json"))
            if (store.root / "runs").exists()
            else True
        )
        assert not (store.root / "latest_attempt.json").exists()
    finally:
        source.write_bytes(original)
