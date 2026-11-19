"""Native-bound dry-run repairs preserve scope and actual C++ behavior."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.analysis import persist_native_analysis
from cppulse.errors import ContractError, InputChanged
from cppulse.repairs import plan_repairs, validate_plan
from cppulse.run_store import RunSnapshot
from tests.native_buffer_fixture import add_parsed_buffer_fixture
from test_analysis_inventory import native_snapshot


def normalized(
    tmp_path: Path,
    source: bytes = b"typedef unsigned long Count;\n",
    *,
    standard: str = "c++17",
    partial: bool = False,
) -> RunSnapshot:
    """Labeled synthetic contract fixture; actual producer checks are separate."""

    def mutate(report: dict[str, Any], root: Path) -> None:
        (root / "main.cpp").write_bytes(source)
        database_path = root / "compile_commands.json"
        database = json.loads(database_path.read_text())
        database[0]["arguments"][1] = "-std=" + standard
        database_path.write_text(json.dumps(database))
        cell = report["metadata"]["analysis"]["files"][0]
        cell["parse_arguments"][2] = "-std=" + standard
        if partial:
            cell.update(status="partial", error_count=1)
        finding = {
            "rule_id": "CPP-MOD-009",
            "category": "modernization",
            "severity": "info",
            "file": "main.cpp",
            "line": 1,
            "column": 23,
            "message": "typedef 'Count' should use a C++11 type alias instead",
        }
        report["metadata"]["total_loc"] = len(source.splitlines())
        report["findings"] = [finding]
        report["summary"]["total_findings"] = 1
        report["summary"]["by_category"]["modernization"] = 1
        report["summary"]["by_severity"]["info"] = 1

        add_parsed_buffer_fixture(report, root)

    snapshot, selection = native_snapshot(tmp_path, mutate=mutate)
    selection["requested_rules"] = ["CPP-MOD-009"]
    return persist_native_analysis(
        snapshot, workspace=tmp_path, store=tmp_path / "store", **selection
    )


def test_plan_is_precise_bound_deterministic_and_dry_run(tmp_path: Path) -> None:
    snapshot = normalized(tmp_path)
    before = (tmp_path / "main.cpp").read_bytes()
    plan = plan_repairs(snapshot, workspace=tmp_path)
    assert plan_repairs(snapshot, workspace=tmp_path) == plan
    validate_plan(plan)
    assert (tmp_path / "main.cpp").read_bytes() == before
    assert plan["status"] == "planned"
    edit = plan["edits"][0]
    assert before[edit["start_byte"] : edit["end_byte"]] == edit["before"].encode()
    assert edit["after"] == "using Count = unsigned long;"
    assert edit["before_sha256"] == hashlib.sha256(before).hexdigest()
    assert edit["observations"][0]["receipt_id"] == "analyze"
    assert "-typedef unsigned long Count;" in plan["diff"]


def test_stale_source_cannot_get_a_repair(tmp_path: Path) -> None:
    snapshot = normalized(tmp_path)
    (tmp_path / "main.cpp").write_text("typedef int Changed;\n")
    with pytest.raises(InputChanged):
        plan_repairs(snapshot, workspace=tmp_path)


@pytest.mark.parametrize(
    "source",
    [
        b"typedef int Count, Other;\n",
        b"typedef int (*Count)(int);\n",
        b"typedef TYPE Count;\n",
        b"typedef int Count; int another;\n",
        b"/* macro */ typedef int Count;\n",
    ],
)
def test_complex_or_ambiguous_aliases_are_explicitly_unsupported(
    tmp_path: Path, source: bytes
) -> None:
    snapshot = normalized(tmp_path, source)
    plan = plan_repairs(snapshot, workspace=tmp_path)
    assert plan["edits"] == []
    assert plan["status"] == "no_changes"
    assert plan["rejected"][0]["reason"]


def test_plan_tampering_is_rejected(tmp_path: Path) -> None:
    plan = plan_repairs(normalized(tmp_path), workspace=tmp_path)
    changed = deepcopy(plan)
    changed["edits"][0]["after"] = "arbitrary_code();"
    with pytest.raises(ContractError):
        validate_plan(changed)


def test_unknown_observation_selection_is_not_silently_ignored(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="selection"):
        plan_repairs(
            normalized(tmp_path), workspace=tmp_path, observation_ids=["missing"]
        )


@pytest.mark.parametrize("standard", ["c++11", "c++14", "c++17", "c++20"])
def test_before_after_proposal_compiles_and_preserves_type_behavior(
    tmp_path: Path,
    standard: str,
) -> None:
    """Actual GCC validates the narrow proposal; this is a test, not plan credit."""
    source = b'typedef unsigned long Count;\nstatic_assert(__is_same(Count, unsigned long), "type");\nint main() { Count count = 7; return count == 7 ? 0 : 1; }\n'
    snapshot = normalized(tmp_path, source)
    plan = plan_repairs(snapshot, workspace=tmp_path)
    assert len(plan["edits"]) == 1
    proposed = source
    for edit in reversed(plan["edits"]):
        proposed = (
            proposed[: edit["start_byte"]]
            + edit["after"].encode()
            + proposed[edit["end_byte"] :]
        )
    for label, content in [("before", source), ("after", proposed)]:
        path = tmp_path / (label + ".cpp")
        path.write_bytes(content)
        compiled = subprocess.run(
            [
                "g++",
                "-std=" + standard,
                "-Wall",
                "-Wextra",
                "-Werror",
                str(path),
                "-o",
                str(tmp_path / label),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert compiled.returncode == 0, compiled.stderr
        assert subprocess.run([str(tmp_path / label)], check=False).returncode == 0
    assert (tmp_path / "main.cpp").read_bytes() == source


@pytest.mark.parametrize(
    "source",
    [
        b"typedef unsigned long Count;\n#define SOMETHING 1\n",
        b"typedef unsigned long Count;\r#define SOMETHING 1\r",
        b"typedef unsigned long Count;\n%:define SOMETHING 1\n",
        b"typedef unsigned long Count;\n??=define SOMETHING 1\n",
    ],
)
def test_source_directives_are_not_treated_as_literal_aliases(
    tmp_path: Path, source: bytes
) -> None:
    plan = plan_repairs(normalized(tmp_path, source), workspace=tmp_path)
    assert plan["edits"] == []
    assert plan["rejected"]


def test_crlf_and_unicode_comment_are_preserved(tmp_path: Path) -> None:
    source = "\ttypedef unsigned long Count; // café\r\n".encode()
    plan = plan_repairs(normalized(tmp_path, source), workspace=tmp_path)
    edit = plan["edits"][0]
    proposed = (
        source[: edit["start_byte"]]
        + edit["after"].encode()
        + source[edit["end_byte"] :]
    )
    assert proposed == "\tusing Count = unsigned long; // café\r\n".encode()


def test_rewritten_using_declaration_without_typedef_observation_is_a_noop(
    tmp_path: Path,
) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        (root / "main.cpp").write_text("using Count = unsigned long;\n")

    snapshot, selection = native_snapshot(tmp_path, mutate=mutate)
    selection["requested_rules"] = ["CPP-MOD-009"]
    normalized_run = persist_native_analysis(
        snapshot, workspace=tmp_path, store=tmp_path / "store", **selection
    )
    plan = plan_repairs(normalized_run, workspace=tmp_path)
    assert plan["status"] == "no_changes"
    assert plan["diff"] == ""
    assert not plan["rejected"]


def test_module_command_publishes_complete_plan_without_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from cppulse.repairs import main

    snapshot = normalized(tmp_path)
    output = tmp_path / "proposal.json"
    argv = [
        "--store",
        str(tmp_path / "store"),
        "--workspace",
        str(tmp_path),
        "--run-id",
        snapshot.run_id,
        "--manifest-sha256",
        snapshot.manifest_sha256,
        "--output",
        str(output),
    ]
    assert main(argv) == 0
    validate_plan(json.loads(output.read_text()))
    before = output.read_bytes()
    assert main(argv) == 2
    assert output.read_bytes() == before
    assert not list(tmp_path.glob(".cppulse-repair-*"))
    capsys.readouterr()


@pytest.mark.parametrize("selected", [[{}], [""], ["x" * 129], [1]])
def test_malformed_selection_is_a_contract_error(
    tmp_path: Path, selected: list[Any]
) -> None:
    with pytest.raises(ContractError, match="selection"):
        plan_repairs(normalized(tmp_path), workspace=tmp_path, observation_ids=selected)


def test_partial_native_scope_cannot_get_an_edit(tmp_path: Path) -> None:
    plan = plan_repairs(normalized(tmp_path, partial=True), workspace=tmp_path)
    assert plan["edits"] == []
    assert "complete matched analysis" in plan["rejected"][0]["reason"]


def test_cpp98_observation_cannot_be_rewritten_to_cpp11_syntax(tmp_path: Path) -> None:
    plan = plan_repairs(normalized(tmp_path, standard="c++98"), workspace=tmp_path)
    assert plan["edits"] == []
    assert "C++11-or-later" in plan["rejected"][0]["reason"]


@pytest.mark.parametrize("ending", [b"", b"\r", b"\r\n", b"\n\r"])
def test_unified_diff_applies_exactly_for_native_line_endings(
    tmp_path: Path, ending: bytes
) -> None:
    source = b"typedef unsigned long Count;" + ending
    plan = plan_repairs(normalized(tmp_path, source), workspace=tmp_path)
    target = tmp_path / "patch target"
    target.mkdir()
    (target / "main.cpp").write_bytes(source)
    patch = tmp_path / "proposal.patch"
    patch.write_bytes(plan["diff"].encode())
    applied = subprocess.run(
        ["git", "apply", "--unsafe-paths", "--directory=" + str(target), str(patch)],
        cwd="/tmp",
        capture_output=True,
        text=True,
        check=False,
    )
    assert applied.returncode == 0, applied.stderr
    assert (
        hashlib.sha256((target / "main.cpp").read_bytes()).hexdigest()
        == plan["edits"][0]["after_sha256"]
    )
    assert (tmp_path / "main.cpp").read_bytes() == source


@pytest.mark.parametrize("inside_run", [False, True])
def test_plan_output_cannot_mutate_selected_immutable_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], inside_run: bool
) -> None:
    from cppulse.repairs import main

    snapshot = normalized(tmp_path)
    store = tmp_path / "store"
    output = (
        snapshot.path / "new-unlisted-plan.json"
        if inside_run
        else store / "new-plan.json"
    )
    before = {
        str(path.relative_to(store)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in store.rglob("*")
        if path.is_file()
    }
    assert (
        main(
            [
                "--store",
                str(store),
                "--workspace",
                str(tmp_path),
                "--run-id",
                snapshot.run_id,
                "--manifest-sha256",
                snapshot.manifest_sha256,
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()
    assert "selected store" in capsys.readouterr().err
    assert before == {
        str(path.relative_to(store)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in store.rglob("*")
        if path.is_file()
    }


def test_mismatching_derived_observation_cannot_borrow_original_native_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fault-inject a normalized-consumer mismatch without modifying source bytes."""
    import cppulse.repairs as repairs

    snapshot = normalized(tmp_path)
    original = repairs.read_documents

    def mismatching_reader(selected: RunSnapshot) -> dict[str, Any]:
        documents = deepcopy(original(selected))
        documents["observations"][0]["items"][0]["severity"] = "warning"
        return documents

    monkeypatch.setattr(repairs, "read_documents", mismatching_reader)
    plan = plan_repairs(snapshot, workspace=tmp_path)
    assert plan["edits"] == []
    assert "original native report" in plan["rejected"][0]["reason"]


def test_public_module_rejects_nul_paths_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from cppulse.repairs import main

    assert (
        main(
            [
                "--store",
                str(tmp_path / "store"),
                "--workspace",
                str(tmp_path),
                "--run-id",
                "fake",
                "--manifest-sha256",
                "a" * 64,
                "--output",
                "bad\x00path",
            ]
        )
        == 2
    )
    assert "NUL" in capsys.readouterr().err


def test_direct_api_reopens_with_a_real_read_bound(tmp_path: Path) -> None:
    from cppulse.errors import IntegrityError

    snapshot = normalized(tmp_path)
    descriptor = next(
        row for row in snapshot.manifest["artifacts"] if row["id"] == "native-report"
    )
    with (snapshot.path / descriptor["path"]).open("wb") as stream:
        stream.truncate(33 * 1024**2)
    with pytest.raises(IntegrityError, match="read byte limit"):
        plan_repairs(snapshot, workspace=tmp_path)
