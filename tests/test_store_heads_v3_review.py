"""Independent hostile-control and real historical-wheel v3 boundary checks."""

from pathlib import Path
import json
import os
import subprocess

import pytest

from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.run_store import RunStore
from cppulse.store_heads import export_store_v2, upgrade_store_to_v3
from test_contracts_v2 import manifest_document, source_document
from test_run_store_v2 import publish


@pytest.mark.parametrize("name", ["store-format.json", "heads.json"])
@pytest.mark.parametrize(
    "damage",
    [
        "symlink",
        "hardlink",
        "world-writable",
        "duplicate-key",
        "unknown-version",
        "oversized",
    ],
)
def test_v3_controls_refuse_unsafe_bytes_without_fallback(
    tmp_path: Path, name: str, damage: str
) -> None:
    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "baseline")
    path = store.root / name
    raw = path.read_bytes()
    if damage == "symlink":
        target = tmp_path / "target"
        target.write_bytes(raw)
        path.unlink()
        path.symlink_to(target)
    elif damage == "hardlink":
        os.link(path, tmp_path / "linked")
    elif damage == "world-writable":
        path.chmod(0o666)
    elif damage == "duplicate-key":
        path.write_bytes(b'{"version":"3.0.0",' + raw[1:])
    elif damage == "unknown-version":
        document = json.loads(raw)
        document["version"] = "999.0.0"
        path.write_text(json.dumps(document))
    else:
        path.write_bytes(raw + b" " * 65536)
    before = (store.root / "runs/baseline/run_manifest.json").read_bytes()
    with pytest.raises((ContractError, IntegrityError, PublicationConflict)):
        store.resolve_heads()
    with pytest.raises((ContractError, IntegrityError, PublicationConflict)):
        store.resolve_latest()
    assert (store.root / "runs/baseline/run_manifest.json").read_bytes() == before
    assert all(
        (store.root / name).is_dir() for name in ("latest.json", "latest_attempt.json")
    )


@pytest.mark.parametrize("damage", ["symlink", "mode", "nonempty"])
def test_v3_legacy_fences_are_checked_on_reads(tmp_path: Path, damage: str) -> None:
    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "baseline")
    path = store.root / "latest_attempt.json"
    if damage == "symlink":
        path.rmdir()
        target = tmp_path / "fake-fence"
        target.mkdir(mode=0o700)
        path.symlink_to(target, target_is_directory=True)
    elif damage == "mode":
        path.chmod(0o755)
    else:
        (path / "unexpected").write_bytes(b"preserved")
    authority = (store.root / "heads.json").read_bytes()
    with pytest.raises((IntegrityError, PublicationConflict)):
        store.resolve_heads()
    assert (store.root / "heads.json").read_bytes() == authority


