"""Actual direct-GCC/ELF/CTest sanitizer chains, not synthetic proof documents."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cppulse.collection import collect
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.identities import snapshot_inputs
from cppulse.run_store import RunStore
from cppulse.sanitizers import (
    ObjectSelection,
    SanitizerSelection,
    normalize_gcc_sanitizer,
    persist_gcc_sanitizer,
)
from scripts.demo_sanitizers import collect_case, make_plan, selected_tools

FIXTURE = Path(__file__).resolve().parents[1] / "demo/sanitizer-fixture"


def selection(sanitizer: str, scenario: str) -> SanitizerSelection:
    """Select original observed role IDs; no expected outcome enters the API."""
    return SanitizerSelection(
        sanitizer + "-" + scenario,
        sanitizer,
        (
            ("main.cpp", "prebuilt.cpp")
            if scenario.startswith("prebuilt")
            else ("main.cpp",)
        ),
        "compiler-version",
        "nm-version",
        "readelf-version",
        (ObjectSelection("compile", "nm-object", "elf-object"),),
        "link",
        "elf-binary",
        "sanitizer-tests",
    )


@pytest.fixture(scope="module")
def actual_cases(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Compile/link/inspect/run all twelve real selected-input cases afresh."""
    directory = tmp_path_factory.mktemp("actual-gcc-sanitizers")
    tools = selected_tools()
    assert tools["version"] == "14.2.0", "This first adapter requires actual GCC14.2.0"
    store = RunStore(directory / "store")
    cases: dict[str, Any] = {"store": store, "tools": tools, "directory": directory}
    for sanitizer in ["asan", "ubsan", "tsan"]:
        scenarios = (
            [
                "clean",
                "bad",
                "plain-object",
                "substituted-binary",
                "zero-tests",
                "all-skipped",
                "prebuilt-gap",
                "prebuilt-gap-bad",
            ]
            if sanitizer == "asan"
            else ["clean", "bad"]
        )
        for scenario in scenarios:
            key = sanitizer + "-" + scenario
            case = collect_case(
                directory / key, sanitizer, scenario, tools, FIXTURE, store
            )
            snapshot = store.open_run(
                case["raw_run_id"], manifest_sha256=case["raw_manifest_sha256"]
            )
            facts = normalize_gcc_sanitizer(snapshot, selection(sanitizer, scenario))
            cases[key] = (case, snapshot, facts)
    return cases


@pytest.mark.parametrize("sanitizer", ["asan", "ubsan"])
def test_actual_clean_has_callsite_runtime_and_exercised_linked_binary(
    actual_cases: dict[str, Any], sanitizer: str
) -> None:
    _, snapshot, facts = actual_cases[sanitizer + "-clean"]
    assert facts["outcome"] == "passed"
    assert facts["usability"] == "usable"
    assert facts["object_proofs"][0]["observed_symbols"]
    assert (
        facts["runtime_proof"]["required_soname"]
        in facts["runtime_proof"]["observed_needed"]
    )
    assert facts["exercise_proofs"][0]["test_case_ids"]
    ids = {row["id"]: row for row in snapshot.manifest["artifacts"]}
    original = facts["binary_artifact_id"]
    exercised = facts["exercise_proofs"][0]["artifact_id"]
    assert original != exercised
    assert ids[original]["sha256"] == ids[exercised]["sha256"]
    assert not facts["diagnostics"]


@pytest.mark.parametrize("sanitizer", ["asan", "ubsan"])
def test_actual_intentional_runtime_defect_is_bound_to_selected_test(
    actual_cases: dict[str, Any], sanitizer: str
) -> None:
    _, _, facts = actual_cases[sanitizer + "-bad"]
    assert (facts["outcome"], facts["usability"]) == ("failed", "usable")
    assert (
        facts["diagnostics"][0]["test_case_id"]
        in facts["exercise_proofs"][0]["test_case_ids"]
    )
    assert facts["diagnostics"][0]["artifact_id"] in facts["diagnostic_artifact_ids"]


