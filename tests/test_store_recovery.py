"""Explicit local dead-writer recovery never treats old facts as fresh success."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.run_store import RunStore
from cppulse.store_coordination import GUARD_NAME, new_lock_document, publication_guard


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_writer_lock_records_actual_local_process_incarnation(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    with store.begin("selected"):
        lock = json.loads((store.root / ".publication.lock").read_bytes())
        assert lock["version"] == "2.0.0"
        assert lock["pid"] == os.getpid()
        assert lock["owner"]["status"] == "available"
        assert lock["owner"]["start_ticks"] > 0


def test_live_owner_cannot_be_recovered_and_inspection_is_read_only(
    tmp_path: Path,
) -> None:
    from cppulse.store_recovery import inspect_store_lock, recover_store_lock

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    with store.begin("selected"):
        path = store.root / ".publication.lock"
        raw = path.read_bytes()
        lock = json.loads(raw)
        before = {
            str(p.relative_to(store.root)): p.read_bytes()
            for p in store.root.rglob("*")
            if p.is_file()
        }
        report = inspect_store_lock(store.root)
        assert report["status"] == "protected"
        assert report["owner_observation"]["status"] == "alive"
        with pytest.raises(PublicationConflict):
            recover_store_lock(
                store.root,
                expected_lock_sha256=digest(path),
                expected_lock_token=lock["token"],
            )
        assert before == {
            str(p.relative_to(store.root)): p.read_bytes()
            for p in store.root.rglob("*")
            if p.is_file()
        }


def test_actual_owned_child_death_preserves_lock_stage_and_allows_new_writer(
    tmp_path: Path,
) -> None:
    from cppulse.store_recovery import (
        inspect_store_lock,
        recover_store_lock,
        validate_recovery_report,
    )

    root = tmp_path / "store"
    marker = tmp_path / "ready.json"
    payload = tmp_path / "input.bin"
    payload.write_bytes(b"retained original staged bytes")
    program = """from pathlib import Path
import json,os,sys,time
from cppulse.run_store import RunStore
with RunStore(sys.argv[1],format_version="2.0.0").begin("owned-child") as stage:
 stage.copy_artifact("original",Path(sys.argv[3]),"original.bin")
 Path(sys.argv[2]).write_text(json.dumps({"pid":os.getpid(),"stage":str(stage.path)}))
 while True:time.sleep(.1)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", program, str(root), str(marker), str(payload)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            assert child.poll() is None
            time.sleep(0.02)
        assert marker.exists()
        lock_path = root / ".publication.lock"
        raw = lock_path.read_bytes()
        lock = json.loads(raw)
        stage = Path(json.loads(marker.read_text())["stage"])
        original_sha = digest(stage / "original.bin")
        child.send_signal(signal.SIGKILL)
        child.wait(timeout=10)
        assert inspect_store_lock(root)["status"] == "eligible"
        result = recover_store_lock(
            root,
            expected_lock_sha256=hashlib.sha256(raw).hexdigest(),
            expected_lock_token=lock["token"],
        )
        validate_recovery_report(result)
        assert result["status"] == "recovered"
        assert result["owner_observation"]["status"] in {"absent", "zombie"}
        assert Path(result["preserved_lock"]["path"]).read_bytes() == raw
        assert digest(stage / "original.bin") == original_sha
        assert not lock_path.exists()
        assert not (root / "latest.json").exists()
        assert not (root / "latest_attempt.json").exists()
        with RunStore(root, format_version="2.0.0").begin("fresh-after-recovery"):
            pass
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        child.communicate(timeout=10)


@pytest.mark.parametrize("kind", ["legacy", "foreign", "unavailable"])
def test_unknown_or_foreign_owner_remains_protected(tmp_path: Path, kind: str) -> None:
    from cppulse.store_recovery import inspect_store_lock, recover_store_lock

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    token = "a" * 32
    lock = new_lock_document("abandoned", token)
    if kind == "legacy":
        lock = {"pid": os.getpid(), "run_id": "abandoned", "token": token}
    elif kind == "foreign":
        lock["owner"]["boot_id"] = "00000000-0000-0000-0000-000000000000"
    else:
        lock["owner"] = {
            "status": "unavailable",
            "boot_id": None,
            "start_ticks": None,
            "pid_namespace": None,
            "uid": None,
            "reason": "Unsupported original owner platform.",
        }
    path = store.root / ".publication.lock"
    path.write_text(json.dumps(lock))
    before = path.read_bytes()
    assert inspect_store_lock(store.root)["status"] == "protected"
    with pytest.raises((PublicationConflict, IntegrityError)):
        recover_store_lock(
            store.root, expected_lock_sha256=digest(path), expected_lock_token=token
        )
    assert path.read_bytes() == before


def test_pid_reuse_observation_never_signals_the_current_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse.store_recovery import recover_store_lock

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    lock = new_lock_document("old-incarnation", "b" * 32)
    lock["owner"]["start_ticks"] -= 1
    path = store.root / ".publication.lock"
    path.write_text(json.dumps(lock))
    monkeypatch.setattr(
        os, "kill", lambda *args: pytest.fail("Recovery must not signal any process")
    )
    result = recover_store_lock(
        store.root, expected_lock_sha256=digest(path), expected_lock_token=lock["token"]
    )
    assert result["owner_observation"]["status"] == "pid_reused"
    assert result["status"] == "recovered"


def test_wrong_selected_lock_identity_never_changes_owner_file(tmp_path: Path) -> None:
    from cppulse.store_recovery import recover_store_lock

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    lock = new_lock_document("selected", "c" * 32)
    lock["owner"]["start_ticks"] -= 1
    path = store.root / ".publication.lock"
    path.write_text(json.dumps(lock))
    before = path.read_bytes()
    for sha, token in [("0" * 64, lock["token"]), (digest(path), "d" * 32)]:
        with pytest.raises((ContractError, PublicationConflict)):
            recover_store_lock(
                store.root, expected_lock_sha256=sha, expected_lock_token=token
            )
        assert path.read_bytes() == before


@pytest.mark.parametrize("kind", ["symlink", "fifo", "hardlink"])
def test_coordination_guard_never_touches_external_or_nonregular_targets(
    tmp_path: Path, kind: str
) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    target = tmp_path / "external"
    target.write_bytes(b"external preserved")
    target.chmod(0o600)
    path = store.root / GUARD_NAME
    if kind == "symlink":
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        os.link(target, path)
    with pytest.raises((IntegrityError, PublicationConflict)):
        with store.begin("refused"):
            pass
    assert target.read_bytes() == b"external preserved"
    assert not (store.root / ".publication.lock").exists()


def test_live_coordination_excludes_another_begin_with_bounded_wait(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    descriptor = os.open(store.root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with publication_guard(descriptor, timeout_seconds=0.1):
            started = time.monotonic()
            with pytest.raises(PublicationConflict, match="busy"):
                with store.begin("blocked"):
                    pass
            assert time.monotonic() - started < 3
            assert not (store.root / ".publication.lock").exists()
    finally:
        os.close(descriptor)
