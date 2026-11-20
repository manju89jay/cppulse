"""Measure actual processes without turning missing or failed work into a pass."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def benchmark() -> ModuleType:
    """Import the executable runner without requiring a package installation."""
    spec = importlib.util.spec_from_file_location(
        "cppulse_test_benchmark", ROOT / "tools/benchmark.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_suite(tmp_path: Path, *cases: dict[str, object]) -> Path:
    """Write an explicit recipe, keeping execution working directories separate."""
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"version": "1.0.0", "id": "observed", "cases": cases}))
    return suite


def case(id: str, script: str, **options: object) -> dict[str, object]:
    """Declare an actual Python process rather than mocking measurement success."""
    return {
        "id": id,
        "argv": [sys.executable, "-c", script],
        "cwd": ".",
        "repetitions": 1,
        "timeout_seconds": 5,
        **options,
    }


def test_records_each_actual_repetition_and_resource_scope(
    benchmark: ModuleType, tmp_path: Path
) -> None:
    suite = write_suite(
        tmp_path,
        case("repeat", "print(sum(range(100000)))", repetitions=3),
    )
    result = benchmark.run_suite(suite, tmp_path / "evidence")
    assert result["status"] == "passed"
    assert result["exit_status"] == 0
    assert len(result["measurements"]) == 3
    for row in result["measurements"]:
        assert row["returncode"] == 0
        assert row["wall_seconds"] > 0
        assert row["resource_scope"]
        assert "4999950000" in Path(row["log"]).read_text()
        if sys.platform.startswith("linux"):
            assert row["cpu_seconds"] is not None
            assert row["peak_rss_bytes"] > 0
    assert result["environment"]["hostname"]
    assert result["limitations"]
    schema = json.loads(
        (ROOT / "tools/contracts/benchmark-result.schema.json").read_text()
    )
    jsonschema.validate(result, schema)


def test_known_failure_does_not_discard_independent_measurement(
    benchmark: ModuleType, tmp_path: Path
) -> None:
    suite = write_suite(
        tmp_path,
        case("fail", "print('known failure'); raise SystemExit(9)"),
        case("independent", "print('still measured')"),
    )
    result = benchmark.run_suite(suite, tmp_path / "evidence")
    assert result["status"] == "failed"
    assert result["exit_status"] == 1
    assert [row["status"] for row in result["measurements"]] == ["failed", "passed"]
    assert result["measurements"][0]["returncode"] == 9


def test_missing_tool_is_blocked_and_never_a_zero_time_success(
    benchmark: ModuleType, tmp_path: Path
) -> None:
    suite = write_suite(
        tmp_path,
        case("absent", "", argv=[str(tmp_path / "missing executable")]),
    )
    result = benchmark.run_suite(suite, tmp_path / "evidence")
    assert result["status"] == "blocked"
    assert result["exit_status"] == 2
    assert result["measurements"][0]["returncode"] is None
    assert result["measurements"][0]["reason"]


def test_timeout_retains_output_and_fails_measurement(
    benchmark: ModuleType, tmp_path: Path
) -> None:
    suite = write_suite(
        tmp_path,
        case(
            "timeout",
            "import time; print('before timeout', flush=True); time.sleep(30)",
            timeout_seconds=0.1,
        ),
    )
    result = benchmark.run_suite(suite, tmp_path / "evidence")
    assert result["status"] == "failed"
    row = result["measurements"][0]
    assert "timeout" in row["reason"].lower()
    assert "before timeout" in Path(row["log"]).read_text()
    assert row["wall_seconds"] < 10


def test_arguments_remain_literal_and_cwd_is_relative_to_suite(
    benchmark: ModuleType, tmp_path: Path
) -> None:
    target = tmp_path / "selected working directory"
    target.mkdir()
    marker = tmp_path / "shell-must-not-run"
    literal = f"literal $(touch {marker}); & 'quoted'"
    suite = write_suite(
        tmp_path,
        case(
            "literal",
            "",
            argv=[
                sys.executable,
                "-c",
                "import os,sys; print(os.getcwd()); print(sys.argv[1])",
                literal,
            ],
            cwd=target.name,
        ),
    )
    result = benchmark.run_suite(suite, tmp_path / "evidence")
    log = Path(result["measurements"][0]["log"]).read_text()
    assert literal in log
    assert str(target) in log
    assert not marker.exists()


def test_rejects_duplicate_cases_before_any_execution(
    benchmark: ModuleType, tmp_path: Path
) -> None:
    marker = tmp_path / "must-not-run"
    command = case("duplicate", f"open({str(marker)!r}, 'w').close()")
    suite = write_suite(tmp_path, command, command)
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        benchmark.run_suite(suite, tmp_path / "evidence")
    assert not marker.exists()


def test_never_overwrites_an_existing_measurement_directory(
    benchmark: ModuleType, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    original = evidence / "benchmark-results.json"
    original.write_text("previous measurements\n")
    suite = write_suite(tmp_path, case("nothing", "pass"))
    with pytest.raises(FileExistsError):
        benchmark.run_suite(suite, evidence)
    assert original.read_text() == "previous measurements\n"


def test_cancellation_publishes_interrupted_not_stale_success(
    benchmark: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite = write_suite(tmp_path, case("cancelled", "import time; time.sleep(30)"))

    def interrupt(*args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(benchmark, "wait_process", interrupt)
    result = benchmark.run_suite(suite, tmp_path / "evidence")
    assert result["status"] == "interrupted"
    assert result["exit_status"] == 130
    assert result["measurements"][0]["status"] == "interrupted"
    assert (
        json.loads((tmp_path / "evidence/benchmark-results.json").read_text())[
            "exit_status"
        ]
        == 130
    )