def test_recovering_ubsan_exit_zero_and_passed_ctest_still_has_failed_sanitizer(
    actual_cases: dict[str, Any]
) -> None:
    _, snapshot, facts = actual_cases["ubsan-bad"]
    receipts = [
        snapshot.read_json(row["id"])
        for row in snapshot.manifest["artifacts"]
        if row.get("contract", {}).get("kind") == "execution_receipt"
    ]
    test = next(row for row in receipts if row["id"] == "tests")
    assert test["exit_code"] == 0 and test["status"] == "passed"
    assert test["tests"]["passed"] == 1
    assert facts["outcome"] == "failed"
    assert facts["diagnostics"][0]["file"] == "main.cpp"


@pytest.mark.parametrize(
    "scenario",
    ["plain-object", "substituted-binary", "zero-tests", "all-skipped", "prebuilt-gap"],
)
def test_actual_missing_instrumentation_binary_substitution_or_no_executed_cases_never_passes(
    actual_cases: dict[str, Any], scenario: str
) -> None:
    _, _, facts = actual_cases["asan-" + scenario]
    assert facts["outcome"] == "unsupported"
    assert facts["usability"] != "usable"
    assert facts["limitations"]


def test_credible_diagnostic_survives_additional_uninstrumented_library_gap(
    actual_cases: dict[str, Any]
) -> None:
    _, _, facts = actual_cases["asan-prebuilt-gap-bad"]
    assert (facts["outcome"], facts["usability"]) == ("failed", "usable")
    assert any(
        row["instrumentation"] == "unverified" for row in facts["linked_components"]
    )
    assert facts["requested_files"] == ["main.cpp", "prebuilt.cpp"]


@pytest.mark.parametrize("scenario", ["clean", "bad"])
def test_actual_tsan_runtime_startup_is_not_misreported_as_race(
    actual_cases: dict[str, Any], scenario: str
) -> None:
    _, _, facts = actual_cases["tsan-" + scenario]
    if facts["usability"] == "unsupported":
        assert facts["outcome"] == "unsupported"
        assert any("runtime startup failed" in row for row in facts["limitations"])
        assert not facts["diagnostics"]
    else:
        assert facts["outcome"] == ("passed" if scenario == "clean" else "failed")


def test_unknown_selector_or_source_inventory_is_rejected_before_normalization(
    actual_cases: dict[str, Any]
) -> None:
    _, snapshot, _ = actual_cases["asan-clean"]
    with pytest.raises(ContractError):
        normalize_gcc_sanitizer(
            snapshot, replace(selection("asan", "clean"), link_receipt_id="absent")
        )
    with pytest.raises(ContractError):
        normalize_gcc_sanitizer(
            snapshot,
            replace(selection("asan", "clean"), requested_files=("absent.cpp",)),
        )


def test_derived_publication_retains_all_original_artifacts_and_config_identity(
    actual_cases: dict[str, Any]
) -> None:
    case, snapshot, _ = actual_cases["asan-clean"]
    derived = persist_gcc_sanitizer(
        snapshot,
        workspace=Path(case["workspace"]),
        store=actual_cases["store"],
        selection=selection("asan", "clean"),
    )
    derived.verify()
    assert derived.manifest["source"] == snapshot.manifest["source"]
    assert derived.manifest["config_digest"] == snapshot.manifest["config_digest"]
    ids = {row["id"]: row for row in derived.manifest["artifacts"]}
    assert all(ids[row["id"]] == row for row in snapshot.manifest["artifacts"])
    with pytest.raises(ContractError):
        normalize_gcc_sanitizer(derived, selection("asan", "clean"))


def test_publication_refuses_mutated_live_source_without_corrupting_original(
    actual_cases: dict[str, Any]
) -> None:
    case, snapshot, _ = actual_cases["ubsan-clean"]
    path = Path(case["workspace"]) / "main.cpp"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n// source changed after collection\n")
        with pytest.raises(InputChanged):
            persist_gcc_sanitizer(
                snapshot,
                workspace=path.parent,
                store=actual_cases["store"],
                selection=selection("ubsan", "clean"),
            )
        snapshot.verify()
    finally:
        path.write_bytes(original)


