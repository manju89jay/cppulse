"""Explicit v3 migration and coherent head semantics; v2 tests remain unchanged."""
from pathlib import Path
import json
import pytest
from cppulse.errors import IntegrityError, PublicationConflict, ContractError
from cppulse.run_store import RunStore
from cppulse.store_heads import upgrade_store_to_v3, read_heads
from test_run_store_v2 import publish


def test_empty_v3_and_completed_partial_head_epochs(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store", format_version="3.0.0")
    assert read_heads(store.root)["generation"] == 0
    with pytest.raises(IntegrityError):
        store.resolve_latest()
    publish(store, "completed")
    publish(store, "partial", status="partial")
    assert read_heads(store.root)["generation"] == 2
    assert store.resolve_latest().run_id == "completed"
    assert store.resolve_latest_attempt().run_id == "partial"
    for name in ("latest.json", "latest_attempt.json"):
        assert (store.root / name).is_dir()


def test_migrate_preserves_originals_and_readonly_v2_still_works(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "old")
    publish(store, "cancelled", status="cancelled")
    old = {
        name: (store.root / name).read_bytes()
        for name in ("latest.json", "latest_attempt.json")
    }
    assert RunStore.open_existing(store.root).resolve_latest().run_id == "old"
    upgrade_store_to_v3(store.root)
    plan = json.loads((store.root / ".migration-v3" / "plan.json").read_bytes())
    for name, raw in old.items():
        assert bytes.fromhex(plan["originals"][name]) == raw
    assert RunStore.open_existing(store.root).resolve_latest().run_id == "old"
    assert store.resolve_latest_attempt().run_id == "cancelled"
    publish(store, "new")
    assert store.resolve_latest().run_id == "new"
    assert upgrade_store_to_v3(store.root)["generation"] == 1
    with pytest.raises(ContractError):
        RunStore(store.root, format_version="2.0.0")


def test_active_writer_blocks_migration(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    with store.begin("active"):
        with pytest.raises(PublicationConflict):
            upgrade_store_to_v3(store.root)
    assert not (store.root / "store-format.json").exists()


def test_heads_corruption_never_falls_back_to_legacy(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "good")
    (store.root / "heads.json").write_text("{}")
    with pytest.raises(ContractError):
        store.resolve_latest()


def test_incomplete_migration_blocks_reads_and_writes(
    tmp_path: Path, monkeypatch
) -> None:
    import cppulse.store_heads as heads

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "good")
    original = heads._fences

    def stop(root):
        raise OSError("authored interruption")

    monkeypatch.setattr(heads, "_fences", stop)
    with pytest.raises(OSError):
        upgrade_store_to_v3(store.root)
    with pytest.raises(PublicationConflict):
        store.resolve_latest()
    with pytest.raises(PublicationConflict):
        store.begin("forbidden")
    monkeypatch.setattr(heads, "_fences", original)
    upgrade_store_to_v3(store.root)
    assert store.resolve_latest().run_id == "good"


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_actual_sigkill_single_head_commit_has_one_generation(
    tmp_path: Path, boundary: str
) -> None:
    import subprocess
    import sys
    import time

    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "baseline")
    marker = tmp_path / "barrier"
    code = """from pathlib import Path
import sys,time
import cppulse.store_heads as h
from cppulse.run_store import RunStore
from test_run_store_v2 import publish
original=h._replace
def replace(root,name,document):
 if name==h.HEADS:
  if sys.argv[3]=='after':original(root,name,document)
  Path(sys.argv[2]).write_text(sys.argv[3])
  while True:time.sleep(.1)
 return original(root,name,document)
h._replace=replace
publish(RunStore(sys.argv[1]),'new-completed')
"""
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "python") + ":" + str(Path.cwd() / "tests")
    log = (tmp_path / "child.log").open("w")
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(store.root), str(marker), boundary],
        env=env,
        stdout=log,
        stderr=log,
    )
    try:
        deadline = time.monotonic() + 15
        while not marker.exists():
            assert child.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.02)
        child.kill()
        child.wait(timeout=10)
        assert child.returncode == -9
        generation, completed, attempt = store.resolve_heads()
        assert completed is not None and attempt is not None
        expected = "baseline" if boundary == "before" else "new-completed"
        assert completed.run_id == attempt.run_id == expected
        assert generation == (1 if boundary == "before" else 2)
        assert store.open_run("new-completed").manifest["status"] == "completed"
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        log.close()


