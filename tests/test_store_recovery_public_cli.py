"""Public lock inspection and exact owned-dead-writer recovery controls."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from cppulse.cli import main
from cppulse.run_store import RunStore
from cppulse.store_recovery import validate_recovery_report


def test_public_lock_inspection_is_read_only_and_live_recovery_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    with store.begin("active"):
        before = {
            str(path.relative_to(store.root)): path.read_bytes()
            for path in store.root.rglob("*")
            if path.is_file()
        }
        assert main(["store-recovery", "inspect", "--store", str(store.root)]) == 0
        observed = json.loads(capsys.readouterr().out)
        validate_recovery_report(observed)
        assert observed["status"] == "protected"
        assert (
            main(
                [
                    "store-recovery",
                    "recover",
                    "--store",
                    str(store.root),
                    "--expected-lock-sha256",
                    observed["lock_sha256"],
                    "--expected-lock-token",
                    observed["lock"]["token"],
                ]
            )
            == 2
        )
        assert before == {
            str(path.relative_to(store.root)): path.read_bytes()
            for path in store.root.rglob("*")
            if path.is_file()
        }


def test_public_recovery_requires_both_exact_pins_before_opening_store(
    tmp_path: Path,
) -> None:
    store = tmp_path / "does-not-exist"
    with pytest.raises(SystemExit) as error:
        main(["store-recovery", "recover", "--store", str(store)])
    assert error.value.code == 2
    assert not store.exists()


def test_public_owned_child_recovery_preserves_original_bytes_and_no_promotion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "store"
    ready = tmp_path / "ready"
    program = """from pathlib import Path
import sys,time
from cppulse.run_store import RunStore
with RunStore(sys.argv[1],format_version="2.0.0").begin('public-child') as stage:
 stage._put('original','original.bin',b'original owned staged bytes','application/octet-stream',None)
 Path(sys.argv[2]).write_text(str(stage.path))
 while True:time.sleep(.05)
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "python"),
    }
    child = subprocess.Popen(
        [sys.executable, "-c", program, str(store), str(ready)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            assert child.poll() is None
            time.sleep(0.02)
        assert ready.exists()
        stage = Path(ready.read_text())
        original = (stage / "original.bin").read_bytes()
        raw = (store / ".publication.lock").read_bytes()
        lock = json.loads(raw)
        child.kill()
        child.wait(timeout=10)
        assert (
            main(
                [
                    "store-recovery",
                    "recover",
                    "--store",
                    str(store),
                    "--expected-lock-sha256",
                    hashlib.sha256(raw).hexdigest(),
                    "--expected-lock-token",
                    lock["token"],
                ]
            )
            == 0
        )
        report = json.loads(capsys.readouterr().out)
        validate_recovery_report(report)
        assert report["status"] == "recovered" and not report["facts_reused"]
        assert (stage / "original.bin").read_bytes() == original
        assert Path(report["preserved_lock"]["path"]).read_bytes() == raw
        assert not (store / "latest.json").exists()
        assert not (store / "latest_attempt.json").exists()
        with RunStore(store, format_version="2.0.0").begin("fresh-writer"):
            pass
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