def test_no_implicit_acceptance_of_uncontrolled_runtime_options(
    tmp_path: Path, actual_cases: dict[str, Any]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for path in FIXTURE.glob("*.cpp"):
        (workspace / path.name).write_bytes(path.read_bytes())
    (workspace / "CMakeLists.txt").write_bytes(
        (FIXTURE / "CMakeLists.txt").read_bytes()
    )
    for guard in ["CTestCustom.cmake", "CTestCustom.ctest"]:
        (workspace / guard).write_bytes((FIXTURE / guard).read_bytes())
    (workspace / "build").mkdir()
    source = snapshot_inputs(
        workspace,
        [
            "main.cpp",
            "prebuilt.cpp",
            "CMakeLists.txt",
            "CTestCustom.cmake",
            "CTestCustom.ctest",
        ],
    )
    plan, contexts = make_plan(workspace, "asan", "clean", actual_cases["tools"])
    for step in plan["recipe"]["steps"]:
        if step["id"] == "tests":
            step["environment"].pop("ASAN_OPTIONS")
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=contexts,
        store=RunStore(tmp_path / "store"),
    )
    facts = normalize_gcc_sanitizer(snapshot, selection("asan", "clean"))
    assert facts["usability"] == "unsupported"
    assert any("runtime environment" in row for row in facts["limitations"])


def test_tampered_retained_object_is_integrity_error(
    actual_cases: dict[str, Any]
) -> None:
    _, snapshot, facts = actual_cases["asan-plain-object"]
    # Tamper a copied inspection log, then restore it so the fixture stays usable.
    artifact = next(
        row
        for row in snapshot.manifest["artifacts"]
        if row["id"] == facts["runtime_proof"]["inspection_artifact_id"]
    )
    path = snapshot.path / artifact["path"]
    content = path.read_bytes()
    try:
        path.write_bytes(content + b"tampered")
        with pytest.raises(IntegrityError):
            normalize_gcc_sanitizer(snapshot, selection("asan", "plain-object"))
    finally:
        path.write_bytes(content)


def test_driver_resume_verifies_pins_and_reads_retained_facts(
    actual_cases: dict[str, Any]
) -> None:
    from scripts.demo_sanitizers import normalize_case

    case, _, _ = actual_cases["ubsan-clean"]
    normalized = normalize_case(case, actual_cases["store"])
    resumed = normalize_case(
        {**normalized, "facts": {"outcome": "forged"}}, actual_cases["store"]
    )
    assert resumed["normalized_run_id"] == normalized["normalized_run_id"]
    assert resumed["facts"]["outcome"] == "passed"
    with pytest.raises(IntegrityError):
        normalize_case(
            {**normalized, "normalized_manifest_sha256": "0" * 64},
            actual_cases["store"],
        )
    with pytest.raises(IntegrityError):
        normalize_case(
            {**normalized, "normalized_manifest_sha256": None}, actual_cases["store"]
        )


def test_derived_metadata_limit_is_retained_from_selected_plan(
    tmp_path: Path, actual_cases: dict[str, Any]
) -> None:
    def collect_at(name: str, cap: int):
        workspace = tmp_path / name
        workspace.mkdir()
        for file in [
            "main.cpp",
            "prebuilt.cpp",
            "CMakeLists.txt",
            "CTestCustom.cmake",
            "CTestCustom.ctest",
        ]:
            (workspace / file).write_bytes((FIXTURE / file).read_bytes())
        (workspace / "build").mkdir()
        source = snapshot_inputs(
            workspace,
            [
                "main.cpp",
                "prebuilt.cpp",
                "CMakeLists.txt",
                "CTestCustom.cmake",
                "CTestCustom.ctest",
            ],
        )
        plan, contexts = make_plan(workspace, "asan", "clean", actual_cases["tools"])
        plan["limits"]["max_metadata_bytes"] = cap
        store = RunStore(tmp_path / (name + "-store"))
        return (
            workspace,
            store,
            collect(
                plan, workspace=workspace, source=source, contexts=contexts, store=store
            ),
        )

    _, _, baseline = collect_at("baseline", 16 * 1024 * 1024)
    cap = (baseline.path / "run_manifest.json").stat().st_size + 500
    workspace, store, snapshot = collect_at("lowlimit", cap)
    assert (snapshot.path / "run_manifest.json").stat().st_size < cap
    with pytest.raises(IntegrityError, match="max_metadata_bytes"):
        persist_gcc_sanitizer(
            snapshot,
            workspace=workspace,
            store=store,
            selection=selection("asan", "clean"),
        )
    snapshot.verify()


