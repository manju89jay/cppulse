"""Fresh real-native work units and bounded process fault retention."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator
import sys
import threading
import time

import pytest

from cppulse.errors import ContractError, IntegrityError
from cppulse.execution import (
    CancellationToken,
    ProcessLimits,
    ProcessOutcome,
    run_bounded_process,
)
from cppulse.identities import context_identity, snapshot_inputs
from cppulse.tooling import load_rule_registry
from cppulse.work_units import execute_work_units, prepare_work_unit, validate_work_unit

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native() -> Path:
    path = Path(
        os.environ.get(
            "CPPULSE_WORK_UNIT_NATIVE",
            ROOT / "analyzer-core/build-production-work-units/cppulse-analyzer",
        )
    )
    if not path.is_file():
        pytest.skip(
            "Real native work-unit binary must be built for runtime qualification"
        )
    return path


def request(
    tmp_path: Path,
    native: Path,
    *,
    name: str = "unit-one",
    text: str = "int value() { return 1; }\n",
    limits: dict | None = None,
) -> dict:
    source_root = tmp_path / "readonly-source"
    source_root.mkdir(exist_ok=True)
    (source_root / f"{name}.cpp").write_text(text)
    source = snapshot_inputs(source_root, [f"{name}.cpp"])
    context = context_identity(
        {
            "compiler": {"name": "libclang", "version": "observed-by-native"},
            "argv": ["-std=c++17", "-x", "c++"],
            "working_directory": str(source_root),
            "language_standard": "c++17",
            "target": None,
            "provenance": "fallback",
            "dependencies": [],
            "limitations": ["Actual parse context remains separately observed."],
        }
    )
    return prepare_work_unit(
        unit_id=name,
        source_root=source_root,
        work_root=tmp_path / "work" / name,
        source=source,
        primary_file=f"{name}.cpp",
        context=context,
        native_executable=native,
        configuration={},
        registry=load_rule_registry(),
        limits=limits,
    )


def test_fresh_native_receipt_selects_one_file_outside_source(
    tmp_path: Path, native: Path
) -> None:
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
    assert checked.report["metadata"]["analysis"]["files"][0]["path"].endswith(
        "unit-one.cpp"
    )
    assert checked.report["findings"] == []
    assert checked.invocation_context["id"] != unit["context"]["id"]
    assert checked.observed_context["argv"] == unit["context"]["argv"]


def test_partial_is_retained_and_does_not_become_clean(
    tmp_path: Path, native: Path
) -> None:
    unit = request(
        tmp_path,
        native,
        text='#include "does_not_exist.hpp"\nint value() { return 1; }\n',
    )
    execution = next(execute_work_units([unit], native_executable=native))
    assert execution.result["outcome"] == "partial"
    assert execution.result["parse_status"] == "partial"
    assert execution.result["execution_receipt"]["status"] == "passed"
    assert execution.result["artifacts"]


def test_checkpoint_resume_preserves_original_receipt_and_rechecks_bytes(
    tmp_path: Path, native: Path
) -> None:
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


def test_real_native_low_memory_is_explicit_failure(
    tmp_path: Path, native: Path
) -> None:
    unit = request(tmp_path, native, limits={"address_space_bytes": 1})
    result = next(execute_work_units([unit], native_executable=native)).result
    assert result["outcome"] == "process_error"
    assert result["parse_status"] is None
    assert result["execution_receipt"]["exit_code"] == 2
    assert not result["limits_applied"]["address_space"]


def test_process_wall_log_and_cancellation_are_bounded(tmp_path: Path) -> None:
    cancel = CancellationToken()
    with (
        (tmp_path / "stdout").open("wb") as stdout,
        (tmp_path / "stderr").open("wb") as stderr,
    ):
        outcome = run_bounded_process(
            [
                sys.executable,
                "-c",
                "import os; os.write(1,b'x'*100000)",
            ],
            cwd=tmp_path,
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=5,
            limits=ProcessLimits(max_log_bytes=97, termination_grace_seconds=0.1),
            cancel=cancel,
        )
    assert outcome.status == "passed"
    assert outcome.captured_bytes == 97
    assert (tmp_path / "stdout").stat().st_size == 97
    assert outcome.stdout_bytes == 100000
    with (
        (tmp_path / "timeout-out").open("wb") as stdout,
        (tmp_path / "timeout-err").open("wb") as stderr,
    ):
        outcome = run_bounded_process(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=0.1,
            limits=ProcessLimits(termination_grace_seconds=0.1),
        )
    assert outcome.status == "timed_out"
    timer = threading.Timer(0.1, cancel.cancel)
    timer.start()
    began = time.monotonic()
    with (
        (tmp_path / "out2").open("wb") as stdout,
        (tmp_path / "err2").open("wb") as stderr,
    ):
        outcome = run_bounded_process(
            [
                sys.executable,
                "-c",
                "import subprocess,time; subprocess.Popen(['sleep','20']); time.sleep(20)",
            ],
            cwd=tmp_path,
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=10,
            limits=ProcessLimits(termination_grace_seconds=0.1),
            cancel=cancel,
        )
    timer.join()
    assert outcome.status == "cancelled"
    assert time.monotonic() - began < 3


def test_job_bound_is_validated_before_consuming_units(native: Path) -> None:
    with pytest.raises(ContractError):
        list(execute_work_units([], native_executable=native, jobs=0))


def test_work_root_must_not_overlap_source(tmp_path: Path, native: Path) -> None:
    unit = request(tmp_path, native)
    source_root = Path(unit["source_root"])
    with pytest.raises(IntegrityError):
        prepare_work_unit(
            unit_id="unsafe",
            source_root=source_root,
            work_root=source_root / "output",
            source=snapshot_inputs(source_root, [unit["primary_file"]]),
            primary_file=unit["primary_file"],
            context=unit["context"],
            native_executable=native,
            configuration={},
            registry=load_rule_registry(),
        )
    assert not (source_root / "output").exists()


def test_modified_retained_configuration_is_rejected(
    tmp_path: Path, native: Path
) -> None:
    unit = request(tmp_path, native)
    (Path(unit["work_root"]) / unit["inputs"]["configuration"]["path"]).write_text(
        '{"rules":{}}'
    )
    with pytest.raises(IntegrityError):
        next(execute_work_units([unit], native_executable=native))


def test_parallel_failure_retains_other_units(tmp_path: Path, native: Path) -> None:
    bad = request(tmp_path, native, name="too-small", limits={"address_space_bytes": 1})
    good = request(tmp_path, native, name="healthy")
    results = list(
        execute_work_units(iter([bad, good]), native_executable=native, jobs=2)
    )
    assert {r.result["unit_id"]: r.result["outcome"] for r in results} == {
        "too-small": "process_error",
        "healthy": "complete",
    }


def test_duplicate_work_root_has_one_owner(tmp_path: Path, native: Path) -> None:
    unit = request(tmp_path, native)
    with pytest.raises(ContractError):
        list(execute_work_units([unit, unit], native_executable=native, jobs=2))


def test_result_scope_tampering_is_rejected(tmp_path: Path, native: Path) -> None:
    from copy import deepcopy

    unit = request(tmp_path, native)
    execution = next(execute_work_units([unit], native_executable=native))
    result = deepcopy(execution.result)
    result["execution_receipt"]["argv"][2] = "/different/source"
    with pytest.raises(IntegrityError):
        validate_work_unit(unit, result, native_executable=native)


@pytest.mark.parametrize("wall", [None, True, "5", float("nan"), float("inf"), 0])
def test_prepare_rejects_invalid_wall_bounds(
    tmp_path: Path, native: Path, wall: object
) -> None:
    with pytest.raises(ContractError):
        request(tmp_path, native, limits={"wall_seconds": wall})


def test_corrupt_checkpoint_is_explicit_integrity_failure(
    tmp_path: Path, native: Path
) -> None:
    unit = request(tmp_path, native)
    next(execute_work_units([unit], native_executable=native))
    (Path(unit["work_root"]) / "result.json").write_text("{")
    with pytest.raises(IntegrityError):
        next(execute_work_units([unit], native_executable=native))


def test_real_compilation_database_uses_relative_include_context(
    tmp_path: Path, native: Path
) -> None:
    unit = request(tmp_path, native)
    root = Path(unit["source_root"])
    (root / "local.hpp").write_text("inline int local_value() { return 42; }\n")
    (root / unit["primary_file"]).write_text(
        '#include "local.hpp"\nint value() { return local_value(); }\n'
    )
    # A fresh request is required after changing selected source bytes.
    context = context_identity(
        {
            "compiler": {"name": "libclang", "version": "observed-by-native"},
            "argv": ["-std=c++17", "-I.", "-x", "c++"],
            "working_directory": str(root),
            "language_standard": "c++17",
            "target": None,
            "provenance": "fallback",
            "dependencies": [],
            "limitations": [],
        }
    )
    unit = prepare_work_unit(
        unit_id="relative-context",
        source_root=root,
        work_root=tmp_path / "work" / "relative-context",
        source=snapshot_inputs(root, [unit["primary_file"], "local.hpp"]),
        primary_file=unit["primary_file"],
        context=context,
        native_executable=native,
        configuration={},
        registry=load_rule_registry(),
    )
    result = next(execute_work_units([unit], native_executable=native)).result
    assert result["outcome"] == "complete", result
    checked = validate_work_unit(unit, result, native_executable=native)
    assert (
        checked.report["metadata"]["analysis"]["files"][0]["compile_context"]
        == "database"
    )
    assert checked.observed_context["argv"] == unit["context"]["argv"]
    with pytest.raises(IntegrityError, match="Dependency closure"):
        next(execute_work_units([unit], native_executable=native))


def test_native_wall_timeout_retains_failure_not_clean(
    tmp_path: Path, native: Path
) -> None:
    unit = request(tmp_path, native, limits={"wall_seconds": 0.001})
    result = next(execute_work_units([unit], native_executable=native)).result
    assert result["outcome"] == "timed_out"
    assert result["execution_receipt"]["status"] == "timed_out"
    assert result["parse_status"] is None
    assert result["execution_receipt"]["log_artifact_ids"] == ["stdout", "stderr"]


def test_cancelled_scheduler_does_not_consume_unselected_work(native: Path) -> None:
    token = CancellationToken()
    token.cancel()

    def unavailable_units() -> Iterator[dict[str, Any]]:
        raise AssertionError("Cancelled scheduler must not consume the input iterator")
        yield

    assert (
        list(
            execute_work_units(
                unavailable_units(), native_executable=native, cancel=token
            )
        )
        == []
    )


@pytest.mark.parametrize(
    "payload", ["{}", "[]", '"not-a-result"', " " * (1024 * 1024 + 1)]
)
def test_malformed_or_large_checkpoint_is_integrity_error(
    tmp_path: Path, native: Path, payload: str
) -> None:
    unit = request(tmp_path, native)
    (Path(unit["work_root"]) / "result.json").write_text(payload)
    with pytest.raises(IntegrityError):
        next(execute_work_units([unit], native_executable=native))


def test_postflight_source_change_retains_input_changed_result(
    tmp_path: Path, native: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.work_units as runtime

    unit = request(tmp_path, native)
    original = runtime.run_bounded_process

    def changing_process(*args: Any, **kwargs: Any) -> ProcessOutcome:
        result = original(*args, **kwargs)
        (Path(unit["source_root"]) / unit["primary_file"]).write_text(
            "int changed_after_native;\n"
        )
        return result

    monkeypatch.setattr(runtime, "run_bounded_process", changing_process)
    result = next(execute_work_units([unit], native_executable=native)).result
    assert result["outcome"] == "input_changed"
    assert result["execution_receipt"]["status"] == "passed"
    assert "content differs" in result["reason"]
    assert any(item["id"] == "native-report" for item in result["artifacts"])


def test_closing_stream_cancels_pending_workers(
    tmp_path: Path, native: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.work_units as runtime

    first = request(tmp_path, native, name="first")
    second = request(tmp_path, native, name="second")
    started = threading.Event()
    cancelled = threading.Event()

    def worker(
        unit: dict[str, Any], executable: Path, token: CancellationToken
    ) -> runtime.WorkUnitExecution:
        if unit["unit_id"] == "first":
            assert started.wait(2)
            return runtime.WorkUnitExecution({"unit_id": "first"})
        started.set()
        deadline = time.monotonic() + 5
        while not token.is_cancelled() and time.monotonic() < deadline:
            time.sleep(0.01)
        if token.is_cancelled():
            cancelled.set()
        return runtime.WorkUnitExecution({"unit_id": "second"})

    monkeypatch.setattr(runtime, "_execute", worker)
    stream = execute_work_units([first, second], native_executable=native, jobs=2)
    assert next(stream).result["unit_id"] == "first"
    began = time.monotonic()
    stream.close()
    assert cancelled.is_set()
    assert time.monotonic() - began < 2


def resource_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "builtin-resources"
    (root / "include").mkdir(parents=True)
    (root / "include/stddef.h").write_text("// finite authored resource fixture\n")
    return root


def test_explicit_resource_inventory_is_retained_and_bound(
    tmp_path: Path, native: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = resource_fixture(tmp_path)
    monkeypatch.setenv("CPPULSE_CLANG_RESOURCE_DIR", str(resources))
    unit = request(tmp_path, native)
    assert unit["inputs"]["resource_manifest"] is not None
    # The original selection survives later environment changes.
    monkeypatch.setenv("CPPULSE_CLANG_RESOURCE_DIR", str(tmp_path / "wrong-resources"))
    result = next(execute_work_units([unit], native_executable=native)).result
    assert result["outcome"] == "complete", result
    assert "--resource-dir" in result["execution_receipt"]["argv"]
    assert "-resource-dir=" + str(resources) in unit["context"]["argv"]
    checked = validate_work_unit(unit, result, native_executable=native)
    assert checked.observed_context["argv"] == unit["context"]["argv"]


def test_changed_builtin_bytes_invalidate_work_unit(
    tmp_path: Path, native: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = resource_fixture(tmp_path)
    monkeypatch.setenv("CPPULSE_CLANG_RESOURCE_DIR", str(resources))
    unit = request(tmp_path, native)
    (resources / "include/stddef.h").write_text("// changed resource bytes\n")
    with pytest.raises(IntegrityError, match="builtin resources differ"):
        next(execute_work_units([unit], native_executable=native))


def test_unselected_later_resource_override_cannot_change_parse(
    tmp_path: Path, native: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CPPULSE_CLANG_RESOURCE_DIR", raising=False)
    unit = request(tmp_path, native)
    monkeypatch.setenv(
        "CPPULSE_CLANG_RESOURCE_DIR", str(tmp_path / "invalid-resources")
    )
    result = next(execute_work_units([unit], native_executable=native)).result
    assert result["outcome"] == "complete", result
    assert unit["inputs"]["resource_manifest"] is None
    assert not any(arg.startswith("-resource-dir=") for arg in unit["context"]["argv"])