def test_real_installed_old_wheel_fails_closed_and_reads_explicit_export(
    tmp_path: Path,
) -> None:
    old_python = Path(
        "work/cloud-resume/installed-typed-sdk-service-current/core-venv/bin/python"
    ).absolute()
    assert (
        old_python.exists()
    ), "Historical installed wheel required for this acceptance control"
    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "baseline")
    source = tmp_path / "source.json"
    manifest = tmp_path / "manifest.json"
    source.write_text(json.dumps(source_document()))
    manifest.write_text(json.dumps(manifest_document()))
    code = """import hashlib,json,pathlib,sys
import cppulse.run_store as module
from cppulse.run_store import RunStore
root=pathlib.Path(sys.argv[1]); store=RunStore(root)
assert 'site-packages' in module.__file__,module.__file__
try:store.resolve_latest()
except Exception as exc:read_error=type(exc).__name__
else:raise AssertionError('Old reader accepted v3')
try:
 with store.begin('old-writer-attempt') as stage:
  artifact=stage.write_json('artifacts/source.json',json.loads(pathlib.Path(sys.argv[2]).read_bytes()),contract='source')
  manifest=json.loads(pathlib.Path(sys.argv[3]).read_bytes())
  manifest.update(run_id=stage.run_id,artifacts=[artifact])
  stage.publish(manifest)
except Exception as exc:write_error=type(exc).__name__;write_reason=str(exc)
else:raise AssertionError('Old writer published through v3 fences')
print(json.dumps({'module':module.__file__,'module_sha256':hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest(),'read_error':read_error,'write_error':write_error,'write_reason':write_reason}))
"""
    before = (store.root / "heads.json").read_bytes()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    result = subprocess.run(
        [
            str(old_python),
            "-I",
            "-c",
            code,
            str(store.root),
            str(source),
            str(manifest),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    (tmp_path / "historical-wheel-proof.json").write_text(result.stdout)
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    assert proof["read_error"] == "IntegrityError"
    assert proof["write_error"] in {
        "IntegrityError",
        "IsADirectoryError",
        "PublicationConflict",
    }
    assert (store.root / "heads.json").read_bytes() == before
    assert all(
        (store.root / name).is_dir() for name in ("latest.json", "latest_attempt.json")
    )
    assert store.resolve_latest().run_id == "baseline"
    # The actual historical publisher reached commit and retained its run before
    # its legacy pointer replace was refused by the reserved directory fence.
    assert (store.root / "runs/old-writer-attempt/run_manifest.json").is_file()
    destination = tmp_path / "export"
    export_store_v2(store.root, destination)
    result = subprocess.run(
        [
            str(old_python),
            "-I",
            "-c",
            'import sys;from cppulse.run_store import RunStore;assert RunStore.open_existing(sys.argv[1]).resolve_latest().run_id=="baseline"',
            str(destination),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("damage", ["plan-bytes", "plan-symlink", "original-pointer"])
def test_interrupted_migration_corruption_preserves_unconverted_pointer(
    tmp_path: Path, monkeypatch, damage: str
) -> None:
    import cppulse.store_heads as heads

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "baseline")
    original = heads._control_bytes

    def stop(path):
        if path.name == "plan.json":
            raise OSError("Authored pause after migrating marker before fences")
        return original(path)

    with monkeypatch.context() as patch:
        patch.setattr(heads, "_control_bytes", stop)
        with pytest.raises(OSError, match="Authored pause"):
            upgrade_store_to_v3(store.root)
    pointers = {
        name: (store.root / name).read_bytes()
        for name in ("latest.json", "latest_attempt.json")
    }
    plan = store.root / ".migration-v3/plan.json"
    if damage == "plan-bytes":
        plan.write_bytes(plan.read_bytes() + b" ")
    elif damage == "plan-symlink":
        target = tmp_path / "external-plan"
        target.write_bytes(plan.read_bytes())
        plan.unlink()
        plan.symlink_to(target)
    else:
        (store.root / "latest.json").write_bytes(b"changed legacy pointer")
        pointers["latest.json"] = b"changed legacy pointer"
    marker = (store.root / "store-format.json").read_bytes()
    with pytest.raises((IntegrityError, PublicationConflict)):
        upgrade_store_to_v3(store.root)
    assert (store.root / "store-format.json").read_bytes() == marker
    assert not (store.root / "heads.json").exists()
    for name, raw in pointers.items():
        assert (store.root / name).read_bytes() == raw
    with pytest.raises(PublicationConflict):
        store.begin("must-not-start")


def test_concurrent_reader_freezes_both_references_from_single_head_epoch(
    tmp_path: Path,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "epoch-0")
    started = Event()
    finished = Event()
    epochs = []

    def observe():
        started.set()
        while not finished.is_set():
            generation, completed, attempt = store.resolve_heads()
            assert completed is not None and attempt is not None
            # All authored publications here are completed and promoted, so
            # two different IDs are direct evidence of a mixed epoch.
            assert completed.run_id == attempt.run_id
            epochs.append((generation, completed.run_id))

    with ThreadPoolExecutor(max_workers=1) as pool:
        reader = pool.submit(observe)
        assert started.wait(timeout=5)
        try:
            for index in range(1, 21):
                publish(store, "epoch-" + str(index))
        finally:
            finished.set()
        reader.result(timeout=15)
    assert epochs
    assert all(
        run_id == "epoch-" + str(generation - 1) for generation, run_id in epochs
    )
    assert store.resolve_heads()[0] == 21


@pytest.mark.parametrize("damage", ["manifest", "artifact"])
def test_resume_revalidates_pinned_run_bytes_before_destroying_legacy_pointers(
    tmp_path: Path, monkeypatch, damage: str
) -> None:
    import cppulse.store_heads as heads

    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "baseline")
    original = heads._control_bytes

    def stop(path):
        if path.name == "plan.json":
            raise OSError("Authored interruption before legacy fences")
        return original(path)

    with monkeypatch.context() as patch:
        patch.setattr(heads, "_control_bytes", stop)
        with pytest.raises(OSError):
            upgrade_store_to_v3(store.root)
    pointers = {
        name: (store.root / name).read_bytes()
        for name in ("latest.json", "latest_attempt.json")
    }
    target = (
        store.root
        / "runs/baseline"
        / ("run_manifest.json" if damage == "manifest" else "artifacts/source.json")
    )
    target.write_bytes(target.read_bytes() + b" ")
    marker = (store.root / "store-format.json").read_bytes()
    with pytest.raises(IntegrityError):
        upgrade_store_to_v3(store.root)
    assert (store.root / "store-format.json").read_bytes() == marker
    for name, raw in pointers.items():
        assert (store.root / name).read_bytes() == raw


def test_opened_previous_heads_inode_remains_readable_after_atomic_replace(
    tmp_path: Path, monkeypatch
) -> None:
    """Deterministically replace heads between open and fd identity inspection."""
    import cppulse.store_heads as heads

    store = RunStore(tmp_path / "store", format_version="3.0.0")
    publish(store, "baseline")
    initial = (store.root / "heads.json").stat()
    original_fstat = os.fstat
    replaced = False

    def replace_before_inspecting_opened_heads(descriptor):
        nonlocal replaced
        current = original_fstat(descriptor)
        if not replaced and (current.st_dev, current.st_ino) == (
            initial.st_dev,
            initial.st_ino,
        ):
            replaced = True
            publish(store, "replacement")
            assert original_fstat(descriptor).st_nlink == 0
        return original_fstat(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(heads.os, "fstat", replace_before_inspecting_opened_heads)
        generation, completed, attempt = store.resolve_heads()
    assert replaced
    assert generation == 1
    assert completed.run_id == attempt.run_id == "baseline"
    assert store.resolve_heads()[0] == 2
    assert store.resolve_latest().run_id == "replacement"
