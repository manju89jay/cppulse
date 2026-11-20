"""Independent owned-process crash regression for final bounded visibility."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

import cppulse
import pytest

from cppulse.pipeline import analyze
from cppulse.run_store import RunStore
import test_bounded_pipeline as fixtures


CHILD = r"""
from pathlib import Path
import json, os, sys, time
from cppulse.config import effective_config
from cppulse.native import NativeInstallation
from cppulse.run_store import RunStore
import cppulse.pipeline as pipeline
import cppulse.work_unit_analysis as bridge

request = json.loads(Path(sys.argv[1]).read_text())
native = request['native']
installation = NativeInstallation(
    Path(native['analyzer']),
    Path(native['resource_dir']) if native['resource_dir'] else None,
    tuple(Path(path) for path in native['library_dirs']),
    Path(native['metadata']) if native['metadata'] else None,
    tuple(native['limitations']),
)
pipeline.discover_native = lambda: installation
store = RunStore(request['output'])
def pause_before_normalization(material):
    # A staged material projection is explicitly not a published RunSnapshot.
    # Inspect its candidate metadata without asking it for a published hash.
    manifest = material.manifest
    latest = store.resolve_latest()
    attempt = store.resolve_latest_attempt()
    record = {
        'pid': os.getpid(),
        'material_type': type(material).__name__,
        'candidate_run_id': manifest['run_id'],
        'visible_completed_run_id': latest.run_id,
        'visible_attempt_run_id': attempt.run_id,
        'candidate_contract_kinds': sorted({
            artifact['contract']['kind']
            for artifact in manifest['artifacts'] if 'contract' in artifact
        }),
    }
    marker = Path(request['marker'])
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    os.replace(temporary, marker)
    while True:
        time.sleep(.1)
bridge.normalize_work_unit_analysis = pause_before_normalization
config = effective_config(
    Path(request['repo']), Path(request['output']),
    execution={'mode': 'bounded', 'jobs': 1, 'work_directory': request['work']},
    history={'enabled': False},
)
pipeline.analyze(config, report_format='json', timeout=60)
"""


def test_final_run_remains_visible_during_normalization_and_after_owned_child_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never replace a final snapshot with an incomplete raw intermediate."""
    config = fixtures.config(tmp_path, jobs=1)
    native = fixtures.native.__wrapped__()
    fixtures.select_native(monkeypatch, native)
    (config.repo / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(config.repo),
                    "file": str(config.repo / "main.cpp"),
                    "arguments": [
                        "clang++",
                        "-std=c++17",
                        "-c",
                        str(config.repo / "main.cpp"),
                    ],
                }
            ]
        )
        + "\n"
    )
    summary = analyze(config, report_format="json", timeout=60)
    store = RunStore(config.output)
    baseline = store.open_run(
        summary["run_id"], manifest_sha256=summary["manifest_sha256"]
    )
    kinds = {
        artifact["contract"]["kind"]
        for artifact in baseline.manifest["artifacts"]
        if "contract" in artifact
    }
    assert {"analysis_scope", "analysis_inventory", "maintenance_health"} <= kinds
    assert baseline.manifest["status"] == "completed"
    pointers = {name: (store.root / name).read_bytes() for name in ("heads.json",)}
    worker = tmp_path / "owned-child.py"
    worker.write_text(CHILD)
    marker = tmp_path / "barrier.json"
    request: dict[str, Any] = {
        "repo": str(config.repo),
        "output": str(config.output),
        "work": str(tmp_path / "work"),
        "marker": str(marker),
        "native": {
            "analyzer": str(native.analyzer),
            "resource_dir": str(native.resource_dir) if native.resource_dir else None,
            "library_dirs": [str(path) for path in native.library_dirs],
            "metadata": str(native.metadata) if native.metadata else None,
            "limitations": list(native.limitations),
        },
    }
    request_path = tmp_path / "child-request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    environment = os.environ.copy()
    package_root = str(Path(cppulse.__file__).resolve().parent.parent)
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in [package_root, environment.get("PYTHONPATH")] if value
    )
    with (tmp_path / "owned-child.log").open("w") as log:
        child = subprocess.Popen(
            [sys.executable, str(worker), str(request_path)],
            cwd=tmp_path,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 120
            while not marker.exists():
                if child.poll() is not None:
                    raise AssertionError(
                        f"Owned child exited before normalization barrier: {child.returncode}"
                    )
                if time.monotonic() > deadline:
                    raise AssertionError(
                        "Owned child did not reach normalization barrier"
                    )
                time.sleep(0.1)
            observed = json.loads(marker.read_text())
            assert observed["pid"] == child.pid
            visible_during = {
                "completed": store.resolve_latest().run_id,
                "attempt": store.resolve_latest_attempt().run_id,
            }
            # The native workers and consumer processes have joined before this
            # normalizer boundary. Kill/reap only this exact harness-owned child.
            child.kill()
            status = child.wait(timeout=15)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=15)
    assert status == -signal.SIGKILL
    visible_after = {
        "completed": store.resolve_latest().run_id,
        "attempt": store.resolve_latest_attempt().run_id,
    }
    baseline.verify()
    proof = {
        "baseline_run_id": baseline.run_id,
        "baseline_manifest_sha256": baseline.manifest_sha256,
        "barrier": observed,
        "owned_child_exit_status": status,
        "visible_during": visible_during,
        "visible_after": visible_after,
    }
    (tmp_path / "crash-visibility-proof.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    assert set(visible_during.values()) == {baseline.run_id}
    assert set(visible_after.values()) == {baseline.run_id}
    for name, content in pointers.items():
        assert (store.root / name).read_bytes() == content
