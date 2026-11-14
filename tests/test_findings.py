"""Source-byte finding workflows over explicitly synthetic retained native facts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import pytest

from cppulse.analysis import persist_native_analysis
from cppulse.contracts import validate
from cppulse.contracts.finding_workflows import anchor_fingerprint
from cppulse.errors import ContractError, IntegrityError
from cppulse.findings import compare_findings, create_finding_baseline
from cppulse.identities import verify_inputs
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.transfer import export_bundle
from test_analysis_inventory import _finding, native_snapshot

TRIGGER = "int main() { return (int)0.5; }\n"
SCOPE = {
    "scope_files": ["main.cpp"],
    "context_ids": ["native"],
    "rule_ids": ["CPP-MOD-001"],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized(
    root: Path,
    *,
    prefix: str = "",
    count: int = 1,
    partial: bool = False,
    ambiguous: bool = False,
    flags: bool = False,
    verified: bool = True,
    code: str = TRIGGER,
    column: int = 1,
) -> RunSnapshot:
    """Transform labeled fake records; actual native execution is a separate gate."""

    def mutate(report: dict[str, Any], workspace: Path) -> None:
        if count:
            _finding(report, workspace, partial=partial)
            report["findings"] *= count
            for row in report["findings"]:
                row["line"] = len(prefix.splitlines()) + 1
                row["column"] = column
            report["summary"]["total_findings"] = count
            report["summary"]["by_category"]["modernization"] = count
            report["summary"]["by_severity"]["warning"] = count
        (workspace / "main.cpp").write_text(prefix + code + (code if ambiguous else ""))
        report["metadata"]["total_loc"] = len((prefix + code).splitlines()) + int(
            ambiguous
        )
        if flags:
            database = json.loads((workspace / "compile_commands.json").read_bytes())
            database[0]["arguments"].insert(1, "-DS7_CHANGED_CONTEXT=1")
            (workspace / "compile_commands.json").write_text(json.dumps(database))
            report["metadata"]["analysis"]["files"][0]["parse_arguments"].append(
                "-DS7_CHANGED_CONTEXT=1"
            )

    raw, selection = native_snapshot(root, mutate=mutate, verified=verified)
    return persist_native_analysis(
        raw, workspace=root, store=root / "normalized", **selection
    )


def retain(
    parent: RunSnapshot,
    result: Any,
    kind: str,
    store: Path,
    workspace: Path,
    artifact_id: str = "baseline",
) -> RunSnapshot:
    """Test-only publication; production writer belongs to the CLI workflow."""
    runtime = RunStore(store)
    with runtime.begin() as stage:
        known = {row["id"] for row in parent.manifest["artifacts"]}
        for entry in parent.manifest["artifacts"]:
            stage.copy_artifact(
                entry["id"],
                parent.path / entry["path"],
                entry["path"],
                entry["media_type"],
                contract=entry.get("contract"),
            )
        with tempfile.TemporaryDirectory() as temporary:
            for index, blob in enumerate(result.artifacts):
                if blob.id in known:
                    continue
                path = Path(temporary) / str(index)
                path.write_bytes(blob.content)
                stage.copy_artifact(blob.id, path, blob.path, blob.media_type)
        stage.write_json(
            "findings/" + artifact_id + ".json",
            result.document,
            contract=kind,
            artifact_id=artifact_id,
        )
        manifest = parent.manifest
        manifest.update(
            run_id=stage.run_id, artifacts=stage.artifacts, finished_at=now()
        )

        def check() -> None:
            assert not verify_inputs(workspace, manifest["source"])

        return stage.publish(
            manifest,
            source_check=(
                check if manifest["input_verification"] == "verified" else None
            ),
        )


def baseline(
    root: Path, *, count: int = 1, ambiguous: bool = False
) -> tuple[RunSnapshot, Any]:
    original = normalized(root, count=count, ambiguous=ambiguous)
    result = create_finding_baseline(
        original,
        baseline_id="selected-baseline",
        reason="Labeled synthetic baseline fixture",
        created_at=now(),
        **SCOPE,
    )
    return (
        retain(original, result, "finding_baseline", root / "baselines", root),
        result,
    )


def compare(current: RunSnapshot, old: Any, **options: Any):
    return compare_findings(
        current,
        old,
        baseline_artifact_id="baseline",
        generated_at=now(),
        **SCOPE,
        **options,
    )


def test_baseline_hashes_checked_source_and_preserves_native_fingerprint(
    tmp_path: Path,
) -> None:
    original = normalized(tmp_path)
    before = original.manifest
    observations = [
        original.read_json(row["id"])
        for row in before["artifacts"]
        if row.get("contract", {}).get("kind") == "observations"
    ][0]
    result = create_finding_baseline(
        original,
        baseline_id="baseline",
        reason="Selected synthetic facts",
        created_at=now(),
        **SCOPE,
    )
    document = result.document
    validate("finding_baseline", document)
    assert (
        document["findings"][0]["anchor_sha256"]
        == hashlib.sha256(TRIGGER.rstrip("\n").encode()).hexdigest()
    )
    assert (
        document["findings"][0]["fingerprint"]
        != observations["items"][0]["fingerprint"]
    )
    assert observations["items"][0]["fingerprint_version"] == "native-1"
    assert document["cells"][0]["status"] == "complete"
    assert original.manifest == before


def test_line_insertion_preserves_anchored_multiset_with_exact_context(
    tmp_path: Path,
) -> None:
    old, _ = baseline(tmp_path)
    current = normalized(tmp_path, prefix="// inserted line\n\n")
    result = compare(current, old)
    assert result.document["gate"] == "passed"
    assert result.document["counts"] == {
        "current": 1,
        "baseline": 1,
        "new": 0,
        "unchanged": 1,
        "resolved": 0,
        "unknown_current": 0,
        "unknown_baseline": 0,
        "suppressed_new": 0,
        "unsuppressed_new": 0,
    }


@pytest.mark.parametrize(
    "before,after,new,resolved",
    [(1, 2, 1, 0), (2, 1, 0, 1), (0, 1, 1, 0), (1, 0, 0, 1)],
)
def test_duplicate_occurrences_are_multisets_not_fingerprint_deduplication(
    tmp_path, before, after, new, resolved
):
    old, _ = baseline(tmp_path, count=before)
    current = normalized(tmp_path, count=after)
    result = compare(current, old)
    assert result.document["counts"]["new"] == new
    assert result.document["counts"]["resolved"] == resolved
    assert result.document["counts"]["current"] == after
    assert result.document["counts"]["baseline"] == before
    assert result.document["gate"] == ("failed" if new else "passed")


@pytest.mark.parametrize(
    "old_ambiguous,current_ambiguous", [(True, False), (False, True), (True, True)]
)
def test_repeated_source_lines_are_unknown_anchors_not_hidden_matches(
    tmp_path, old_ambiguous, current_ambiguous
):
    old, _ = baseline(tmp_path, ambiguous=old_ambiguous)
    current = normalized(tmp_path, ambiguous=current_ambiguous)
    result = compare(current, old)
    assert result.document["gate"] == "insufficient_evidence"
    assert result.document["counts"]["new"] == 0
    assert result.document["counts"]["unknown_current"] == 1
    assert result.document["counts"]["unknown_baseline"] == 1


def test_changed_context_is_unknown_even_when_line_anchor_matches(tmp_path):
    old, _ = baseline(tmp_path)
    current = normalized(tmp_path, flags=True)
    result = compare(current, old)
    assert result.document["comparable"] is False
    assert result.document["gate"] == "insufficient_evidence"
    assert result.document["counts"]["unknown_current"] == 1


def test_current_partial_known_new_fails_without_claiming_complete_absence(tmp_path):
    old, _ = baseline(tmp_path, count=0)
    current = normalized(tmp_path, count=1, partial=True)
    result = compare(current, old)
    assert result.document["gate"] == "failed"
    assert result.document["incomplete"] is True
    assert result.document["counts"]["new"] == 1


def test_historical_imported_baseline_uses_frozen_raw_bytes_without_source_recheck(
    tmp_path,
):
    old, _ = baseline(tmp_path)
    imported = export_bundle({"baseline": old}, tmp_path / "transfer").open_run(
        "baseline"
    )
    current = normalized(tmp_path, prefix="// shifted\n")
    result = compare(current, imported)
    assert result.document["gate"] == "passed"
    assert any(
        "unauthenticated" in row.lower() for row in result.document["limitations"]
    )
    with pytest.raises(ContractError):
        compare_findings(
            imported, old, baseline_artifact_id="baseline", generated_at=now(), **SCOPE
        )


def test_unknown_current_source_binding_cannot_be_a_definite_new_or_pass(tmp_path):
    old, _ = baseline(tmp_path, count=0)
    original = normalized(tmp_path)
    # The gated normalizer correctly rejects unverified raw collection. This
    # test archives already typed facts without a new current-source check.
    with RunStore(tmp_path / "unverified").begin() as stage:
        for entry in original.manifest["artifacts"]:
            if entry.get("contract", {}).get("kind") == "analysis_inventory":
                claimed = original.read_json(entry["id"])
                claimed["compilation_database_artifact_id"] = None
                for row in claimed["items"]:
                    row.update(context_source="fallback", context_match="unverified")
                stage.write_json(
                    entry["path"],
                    claimed,
                    contract=entry["contract"],
                    artifact_id=entry["id"],
                )
                continue
            stage.copy_artifact(
                entry["id"],
                original.path / entry["path"],
                entry["path"],
                entry["media_type"],
                contract=entry.get("contract"),
            )
        manifest = original.manifest
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        current = stage.publish(manifest)
    result = compare(current, old)
    assert result.document["gate"] == "insufficient_evidence"
    assert result.document["counts"]["new"] == 0
    assert result.document["counts"]["unknown_current"] == 1


def test_comparison_retains_exact_original_baseline_and_manifest_raw_roles(tmp_path):
    old, _ = baseline(tmp_path)
    current = normalized(tmp_path, prefix="// moved\n")
    result = compare(current, old)
    blobs = {blob.id: blob for blob in result.artifacts}
    assert blobs[result.document["baseline_artifact_id"]].content == old.read_bytes(
        "baseline"
    )
    original = old.read_json("baseline")
    assert blobs[
        result.document["baseline_manifest_artifact_id"]
    ].content == old.read_bytes(original["original_manifest_artifact_id"])
    published = retain(
        current,
        result,
        "finding_comparison",
        tmp_path / "comparisons",
        tmp_path,
        "comparison",
    )
    published.verify()
    assert published.read_json("comparison") == result.document


def test_suppression_is_expiring_exact_bounded_and_does_not_change_raw_facts(tmp_path):
    old, _ = baseline(tmp_path, count=0)
    current = normalized(tmp_path, count=2)
    first = compare(current, old)
    group = first.document["groups"][0]
    cell = create_finding_baseline(
        current,
        baseline_id="inspection",
        reason="Synthetic metadata selection",
        created_at=now(),
        **SCOPE,
    ).document
    record = {
        "id": "selected-exception",
        "gate": "finding_regression",
        "baseline_sha256": first.document["baseline_sha256"],
        "fingerprint_version": "native-line-anchor-1",
        "fingerprint": group["fingerprint"],
        "file": "main.cpp",
        "context_id": "native",
        "parse_context_digest": cell["cells"][0]["parse_context_digest"],
        "rule_id": "CPP-MOD-001",
        "rule_version": cell["findings"][0]["rule_version"],
        "max_count": 1,
        "reason": "Explicit synthetic reviewed scope",
        "owner": "fixture-owner",
        "approved_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    raw = (
        current.read_bytes("normalized-observations")
        if any(
            row["id"] == "normalized-observations"
            for row in current.manifest["artifacts"]
        )
        else deepcopy(current.manifest)
    )
    result = compare(current, old, suppressions=[record])
    assert result.document["counts"]["new"] == 2
    assert result.document["counts"]["suppressed_new"] == 1
    assert result.document["counts"]["unsuppressed_new"] == 1
    assert result.document["gate"] == "failed"
    record["max_count"] = 2
    result = compare(current, old, suppressions=[record])
    assert result.document["gate"] == "passed"
    assert result.document["counts"]["new"] == 2
    record["expires_at"] = record["approved_at"][:-6] + "+00:00"
    # Structurally invalid lifetime is rejected rather than authorized.
    with pytest.raises(ContractError):
        compare(current, old, suppressions=[record])
    if isinstance(raw, dict):
        assert current.manifest == raw


def test_pure_workflow_never_executes_or_reads_the_live_project(tmp_path, monkeypatch):
    old, _ = baseline(tmp_path)
    current = normalized(tmp_path, prefix="// moved\n")
    (tmp_path / "main.cpp").unlink()

    def reject(*args, **kwargs):
        raise AssertionError(
            "Finding producer must only read checked retained artifacts"
        )

    monkeypatch.setattr(subprocess, "run", reject)
    monkeypatch.setattr(subprocess, "Popen", reject)
    assert compare(current, old).document["gate"] == "passed"


def test_tampered_retained_source_or_baseline_is_not_reinterpreted(tmp_path):
    old, _ = baseline(tmp_path)
    current = normalized(tmp_path)
    baseline_entry = next(
        row for row in old.manifest["artifacts"] if row["id"] == "baseline"
    )
    (old.path / baseline_entry["path"]).write_text("{}")
    with pytest.raises(IntegrityError):
        compare(current, old)


def test_schema_valid_forged_anchor_is_reconstructed_from_original_source(tmp_path):
    original = normalized(tmp_path)
    result = create_finding_baseline(
        original,
        baseline_id="forged-metadata",
        reason="Explicit adversarial synthetic fixture",
        created_at=now(),
        **SCOPE,
    )
    row = result.document["findings"][0]
    row["anchor_sha256"] = "0" * 64
    row["fingerprint"] = anchor_fingerprint(row)
    # The document is internally consistent and its publication has valid
    # checked bytes. Only reconstruction from retained source exposes the lie.
    validate("finding_baseline", result.document)
    archived = retain(
        original, result, "finding_baseline", tmp_path / "forged", tmp_path
    )
    archived.verify()
    with pytest.raises(IntegrityError, match="retained original source"):
        compare(original, archived)


def test_exact_suppression_bytes_are_retained_and_wrong_scope_or_time_is_inactive(
    tmp_path,
):
    old, _ = baseline(tmp_path, count=0)
    current = normalized(tmp_path)
    initial = compare(current, old).document
    metadata = create_finding_baseline(
        current,
        baseline_id="scope-inspection",
        reason="Synthetic suppression metadata",
        created_at=now(),
        **SCOPE,
    ).document
    instant = datetime.now(timezone.utc)
    request = {
        "id": "finite-review",
        "gate": "finding_regression",
        "baseline_sha256": initial["baseline_sha256"],
        "fingerprint_version": "native-line-anchor-1",
        "fingerprint": initial["groups"][0]["fingerprint"],
        "file": "main.cpp",
        "context_id": "native",
        "parse_context_digest": metadata["cells"][0]["parse_context_digest"],
        "rule_id": "CPP-MOD-001",
        "rule_version": metadata["findings"][0]["rule_version"],
        "max_count": 1,
        "reason": "Explicit narrow synthetic review",
        "owner": "fixture-owner",
        "approved_at": (instant - timedelta(hours=1)).isoformat(),
        "expires_at": (instant + timedelta(hours=1)).isoformat(),
    }
    raw = json.dumps({"records": [request], "version": "2.0.0"}, indent=4).encode()
    accepted = compare(current, old, suppression_bytes=raw)
    artifact = next(
        blob
        for blob in accepted.artifacts
        if blob.id == accepted.document["suppressions_artifact_id"]
    )
    assert artifact.content == raw
    assert accepted.document["gate"] == "passed"
    for changes in (
        {"baseline_sha256": "0" * 64},
        {"parse_context_digest": "0" * 64},
        {"expires_at": (instant - timedelta(minutes=1)).isoformat()},
        {
            "approved_at": (instant + timedelta(minutes=1)).isoformat(),
            "expires_at": (instant + timedelta(hours=2)).isoformat(),
        },
    ):
        rejected = compare(current, old, suppressions=[{**request, **changes}]).document
        assert rejected["gate"] == "failed"
        assert rejected["counts"]["new"] == rejected["counts"]["unsuppressed_new"] == 1
        assert rejected["suppressions"][0]["active"] is False
        assert rejected["suppressions"][0]["inactive_reason"]
    with pytest.raises(ContractError, match="differ"):
        compare(
            current,
            old,
            suppressions=[{**request, "max_count": 2}],
            suppression_bytes=raw,
        )
