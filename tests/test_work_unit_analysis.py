"""Actual immutable bounded publication to full-scope replay regressions."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from cppulse.contracts.work_unit_analysis import validate_analysis_scope
from cppulse.errors import ContractError, IntegrityError
from cppulse.identities import digest_json
from cppulse.run_store import RunStore
from cppulse.work_unit_analysis import read_work_unit_analysis
import test_bounded_pipeline as fixtures


@pytest.fixture(scope="module")
def published(tmp_path_factory: pytest.TempPathFactory):
    import cppulse.pipeline as pipeline

    root = tmp_path_factory.mktemp("unit-analysis")
    config = fixtures.config(root)
    (config.repo / "second.cpp").write_text("int second() { return 2; }\n")
    with pytest.MonkeyPatch.context() as patch:
        fixtures.select_native(patch, fixtures.native.__wrapped__())
        summary = pipeline.analyze(config, report_format="json", timeout=60)
    snapshot = RunStore(config.output).open_run(summary["run_id"])
    return snapshot


class Altered:
    """Retain genuine bytes except specific explicitly edited metadata inputs."""

    def __init__(self, snapshot: Any):
        self.original = snapshot
        self.manifest = deepcopy(snapshot.manifest)
        self.edits: dict[str, Any] = {}

    def verify(self) -> None:
        self.original.verify()

    def read_bytes(self, identifier: str) -> bytes:
        if identifier in self.edits:
            return json.dumps(self.edits[identifier]).encode()
        return self.original.read_bytes(identifier)

    def read_json(self, identifier: str) -> Any:
        if identifier in self.edits:
            return deepcopy(self.edits[identifier])
        return self.original.read_json(identifier)

    def edit(self, identifier: str) -> Any:
        if identifier not in self.edits:
            self.edits[identifier] = json.loads(self.original.read_bytes(identifier))
        return self.edits[identifier]


def test_replays_actual_receipts_after_source_and_worker_paths_removed(published):
    plan = json.loads(published.read_bytes("analysis-plan"))
    source, worker = Path(plan["source_root"]), Path(plan["work_root"])
    source_moved, worker_moved = source.with_name("source-removed"), worker.with_name(
        "work-removed"
    )
    source.rename(source_moved)
    worker.rename(worker_moved)
    try:
        replay = read_work_unit_analysis(published)
    finally:
        source_moved.rename(source)
        worker_moved.rename(worker)
    assert len(replay.scope["units"]) == len(replay.units) == 2
    assert replay.scope["source_digest"] == published.manifest["source"]["digest"]
    assert all(row["outcome"] == "complete" for row in replay.scope["units"])
    assert all(unit.report is not None for unit in replay.units)
    for row, unit in zip(replay.scope["units"], replay.units):
        binding = row["execution"]
        assert binding["receipt_id"] == unit.result["execution_receipt"]["id"]
        assert binding["declared_context_id"] != binding["invocation_context_id"]
        assert binding["request_sha256"] == digest_json(unit.request)


@pytest.mark.parametrize("field", ["unit_id", "primary_file"])
def test_scope_rejects_duplicate_ownership(published, field):
    scope = deepcopy(read_work_unit_analysis(published).scope)
    scope["units"][1][field] = scope["units"][0][field]
    with pytest.raises(ContractError):
        validate_analysis_scope(scope)


def test_absent_execution_cannot_supply_analyzed_parse_or_success(published):
    scope = deepcopy(read_work_unit_analysis(published).scope)
    scope["units"][0]["execution"] = None
    with pytest.raises(ContractError, match="Absent original"):
        validate_analysis_scope(scope)


def test_missing_unit_retains_full_scope_without_fabricated_receipt(published):
    changed = Altered(published)
    bindings = changed.edit("analysis-bindings")
    removed = bindings["units"].pop()
    summary = changed.edit("analysis-summary")
    summary["results"] = [
        r for r in summary["results"] if r["unit_id"] != removed["unit_id"]
    ]
    replay = read_work_unit_analysis(changed)
    assert len(replay.scope["units"]) == 2
    assert len(replay.units) == 1
    missing = next(
        row for row in replay.scope["units"] if row["unit_id"] == removed["unit_id"]
    )
    assert missing["outcome"] == "not_attempted"
    assert missing["parse_status"] is None
    assert missing["execution"] is None


@pytest.mark.parametrize(
    "kind", ["result", "receipt", "input", "output", "plan", "bindings"]
)
def test_rejects_broken_immutable_binding_links(published, kind):
    changed = Altered(published)
    bindings = changed.edit("analysis-bindings")
    link = bindings["units"][0]
    if kind == "result":
        changed.edit(link["result_artifact_id"])["reason"] += " edited"
    elif kind == "receipt":
        changed.edits[link["receipt_artifact_id"]] = deepcopy(
            published.read_json(link["receipt_artifact_id"])
        )
        changed.edits[link["receipt_artifact_id"]]["id"] += "-other"
    elif kind == "input":
        link["inputs"].pop("configuration")
    elif kind == "output":
        link["outputs"].pop()
    elif kind == "plan":
        changed.edit("analysis-plan")["native_sha256"] = "a" * 64
    else:
        bindings["units"].append(deepcopy(link))
    with pytest.raises((IntegrityError, ContractError)):
        read_work_unit_analysis(changed)


def test_normalizes_actual_units_as_one_declared_scope_without_fake_execution(
    published,
):
    from cppulse.work_unit_analysis import normalize_work_unit_analysis

    result = normalize_work_unit_analysis(published)
    assert len(result.analyses) == len(result.bindings) == 2
    assert result.scope["job_context_id"] == result.job_context["id"]
    assert result.job_context["provenance"] == "inferred"
    for normalized, binding in zip(result.analyses, result.bindings):
        assert normalized.inventory["job_context_id"] == result.job_context["id"]
        assert (
            normalized.inventory["receipt_id"]
            == binding["result"]["execution_receipt"]["id"]
        )
        assert normalized.inventory["items"][0]["buffer_coherence"] == "verified"
        assert normalized.inventory["items"][0]["context_match"] == "unverified"
        assert normalized.metrics is not None


def test_persists_original_units_and_full_scope_then_measured_health(
    published, tmp_path
):
    from cppulse.work_unit_analysis import persist_work_unit_analysis
    from cppulse.maintenance import persist_maintenance_health
    from cppulse.workflows import read_documents

    plan = json.loads(published.read_bytes("analysis-plan"))
    store = RunStore(tmp_path / "derived-store")
    derived = persist_work_unit_analysis(
        published, workspace=Path(plan["source_root"]), store=store
    )
    derived.verify()
    documents = read_documents(derived)
    assert len(documents["analysis_scope"]) == 1
    assert len(documents["work_unit_analysis_binding"]) == 2
    assert "execution_facts" not in documents
    scope = documents["analysis_scope"][0]
    scored = persist_maintenance_health(
        derived,
        workspace=Path(plan["source_root"]),
        store=store,
        required_context_ids=[scope["job_context_id"]],
        allow_inferred_parse=True,
    )
    scored.verify()
    health = read_documents(scored)["maintenance_health"][-1]
    assert health["scorer"]["id"] == "analyzed-kloc-context-v4"
    # Fallback is not a recorded inferred compilation command. Opting into
    # inferred parse arguments must not turn fallback evidence into a score.
    assert health["aggregate"]["overall"] is None
    assert health["contexts"][0]["declared_files"] == 2


def test_actual_database_command_public_pipeline_stores_measured_health(
    tmp_path, monkeypatch
):
    import cppulse.pipeline as pipeline
    from cppulse.workflows import read_documents

    cfg = fixtures.config(tmp_path)
    (cfg.repo / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(cfg.repo),
                    "file": str(cfg.repo / "main.cpp"),
                    "arguments": [
                        "clang++",
                        "-std=c++17",
                        "-c",
                        str(cfg.repo / "main.cpp"),
                    ],
                }
            ]
        )
    )
    fixtures.select_native(monkeypatch, fixtures.native.__wrapped__())
    summary = pipeline.analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(summary["run_id"])
    documents = read_documents(snapshot)
    assert documents["analysis_inventory"][0]["items"][0]["context_match"] == "matched"
    assert (
        documents["analysis_inventory"][0]["items"][0]["buffer_coherence"] == "verified"
    )
    health = documents["maintenance_health"][-1]
    assert health["aggregate"]["overall"] == 100
    assert health["contexts"][0]["declared_files"] == 1


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_rejects_invalid_bridge_aggregate_byte_budget(published, limit):
    with pytest.raises(ContractError, match="positive integers"):
        read_work_unit_analysis(published, max_input_bytes=limit)


@pytest.mark.parametrize("field", ["max_input_bytes", "max_report_bytes"])
def test_retained_bridge_budget_failure_is_explicit_without_partial_success(
    published, field
):
    with pytest.raises(IntegrityError, match="bridge byte budget"):
        read_work_unit_analysis(published, **{field: 1})


def test_replay_deduplicates_shared_retained_input_bytes(published):
    replay = read_work_unit_analysis(published)
    assert len(replay.units) == 2
    assert (
        replay.units[0].inputs["rule_registry"]
        is replay.units[1].inputs["rule_registry"]
    )
    assert (
        replay.units[0].inputs["resource_manifest"]
        is replay.units[1].inputs["resource_manifest"]
    )


def test_actual_cross_unit_duplication_is_global_not_per_unit_zero(
    tmp_path, monkeypatch
):
    import cppulse.pipeline as pipeline
    from cppulse.workflows import read_documents

    cfg = fixtures.config(tmp_path)
    source = """int example(int n) {
    int total = 0;
    for (int i = 0; i < n; ++i) {
        total += i * 3;
        if (total % 5 == 0) { total += 2; }
        if (total % 7 == 0) { total -= 1; }
    }
    return total;
}
"""
    (cfg.repo / "main.cpp").write_text(source)
    (cfg.repo / "copy.cpp").write_text(source)
    fixtures.select_native(monkeypatch, fixtures.native.__wrapped__())
    summary = pipeline.analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(summary["run_id"])
    documents = read_documents(snapshot)
    duplicates = [
        item
        for document in documents["analysis_metrics"]
        for item in document["items"]
        if item["metric"] == "duplicate_tokens"
    ]
    assert len(duplicates) == 2
    assert all(
        item["availability"] == "available" and item["value"] > 30
        for item in duplicates
    )
    assert duplicates[0]["value"] == duplicates[1]["value"]


@pytest.mark.parametrize(
    "header,qualified", [("__stddef_size_t.h", True), ("stddef.h", False)]
)
def test_actual_used_sdk_bytes_qualify_only_checked_closed_buffers(
    tmp_path, monkeypatch, header, qualified
):
    import cppulse.pipeline as pipeline
    from cppulse.workflows import read_documents

    cfg = fixtures.config(tmp_path)
    (cfg.repo / "main.cpp").write_text(
        f"#include <{header}>\nint value() {{ return 0; }}\n"
    )
    (cfg.repo / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(cfg.repo),
                    "file": str(cfg.repo / "main.cpp"),
                    "arguments": [
                        "clang++",
                        "-std=c++17",
                        "-c",
                        str(cfg.repo / "main.cpp"),
                    ],
                }
            ]
        )
    )
    fixtures.select_native(monkeypatch, fixtures.native.__wrapped__())
    summary = pipeline.analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(summary["run_id"])
    documents = read_documents(snapshot)
    proof = documents["used_sdk_inputs"][0]
    entries = proof["units"][0]["entries"]
    assert entries and all(entry["status"] == "available" for entry in entries)
    binding = documents["work_unit_analysis_binding"][0]
    assert binding["sdk_used_inputs_artifact_id"] == "sdk-used-inputs"
    inventory = documents["analysis_inventory"][0]["items"][0]
    health = documents["maintenance_health"][-1]
    if qualified:
        assert inventory["buffer_coherence"] == "verified"
        assert inventory["context_match"] == "matched"
        assert health["aggregate"]["overall"] == 100
    else:
        assert inventory["buffer_coherence"] == "unverified"
        assert inventory["context_match"] == "unverified"
        assert health["aggregate"]["overall"] is None
        assert any(
            "query" in reason or "preprocessing" in reason
            for reason in inventory["limitations"]
        )


@pytest.mark.parametrize("content", [b"{", b'{"n":NaN}', b"[" * 2000 + b"]" * 2000])
def test_malformed_nonfinite_or_deep_retained_role_json_is_a_contract_error(content):
    from cppulse.work_unit_analysis import _retained_json

    with pytest.raises(ContractError):
        _retained_json(content, "boundary")


def test_public_bridge_type_annotations_resolve_without_local_runtime_context():
    from typing import get_type_hints
    from cppulse.work_unit_analysis import (
        normalize_work_unit_analysis,
        persist_work_unit_analysis,
    )

    for function in [
        read_work_unit_analysis,
        normalize_work_unit_analysis,
        persist_work_unit_analysis,
    ]:
        annotations = get_type_hints(function)
        assert "return" in annotations
    assert get_type_hints(persist_work_unit_analysis)["workspace"] is Path