def test_post_inventory_ctest_environment_rewrite_cannot_suppress_race_into_pass(
    tmp_path: Path, actual_cases: dict[str, Any]
) -> None:
    import sys

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "build").mkdir()
    for file in [
        "main.cpp",
        "prebuilt.cpp",
        "CMakeLists.txt",
        "CTestCustom.cmake",
        "CTestCustom.ctest",
    ]:
        (workspace / file).write_bytes((FIXTURE / file).read_bytes())
    (workspace / "rewrite.py").write_text(
        "from pathlib import Path\n"
        "p=Path('build/CTestTestfile.cmake')\n"
        "p.write_text(p.read_text()+'\\nset_tests_properties(selected-sanitizer-case PROPERTIES ENVIRONMENT \"TSAN_OPTIONS=halt_on_error=1:report_bugs=0:exitcode=66:symbolize=0\")\\n')\n"
        "Path('rewrite-marker.txt').write_text('actual post-inventory runtime override')\n"
    )
    source = snapshot_inputs(
        workspace,
        [
            "main.cpp",
            "prebuilt.cpp",
            "CMakeLists.txt",
            "CTestCustom.cmake",
            "CTestCustom.ctest",
            "rewrite.py",
        ],
    )
    plan, contexts = make_plan(workspace, "tsan", "bad", actual_cases["tools"])
    steps = plan["recipe"]["steps"]
    test = next(step for step in steps if step["id"] == "tests")
    next(step for step in steps if step["id"] == "configure")["outputs"] = [
        "build/CMakeCache.txt",
        "build/CTestCustom.cmake",
        "build/CTestCustom.ctest",
    ]
    next(step for step in steps if step["id"] == "inventory")["inputs"].remove(
        "build/CTestTestfile.cmake"
    )
    test["inputs"].remove("build/CTestTestfile.cmake")
    test["depends_on"].append("rewrite-env")
    steps.append(
        {
            "id": "rewrite-env",
            "context_id": contexts[0]["id"],
            "argv": [sys.executable, "rewrite.py"],
            "cwd": ".",
            "inputs": ["rewrite.py"],
            "outputs": ["rewrite-marker.txt"],
            "depends_on": ["inventory"],
            "timeout_seconds": 20,
            "environment": test["environment"],
        }
    )
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=contexts,
        store=RunStore(tmp_path / "store"),
    )
    snapshot.verify()
    facts = normalize_gcc_sanitizer(snapshot, selection("tsan", "bad"))
    assert facts["usability"] == "unsupported"
    assert any("CTest definition" in row for row in facts["limitations"])


def test_indirect_ctest_definitions_require_another_producer(
    tmp_path: Path, actual_cases: dict[str, Any]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "build").mkdir()
    for file in [
        "main.cpp",
        "prebuilt.cpp",
        "CMakeLists.txt",
        "CTestCustom.cmake",
        "CTestCustom.ctest",
    ]:
        (workspace / file).write_bytes((FIXTURE / file).read_bytes())
    with (workspace / "CMakeLists.txt").open("a") as stream:
        stream.write(
            '\nset_property(DIRECTORY APPEND PROPERTY TEST_INCLUDE_FILES "${CMAKE_CURRENT_SOURCE_DIR}/extra.cmake")\n'
        )
    (workspace / "extra.cmake").write_text(
        "# Explicitly selected harmless indirect definition fixture\n"
    )
    source = snapshot_inputs(
        workspace,
        [
            "main.cpp",
            "prebuilt.cpp",
            "CMakeLists.txt",
            "CTestCustom.cmake",
            "CTestCustom.ctest",
            "extra.cmake",
        ],
    )
    plan, contexts = make_plan(workspace, "asan", "clean", actual_cases["tools"])
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=contexts,
        store=RunStore(tmp_path / "store"),
    )
    facts = normalize_gcc_sanitizer(snapshot, selection("asan", "clean"))
    assert facts["usability"] == "unsupported"
    assert any("CTest definition" in row for row in facts["limitations"])


