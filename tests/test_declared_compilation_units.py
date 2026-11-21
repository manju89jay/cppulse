"""Declared compilation units remain visible without invented native evidence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest

from cppulse.analysis_execution import (
    _database,
    _declared_context,
    discover_sources,
    run_analysis,
)
from cppulse.identities import snapshot_inputs
from cppulse.native import NativeInstallation
from cppulse.run_store import RunStore
import test_analysis_execution as fixtures


@pytest.fixture
def native() -> NativeInstallation:
    """Use the existing actual-native fixture; never substitute parser results."""
    return fixtures.native.__wrapped__()


def _command(root: Path, name: str, **extra: Any) -> dict[str, Any]:
    return {
        "directory": str(root),
        "file": name,
        "arguments": ["g++", "-std=gnu++14", "-x", "c++", "-c", name],
        **extra,
    }


def test_supported_and_generated_files_are_discovered_without_silent_filtering(
    tmp_path: Path,
) -> None:
    names = [
        "array.c++",
        "array-test.C++",
        "consumer.cpp",
        "detail.hh",
        "detail.ipp",
        "detail.inl",
        "detail.tpp",
        "message.pb.cpp",
        "schema_generated.h",
        "moc_window.cpp",
        "upb-gen/table.c++",
    ]
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("int value;\n")
    paths, gaps = discover_sources(tmp_path)
    assert paths == sorted(names)
    assert gaps == []


def test_declarations_keep_missing_unsupported_and_external_inputs_unassessed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "consumer.cpp").write_text("int value;\n")
    (root / "unsupported.txt").write_text("must not become parser work\n")
    (tmp_path / "external.c++").write_text("must not be read\n")
    database = [
        _command(root, name)
        for name in [
            "consumer.cpp",
            "missing.c++",
            "unsupported.txt",
            "../external.c++",
        ]
    ]
    original = deepcopy(database)
    paths, gaps = discover_sources(root, database)
    assert paths == ["consumer.cpp"]
    assert database == original
    assert len(gaps) == 3
    assert any("missing.c++: source is missing" in reason for reason in gaps)
    assert any(
        "unsupported.txt: unsupported C++ source extension" in reason for reason in gaps
    )
    assert any("external.c++: outside source root" in reason for reason in gaps)
    source = snapshot_inputs(root, paths, inventory_complete=not gaps)
    assert source["inventory_complete"] is False
    assert [row["path"] for row in source["files"]] == ["consumer.cpp"]


def test_symlink_file_and_parent_declarations_cannot_expand_selected_scope(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "external.c++").write_text("must not be read\n")
    try:
        (root / "alias.c++").symlink_to(outside / "external.c++")
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Source symlinks unavailable: {error}")
    paths, gaps = discover_sources(
        root,
        [
            _command(root, "alias.c++"),
            _command(root, "linked/external.c++"),
            _command(root, "linked/../missing.c++"),
        ],
    )
    assert paths == []
    assert sum("source path contains a symlink" in reason for reason in gaps) == 3
    assert any("Symlink directory not traversed: linked" == reason for reason in gaps)


def test_reconciliation_preserves_database_order_arguments_and_build_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    build = root / "build"
    build.mkdir()
    (root / "array.c++").write_text("int value;\n")
    arguments = [
        "g++",
        "-std=gnu++14",
        "-x",
        "c++",
        "-DVALUE=7",
        "-I../includes",
        "-include",
        "../forced.h",
        "-c",
        "../array.c++",
        "-o",
        "array.o",
    ]
    database = [
        _command(build, "../array.c++", arguments=arguments),
        _command(build, "../array.c++", arguments=["g++", "-DOTHER=1", "../array.c++"]),
    ]
    original = deepcopy(database)
    paths, gaps = discover_sources(root, database)
    context = _declared_context(root, "array.c++", database, "a" * 64)
    assert paths == ["array.c++"]
    assert gaps == []
    assert database == original
    assert context["argv"] == arguments
    assert context["working_directory"] == str(build)
    assert context["provenance"] == "observed"
    assert any("first-command" in reason for reason in context["limitations"])


def test_missing_declaration_becoming_present_changes_reconciled_inventory(
    tmp_path: Path,
) -> None:
    database = [_command(tmp_path, "new.c++")]
    before = discover_sources(tmp_path, database)
    (tmp_path / "new.c++").write_text("int value;\n")
    after = discover_sources(tmp_path, database)
    assert before[0] == []
    assert "source is missing" in before[1][0]
    assert after == (["new.c++"], [])


def test_native_three_declared_units_retain_real_parse_outcomes(
    tmp_path: Path, native: NativeInstallation
) -> None:
    cfg = fixtures.configuration(tmp_path, jobs=1)
    build = cfg.repo / "build"
    build.mkdir()
    rows = []
    for name in ["array.c++", "array-test.c++", "consumer.cpp"]:
        (cfg.repo / name).write_text(
            "#if __cplusplus != 201402L\n#error wrong language standard\n#endif\n"
            "#if RECORDED != 7\n#error missing define\n#endif\nint value;\n"
        )
        rows.append(
            _command(
                build,
                "../" + name,
                arguments=[
                    "g++",
                    "-std=gnu++14",
                    "-DRECORDED=7",
                    "-x",
                    "c++",
                    "-c",
                    "../" + name,
                ],
            )
        )
    (build / "compile_commands.json").write_text(json.dumps(rows))
    result = run_analysis(cfg, native, tmp_path / "work", timeout=60)
    report = json.loads(result.report_path.read_bytes())
    outcomes = report["metadata"]["analysis"]["files"]
    assert len(outcomes) == 3
    assert result.compilation_database == rows
    assert result.plan["discovery_gaps"] == []
    for row in outcomes:
        assert row["status"] == "analyzed", row
        assert row["error_count"] == 0
        assert row["compile_context"] == "database"
        assert "-std=gnu++14" in row["parse_arguments"]
        assert "-DRECORDED=7" in row["parse_arguments"]
        assert "-working-directory=" + str(build) in row["parse_arguments"]


def test_native_gaps_and_exclusions_are_distinct_without_fake_work_units(
    tmp_path: Path, native: NativeInstallation
) -> None:
    cfg = fixtures.configuration(tmp_path, jobs=1)
    cfg.settings["exclude_paths"] = ["excluded.c++"]
    (cfg.repo / "consumer.cpp").write_text("int value;\n")
    (cfg.repo / "excluded.c++").write_text("#error configured exclusion\n")
    (cfg.repo / "message.pb.cpp").write_text("#error generated heuristic exclusion\n")
    (cfg.repo / "unsupported.txt").write_text("#error unsupported\n")
    rows = [
        _command(cfg.repo, name)
        for name in [
            "consumer.cpp",
            "excluded.c++",
            "message.pb.cpp",
            "missing.c++",
            "unsupported.txt",
        ]
    ]
    (cfg.repo / "compile_commands.json").write_text(json.dumps(rows))
    result = run_analysis(cfg, native, tmp_path / "work", timeout=60)
    assert result.summary["status"] == "partial"
    assert result.summary["input_verification"] == "unavailable"
    assert result.source["inventory_complete"] is False
    assert len(result.plan["discovery_gaps"]) == 2
    assert len(result.results) == result.summary["unit_count"] == 3
    report = json.loads(result.report_path.read_bytes())
    outcomes = {
        Path(row["path"]).name: row for row in report["metadata"]["analysis"]["files"]
    }
    assert outcomes["consumer.cpp"]["status"] == "analyzed"
    assert outcomes["excluded.c++"]["status"] == "excluded"
    assert "configured exclude_paths" in outcomes["excluded.c++"]["reason"]
    assert outcomes["message.pb.cpp"]["status"] == "excluded"
    assert "heuristic" in outcomes["message.pb.cpp"]["reason"]
    assert set(outcomes) == {"consumer.cpp", "excluded.c++", "message.pb.cpp"}


def test_publication_retains_raw_database_even_when_no_units_can_execute(
    tmp_path: Path, native: NativeInstallation, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.pipeline as pipeline

    cfg = fixtures.configuration(tmp_path, jobs=1)
    cfg.history["enabled"] = False
    rows = [_command(cfg.repo, "missing.c++")]
    (cfg.repo / "compile_commands.json").write_text(json.dumps(rows))
    monkeypatch.setattr(pipeline, "discover_native", lambda: native)
    summary = pipeline.analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(summary["run_id"])
    assert snapshot.manifest["status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    assert snapshot.manifest["source"]["files"] == []
    assert json.loads(snapshot.read_bytes("analysis-compilation-database")) == rows
    plan = json.loads(snapshot.read_bytes("analysis-plan"))
    assert plan["units"] == []
    assert "source is missing" in plan["discovery_gaps"][0]


def test_selected_external_database_reconciles_declarations_without_rewriting(
    tmp_path: Path,
) -> None:
    cfg = fixtures.configuration(tmp_path)
    (cfg.repo / "array.c++").write_text("int value;\n")
    selected = tmp_path / "compile_commands.json"
    rows = [
        _command(tmp_path, "source/array.c++"),
        _command(tmp_path, "source/missing.c++"),
    ]
    selected.write_text(json.dumps(rows))
    cfg = replace(cfg, compilation_database=selected)
    database, _ = _database(cfg, 1024**2)
    assert database == rows
    paths, gaps = discover_sources(cfg.repo, database)
    assert paths == ["array.c++"]
    assert len(gaps) == 1 and "missing.c++" in gaps[0]
