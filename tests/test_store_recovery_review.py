"""Independent owned-process interruption controls for explicit local recovery."""

from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

from cppulse.run_store import RunStore
from cppulse.store_recovery import (
    recover_store_lock,
    validate_recovery_report,
    inspect_recovery_receipt,
    verify_recovery_report,
)
from test_run_store_v2 import publish


def wait_for(path: Path, child: subprocess.Popen, seconds: float = 15) -> None:
    deadline = time.monotonic() + seconds
    while not path.exists():
        assert child.poll() is None, "Owned child exited before test barrier"
        assert time.monotonic() < deadline, "Owned child did not reach test barrier"
        time.sleep(0.02)


def stop_owned(child: subprocess.Popen) -> None:
    if child.poll() is None:
        child.kill()
    child.wait(timeout=10)


def test_interrupted_prepared_recovery_can_resume_exact_selected_lock(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "baseline")
    pointers = {
        name: (store.root / name).read_bytes()
        for name in ("latest.json", "latest_attempt.json")
    }
    payload = tmp_path / "original.bin"
    payload.write_bytes(b"original retained staged observation")
    writer_ready = tmp_path / "writer-ready.json"
    writer_code = """from pathlib import Path
import json,os,sys,time
from cppulse.run_store import RunStore
with RunStore(sys.argv[1],format_version="2.0.0").begin('crashed-writer') as stage:
 stage.copy_artifact('original',Path(sys.argv[2]),'original.bin')
 Path(sys.argv[3]).write_text(json.dumps({'pid':os.getpid(),'stage':str(stage.path)}))
 while True:time.sleep(.1)
"""
    writer_log = (tmp_path / "writer.log").open("w")
    writer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            writer_code,
            str(store.root),
            str(payload),
            str(writer_ready),
        ],
        stdout=writer_log,
        stderr=writer_log,
    )
    try:
        wait_for(writer_ready, writer)
        stage = Path(json.loads(writer_ready.read_bytes())["stage"])
        raw = (store.root / ".publication.lock").read_bytes()
        original = json.loads(raw)
        digest = hashlib.sha256(raw).hexdigest()
        stop_owned(writer)
    finally:
        stop_owned(writer)
        writer_log.close()
    recovery_ready = tmp_path / "recovery-ready.json"
    recovery_code = """from pathlib import Path
import json,os,sys,time
import cppulse.store_recovery as recovery
original_write = recovery._write_at
def write_and_pause(fd,name,content):
 original_write(fd,name,content)
 if name.endswith('.prepared.json'):
  Path(sys.argv[4]).write_text(json.dumps({'pid':os.getpid(),'receipt':name}))
  while True:time.sleep(.1)
recovery._write_at=write_and_pause
recovery.recover_store_lock(sys.argv[1],expected_lock_sha256=sys.argv[2],expected_lock_token=sys.argv[3])
"""
    recovery_log = (tmp_path / "recovery.log").open("w")
    recovering = subprocess.Popen(
        [
            sys.executable,
            "-c",
            recovery_code,
            str(store.root),
            digest,
            original["token"],
            str(recovery_ready),
        ],
        stdout=recovery_log,
        stderr=recovery_log,
    )
    try:
        wait_for(recovery_ready, recovering)
        marker = json.loads(recovery_ready.read_bytes())
        assert marker["pid"] == recovering.pid
        prepared_path = store.root / ".recovery" / marker["receipt"]
        prepared = json.loads(prepared_path.read_bytes())
        validate_recovery_report(prepared)
        assert prepared["status"] == "prepared"
        assert (store.root / ".publication.lock").read_bytes() == raw
        assert Path(prepared["preserved_lock"]["path"]).read_bytes() == raw
        stop_owned(recovering)
    finally:
        stop_owned(recovering)
        recovery_log.close()
    result = recover_store_lock(
        store.root, expected_lock_sha256=digest, expected_lock_token=original["token"]
    )
    validate_recovery_report(result)
    assert result["status"] == "recovered"
    assert (stage / "original.bin").read_bytes() == payload.read_bytes()
    assert Path(prepared["preserved_lock"]["path"]).read_bytes() == raw
    assert prepared_path.read_bytes()
    assert not (store.root / ".publication.lock").exists()
    for name, value in pointers.items():
        assert (store.root / name).read_bytes() == value
    with store.begin("fresh-after-explicit-resume"):
        pass


