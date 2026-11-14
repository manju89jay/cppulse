"""Import transformations over labeled synthetic archives, without tool execution."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.external import normalize_gcc_import, persist_gcc_import
from cppulse.identities import snapshot_inputs, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore
from test_contracts_v2 import manifest_document, policy_document
from test_gcc_diagnostics import PRODUCER, diagnostic


def archive(
    root: Path,
    raw: bytes | None = None,
    *,
    policy: bool = False,
    assessed: bool = False,
) -> tuple[RunSnapshot, RunStore, dict[str, Any]]:
    """Write clearly synthetic report claims with an actual local source identity."""
    (root / "src").mkdir(parents=True)
    (root / "src/main.cpp").write_text("int main() { return 0; }\n")
    raw_path = root / "input.json"
    raw_path.write_bytes(
        raw if raw is not None else json.dumps([diagnostic(), diagnostic()]).encode()
    )
    source = snapshot_inputs(
        root, ["src/main.cpp"], kind="application", inventory_complete=True
    )
    store = RunStore(root / "store")
    with store.begin() as stage:
        stage.copy_artifact(
            "raw-report", raw_path, "reports/gcc.json", "application/json"
        )
        manifest = manifest_document()
        manifest.update(
            run_id=stage.run_id, source=source, stages=[], artifacts=stage.artifacts
        )
        if policy or assessed:
            selected = policy_document()
            stage.write_json(
                "policy.json", selected, contract="policy", artifact_id="policy"
            )
        if assessed:
            from cppulse.policy import evaluate_policy

            manifest["input_verification"] = "verified"
            result = evaluate_policy(
                selected,
                {"run_manifest": manifest},
                generated_at=datetime.now(timezone.utc).isoformat(),
            )
            stage.write_json(
                "assessment.json",
                result,
                contract="assessment",
                artifact_id="assessment",
            )

        def check() -> None:
            assert not verify_inputs(root, source)

        manifest["artifacts"] = stage.artifacts
        snapshot = stage.publish(manifest, source_check=check)
    selection = {
        "report_artifact_id": "raw-report",
        "context_id": snapshot.manifest["contexts"][0]["id"],
        "source_root": "/project",
        "scope_files": ["src/main.cpp"],
        "producer": PRODUCER,
    }
    return snapshot, store, selection


def test_imports_preserve_origin_namespace_and_repeated_occurrences(
    tmp_path: Path,
) -> None:
    parent, _, selection = archive(tmp_path)
    result = normalize_gcc_import(parent, **selection)
    assert result["origin"] == "import" and result["scope_completeness"] == "unverified"
    assert result["receipt_id"] is None and result["proof_receipt_ids"] == []
    assert len(result["observations"]) == 2
    a, b = result["observations"]
    assert a["id"] != b["id"] and a["fingerprint"] == b["fingerprint"]
    assert a["namespaced_rule_id"] == "gcc:-Wunused-variable"


def test_empty_array_does_not_claim_complete_clean_scan(tmp_path: Path) -> None:
    parent, _, selection = archive(tmp_path, b"[]")
    result = normalize_gcc_import(parent, **selection)
    assert result["usability"] == "usable" and result["observations"] == []
    assert result["scope_completeness"] == "unverified"


def test_foreign_transfer_is_readable_but_cannot_publish_current_local_facts(
    tmp_path: Path,
) -> None:
    from cppulse.transfer import export_bundle

    parent, store, selection = archive(tmp_path)
    imported = export_bundle({"upstream": parent}, tmp_path / "transfer").open_run(
        "upstream"
    )
    assert normalize_gcc_import(imported, **selection)["origin"] == "import"
    with pytest.raises(ContractError, match="local RunSnapshot"):
        persist_gcc_import(imported, workspace=tmp_path, store=store, **selection)
    assert store.resolve_latest_attempt().run_id == parent.run_id


def test_derived_publication_preserves_raw_bytes_source_and_config(
    tmp_path: Path,
) -> None:
    parent, store, selection = archive(tmp_path)
    result = persist_gcc_import(parent, workspace=tmp_path, store=store, **selection)
    result.verify()
    assert result.run_id != parent.run_id
    assert result.manifest["config_digest"] == parent.manifest["config_digest"]
    assert result.manifest["source"] == parent.manifest["source"]
    by_id = {a["id"]: a for a in result.manifest["artifacts"]}
    for artifact in parent.manifest["artifacts"]:
        assert by_id[artifact["id"]] == artifact
        assert result.read_bytes(artifact["id"]) == parent.read_bytes(artifact["id"])
    repeated = persist_gcc_import(result, workspace=tmp_path, store=store, **selection)
    assert repeated.run_id == result.run_id
    provenance = next(
        a
        for a in result.manifest["artifacts"]
        if a["path"].endswith("-derivation.json")
    )
    mapping = json.loads(result.read_bytes(provenance["id"]))["selection"]
    assert mapping["source_root"] == selection["source_root"]
    assert mapping["producer_claim"] == PRODUCER


def test_repeated_import_still_checks_selected_source_freshness(tmp_path: Path) -> None:
    parent, store, selection = archive(tmp_path)
    derived = persist_gcc_import(parent, workspace=tmp_path, store=store, **selection)
    (tmp_path / "src/main.cpp").write_text("int changed;\n")
    with pytest.raises(InputChanged):
        persist_gcc_import(derived, workspace=tmp_path, store=store, **selection)
    assert store.resolve_latest_attempt().run_id == derived.run_id


def test_unassessed_policy_can_be_retained_but_assessment_is_not_reused(
    tmp_path: Path,
) -> None:
    parent, store, selection = archive(tmp_path / "policy-only", policy=True)
    persist_gcc_import(
        parent, workspace=tmp_path / "policy-only", store=store, **selection
    ).verify()
    parent, store, selection = archive(tmp_path / "assessed", assessed=True)
    with pytest.raises(ContractError, match="unassessed"):
        persist_gcc_import(
            parent, workspace=tmp_path / "assessed", store=store, **selection
        )


def test_idempotent_read_race_still_rechecks_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent, store, selection = archive(tmp_path)
    derived = persist_gcc_import(parent, workspace=tmp_path, store=store, **selection)
    identifier = normalize_gcc_import(derived, **selection)["id"]
    original = RunSnapshot.read_json

    def mutate(self: RunSnapshot, name: str, **kwargs: Any) -> dict[str, Any]:
        value = original(self, name, **kwargs)
        if self.run_id == derived.run_id and name == identifier:
            (tmp_path / "src/main.cpp").write_text("int changed_during_read;\n")
        return value

    monkeypatch.setattr(RunSnapshot, "read_json", mutate)
    with pytest.raises(InputChanged):
        persist_gcc_import(derived, workspace=tmp_path, store=store, **selection)
    assert store.resolve_latest_attempt().run_id == derived.run_id


def test_malformed_import_publishes_partial_without_erasing_previous_complete(
    tmp_path: Path,
) -> None:
    parent, store, selection = archive(tmp_path, b"invalid JSON")
    result = persist_gcc_import(parent, workspace=tmp_path, store=store, **selection)
    assert result.manifest["status"] == "partial"
    assert store.resolve_latest().run_id == parent.run_id
    assert store.resolve_latest_attempt().run_id == result.run_id


def test_corrupt_report_or_unknown_scope_is_not_promoted(tmp_path: Path) -> None:
    parent, _, selection = archive(tmp_path)
    with pytest.raises(ContractError):
        normalize_gcc_import(parent, **{**selection, "scope_files": ["missing.cpp"]})
    with pytest.raises(ContractError):
        normalize_gcc_import(parent, **{**selection, "context_id": "undeclared"})
    entry = next(a for a in parent.manifest["artifacts"] if a["id"] == "raw-report")
    (parent.path / entry["path"]).write_bytes(b"[]")
    with pytest.raises(IntegrityError):
        normalize_gcc_import(parent, **selection)


def test_normalization_reads_only_retained_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent, _, selection = archive(tmp_path)
    (tmp_path / "src/main.cpp").unlink()

    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Import must not execute tools")

    monkeypatch.setattr(subprocess, "run", reject)
    assert normalize_gcc_import(parent, **selection)["origin"] == "import"
