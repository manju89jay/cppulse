"""Real-native public bounded producer acceptance before pipeline integration."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.analysis_execution import run_analysis, validate_execution_plan
from cppulse.config import effective_config
from cppulse.contracts import validate
from cppulse.errors import ContractError
from cppulse.native import NativeInstallation
from test_analysis_execution_contracts import plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native() -> NativeInstallation:
    binary = Path(
        os.environ.get(
            "CPPULSE_WORK_UNIT_NATIVE",
            ROOT / "analyzer-core/build-cloud-resume/cppulse-analyzer",
        )
    )
    if not binary.is_file():
        pytest.skip("Build real native analyzer for bounded execution acceptance")
    resource = os.environ.get("CPPULSE_CLANG_RESOURCE_DIR")
    return NativeInstallation(
        binary.resolve(), Path(resource) if resource else None, (), None
    )


def configuration(tmp_path: Path, *, jobs: int = 2, **settings: Any):
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    execution = {
        "mode": "bounded",
        "jobs": jobs,
        "wall_seconds": 20,
        "address_space_bytes": 2 * 1024**3,
        "cpu_seconds": 20,
        **settings,
    }
    return effective_config(source, tmp_path / "store", execution=execution)


def test_plan_rejects_duplicate_or_missing_scope(tmp_path: Path) -> None:
    document = plan(tmp_path)
    validate_execution_plan(document)
    document["units"] = []
    with pytest.raises(ContractError, match="complete selected inventory"):
        validate_execution_plan(document)


def test_real_bounded_native_aggregate_matches_clean_whole_repo_semantics(
    tmp_path: Path, native: NativeInstallation
) -> None:
    config = configuration(tmp_path)
    (config.repo / "main.cpp").write_text("int* value() { return new int; }\n")
    (config.repo / "library.hpp").write_text(
        "inline int twice(int x) { return x > 0 ? x * 2 : 0; }\n"
    )
    result = run_analysis(config, native, tmp_path / "work", timeout=60)
    assert result.summary["status"] == "completed", result.summary
    assert result.summary["unit_count"] == 2
    combined = json.loads(result.report_path.read_bytes())
    validate("findings", combined, version="prototype_v1")
    clean = tmp_path / "clean"
    argv = [str(native.analyzer), "--repo", str(config.repo), "--output", str(clean)]
    if native.resource_dir:
        argv.extend(["--resource-dir", str(native.resource_dir)])
    subprocess.run(argv, check=True, capture_output=True, env=native.environment())
    expected = json.loads((clean / "findings.json").read_bytes())
    combined["metadata"].pop("analyzed_at")
    expected["metadata"].pop("analyzed_at")
    for document in (combined, expected):
        for row in document["metadata"]["analysis"]["files"]:
            row["working_directory"] = "process-cwd-observed-separately"
    assert combined == expected
    for unit, outcome in result.results:
        assert outcome["execution_receipt"]["source_digest"] == result.source["digest"]
        assert unit["source_scope"] == "primary-with-global-guard"
        assert unit["context_mode"] == "fallback"
        assert unit["inputs"]["primary_content"]["sha256"] == unit["primary_sha256"]


def test_excluded_and_oversize_files_remain_in_full_scope(
    tmp_path: Path, native: NativeInstallation
) -> None:
    config = configuration(tmp_path)
    config.settings.update(exclude_paths=["skip.hpp"], max_file_bytes=40)
    (config.repo / "good.cpp").write_text("int value;\n")
    (config.repo / "skip.hpp").write_text("int excluded;\n")
    (config.repo / "large.hpp").write_text("// lots of content\n" * 20)
    result = run_analysis(config, native, tmp_path / "work", timeout=60)
    report = json.loads(result.report_path.read_bytes())
    states = {
        Path(row["path"]).name: row["status"]
        for row in report["metadata"]["analysis"]["files"]
    }
    assert states == {
        "good.cpp": "analyzed",
        "skip.hpp": "excluded",
        "large.hpp": "skipped",
    }
    assert result.summary["status"] == "partial"
    assert result.summary["unit_count"] == 3
    validate("findings", report, version="prototype_v1")


def test_resume_reexecutes_unknown_closure_and_preserves_historical_receipts(
    tmp_path: Path, native: NativeInstallation
) -> None:
    config = configuration(tmp_path, work_directory=str(tmp_path / "persistent"))
    (config.repo / "main.cpp").write_text("int value;\n")
    first = run_analysis(config, native, tmp_path / "work", timeout=60)
    config.execution["resume"] = True
    second = run_analysis(config, native, tmp_path / "unused", timeout=60)
    assert second.summary["resumed_units"] == 0
    assert (
        first.results[0][1]["execution_receipt"]
        != second.results[0][1]["execution_receipt"]
    )
    assert first.work_root == second.work_root
    original_path = Path(first.results[0][0]["work_root"]) / "result.json"
    assert json.loads(original_path.read_bytes()) == first.results[0][1]
    assert second.summary["status"] == "completed"


def test_original_compilation_database_and_header_inference_are_used(
    tmp_path: Path, native: NativeInstallation
) -> None:
    config = configuration(tmp_path)
    (config.repo / "main.cpp").write_text(
        '#include "library.hpp"\nint main() { return VALUE; }\n'
    )
    (config.repo / "library.hpp").write_text("inline int value() { return VALUE; }\n")
    db = [
        {
            "directory": str(config.repo),
            "file": "main.cpp",
            "arguments": [
                "clang++",
                "-std=c++17",
                "-DVALUE=4",
                "-I.",
                "-c",
                "main.cpp",
                "-o",
                "object.o",
            ],
        }
    ]
    (config.repo / "compile_commands.json").write_text(json.dumps(db))
    result = run_analysis(config, native, tmp_path / "work", timeout=60)
    assert result.summary["status"] == "completed", result.summary
    report = json.loads(result.report_path.read_bytes())
    rows = {
        Path(row["path"]).name: row for row in report["metadata"]["analysis"]["files"]
    }
    assert rows["main.cpp"]["compile_context"] == "database"
    assert rows["library.hpp"]["compile_context"] == "inferred"
    assert all("-DVALUE=4" in row["parse_arguments"] for row in rows.values())
    database_inputs = [
        Path(unit["work_root"]) / unit["inputs"]["compilation_database"]["path"]
        for unit, _ in result.results
    ]
    assert database_inputs[0].samefile(database_inputs[1])
    assert all(
        unit["context_mode"] == "compilation_database" for unit, _ in result.results
    )


def test_shared_header_change_invalidates_resume_and_preserves_original_receipt(
    tmp_path: Path, native: NativeInstallation
) -> None:
    config = configuration(tmp_path, work_directory=str(tmp_path / "persistent"))
    (config.repo / "main.cpp").write_text(
        '#include "library.hpp"\nint main() { return value(); }\n'
    )
    (config.repo / "library.hpp").write_text("inline int value() { return 1; }\n")
    first = run_analysis(config, native, tmp_path / "work", timeout=60)
    first_receipt = first.results[0][1]["execution_receipt"]
    (config.repo / "library.hpp").write_text("inline int value() { return 2; }\n")
    config.execution["resume"] = True
    second = run_analysis(config, native, tmp_path / "unused", timeout=60)
    assert second.summary["status"] == "completed"
    assert second.summary["resumed_units"] == 0
    assert second.work_root != first.work_root
    assert first_receipt != second.results[0][1]["execution_receipt"]
    assert first.summary_path.is_file()


def test_overall_timeout_retains_full_not_attempted_scope(
    tmp_path: Path, native: NativeInstallation
) -> None:
    config = configuration(tmp_path)
    (config.repo / "main.cpp").write_text("int main() { return 0; }\n")
    result = run_analysis(config, native, tmp_path / "work", timeout=0.001)
    assert result.summary["status"] == "cancelled"
    assert result.summary["unit_count"] == 1
    assert result.summary["outcomes"]["not_attempted"] == 1
    report = json.loads(result.report_path.read_bytes())
    assert len(report["metadata"]["analysis"]["files"]) == 1
    assert report["metadata"]["analysis"]["files"][0]["status"] == "failed"
    assert not result.results


def test_changed_builtin_selection_causes_fresh_resume_attempt(
    tmp_path: Path, native: NativeInstallation
) -> None:
    resource_root = tmp_path / "resources"
    (resource_root / "include").mkdir(parents=True)
    (resource_root / "include/stddef.h").write_text("// authored resource fixture v1\n")
    selected = NativeInstallation(
        native.analyzer, resource_root, native.library_dirs, native.metadata
    )
    config = configuration(tmp_path, work_directory=str(tmp_path / "persistent"))
    (config.repo / "main.cpp").write_text("int main() { return 0; }\n")
    first = run_analysis(config, selected, tmp_path / "work", timeout=60)
    (resource_root / "include/stddef.h").write_text("// authored resource fixture v2\n")
    config.execution["resume"] = True
    second = run_analysis(config, selected, tmp_path / "unused", timeout=60)
    assert second.summary["status"] == "completed"
    assert second.work_root != first.work_root
    assert second.summary["resumed_units"] == 0
    first_contexts = {
        entry["digest"]
        for entry in first.contexts
        if entry["compiler"]["name"] == "libclang"
    }
    second_contexts = {
        entry["digest"]
        for entry in second.contexts
        if entry["compiler"]["name"] == "libclang"
    }
    assert first_contexts != second_contexts


@pytest.mark.parametrize("disappearing", ["resources", "native"])
def test_postflight_dependency_disappearance_retains_changed_receipts(
    tmp_path: Path,
    native: NativeInstallation,
    monkeypatch: pytest.MonkeyPatch,
    disappearing: str,
) -> None:
    import shutil
    import cppulse.analysis_execution as engine

    isolated_native = tmp_path / "isolated-analyzer"
    shutil.copy2(native.analyzer, isolated_native)
    resource_root = tmp_path / "resources"
    (resource_root / "include").mkdir(parents=True)
    (resource_root / "include/stddef.h").write_text("// authored builtin fixture\n")
    selected = NativeInstallation(
        isolated_native, resource_root, native.library_dirs, None
    )
    cfg = configuration(tmp_path)
    (cfg.repo / "main.cpp").write_text("int value() { return 1; }\n")
    original = engine.discover_sources
    calls = 0

    def disappearing_after_worker(root: Path, database=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            if disappearing == "native":
                isolated_native.unlink()
            else:
                shutil.rmtree(resource_root)
        return original(root, database)

    monkeypatch.setattr(engine, "discover_sources", disappearing_after_worker)
    result = run_analysis(cfg, selected, tmp_path / "work", timeout=60)
    assert result.summary["status"] == "input_changed"
    assert result.summary["input_verification"] == "changed"
    assert len(result.results) == 1
    assert result.results[0][1]["execution_receipt"]["status"] == "passed"
    assert result.summary["results"]
    assert any("became unavailable" in line for line in result.summary["limitations"])
    assert (
        json.loads(result.report_path.read_bytes())["metadata"]["analysis"]["files"][0][
            "status"
        ]
        == "failed"
    )


def test_forced_header_context_remains_unqualified_without_pch_closure(
    tmp_path: Path, native: NativeInstallation
) -> None:
    cfg = configuration(tmp_path)
    (cfg.repo / "main.cpp").write_text("int main() { return VALUE; }\n")
    (cfg.repo / "forced.hpp").write_text("#define VALUE 1\n")
    (cfg.repo / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(cfg.repo),
                    "file": "main.cpp",
                    "arguments": [
                        "clang++",
                        "-std=c++17",
                        "-include",
                        "forced.hpp",
                        "-c",
                        "main.cpp",
                    ],
                }
            ]
        )
    )
    result = run_analysis(cfg, native, tmp_path / "work", timeout=60)
    assert result.summary["status"] == "partial"
    assert result.summary["input_verification"] == "unavailable"
    assert any("PCH/module" in value for value in result.summary["limitations"])
    assert result.results and all(
        row["execution_receipt"]["status"] == "passed" for _, row in result.results
    )


@pytest.mark.parametrize("field", ["directory", "file", "command"])
def test_database_rejects_nul_strings_before_native_execution(
    tmp_path: Path, field: str
) -> None:
    from cppulse.analysis_execution import _database

    cfg = configuration(tmp_path)
    row = {
        "directory": str(cfg.repo),
        "file": "main.cpp",
        "command": "clang++ -c main.cpp",
    }
    row[field] += "\0ignored"
    (cfg.repo / "compile_commands.json").write_text(json.dumps([row]))
    with pytest.raises(ContractError, match="NUL"):
        _database(cfg, 1024 * 1024)