def test_other_user_writable_lock_is_not_qualified_for_recovery(tmp_path: Path) -> None:
    import pytest
    from cppulse.errors import IntegrityError, PublicationConflict
    from cppulse.store_coordination import new_lock_document
    from cppulse.store_recovery import inspect_store_lock

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    lock = new_lock_document("previous-incarnation", "a" * 32)
    lock["owner"]["start_ticks"] -= 1
    path = store.root / ".publication.lock"
    path.write_text(json.dumps(lock))
    path.chmod(0o666)
    raw = path.read_bytes()
    try:
        observation = inspect_store_lock(store.root)
    except IntegrityError:
        observation = None
    if observation is not None:
        assert observation["status"] == "protected"
    with pytest.raises((IntegrityError, PublicationConflict)):
        recover_store_lock(
            store.root,
            expected_lock_sha256=hashlib.sha256(raw).hexdigest(),
            expected_lock_token=lock["token"],
        )
    assert path.read_bytes() == raw


def test_actual_post_unlink_sigkill_reconciles_without_touching_new_writer(
    tmp_path: Path,
) -> None:
    from cppulse.store_recovery import inspect_recovery_receipt, verify_recovery_report

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "baseline")
    pointers = {
        name: (store.root / name).read_bytes()
        for name in ("latest.json", "latest_attempt.json")
    }
    ready = tmp_path / "writer.ready"
    code = """from pathlib import Path
import sys,time
from cppulse.run_store import RunStore
with RunStore(sys.argv[1],format_version="2.0.0").begin('abandoned') as stage:
 (stage.path/'original.bin').write_bytes(b'preserve original staged bytes')
 Path(sys.argv[2]).write_text(str(stage.path))
 while True:time.sleep(.1)
"""
    writer = subprocess.Popen([sys.executable, "-c", code, str(store.root), str(ready)])
    try:
        wait_for(ready, writer)
        stage = Path(ready.read_text())
        stage_identity = (stage.stat().st_dev, stage.stat().st_ino)
        staged_bytes = (stage / "original.bin").read_bytes()
        raw = (store.root / ".publication.lock").read_bytes()
        token = json.loads(raw)["token"]
        sha = hashlib.sha256(raw).hexdigest()
    finally:
        stop_owned(writer)
    barrier = tmp_path / "recovery.ready"
    code = """from pathlib import Path
import sys,time
import cppulse.store_recovery as recovery
original=recovery._write_at
def write(fd,name,content):
 if name.endswith('.recovered.json'):
  assert not (Path(sys.argv[1])/'.publication.lock').exists()
  Path(sys.argv[4]).write_text(name)
  while True:time.sleep(.1)
 original(fd,name,content)
recovery._write_at=write
recovery.recover_store_lock(sys.argv[1],expected_lock_sha256=sys.argv[2],expected_lock_token=sys.argv[3])
"""
    recovering = subprocess.Popen(
        [sys.executable, "-c", code, str(store.root), sha, token, str(barrier)]
    )
    try:
        wait_for(barrier, recovering)
        assert not (store.root / ".publication.lock").exists()
        assert not (store.root / ".recovery" / barrier.read_text()).exists()
    finally:
        stop_owned(recovering)
    preserved = {
        path: path.read_bytes() for path in (store.root / ".recovery").iterdir()
    }
    assert len(preserved) == 2
    with store.begin("new-active-writer") as fresh:
        fresh_raw = (store.root / ".publication.lock").read_bytes()
        fresh_identity = (fresh.path.stat().st_dev, fresh.path.stat().st_ino)
        observation = inspect_recovery_receipt(
            store.root, expected_lock_sha256=sha, expected_lock_token=token
        )
        assert observation["status"] == "reconcilable"
        assert (
            observation["current_lock_sha256"] == hashlib.sha256(fresh_raw).hexdigest()
        )
        assert {path: path.read_bytes() for path in preserved} == preserved
        result = recover_store_lock(
            store.root, expected_lock_sha256=sha, expected_lock_token=token
        )
        assert result["status"] == "reconciled"
        assert result["current_lock_action"] == "left_unchanged"
        verify_recovery_report(result)
        assert (store.root / ".publication.lock").read_bytes() == fresh_raw
        assert (fresh.path.stat().st_dev, fresh.path.stat().st_ino) == fresh_identity
        for name, value in pointers.items():
            assert (store.root / name).read_bytes() == value
        assert {path: path.read_bytes() for path in preserved} == preserved
        assert (stage.stat().st_dev, stage.stat().st_ino) == stage_identity
        assert (stage / "original.bin").read_bytes() == staged_bytes
        assert Path(result["preserved_lock"]["path"]).read_bytes() == raw