def test_pre_marker_archive_is_resumable_without_overwriting_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    import cppulse.run_store as rs

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "old")
    original = rs._write_new

    def stop(path, content):
        if path.name == "store-format.json":
            raise OSError("before marker")
        return original(path, content)

    with monkeypatch.context() as patch:
        patch.setattr(rs, "_write_new", stop)
        with pytest.raises(OSError):
            upgrade_store_to_v3(store.root)
    plan = (store.root / ".migration-v3" / "plan.json").read_bytes()
    assert store.resolve_latest().run_id == "old"
    upgrade_store_to_v3(store.root)
    assert (store.root / ".migration-v3" / "plan.json").read_bytes() == plan
    assert store.resolve_latest().run_id == "old"


def test_export_distinct_v2_snapshot_preserves_epoch_and_exact_bytes(
    tmp_path: Path,
) -> None:
    from cppulse.store_heads import export_store_v2

    store = RunStore(tmp_path / "store", format_version="3.0.0")
    completed = publish(store, "completed")
    attempt = publish(store, "partial", status="partial")
    before = (store.root / "heads.json").read_bytes()
    output = tmp_path / "export"
    report = export_store_v2(store.root, output)
    assert report["source_generation"] == 2
    assert (store.root / "heads.json").read_bytes() == before
    legacy = RunStore.open_existing(output)
    assert legacy.resolve_latest().manifest_sha256 == completed.manifest_sha256
    assert legacy.resolve_latest_attempt().manifest_sha256 == attempt.manifest_sha256
    assert (output / "latest.json").is_file()
    assert not (output / "store-format.json").exists()
    for run in ("completed", "partial"):
        for path in (store.root / "runs" / run).rglob("*"):
            if path.is_file():
                assert (
                    output / path.relative_to(store.root)
                ).read_bytes() == path.read_bytes()
    with pytest.raises(PublicationConflict):
        export_store_v2(store.root, output)
    with pytest.raises(PublicationConflict):
        export_store_v2(store.root, store.root / "nested")


def test_export_corrupt_source_retains_failure_without_pointers(tmp_path: Path) -> None:
    from cppulse.store_heads import export_store_v2

    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "good")
    (store.root / "runs/good/artifacts/source.json").write_bytes(b"corrupt")
    with pytest.raises(IntegrityError):
        export_store_v2(store.root, tmp_path / "failed-export")
    assert not (tmp_path / "failed-export/latest.json").exists()


