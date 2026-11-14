"""Fresh real-native work units and bounded process fault retention."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import time

import pytest

from cppulse.errors import ContractError, IntegrityError
from cppulse.execution import CancellationToken, ProcessLimits, run_bounded_process
from cppulse.identities import context_identity, snapshot_inputs
from cppulse.tooling import load_rule_registry
from cppulse.work_units import execute_work_units, prepare_work_unit, validate_work_unit

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def native() -> Path:
    path = Path(os.environ.get("CPPULSE_WORK_UNIT_NATIVE", ROOT / "analyzer-core/build-production-work-units/cppulse-analyzer"))
    if not path.is_file():
        pytest.skip("Real native work-unit binary must be built for runtime qualification")
    return path


def request(tmp_path: Path, native: Path, *, name: str = "unit-one", text: str = "int value() { return 1; }\n", limits: dict | None = None) -> dict:
    source_root = tmp_path / "readonly-source"
    source_root.mkdir(exist_ok=True)
    (source_root / f"{name}.cpp").write_text(text)
    source = snapshot_inputs(source_root, [f"{name}.cpp"])
    context = context_identity({"compiler": {"name": "libclang", "version": "observed-by-native"}, "argv": ["-std=c++17", "-x", "c++"], "working_directory": str(source_root), "provenance": "fallback", "dependencies": [], "limitations": ["Actual parse context remains separately observed."]})
    return prepare_work_unit(unit_id=name, source_root=source_root, work_root=tmp_path / "work" / name, source=source, primary_file=f"{name}.cpp", context=context, native_executable=native, configuration={}, registry=load_rule_registry(), limits=limits)


def test_fresh_native_receipt_selects_one_file_outside_source(tmp_path: Path, native: Path) -> None:
    unit = request(tmp_path, native)
    (Path(unit["source_root"]) / "unrequested.cpp").write_text("int* raw = new int;\n")
    results = list(execute_work_units(iter([unit]), native_executable=native, jobs=1))
    assert len(results) == 1
    execution = results[0]
    assert execution.result["outcome"] == "complete", execution.result
    assert execution.result["execution_receipt"]["argv"][0] == str(native.resolve())
    assert "--file-list" in execution.result["execution_receipt"]["argv"]
    checked = validate_work_unit(unit, execution.result, native_executable=native)
    assert len(checked.report["metadata"]["analysis"]["files"]) == 1
    assert checked.report["metadata"]["analysis"]["files"][0]["path"].endswith("unit-one.cpp")
    assert checked.report["findings"] == []
    assert checked.invocation_context["id"] != unit["context"]["id"]
    assert checked.observed_context["argv"] == unit["context"]["argv"]


def test_partial_is_retained_and_does_not_become_clean(tmp_path: Path, native: Path) -> None:
    unit = request(tmp_path, native, text='#include "does_not_exist.hpp"\nint value() { return 1; }\n')
    execution = next(execute_work_units([unit], native_executable=native))
    assert execution.result["outcome"] == "partial"
    assert execution.result["parse_status"] == "partial"
    assert execution.result["execution_receipt"]["status"] == "passed"
    assert execution.result["artifacts"]


def test_checkpoint_resume_preserves_original_receipt_and_rechecks_bytes(tmp_path: Path, native: Path) -> None:
    unit = request(tmp_path, native)
    first = next(execute_work_units([unit], native_executable=native))
    second = next(execute_work_units([unit], native_executable=native))
    assert first.result["outcome"] == "complete"
    assert second.resumed
    assert second.result == first.result
    report = Path(unit["work_root"]) / "output/findings.json"
    report.write_text("{}")
    with pytest.raises(IntegrityError):
        list(execute_work_units([unit], native_executable=native))


def test_changed_primary_is_never_resumed(tmp_path: Path, native: Path) -> None:
    unit = request(tmp_path, native)
    next(execute_work_units([unit], native_executable=native))
    (Path(unit["source_root"]) / unit["primary_file"]).write_text("int changed;\n")
    with pytest.raises(IntegrityError):
        list(execute_work_units([unit], native_executable=native))


def test_real_native_low_memory_is_explicit_failure(tmp_path: Path, native: Path) -> None:
    unit = request(tmp_path, native, limits={"address_space_bytes": 1})
    result = next(execute_work_units([unit], native_executable=native)).result
    assert result["outcome"] == "process_error"
    assert result["parse_status"] is None
    assert result["execution_receipt"]["exit_code"] == 2
    assert not result["limits_applied"]["address_space"]


def test_process_wall_log_and_cancellation_are_bounded(tmp_path: Path) -> None:
    cancel = CancellationToken()
    with (tmp_path / "stdout").open("wb") as stdout, (tmp_path / "stderr").open("wb") as stderr:
        outcome = run_bounded_process([sys.executable, "-c", "import os,time; os.write(1,b'x'*100000); time.sleep(5)"], cwd=tmp_path, stdout=stdout, stderr=stderr, timeout_seconds=0.1, limits=ProcessLimits(max_log_bytes=97, termination_grace_seconds=0.1), cancel=cancel)
    assert outcome.status == "timed_out"
    assert outcome.captured_bytes == 97
    assert (tmp_path / "stdout").stat().st_size == 97
    assert outcome.stdout_bytes == 100000
    timer = threading.Timer(0.1, cancel.cancel)
    timer.start()
    began = time.monotonic()
    with (tmp_path / "out2").open("wb") as stdout, (tmp_path / "err2").open("wb") as stderr:
        outcome = run_bounded_process([sys.executable, "-c", "import subprocess,time; subprocess.Popen(['sleep','20']); time.sleep(20)"], cwd=tmp_path, stdout=stdout, stderr=stderr, timeout_seconds=10, limits=ProcessLimits(termination_grace_seconds=0.1), cancel=cancel)
    timer.join()
    assert outcome.status == "cancelled"
    assert time.monotonic() - began < 3


def test_job_bound_is_validated_before_consuming_units(native: Path) -> None:
    with pytest.raises(ContractError):
        list(execute_work_units([], native_executable=native, jobs=0))
