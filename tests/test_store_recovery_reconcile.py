"""Interrupted recovery retains its journal and never removes a newer writer."""

from pathlib import Path
import hashlib
import json

import pytest

from cppulse.errors import IntegrityError, PublicationConflict
from cppulse.run_store import RunStore
from cppulse.store_coordination import new_lock_document
import cppulse.store_recovery as recovery


def interrupted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    stage = store.root / ".staging" / "old-incarnation"
    stage.mkdir()
    (stage / "original.bin").write_bytes(b"original staged observation")
    lock = new_lock_document("old-incarnation", "a" * 32)
    lock["owner"]["start_ticks"] -= 1  # Explicit synthetic PID-reuse metadata.
    path = store.root / ".publication.lock"
    path.write_text(json.dumps(lock))
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    original = recovery._write_at

    def fail_final(parent: int, name: str, content: bytes):
        if name.endswith(".recovered.json"):
            raise OSError("Authored final receipt write interruption")
        return original(parent, name, content)

    with monkeypatch.context() as patch:
        patch.setattr(recovery, "_write_at", fail_final)
        with pytest.raises(OSError, match="Authored final"):
            recovery.recover_store_lock(
                store.root, expected_lock_sha256=sha, expected_lock_token=lock["token"]
            )
    assert not path.exists()
    assert len(list((store.root / ".recovery").glob("*.prepared.json"))) == 1
    return store, sha, lock["token"]


def test_after_unlock_reconciliation_observes_and_preserves_active_new_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, sha, token = interrupted(tmp_path, monkeypatch)
    with store.begin("new-writer"):
        path = store.root / ".publication.lock"
        current = path.read_bytes()
        report = recovery.inspect_recovery_receipt(
            store.root, expected_lock_sha256=sha, expected_lock_token=token
        )
        assert report["status"] == "reconcilable"
        assert path.read_bytes() == current
        result = recovery.recover_store_lock(
            store.root, expected_lock_sha256=sha, expected_lock_token=token
        )
        recovery.validate_recovery_report(result)
        recovery.verify_recovery_report(result)
        assert result["status"] == "reconciled"
        assert result["current_lock_sha256"] == hashlib.sha256(current).hexdigest()
        assert result["current_lock_action"] == "left_unchanged"
        assert result["source_journal"]["path"].endswith(".prepared.json")
        assert path.read_bytes() == current
        assert not (store.root / "latest.json").exists()


def test_corrupt_archived_receipt_never_reconciles_or_touches_new_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, sha, token = interrupted(tmp_path, monkeypatch)
    archive = next((store.root / ".recovery").glob("*.lock.json"))
    archive.write_bytes(b"changed")
    with store.begin("new-writer"):
        path = store.root / ".publication.lock"
        current = path.read_bytes()
        with pytest.raises((IntegrityError, PublicationConflict)):
            recovery.recover_store_lock(
                store.root, expected_lock_sha256=sha, expected_lock_token=token
            )
        assert path.read_bytes() == current


def test_stored_reconciliation_journal_corruption_is_detected_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, sha, token = interrupted(tmp_path, monkeypatch)
    result = recovery.recover_store_lock(
        store.root, expected_lock_sha256=sha, expected_lock_token=token
    )
    recovery.verify_recovery_report(result)
    journal = Path(result["source_journal"]["path"])
    journal.write_bytes(journal.read_bytes() + b" ")
    before = {
        str(path.relative_to(store.root)): path.read_bytes()
        for path in store.root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(IntegrityError, match="journal changed"):
        recovery.verify_recovery_report(result)
    assert before == {
        str(path.relative_to(store.root)): path.read_bytes()
        for path in store.root.rglob("*")
        if path.is_file()
    }