@pytest.mark.parametrize("custom_name", ["CTestCustom.cmake", "CTestCustom.ctest"])
def test_automatic_ctest_custom_environment_cannot_suppress_into_clean(
    tmp_path: Path, actual_cases: dict[str, Any], custom_name: str
) -> None:
    import sys

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "build").mkdir()
    for file in [
        "main.cpp",
        "prebuilt.cpp",
        "CMakeLists.txt",
        "CTestCustom.cmake",
        "CTestCustom.ctest",
    ]:
        (workspace / file).write_bytes((FIXTURE / file).read_bytes())
    (workspace / "rewrite.py").write_text(
        "from pathlib import Path\n"
        "Path('build/CTestCustom.cmake').unlink(missing_ok=True)\n"
        f"Path('build/{custom_name}').write_text('set(ENV{{TSAN_OPTIONS}} \"halt_on_error=1:report_bugs=0:exitcode=66:symbolize=0\")\\n')\n"
        "Path('rewrite-marker.txt').write_text('actual automatic custom environment override')\n"
    )
    source = snapshot_inputs(
        workspace,
        [
            "main.cpp",
            "prebuilt.cpp",
            "CMakeLists.txt",
            "CTestCustom.cmake",
            "CTestCustom.ctest",
            "rewrite.py",
        ],
    )
    plan, contexts = make_plan(workspace, "tsan", "bad", actual_cases["tools"])
    steps = plan["recipe"]["steps"]
    tests = next(step for step in steps if step["id"] == "tests")
    # Omit automatic custom material from selected input/output roles while
    # retaining the primary definition. The original implementation accepted it.
    guards = {"build/CTestCustom.cmake", "build/CTestCustom.ctest"}
    for step in steps:
        step["inputs"] = [path for path in step["inputs"] if path not in guards]
        step["outputs"] = [path for path in step["outputs"] if path not in guards]
    tests["depends_on"].append("rewrite-env")
    steps.append(
        {
            "id": "rewrite-env",
            "context_id": contexts[0]["id"],
            "argv": [sys.executable, "rewrite.py"],
            "cwd": ".",
            "inputs": ["rewrite.py"],
            "outputs": ["rewrite-marker.txt"],
            "depends_on": ["inventory"],
            "timeout_seconds": 20,
            "environment": tests["environment"],
        }
    )
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=contexts,
        store=RunStore(tmp_path / "store"),
    )
    snapshot.verify()
    facts = normalize_gcc_sanitizer(snapshot, selection("tsan", "bad"))
    assert facts["usability"] == "unsupported"
    assert any("CTest custom" in row for row in facts["limitations"])


def test_compile_cwd_cannot_relabel_unlisted_source_as_selected_file(
    tmp_path: Path, actual_cases: dict[str, Any]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "build").mkdir()
    (workspace / "subdir").mkdir()
    for file in [
        "main.cpp",
        "prebuilt.cpp",
        "CMakeLists.txt",
        "CTestCustom.cmake",
        "CTestCustom.ctest",
    ]:
        (workspace / file).write_bytes((FIXTURE / file).read_bytes())
    (workspace / "subdir/main.cpp").write_bytes((workspace / "main.cpp").read_bytes())
    (workspace / "main.cpp").write_text(
        "// Selected clean uninstrumented source\nint main() { return 0; }\n"
    )
    (workspace / "subdir/build").symlink_to("../build", target_is_directory=True)
    source = snapshot_inputs(
        workspace,
        [
            "main.cpp",
            "prebuilt.cpp",
            "CMakeLists.txt",
            "CTestCustom.cmake",
            "CTestCustom.ctest",
        ],
    )
    plan, contexts = make_plan(workspace, "asan", "clean", actual_cases["tools"])
    next(step for step in plan["recipe"]["steps"] if step["id"] == "compile")[
        "cwd"
    ] = "subdir"
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=contexts,
        store=RunStore(tmp_path / "store"),
    )
    snapshot.verify()
    facts = normalize_gcc_sanitizer(snapshot, selection("asan", "clean"))
    assert facts["usability"] == "unsupported"
    assert not facts["object_proofs"]
    assert any("workspace root" in row for row in facts["limitations"])


