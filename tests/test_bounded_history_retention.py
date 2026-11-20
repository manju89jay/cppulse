"""Archiving optional history sidecars does not manufacture producer evidence."""

from __future__ import annotations

from pathlib import Path

import pytest

from cppulse.importer import import_pipeline
from cppulse.run_store import RunStore
import test_pipeline_snapshot_import as fixtures


@pytest.fixture
def archive_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    return fixtures.bundle.__wrapped__(tmp_path)


@pytest.mark.parametrize(
    "payload", [b'{"records":[]}\n', b"not a valid JSON report\xff\n"]
)
def test_optional_history_sidecars_remain_exact_opaque_unverified_claims(
    archive_bundle: tuple[Path, Path, Path], payload: bytes
) -> None:
    output, source, store = archive_bundle
    for name in ("git_history.json", "git_behavior.json"):
        (output / name).write_bytes(payload)
    result = import_pipeline(output, source, store, run_id="opaque-history")
    snapshot = RunStore.open_existing(store).open_run(result["run_id"])
    snapshot.verify()
    assert snapshot.manifest["input_verification"] == "unverified"
    assert snapshot.manifest["contexts"] == []
    assert [stage["id"] for stage in snapshot.manifest["stages"]] == ["archive-import"]
    for name in ("git_history.json", "git_behavior.json"):
        descriptor = next(
            row for row in snapshot.manifest["artifacts"] if row["path"] == name
        )
        assert "contract" not in descriptor
        assert snapshot.read_bytes(descriptor["id"]) == payload
    assert not any(
        row.get("contract", {}).get("kind") in {"execution_receipt", "evidence"}
        for row in snapshot.manifest["artifacts"]
    )
    assert (
        snapshot.read_json("normalized-risk")["health_score"]["availability"]
        == "unverified"
    )