def test_actual_sigkill_after_unlink_preserves_new_writer_and_replays_receipt(
    tmp_path: Path,
) -> None:
    """Kill owned real processes at the durable-unlink/final-receipt boundary."""
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "baseline")
    pointers = {
        name: (store.root / name).read_bytes()
        for name in ("latest.json", "latest_attempt.json")
    }
    marker = tmp_path / "writer-ready"
    writer_code = """from pathlib import Path
import sys,time
from cppulse.run_store import RunStore
with RunStore(sys.argv[1],format_version="2.0.0").begin('old-owner') as stage:
 (stage.path/'retained.bin').write_bytes(b'original unpublished bytes')
 Path(sys.argv[2]).write_text(str(stage.path))
 while True:time.sleep(.1)
"""
    log = (tmp_path / "processes.log").open("w")
    writer = subprocess.Popen(
        [sys.executable, "-c", writer_code, str(store.root), str(marker)],
        stdout=log,
        stderr=log,
    )
    try:
        wait_for(marker, writer)
        stage = Path(marker.read_text())
        raw = (store.root / ".publication.lock").read_bytes()
        lock = json.loads(raw)
    finally:
        stop_owned(writer)
    sha = hashlib.sha256(raw).hexdigest()
    ready = tmp_path / "after-unlink"
    program = """from pathlib import Path
import sys,time
import cppulse.store_recovery as r
original=r._write_at
def barrier(fd,name,content):
 if name.endswith('.recovered.json'):
  assert not (Path(sys.argv[1])/'.publication.lock').exists()
  Path(sys.argv[4]).write_text(name)
  while True:time.sleep(.1)
 return original(fd,name,content)
r._write_at=barrier
r.recover_store_lock(sys.argv[1],expected_lock_sha256=sys.argv[2],expected_lock_token=sys.argv[3])
"""
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            program,
            str(store.root),
            sha,
            lock["token"],
            str(ready),
        ],
        stdout=log,
        stderr=log,
    )
    try:
        wait_for(ready, child)
        assert not (store.root / ".publication.lock").exists()
    finally:
        stop_owned(child)
        log.close()
    prepared = next((store.root / ".recovery").glob("*.prepared.json"))
    prepared_raw = prepared.read_bytes()
    with store.begin("actual-new-writer"):
        current_path = store.root / ".publication.lock"
        current = current_path.read_bytes()
        before = current_path.stat()
        observation = inspect_recovery_receipt(
            store.root, expected_lock_sha256=sha, expected_lock_token=lock["token"]
        )
        assert observation["status"] == "reconcilable"
        result = recover_store_lock(
            store.root, expected_lock_sha256=sha, expected_lock_token=lock["token"]
        )
        verify_recovery_report(result)
        assert result["status"] == "reconciled"
        assert result["current_lock_action"] == "left_unchanged"
        assert current_path.read_bytes() == current
        assert current_path.stat().st_ino == before.st_ino
        assert prepared.read_bytes() == prepared_raw
        assert (stage / "retained.bin").read_bytes() == b"original unpublished bytes"
        for name, content in pointers.items():
            assert (store.root / name).read_bytes() == content
        assert Path(result["preserved_lock"]["path"]).read_bytes() == raw