def test_custom_default_options_hook_cannot_hide_recovering_ubsan_error(
    tmp_path: Path, actual_cases: dict[str, Any]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "build").mkdir()
    files = [
        "main.cpp",
        "prebuilt.cpp",
        "CMakeLists.txt",
        "CTestCustom.cmake",
        "CTestCustom.ctest",
    ]
    for file in files:
        (workspace / file).write_bytes((FIXTURE / file).read_bytes())
    (workspace / "suppressions.txt").write_text("signed-integer-overflow:*\n")
    with (workspace / "main.cpp").open("a") as stream:
        stream.write(
            '\nextern "C" const char* __ubsan_default_options() { return "suppressions='
            + str(workspace / "suppressions.txt")
            + '"; }\n'
        )
    source = snapshot_inputs(workspace, [*files, "suppressions.txt"])
    plan, contexts = make_plan(workspace, "ubsan", "bad", actual_cases["tools"])
    next(step for step in plan["recipe"]["steps"] if step["id"] == "tests")[
        "inputs"
    ].append("suppressions.txt")
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=contexts,
        store=RunStore(tmp_path / "store"),
    )
    snapshot.verify()
    facts = normalize_gcc_sanitizer(snapshot, selection("ubsan", "bad"))
    assert facts["usability"] == "unsupported"
    assert any("custom sanitizer runtime" in row for row in facts["limitations"])


@pytest.mark.parametrize("logical_id", ["x" * 128, "valid:logical:fact"])
def test_valid_logical_ids_have_safe_short_storage_ids(
    actual_cases: dict[str, Any], logical_id: str
) -> None:
    case, snapshot, _ = actual_cases["asan-clean"]
    selected = replace(selection("asan", "clean"), id=logical_id)
    derived = persist_gcc_sanitizer(
        snapshot,
        workspace=Path(case["workspace"]),
        store=actual_cases["store"],
        selection=selected,
    )
    derived.verify()
    descriptor = next(
        row
        for row in derived.manifest["artifacts"]
        if row.get("contract", {}).get("kind") == "sanitizer_facts"
    )
    assert derived.read_json(descriptor["id"])["id"] == logical_id
    assert ":" not in descriptor["path"]
    assert len(descriptor["id"]) <= 128


def test_ctest_bracket_comments_require_another_definition_dialect(
    tmp_path: Path,
) -> None:
    import sys

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "build").mkdir()
    files = [
        "main.cpp",
        "prebuilt.cpp",
        "CMakeLists.txt",
        "CTestCustom.cmake",
        "CTestCustom.ctest",
    ]
    for file in files:
        (workspace / file).write_bytes((FIXTURE / file).read_bytes())
    (workspace / "rewrite.py").write_text(
        "from pathlib import Path\n"
        "p=Path('build/CTestTestfile.cmake')\n"
        "p.write_text(p.read_text()+'\\n#[=[\\n# opaque bracket comment body\\n#]=]\\n')\n"
    )
    source = snapshot_inputs(workspace, [*files, "rewrite.py"])
    plan, contexts = make_plan(workspace, "asan", "clean", selected_tools())
    steps = plan["recipe"]["steps"]
    configure = next(step for step in steps if step["id"] == "configure")
    configure["outputs"].remove("build/CTestTestfile.cmake")
    inventory = next(step for step in steps if step["id"] == "inventory")
    inventory["depends_on"].append("write-definition")
    steps.append(
        {
            "id": "write-definition",
            "context_id": contexts[0]["id"],
            "argv": [sys.executable, "rewrite.py"],
            "cwd": ".",
            "inputs": ["rewrite.py"],
            "outputs": ["build/CTestTestfile.cmake"],
            "depends_on": ["configure"],
            "timeout_seconds": 20,
            "environment": configure["environment"],
        }
    )
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=contexts,
        store=RunStore(tmp_path / "store"),
    )
    snapshot.verify()
    facts = normalize_gcc_sanitizer(snapshot, selection("asan", "clean"))
    assert facts["usability"] == "unsupported"
    assert any("CTest definition" in row for row in facts["limitations"])
