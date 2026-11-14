"""Selected package use needs actual GCC dependency and GNU archive observations."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import pytest

from cppulse.collection import collect
from cppulse.consumer import (
    describe_distribution,
    normalize_consumer_usage,
    parse_gcc_depfile,
    parse_gnu_linker_map,
)
from cppulse.errors import CompatibilityError, ContractError
from cppulse.identities import context_identity, hash_artifact, snapshot_inputs
from cppulse.run_store import RunStore


@pytest.mark.parametrize(
    "content,target,dependencies",
    [
        (
            b"build/main.o: main.cpp include/demo.hpp\n",
            "build/main.o",
            ["main.cpp", "include/demo.hpp"],
        ),
        (
            b"build/main.o: main.cpp \\\n include/path\\ with\\ space.hpp file\\#name.hpp dollar$$name.hpp\n",
            "build/main.o",
            [
                "main.cpp",
                "include/path with space.hpp",
                "file#name.hpp",
                "dollar$name.hpp",
            ],
        ),
    ],
)
def test_gcc_dependencies_preserve_actual_escaped_file_names(
    content: bytes, target: str, dependencies: list[str]
) -> None:
    assert parse_gcc_depfile(content) == (target, dependencies)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"main.o main2.o: main.cpp\n",
        b"main.o: $(GUESS)\n",
        b"main.o: main.cpp\nmain.cpp:\n",
        b"main.o: \xff\n",
    ],
)
def test_unsupported_or_ambiguous_dependency_data_is_not_use_proof(
    content: bytes,
) -> None:
    with pytest.raises(CompatibilityError):
        parse_gcc_depfile(content)


def test_archive_load_alone_is_not_archive_member_use() -> None:
    assert (
        parse_gnu_linker_map(b"Memory Configuration\n\nLOAD package/libunused.a\n")
        == {}
    )


def test_map_members_come_only_from_the_actual_archive_selection_section() -> None:
    data = b"Archive member included to satisfy reference by file (symbol)\n\npackage/libdemo.a(selected.o)\n                              /tmp/main.o (selected())\n\nDiscarded input sections\npackage/libunused.a(fake.o)\n"
    assert parse_gnu_linker_map(data) == {"package/libdemo.a": ["selected.o"]}


def collect_actual_use(
    workspace: Path,
    *,
    standard: str = "c++17",
    extra_flags: tuple[str, ...] = (),
    source_note: str = "",
    probe_source: str = "#include <bits/c++config.h>\n",
    shadow_source: bool = False,
) -> dict[str, Any]:
    """Compile a tiny synthetic real archive/consumer, preserving original facts."""
    compiler, archiver = shutil.which("g++"), shutil.which("ar")
    if compiler is None or archiver is None:
        pytest.skip("Selected actual GNU compiler/archive tools are unavailable")
    compiler, archiver = str(Path(compiler).resolve()), str(Path(archiver).resolve())
    (workspace / "package").mkdir()
    (workspace / "build").mkdir()
    for name, text in {
        "main.cpp": source_note
        + '#include "demo.hpp"\nint library();\nint main(){return add_one(library())==42?0:1;}\n',
        "library.cpp": "int library(){return 41;}\n",
        "package/demo.hpp": "#pragma once\ninline int add_one(int value){return value+1;}\n",
        "probe.cpp": probe_source,
    }.items():
        (workspace / name).write_text(text)
    if shadow_source:
        (workspace / "shadow").mkdir()
        (workspace / "shadow/main.cpp").write_text(
            "// Intentionally unlisted actual compiler input.\n"
            + (workspace / "main.cpp").read_text()
        )
    flags = [
        "-std=" + standard,
        "-O0",
        "-g0",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-v",
        "-Ipackage",
        *extra_flags,
    ]
    source = snapshot_inputs(
        workspace,
        ["main.cpp", "library.cpp", "package/demo.hpp", "probe.cpp"],
        inventory_complete=True,
    )
    context = context_identity(
        {
            "id": "gcc-consumer",
            "compiler": {
                "name": "GNU",
                "version": "14.2.0",
                "sha256": hash_artifact(
                    compiler, "gcc", "gcc", "application/octet-stream"
                )["sha256"],
            },
            "argv": [compiler, *flags],
            "working_directory": ".",
            "language_standard": "c++17",
            "target": "x86_64-linux-gnu",
            "provenance": "inferred",
            "dependencies": [],
            "limitations": [
                "Synthetic selected real compiler-use regression; not a complete toolchain closure."
            ],
        }
    )

    def step(identifier, argv, inputs=(), outputs=(), dependencies=(), cwd="."):
        return {
            "id": identifier,
            "context_id": context["id"],
            "argv": argv,
            "cwd": cwd,
            "depends_on": list(dependencies),
            "inputs": list(inputs),
            "outputs": list(outputs),
            "timeout_seconds": 60,
        }

    steps = [
        step(
            "library",
            [compiler, "-std=c++17", "-c", "library.cpp", "-o", "build/library.o"],
            ["library.cpp"],
            ["build/library.o"],
        ),
        step(
            "archive",
            [archiver, "rcs", "package/libdemo.a", "build/library.o"],
            ["build/library.o"],
            ["package/libdemo.a"],
            ["library"],
        ),
        step(
            "configuration",
            [compiler, *flags, "-dM", "-E", "-x", "c++", "probe.cpp"],
            ["probe.cpp"],
        ),
        step("target", [compiler, "-dumpmachine"]),
        step(
            "consumer",
            [
                compiler,
                *[
                    "-I../package" if shadow_source and flag == "-Ipackage" else flag
                    for flag in flags
                ],
                "-MMD",
                "-MF",
                "../build/main.d" if shadow_source else "build/main.d",
                "main.cpp",
                "../package/libdemo.a" if shadow_source else "package/libdemo.a",
                (
                    "-Wl,-v,-Map,../build/main.map"
                    if shadow_source
                    else "-Wl,-v,-Map,build/main.map"
                ),
                "-o",
                "../build/consumer" if shadow_source else "build/consumer",
            ],
            ["main.cpp", "package/demo.hpp", "package/libdemo.a"],
            ["build/consumer", "build/main.d", "build/main.map"],
            ["archive", "configuration", "target"],
            cwd="shadow" if shadow_source else ".",
        ),
        step(
            "execute",
            [str(workspace / "build/consumer")],
            ["build/consumer"],
            [],
            ["consumer"],
        ),
    ]
    binding = {
        "id": "consumer-build",
        "step_id": "consumer",
        "kind": "build",
        "scope_files": ["main.cpp", "package/demo.hpp"],
        "exercised_inputs": ["build/consumer"],
        "report_path": None,
        "adapter": None,
        "adapter_version": None,
        "inventory_step_id": None,
        "producer_version_step_id": None,
        "execution_log_path": None,
    }
    plan = {
        "version": "2.0.0",
        "id": "actual-consumer-use",
        "recipe": {
            "version": "2.0.0",
            "id": "actual-consumer-use",
            "jobs": 1,
            "contexts": [context["id"]],
            "steps": steps,
        },
        "bindings": [binding],
        "limits": {
            "max_log_bytes": 1024 * 1024,
            "max_artifact_bytes": 64 * 1024 * 1024,
            "max_metadata_bytes": 16 * 1024 * 1024,
            "termination_grace_seconds": 1,
        },
    }
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=[context],
        store=RunStore(workspace / "store"),
    )
    snapshot.verify()
    assert snapshot.manifest["status"] == "completed"
    facts = {
        doc["receipt"]["id"]: doc
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == "execution_facts"
        for doc in [snapshot.read_json(entry["id"])]
    }
    actual = facts["consumer"]
    roles = {
        row["path"]: row["artifact_id"]
        for row in [
            *actual["binding"]["input_artifacts"],
            *actual["binding"]["output_artifacts"],
        ]
    }
    subject = describe_distribution(
        snapshot,
        subject_id="demo-package",
        kind="compiled",
        distribution_files={
            "include/demo.hpp": roles["package/demo.hpp"],
            "lib/libdemo.a": roles["package/libdemo.a"],
        },
    )
    return {
        "snapshot": snapshot,
        "subject": subject,
        "roles": roles,
        "facts": facts,
        "workspace": workspace,
    }


@pytest.fixture(scope="module")
def actual_use(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return collect_actual_use(tmp_path_factory.mktemp("consumer with spaces"))


def test_real_selected_archive_and_packaged_header_use(
    actual_use: dict[str, Any]
) -> None:
    roles = actual_use["roles"]
    result = normalize_consumer_usage(
        actual_use["snapshot"],
        actual_use["subject"],
        usage_id="actual-package-use",
        receipt_id="consumer",
        configuration_probe_receipt_id="configuration",
        target_probe_receipt_id="target",
        required_artifact_ids=[roles["package/demo.hpp"], roles["package/libdemo.a"]],
        depfile_artifact_ids=[roles["build/main.d"]],
        link_map_artifact_id=roles["build/main.map"],
    )
    assert result["status"] == "verified", result["limitations"]
    assert {row["proof_kind"] for row in result["records"]} == {
        "depfile",
        "gnu-linker-map",
    }
    archive = next(
        row for row in result["records"] if row["proof_kind"] == "gnu-linker-map"
    )
    assert archive["members"] == ["library.o"]
    config = result["observed_configuration"]
    assert config["compiler"]["version"] == "14.2.0"
    assert config["language_standard"] == "c++17"
    assert config["exceptions"] is True and config["rtti"] is True
    assert config["target"] == "x86_64-linux-gnu" and config["os"] == "linux"
    assert result["compiler_version"] == "14.2.0" and result["linker_version"] == "2.44"
    # Executed stdout-only probes have available material even with outputs=[].
    assert actual_use["facts"]["configuration"]["material_status"] == "available"
    assert actual_use["facts"]["target"]["material_status"] == "available"
    assert not actual_use["facts"]["target"]["output_facts"]
    assert actual_use["facts"]["execute"]["receipt"]["status"] == "passed"


def test_missing_map_keeps_actual_header_use_without_claiming_archive_use(
    actual_use: dict[str, Any]
) -> None:
    roles = actual_use["roles"]
    result = normalize_consumer_usage(
        actual_use["snapshot"],
        actual_use["subject"],
        usage_id="incomplete-package-use",
        receipt_id="consumer",
        configuration_probe_receipt_id="configuration",
        target_probe_receipt_id="target",
        required_artifact_ids=[roles["package/demo.hpp"], roles["package/libdemo.a"]],
        depfile_artifact_ids=[roles["build/main.d"]],
    )
    assert result["status"] == "unverified"
    assert [row["proof_kind"] for row in result["records"]] == ["depfile"]
    assert any("archive" in reason.lower() for reason in result["limitations"])


def test_use_rejects_a_distribution_selector_outside_the_subject(
    actual_use: dict[str, Any]
) -> None:
    roles = actual_use["roles"]
    with pytest.raises(ContractError):
        normalize_consumer_usage(
            actual_use["snapshot"],
            actual_use["subject"],
            usage_id="bad-selection",
            receipt_id="consumer",
            configuration_probe_receipt_id="configuration",
            target_probe_receipt_id="target",
            required_artifact_ids=[roles["build/consumer"]],
            depfile_artifact_ids=[roles["build/main.d"]],
        )


def test_actual_cwd_source_cannot_borrow_root_source_identity(tmp_path: Path) -> None:
    data = collect_actual_use(tmp_path, shadow_source=True)
    roles = data["roles"]
    result = normalize_consumer_usage(
        data["snapshot"],
        data["subject"],
        usage_id="shadow-source",
        receipt_id="consumer",
        configuration_probe_receipt_id="configuration",
        target_probe_receipt_id="target",
        required_artifact_ids=[roles["package/demo.hpp"], roles["package/libdemo.a"]],
        depfile_artifact_ids=[roles["build/main.d"]],
        link_map_artifact_id=roles["build/main.map"],
    )
    assert result["status"] == "unverified", result
    assert any("source" in reason.lower() for reason in result["limitations"])