@pytest.mark.parametrize(
    "boundary",
    [
        "plan",
        "marker",
        "unlink-latest.json",
        "mkdir-latest.json",
        "unlink-latest_attempt.json",
        "mkdir-latest_attempt.json",
        "heads",
        "active",
    ],
)
def test_actual_sigkill_each_durable_migration_step_resumes_original_epoch(
    tmp_path: Path, boundary: str
) -> None:
    import os
    import subprocess
    import sys
    import time

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "completed")
    publish(store, "partial", status="partial")
    originals = {
        name: (store.root / name).read_bytes()
        for name in ("latest.json", "latest_attempt.json")
    }
    marker = tmp_path / "barrier"
    code = """from pathlib import Path
import os,sys,time
import cppulse.run_store as rs
import cppulse.store_heads as h
boundary=sys.argv[3]
def pause(name):
 if name==boundary:
  Path(sys.argv[2]).write_text(name)
  while True:time.sleep(.1)
original_write=rs._write_new
def write(path,content):
 original_write(path,content)
 names={'plan.json':'plan','store-format.json':'marker','heads.json':'heads'}
 if path.name in names:pause(names[path.name])
rs._write_new=write
original_unlink=os.unlink
def unlink(name,*args,**kwargs):
 original_unlink(name,*args,**kwargs)
 if name in h.LEGACY:pause('unlink-'+name)
os.unlink=unlink
original_mkdir=os.mkdir
def mkdir(name,*args,**kwargs):
 original_mkdir(name,*args,**kwargs)
 if name in h.LEGACY:pause('mkdir-'+name)
os.mkdir=mkdir
original_replace=h._replace
def replace(root,name,document):
 original_replace(root,name,document)
 if name==h.FORMAT:pause('active')
h._replace=replace
h.upgrade_store_to_v3(sys.argv[1])
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "python") + ":" + str(Path.cwd() / "tests")
    log = (tmp_path / "child.log").open("w")
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(store.root), str(marker), boundary],
        env=env,
        stdout=log,
        stderr=log,
    )
    try:
        deadline = time.monotonic() + 15
        while not marker.exists():
            assert child.poll() is None, (tmp_path / "child.log").read_text()
            assert time.monotonic() < deadline
            time.sleep(0.02)
        child.kill()
        child.wait(timeout=10)
        assert child.returncode == -9
        upgrade_store_to_v3(store.root)
        generation, completed, attempt = store.resolve_heads()
        assert generation == 0
        assert completed.run_id == "completed"
        assert attempt.run_id == "partial"
        plan = json.loads((store.root / ".migration-v3/plan.json").read_bytes())
        for name, raw in originals.items():
            assert bytes.fromhex(plan["originals"][name]) == raw
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        log.close()


def test_v3_make_latest_false_retains_completed_reference(tmp_path: Path) -> None:
    from test_contracts_v2 import manifest_document, source_document

    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "baseline")
    with store.begin("completed-not-promoted") as stage:
        artifact = stage.write_json(
            "artifacts/source.json", source_document(), contract="source"
        )
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, artifacts=[artifact])
        stage.publish(manifest, make_latest=False)
    generation, completed, attempt = store.resolve_heads()
    assert generation == 2
    assert completed.run_id == "baseline"
    assert attempt.run_id == "completed-not-promoted"


def test_default_fresh_v3_and_existing_v2_write_requires_explicit_choice(
    tmp_path: Path,
) -> None:
    from cppulse.store_heads import protocol

    fresh = RunStore(tmp_path / "fresh")
    assert protocol(fresh.root)["phase"] == "active"
    assert fresh.format_version == "3.0.0"
    publish(fresh, "fresh-completed")
    legacy = RunStore(tmp_path / "legacy", format_version="2.0.0")
    publish(legacy, "old")
    assert legacy.format_version == "2.0.0"
    raw = (legacy.root / "latest.json").read_bytes()
    current = RunStore(legacy.root)
    assert current.resolve_latest().run_id == "old"
    with pytest.raises(PublicationConflict) as caught:
        current.begin("forbidden-implicit-write")
    assert caught.value.code == "STORE_UPGRADE_REQUIRED"
    assert (legacy.root / "latest.json").read_bytes() == raw
    assert not (legacy.root / "store-format.json").exists()
    assert not (legacy.root / ".publication.lock").exists()
    publish(RunStore(legacy.root, format_version="2.0.0"), "explicit-legacy")
    upgrade_store_to_v3(legacy.root)
    publish(RunStore(legacy.root), "explicitly-upgraded")
    assert current.resolve_latest().run_id == "explicitly-upgraded"


def test_reader_keeps_opened_head_descriptor_after_concurrent_replace(
    tmp_path: Path, monkeypatch
) -> None:
    import os
    import cppulse.store_heads as heads

    store = RunStore(tmp_path / "store")
    publish(store, "baseline")
    replacement = heads.read_heads(store.root)
    replacement["generation"] += 1
    original = os.fstat
    replaced = False

    def replace_before_fstat(fd):
        nonlocal replaced
        if not replaced and os.readlink("/proc/self/fd/" + str(fd)) == str(
            store.root / "heads.json"
        ):
            replaced = True
            heads._replace(store.root, heads.HEADS, replacement)
        return original(fd)

    monkeypatch.setattr(heads.os, "fstat", replace_before_fstat)
    retained = heads.read_heads(store.root)
    assert replaced
    assert retained["generation"] == 1
    assert heads.read_heads(store.root)["generation"] == 2


def test_corrupt_active_authority_refuses_writer_before_staging(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    publish(store, "baseline")
    (store.root / "heads.json").write_text("{}")
    with pytest.raises(ContractError):
        store.begin("must-not-stage")
    assert not (store.root / ".staging/must-not-stage").exists()
    assert not (store.root / ".publication.lock").exists()


def test_writer_rechecks_authority_inside_acquisition_guard(
    tmp_path: Path, monkeypatch
) -> None:
    from contextlib import contextmanager
    import cppulse.run_store as rs

    store = RunStore(tmp_path / "store")
    publish(store, "baseline")
    original = rs.publication_guard

    @contextmanager
    def corrupt_after_acquiring(root_fd, **kwargs):
        with original(root_fd, **kwargs) as lease:
            (store.root / "heads.json").write_text("{}")
            yield lease

    monkeypatch.setattr(rs, "publication_guard", corrupt_after_acquiring)
    with pytest.raises(ContractError):
        store.begin("must-not-stage")
    assert not (store.root / ".staging/must-not-stage").exists()
    assert not (store.root / ".publication.lock").exists()
