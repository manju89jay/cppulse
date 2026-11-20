"""Public workflows retain real process outcomes and reject ambiguous requests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from cppulse.execution import CancellationToken
from cppulse.run_store import RunStore
from cppulse.workflows import collect_request
from test_collection import build_plan, documents


def request_for(workspace: Path, script: str, *, exit_code: int = 0) -> dict[str, Any]:
    """Declare a clearly synthetic local command fixture, never a compiler claim."""
    plan, source, contexts = build_plan(workspace, script, exit_code=exit_code)
    return {
        "version": "2.0.0",
        "id": "public-local-fixture",
        "source": {
            "kind": source["kind"],
            "files": [row["path"] for row in source["files"]],
            "inventory_complete": True,
            "limitations": [
                "Synthetic Python process/output fixture; not a C++ tool claim."
            ],
        },
        "contexts": contexts,
        "plan": plan,
        "normalizers": [],
    }


@pytest.mark.parametrize(
    "case,expected",
    [
        ("pass", "completed"),
        ("failed_command", "completed"),
        ("missing_output", "partial"),
    ],
)
def test_capture_completion_is_distinct_from_observed_command_failure(
    tmp_path: Path, case: str, expected: str
) -> None:
    script = "print('actual fixture execution')"
    if case != "missing_output":
        script += "\nfrom pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('observed local material')"
    request = request_for(tmp_path, script, exit_code=int(case == "failed_command"))
    before = deepcopy(request)
    result = collect_request(request, workspace=tmp_path, store=tmp_path / "store")
    validate("workflow_result", result)
    assert result["status"] == expected
    assert result["exit_code"] == (3 if expected == "partial" else 0)
    assert request == before
    snapshot = RunStore.open_existing(tmp_path / "store").open_run(
        result["raw_run"]["run_id"],
        manifest_sha256=result["raw_run"]["manifest_sha256"],
    )
    assert documents(snapshot, "execution_receipt")[0]["status"] == (
        "failed" if case == "failed_command" else "passed"
    )
    final = RunStore.open_existing(tmp_path / "store").open_run(
        result["final_run"]["run_id"],
        manifest_sha256=result["final_run"]["manifest_sha256"],
    )
    assert final.manifest["source"] == snapshot.manifest["source"]


def test_invalid_late_normalizer_does_not_execute_or_create_store(
    tmp_path: Path,
) -> None:
    request = request_for(
        tmp_path,
        "from pathlib import Path\nPath('EXECUTED').write_text('should not run')",
    )
    request["normalizers"] = [
        {"id": "unknown", "kind": "run_python_module", "normalizer_version": "1.0.0"}
    ]
    with pytest.raises(ContractError):
        collect_request(request, workspace=tmp_path, store=tmp_path / "must-not-exist")
    assert not (tmp_path / "EXECUTED").exists()
    assert not (tmp_path / "must-not-exist").exists()


def test_cancelled_capture_retains_a_pin_without_executing(tmp_path: Path) -> None:
    request = request_for(
        tmp_path,
        "from pathlib import Path\nPath('EXECUTED').write_text('should not run')",
    )
    token = CancellationToken()
    token.cancel()
    result = collect_request(
        request, workspace=tmp_path, store=tmp_path / "store", cancel=token
    )
    validate("workflow_result", result)
    assert result["status"] == "cancelled" and result["exit_code"] == 130
    assert result["raw_run"]["status"] == "cancelled"
    assert not (tmp_path / "EXECUTED").exists()
    assert RunStore.open_existing(tmp_path / "store").resolve_heads()[1] is None


def test_request_control_size_limit_is_checked_before_commands(tmp_path: Path) -> None:
    request = request_for(
        tmp_path,
        "from pathlib import Path\nPath('EXECUTED').write_text('should not run')",
    )
    request["source"]["limitations"].append("selected scope explanation " * 500)
    request["plan"]["limits"]["max_metadata_bytes"] = 4096
    with pytest.raises(ContractError):
        collect_request(request, workspace=tmp_path, store=tmp_path / "store")
    assert not (tmp_path / "EXECUTED").exists() and not (tmp_path / "store").exists()


def test_public_import_normalizers_preserve_independent_malformed_and_usable_claims(
    tmp_path: Path,
) -> None:
    import json

    warning = [
        {
            "kind": "warning",
            "message": "Explicitly synthetic imported warning",
            "option": "-Wconversion",
            "locations": [{"caret": {"file": "source.cpp", "line": 1, "column": 1}}],
        }
    ]
    script = (
        "from pathlib import Path\nimport sys\nPath('build').mkdir()\nPath('build/app').write_text('fixture material')\nprint('not a GCC report')\nsys.stderr.write("
        + repr(json.dumps(warning))
        + ")"
    )
    request = request_for(tmp_path, script)
    for stream in ["stdout", "stderr"]:
        request["normalizers"].append(
            {
                "id": "import-" + stream,
                "kind": "gcc_import",
                "normalizer_version": "1.0.0",
                "report": {"step_id": "build", "role": stream, "path": None},
                "context_id": "local",
                "source_root": str(tmp_path),
                "scope_files": ["source.cpp"],
                "producer": {"name": "GNU-G++", "version": "14.2.0"},
            }
        )
    result = collect_request(request, workspace=tmp_path, store=tmp_path / "store")
    validate("workflow_result", result)
    assert result["status"] == "partial" and result["exit_code"] == 3
    assert [row["status"] for row in result["normalizers"]] == [
        "completed",
        "completed",
    ]
    assert [row["usability"] for row in result["normalizers"]] == [
        "malformed",
        "usable",
    ]
    final = RunStore.open_existing(tmp_path / "store").open_run(
        result["final_run"]["run_id"],
        manifest_sha256=result["final_run"]["manifest_sha256"],
    )
    claims = documents(final, "external_analysis_facts")
    assert len(claims) == 2 and all(
        row["origin"] == "import" and row["scope_completeness"] == "unverified"
        for row in claims
    )
    assert any(row["observations"] for row in claims)
    assert len(documents(final, "collection_request")) == 1


def frozen_request(snapshot: Any) -> dict[str, Any]:
    """Replay routing over a checked fixture; this helper launches no commands."""
    source = snapshot.manifest["source"]
    return {
        "version": "2.0.0",
        "id": "frozen-producer-routing",
        "source": {
            "kind": source["kind"],
            "files": [row["path"] for row in source["files"]],
            "inventory_complete": source["inventory_complete"],
            "limitations": source["limitations"],
        },
        "contexts": snapshot.manifest["contexts"],
        "plan": documents(snapshot, "collection_plan")[0],
        "normalizers": [],
    }


def test_native_routing_uses_original_receipt_roles_and_typed_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_analysis_inventory import native_snapshot
    from test_public_workflow_contracts import normalizer
    import cppulse.workflows as workflows

    from tests.native_buffer_fixture import add_parsed_buffer_fixture

    snapshot, selection = native_snapshot(tmp_path, mutate=add_parsed_buffer_fixture)
    request = frozen_request(snapshot)
    item = normalizer("native_analysis")
    item.update(
        id="public-native",
        step_id=selection["receipt_id"],
        requested_files=["main.cpp"],
        requested_rules=selection["requested_rules"],
    )
    fact = next(
        row
        for row in documents(snapshot, "execution_facts")
        if row["receipt"]["id"] == selection["receipt_id"]
    )
    for key, name in [
        ("report", "report_artifact_id"),
        ("registry", "registry_artifact_id"),
        ("config", "config_artifact_id"),
        ("compilation_database", "compilation_database_artifact_id"),
        ("resource_manifest", "resource_manifest_artifact_id"),
    ]:
        identifier = selection[name]
        direction = "output" if key == "report" else "input"
        path = next(
            row["path"]
            for row in fact["binding"][direction + "_artifacts"]
            if row["artifact_id"] == identifier
        )
        item[key] = {
            "step_id": selection["receipt_id"],
            "role": direction,
            "path": path,
        }
    request["normalizers"] = [item]
    monkeypatch.setattr(workflows, "collect", lambda *args, **kwargs: snapshot)
    result = collect_request(
        request, workspace=tmp_path, store=snapshot.path.parents[1]
    )
    # The frozen synthetic producer fixture is explicitly partial. Completing a
    # transform cannot upgrade its original collection completeness.
    assert result["status"] == snapshot.manifest["status"] == "partial"
    assert result["normalizers"][0]["status"] == "completed"
    assert {row["kind"] for row in result["normalizers"][0]["fact_artifacts"]} == {
        "analysis_inventory",
        "observations",
        "analysis_metrics",
    }
    final = RunStore.open_existing(snapshot.path.parents[1]).open_run(
        result["final_run"]["run_id"]
    )
    assert (
        documents(final, "analysis_inventory")[0]["items"][0]["context_match"]
        == "matched"
    )
    assert all(
        cell["availability"] == "unavailable"
        for document in documents(final, "analysis_metrics")
        for cell in document["items"]
    )


@pytest.mark.parametrize(
    "changed,code", [("build/app", "STALE_OUTPUT"), ("source.cpp", "STALE_SOURCE")]
)
def test_post_capture_mutation_returns_partial_with_original_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str, code: str
) -> None:
    import cppulse.workflows as workflows

    request = request_for(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('original material')",
    )
    original = workflows.collect
    captured = []

    def mutate(*args: Any, **kwargs: Any) -> Any:
        snapshot = original(*args, **kwargs)
        captured.append(snapshot)
        (tmp_path / changed).write_text("changed after the actual capture")
        return snapshot

    monkeypatch.setattr(workflows, "collect", mutate)
    result = collect_request(request, workspace=tmp_path, store=tmp_path / "store")
    validate("workflow_result", result)
    assert result["status"] == "partial" and result["exit_code"] == 3
    assert result["error"]["code"] == code
    assert result["raw_run"]["run_id"] == captured[0].run_id
    assert result["final_run"]["status"] == "partial"
    latest = RunStore.open_existing(tmp_path / "store").resolve_latest_attempt()
    assert latest.run_id == result["final_run"]["run_id"]
    assert latest.manifest["input_verification"] == "unverified"
    captured[0].verify()


def test_metadata_derivation_retains_exact_noncanonical_parent_manifest_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import json
    import cppulse.workflows as workflows

    request = request_for(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('original material')",
    )
    original = workflows.collect
    original_bytes = []

    def noncanonical(*args: Any, **kwargs: Any) -> Any:
        snapshot = original(*args, **kwargs)
        # Clearly labeled local fixture emulating an older valid JSON layout.
        content = json.dumps(snapshot.manifest, separators=(",", ":")).encode()
        (snapshot.path / "run_manifest.json").write_bytes(content)
        original_bytes.append(content)
        return RunStore.open_existing(snapshot.path.parents[1]).open_run(
            snapshot.run_id, manifest_sha256=hashlib.sha256(content).hexdigest()
        )

    monkeypatch.setattr(workflows, "collect", noncanonical)
    result = collect_request(request, workspace=tmp_path, store=tmp_path / "store")
    assert result["status"] == "completed"
    final = RunStore.open_existing(tmp_path / "store").open_run(
        result["final_run"]["run_id"]
    )
    assert any(
        final.read_bytes(row["id"]) == original_bytes[0]
        for row in final.manifest["artifacts"]
        if row["path"].startswith("workflows/provenance/")
    )


def test_late_cancellation_advances_latest_attempt_to_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.workflows as workflows

    request = request_for(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('original material')",
    )
    token = CancellationToken()
    original = workflows._derive

    def cancel_after_metadata(*args: Any, **kwargs: Any) -> Any:
        child = original(*args, **kwargs)
        token.cancel()
        return child

    monkeypatch.setattr(workflows, "_derive", cancel_after_metadata)
    result = collect_request(
        request, workspace=tmp_path, store=tmp_path / "store", cancel=token
    )
    assert result["status"] == "cancelled" and result["exit_code"] == 130
    latest = RunStore.open_existing(tmp_path / "store").resolve_latest_attempt()
    assert (
        latest.run_id == result["final_run"]["run_id"]
        and latest.manifest["status"] == "cancelled"
    )


def test_post_capture_metadata_quota_preserves_pins_and_partial_attempt(
    tmp_path: Path,
) -> None:
    script = "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('original material')"
    seed = tmp_path / "seedcase"
    seed.mkdir()
    seed_request = request_for(seed, script)
    reference = collect_request(seed_request, workspace=seed, store=seed / "store")
    raw = RunStore.open_existing(seed / "store").open_run(
        reference["raw_run"]["run_id"]
    )
    limit = len(raw.read_manifest_bytes()) + 150
    case = tmp_path / "capcase0"
    case.mkdir()
    request = request_for(case, script)
    request["plan"]["limits"]["max_metadata_bytes"] = limit
    result = collect_request(request, workspace=case, store=case / "store")
    assert result["status"] == "partial" and result["exit_code"] == 3
    assert result["raw_run"]["status"] == "completed" and result["error"] is not None
    latest = RunStore.open_existing(case / "store").resolve_latest_attempt()
    assert (
        latest.run_id == result["final_run"]["run_id"]
        and latest.manifest["status"] == "partial"
    )
