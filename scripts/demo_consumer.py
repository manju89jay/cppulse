"""Collect pinned distribution packages before selected consumer verification."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from uuid import uuid4

from cppulse.collection import collect
from cppulse.consumer import (
    compare_consumers,
    declare_consumer_matrix,
    describe_distribution,
    normalize_consumer_usage,
    persist_consumer_documents,
)
from cppulse.identities import context_identity, hash_artifact, snapshot_inputs
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.transfer import export_bundle

ROOT = Path(__file__).resolve().parents[1]


def selected_tool(name: str) -> str:
    """Select an installed local tool without installing or fetching anything."""
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Required local tool is unavailable: {name}")
    return str(Path(path).resolve(strict=True))


def pinned_sources(
    cache: Path, workspace: Path
) -> tuple[list[str], list[dict[str, Any]]]:
    """Copy only verified pinned tracked source bytes, never Git internals/builds."""
    lock = json.loads((ROOT / "demo/corpus-lock.json").read_text())
    selected = []
    provenance = []
    environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    for project in lock["projects"]:
        source = cache / project["id"]
        revision = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], env=environment, text=True
        ).strip()
        if revision != project["revision"]:
            raise RuntimeError(f"Pinned revision differs for {source}: {revision}")
        dirty = subprocess.check_output(
            ["git", "-C", str(source), "diff", "--name-only", "HEAD"],
            env=environment,
            text=True,
        )
        if dirty:
            raise RuntimeError(f"Pinned tracked source has changes: {source}")
        entries = (
            subprocess.check_output(
                ["git", "-C", str(source), "ls-files", "--stage", "-z"], env=environment
            )
            .decode()
            .split("\0")
        )
        excluded_gitlinks = []
        for entry in sorted(filter(None, entries)):
            metadata, name = entry.split("\t", 1)
            if metadata.split()[0] == "160000":
                excluded_gitlinks.append(name)
                continue
            original = source / name
            if original.is_symlink() or not original.is_file():
                raise RuntimeError(f"Pinned source is not a regular file: {original}")
            relative = Path("sources") / project["id"] / name
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            selected.append(relative.as_posix())
        provenance.append({**project, "excluded_gitlinks": excluded_gitlinks})
    seed = "sources/synthetic/include/cppulse_seed/checked.hpp"
    target = workspace / seed
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / "demo/package-consumer/seed/include/cppulse_seed/checked.hpp", target
    )
    selected.append(seed)
    return selected, provenance


def step(
    identifier: str,
    argv: list[str],
    *,
    inputs: list[str] = (),
    outputs: list[str] = (),
    depends_on: list[str] = (),
    cwd: str = ".",
) -> dict[str, Any]:
    """Declare a bounded explicit collection step."""
    return {
        "id": identifier,
        "context_id": "gcc-package-job",
        "argv": argv,
        "cwd": cwd,
        "depends_on": list(depends_on),
        "inputs": list(inputs),
        "outputs": list(outputs),
        "timeout_seconds": 180,
    }


def build_binding(
    identifier: str, step_id: str, scope: list[str], outputs: list[str]
) -> dict[str, Any]:
    """Retain a selected build/copy result; this does not claim test execution."""
    return {
        "id": identifier,
        "step_id": step_id,
        "kind": "build",
        "scope_files": scope,
        "exercised_inputs": outputs,
        "report_path": None,
        "adapter": None,
        "adapter_version": None,
        "inventory_step_id": None,
        "producer_version_step_id": None,
        "execution_log_path": None,
    }


def output_ids(snapshot: RunSnapshot, receipt_id: str) -> dict[str, str]:
    """Resolve exact output role IDs from a checked retained execution receipt."""
    facts = [
        snapshot.read_json(entry["id"])
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == "execution_facts"
    ]
    selected = next(item for item in facts if item["receipt"]["id"] == receipt_id)
    return {
        item["path"]: item["artifact_id"]
        for item in selected["binding"]["output_artifacts"]
    }


def retained_facts(snapshot: RunSnapshot) -> dict[str, dict[str, Any]]:
    """Read only checked typed observations, keyed by actual recipe step."""
    return {
        document["receipt"]["id"]: document
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == "execution_facts"
        for document in [snapshot.read_json(entry["id"])]
    }


def test_binding(
    identifier: str, selected: str, scope: list[str], binary: str, directory: str
) -> dict[str, Any]:
    """Select the real CTest report, inventory, command log and produced binary."""
    return {
        "id": identifier,
        "step_id": selected,
        "kind": "tests",
        "scope_files": scope,
        "exercised_inputs": [binary],
        "report_path": directory + "/junit.xml",
        "adapter": "ctest-junit",
        "adapter_version": "1.0.0",
        "inventory_step_id": selected + "-inventory",
        "producer_version_step_id": "ctest-version",
        "execution_log_path": directory + "/Testing/Temporary/LastTest.log",
    }


def consumer_run(
    directory: Path,
    package: dict[str, Any],
    package_snapshot: RunSnapshot,
    store: RunStore,
    tools: dict[str, str],
    *,
    scenario: str,
    maintainer: bool = False,
    fallback: dict[str, Any] | None = None,
) -> tuple[RunSnapshot, dict[str, Any]]:
    """Compile/test actual packaged bytes; preserve each run's own source scope."""
    workspace = directory / "workspace"
    workspace.mkdir(parents=True)
    source_paths = []
    for subject in package["subjects"]:
        for file in subject["distribution_files"]:
            relative = "package/" + file["path"]
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package_snapshot.read_bytes(file["artifact_id"]))
            source_paths.append(relative)
    if scenario == "changed-package":
        target = workspace / "package/include/utf8cpp/utf8.h"
        target.write_bytes(
            target.read_bytes()
            + b"\n// Clearly synthetic changed-package identity case.\n"
        )
    if maintainer:
        old_sources = {
            row["path"]: row
            for subject in package["subjects"]
            for row in subject["source_files"]
        }
        old_roles = {
            row["path"]: row["artifact_id"]
            for facts in retained_facts(package_snapshot).values()
            for row in facts["binding"]["input_artifacts"]
        }
        for path, identity in old_sources.items():
            content = package_snapshot.read_bytes(old_roles[path])
            if (
                hash_artifact(
                    package_snapshot.path
                    / next(
                        row["path"]
                        for row in package_snapshot.manifest["artifacts"]
                        if row["id"] == old_roles[path]
                    ),
                    "source",
                    "source",
                    "application/octet-stream",
                )["sha256"]
                != identity["sha256"]
            ):
                raise RuntimeError("Retained original package source identity changed")
            target = workspace / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            source_paths.append(path)
    for name in [
        "main.cpp",
        "self-containment.cpp",
        "configuration-probe.cpp",
        "CMakeLists.txt",
    ]:
        shutil.copy2(ROOT / "demo/package-consumer" / name, workspace / name)
        source_paths.append(name)
    (workspace / "package-build-provenance.json").write_bytes(
        (package_snapshot.path / "run_manifest.json").read_bytes()
    )
    source_paths.append("package-build-provenance.json")
    (workspace / "build").mkdir()
    standard = "c++20" if scenario == "incompatible-cxx20" else "c++17"
    flags = [
        "-std=" + standard,
        "-O0",
        "-g0",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-v",
        "-Ipackage/include",
        "-Ipackage/include/utf8cpp",
    ]
    if scenario == "no-exceptions":
        flags.append("-fno-exceptions")
    package_inputs = sorted(
        {path for path in source_paths if path.startswith("package/")}
    )
    main = "build/package-consumer"
    header = "build/header-consumer"
    steps = [
        step(
            "configuration-probe",
            [
                tools["compiler"],
                *flags,
                "-dM",
                "-E",
                "-x",
                "c++",
                "configuration-probe.cpp",
            ],
            inputs=["configuration-probe.cpp"],
        ),
        step("target-probe", [tools["compiler"], "-dumpmachine"]),
        step(
            "consumer-build",
            [
                tools["compiler"],
                *flags,
                "-MMD",
                "-MF",
                "build/main.d",
                "main.cpp",
                "package/lib/libfmt.a",
                "-Wl,-v,-Map,build/main.map",
                "-o",
                main,
            ],
            inputs=["main.cpp", *package_inputs],
            outputs=[main, "build/main.d", "build/main.map"],
            depends_on=["configuration-probe", "target-probe"],
        ),
        step(
            "header-build",
            [
                tools["compiler"],
                *flags,
                "-MMD",
                "-MF",
                "build/header.d",
                "self-containment.cpp",
                "-Wl,-v,-Map,build/header.map",
                "-o",
                header,
            ],
            inputs=["self-containment.cpp", *package_inputs],
            outputs=[header, "build/header.d", "build/header.map"],
            depends_on=["configuration-probe", "target-probe"],
        ),
        step("ctest-version", [tools["ctest"], "--version"]),
    ]
    bindings = [
        build_binding(
            "consumer-built", "consumer-build", ["main.cpp", *package_inputs], [main]
        ),
        build_binding(
            "header-built",
            "header-build",
            ["self-containment.cpp", *package_inputs],
            [header],
        ),
    ]
    for label, binary, producer, source_name in [
        ("main", main, "consumer-build", "main.cpp"),
        ("header", header, "header-build", "self-containment.cpp"),
    ]:
        target = "tests/" + label
        configure_id = "configure-tests-" + label
        test_id = label + "-tests"
        steps.extend(
            [
                step(
                    configure_id,
                    [
                        tools["cmake"],
                        "-S",
                        ".",
                        "-B",
                        target,
                        "-DCPPULSE_SELECTED_BINARY=" + str(workspace / binary),
                    ],
                    inputs=["CMakeLists.txt"],
                    outputs=[target + "/CTestTestfile.cmake"],
                ),
                step(
                    test_id + "-inventory",
                    [tools["ctest"], "--show-only=json-v1"],
                    cwd=target,
                    inputs=[binary, target + "/CTestTestfile.cmake"],
                    depends_on=[configure_id, producer],
                ),
                step(
                    test_id,
                    [
                        tools["ctest"],
                        "--output-on-failure",
                        "--output-junit",
                        "junit.xml",
                    ],
                    cwd=target,
                    inputs=[binary, target + "/CTestTestfile.cmake"],
                    outputs=[
                        target + "/junit.xml",
                        target + "/Testing/Temporary/LastTest.log",
                    ],
                    depends_on=[test_id + "-inventory", "ctest-version"],
                ),
            ]
        )
        bindings.append(
            test_binding(
                test_id, test_id, [source_name, *package_inputs], binary, target
            )
        )
    context = context_identity(
        {
            "id": "gcc-package-job",
            "compiler": {
                "name": "GNU",
                "version": tools["compiler_version"],
                "sha256": hash_artifact(
                    tools["compiler"],
                    "compiler",
                    "compiler",
                    "application/octet-stream",
                )["sha256"],
            },
            "argv": steps[2]["argv"],
            "working_directory": ".",
            "language_standard": standard,
            "target": tools["compiler_target"],
            "provenance": "inferred",
            "dependencies": [],
            "limitations": [
                "Job selection is inferred; consumer-use normalization independently observes actual GCC flags/probes/depfiles/maps. System runtime/header closure is not complete."
            ],
        }
    )
    plan = {
        "version": "2.0.0",
        "id": "selected-package-" + scenario,
        "recipe": {
            "version": "2.0.0",
            "id": "selected-package-consumer",
            "jobs": 1,
            "contexts": [context["id"]],
            "steps": steps,
        },
        "bindings": bindings,
        "limits": {
            "max_log_bytes": 1024 * 1024,
            "max_artifact_bytes": 64 * 1024 * 1024,
            "max_metadata_bytes": 16 * 1024 * 1024,
            "termination_grace_seconds": 1,
        },
    }
    source = snapshot_inputs(
        workspace,
        sorted(set(source_paths)),
        kind="library" if maintainer else "application",
        inventory_complete=True,
    )
    for name, document in [("plan", plan), ("source", source), ("context", context)]:
        (directory / (name + ".json")).write_text(json.dumps(document, indent=2) + "\n")
    raw = collect(
        plan, workspace=workspace, source=source, contexts=[context], store=store
    )
    raw.verify()
    facts = retained_facts(raw)
    roles = {
        row["path"]: row["artifact_id"]
        for row in [
            *facts["consumer-build"]["binding"]["input_artifacts"],
            *facts["consumer-build"]["binding"]["output_artifacts"],
        ]
    }
    header_roles = {
        row["path"]: row["artifact_id"]
        for row in [
            *facts["header-build"]["binding"]["input_artifacts"],
            *facts["header-build"]["binding"]["output_artifacts"],
        ]
    }
    subjects = []
    usages = []
    matrices = []
    for old in package["subjects"]:
        identifier = old["id"]
        subject = describe_distribution(
            raw,
            subject_id=identifier,
            kind=old["kind"],
            distribution_files={
                row["path"]: roles["package/" + row["path"]]
                for row in old["distribution_files"]
            },
            source_files=(
                [row["path"] for row in old["source_files"]] if maintainer else []
            ),
            limitations=[
                "Selected original library sources are retained only in the maintainer run; downstream package bytes have an independent application source identity."
            ],
        )
        subjects.append(subject)
        selected_paths = {
            "fmt-10.2.1": ["package/lib/libfmt.a", "package/include/fmt/format.h"],
            "utfcpp-4.0.5": ["package/include/utf8cpp/utf8.h"],
            "synthetic-throwing-header": ["package/include/cppulse_seed/checked.hpp"],
        }[identifier]
        usage = normalize_consumer_usage(
            raw,
            subject,
            usage_id=identifier + "-main-use",
            receipt_id="consumer-build",
            configuration_probe_receipt_id="configuration-probe",
            target_probe_receipt_id="target-probe",
            required_artifact_ids=[roles[path] for path in selected_paths],
            depfile_artifact_ids=(
                [roles["build/main.d"]] if "build/main.d" in roles else []
            ),
            link_map_artifact_id=roles.get("build/main.map"),
        )
        usages.append(usage)
        expected = usage["observed_configuration"]
        if expected is None:
            if fallback is None:
                raise RuntimeError(
                    "Maintainer context did not produce usable configuration: "
                    + str(usage)
                )
            expected = json.loads(
                json.dumps(fallback[identifier]["cases"][0]["configuration"])
            )
            expected["exceptions"] = (
                False if scenario == "no-exceptions" else expected["exceptions"]
            )
            expected["language_standard"] = standard
        cases = [
            {
                "id": "main",
                "required": True,
                "context_id": context["id"],
                "configuration": expected,
                "tests": [
                    (
                        "consumer-workload-not-selected"
                        if scenario == "missing-local-test"
                        else "main-tests"
                    )
                ],
                "instantiations": [
                    "selected fmt formatting and UTF string-iterator consumer"
                ],
                "self_containment_headers": [],
                "usage_ids": [usage["id"]],
            }
        ]
        if identifier == "utfcpp-4.0.5":
            selected = normalize_consumer_usage(
                raw,
                subject,
                usage_id=identifier + "-self-containment-use",
                receipt_id="header-build",
                configuration_probe_receipt_id="configuration-probe",
                target_probe_receipt_id="target-probe",
                required_artifact_ids=[header_roles["package/include/utf8cpp/utf8.h"]],
                depfile_artifact_ids=(
                    [header_roles["build/header.d"]]
                    if "build/header.d" in header_roles
                    else []
                ),
                link_map_artifact_id=header_roles.get("build/header.map"),
            )
            usages.append(selected)
            selected_config = selected["observed_configuration"] or (
                fallback[identifier]["cases"][1]["configuration"] if fallback else None
            )
            if selected_config is None:
                raise RuntimeError(
                    "Requested maintainer self-containment compile was not verified"
                )
            cases.append(
                {
                    "id": "self-contained-header",
                    "required": True,
                    "context_id": context["id"],
                    "configuration": selected_config,
                    "tests": ["header-tests"],
                    "instantiations": [],
                    "self_containment_headers": ["include/utf8cpp/utf8.h"],
                    "usage_ids": [selected["id"]],
                }
            )
        matrices.append(
            declare_consumer_matrix(
                raw, subject, matrix_id=identifier + "-consumers", cases=cases
            )
        )
    derived = persist_consumer_documents(
        raw,
        [("distribution_subject", subject) for subject in subjects]
        + [("consumer_usage", usage) for usage in usages]
        + [("consumer_matrix", matrix) for matrix in matrices],
        workspace=workspace,
        store=store,
    )
    derived.verify()
    if maintainer and not all(usage["status"] == "verified" for usage in usages):
        raise RuntimeError(
            "Actual maintainer package use is not fully verified: " + str(usages)
        )
    evidence = {
        record["id"]: {"status": record["status"], "usability": record["usability"]}
        for entry in raw.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == "evidence"
        for record in raw.read_json(entry["id"])["records"]
    }
    summary = {
        "scenario": scenario,
        "workspace": str(workspace),
        "raw_run_id": raw.run_id,
        "run_id": derived.run_id,
        "manifest_sha256": derived.manifest_sha256,
        "source_digest": source["digest"],
        "source_kind": source["kind"],
        "status": derived.manifest["status"],
        "usage": {usage["id"]: usage for usage in usages},
        "matrices": {matrix["subject_id"]: matrix for matrix in matrices},
        "evidence": evidence,
        "compiler_build_status": facts["consumer-build"]["receipt"]["status"],
    }
    (directory / "consumer-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    return derived, summary


def package_run(
    directory: Path, cache: Path, store: RunStore, tools: dict[str, str]
) -> dict[str, Any]:
    """Build/install exact cached libraries and retain a source-bound package run."""
    workspace = directory / "workspace"
    workspace.mkdir(parents=True)
    sources, projects = pinned_sources(cache, workspace)
    fmt_inputs = [name for name in sources if name.startswith("sources/fmt/")]
    utf_inputs = [name for name in sources if name.startswith("sources/utfcpp/")]
    seed = [name for name in sources if name.startswith("sources/synthetic/")]
    fmt_headers = [
        "package/include/fmt/" + path.name
        for path in sorted((workspace / "sources/fmt/include/fmt").glob("*.h"))
    ]
    utf_headers = [
        "package/include/utf8cpp/"
        + path.relative_to(workspace / "sources/utfcpp/source").as_posix()
        for path in sorted((workspace / "sources/utfcpp/source").rglob("*.h"))
    ]
    archive = "package/lib/libfmt.a"
    seeded_header = "package/include/cppulse_seed/checked.hpp"
    configure = [
        tools["cmake"],
        "-S",
        "sources/fmt",
        "-B",
        "fmt-build",
        "-DFMT_TEST=OFF",
        "-DFMT_DOC=OFF",
        "-DFMT_FUZZ=OFF",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DCMAKE_INSTALL_LIBDIR=lib",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_CXX_COMPILER=" + tools["compiler"],
        "-DCMAKE_INSTALL_PREFIX=" + str(workspace / "package"),
    ]
    steps = [
        step(
            "fmt-configure",
            configure,
            inputs=fmt_inputs,
            outputs=[
                "fmt-build/CMakeCache.txt",
                "fmt-build/Makefile",
                "fmt-build/cmake_install.cmake",
                "fmt-build/compile_commands.json",
            ],
        ),
        step(
            "fmt-build",
            [tools["cmake"], "--build", "fmt-build", "--parallel", "2"],
            inputs=fmt_inputs + ["fmt-build/CMakeCache.txt", "fmt-build/Makefile"],
            outputs=["fmt-build/libfmt.a"],
            depends_on=["fmt-configure"],
        ),
        step(
            "fmt-install",
            [tools["cmake"], "--install", "fmt-build"],
            inputs=fmt_inputs + ["fmt-build/libfmt.a", "fmt-build/cmake_install.cmake"],
            outputs=[archive, *fmt_headers],
            depends_on=["fmt-build"],
        ),
        step(
            "utfcpp-configure",
            [
                tools["cmake"],
                "-S",
                "sources/utfcpp",
                "-B",
                "utfcpp-build",
                "-DCMAKE_CXX_COMPILER=" + tools["compiler"],
                "-DCMAKE_INSTALL_PREFIX=" + str(workspace / "package"),
            ],
            inputs=utf_inputs,
            outputs=["utfcpp-build/CMakeCache.txt", "utfcpp-build/cmake_install.cmake"],
        ),
        step(
            "utfcpp-install",
            [tools["cmake"], "--install", "utfcpp-build"],
            inputs=utf_inputs
            + ["utfcpp-build/CMakeCache.txt", "utfcpp-build/cmake_install.cmake"],
            outputs=utf_headers,
            depends_on=["utfcpp-configure"],
        ),
        step(
            "seed-install",
            [tools["cmake"], "-E", "copy", seed[0], seeded_header],
            inputs=seed,
            outputs=[seeded_header],
        ),
    ]
    context = context_identity(
        {
            "id": "gcc-package-job",
            "compiler": {
                "name": "GNU",
                "version": tools["compiler_version"],
                "sha256": hash_artifact(
                    tools["compiler"],
                    "compiler",
                    "compiler",
                    "application/octet-stream",
                )["sha256"],
            },
            "argv": configure,
            "working_directory": ".",
            "language_standard": "c++17",
            "target": tools["compiler_target"],
            "provenance": "inferred",
            "dependencies": [],
            "limitations": [
                "Selected CMake packaging job, not an exact per-translation-unit compiler context or full system/runtime dependency closure."
            ],
        }
    )
    plan = {
        "version": "2.0.0",
        "id": "pinned-library-packaging",
        "recipe": {
            "version": "2.0.0",
            "id": "pinned-library-packaging",
            "jobs": 1,
            "contexts": [context["id"]],
            "steps": steps,
        },
        "bindings": [
            build_binding(
                "fmt-package", "fmt-install", fmt_inputs, [archive, *fmt_headers]
            ),
            build_binding("utfcpp-package", "utfcpp-install", utf_inputs, utf_headers),
            build_binding(
                "synthetic-seed-package", "seed-install", seed, [seeded_header]
            ),
        ],
        "limits": {
            "max_log_bytes": 1024 * 1024,
            "max_artifact_bytes": 64 * 1024 * 1024,
            "max_metadata_bytes": 16 * 1024 * 1024,
            "termination_grace_seconds": 1,
        },
    }
    source = snapshot_inputs(
        workspace, sources, kind="library", inventory_complete=True
    )
    for name, document in [
        ("plan", plan),
        ("source", source),
        ("context", context),
        ("pins", {"projects": projects}),
    ]:
        (directory / (name + ".json")).write_text(json.dumps(document, indent=2) + "\n")
    raw = collect(
        plan, workspace=workspace, source=source, contexts=[context], store=store
    )
    raw.verify()
    if raw.manifest["status"] != "completed":
        raise RuntimeError(
            "Pinned packaging collection is incomplete; inspect " + str(raw.path)
        )
    subjects = []
    for identifier, kind, receipt_id, selected_sources in [
        (
            "fmt-10.2.1",
            "compiled",
            "fmt-install",
            [name for name in fmt_inputs if "/include/" in name or "/src/" in name],
        ),
        (
            "utfcpp-4.0.5",
            "header-only",
            "utfcpp-install",
            [name for name in utf_inputs if "/source/" in name],
        ),
        ("synthetic-throwing-header", "header-only", "seed-install", seed),
    ]:
        outputs = output_ids(raw, receipt_id)
        selected = {
            path.removeprefix("package/"): artifact_id
            for path, artifact_id in outputs.items()
        }
        subjects.append(
            describe_distribution(
                raw,
                subject_id=identifier,
                kind=kind,
                distribution_files=selected,
                source_files=selected_sources,
                limitations=[
                    "Pinned local package bytes only; no upstream full test suite or consumer verification is claimed by this packaging step."
                ],
            )
        )
    derived = persist_consumer_documents(
        raw,
        [("distribution_subject", subject) for subject in subjects],
        workspace=workspace,
        store=store,
    )
    derived.verify()
    return {
        "workspace": str(workspace),
        "raw_run_id": raw.run_id,
        "run_id": derived.run_id,
        "run_path": str(derived.path),
        "manifest_sha256": derived.manifest_sha256,
        "source_digest": source["digest"],
        "subjects": subjects,
        "projects": projects,
        "status": derived.manifest["status"],
        "scope": "Actual build/install of selected pinned distribution bytes; consumer checks follow separately.",
    }


def main() -> None:
    """Run selected local package/consumer cases without downloads or Git writes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tests/tmp/corpus")
    parser.add_argument("--output", type=Path, default=ROOT / "output/consumer-demo")
    parser.add_argument("--phase", choices=["package", "all"], default="all")
    parser.add_argument(
        "--reuse-package-summary",
        type=Path,
        help="Explicitly reuse the already verified package snapshot named by a prior summary; does not rebuild it",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    batch = output / "batches" / uuid4().hex
    batch.mkdir(parents=True)
    tools = {
        "cmake": selected_tool("cmake"),
        "ctest": selected_tool("ctest"),
        "compiler": selected_tool("g++"),
    }
    commands = [
        [tools["compiler"], "-dumpfullversion", "-dumpversion"],
        [tools["compiler"], "-dumpmachine"],
    ]
    for name, command in zip(["compiler_version", "compiler_target"], commands):
        tools[name] = subprocess.check_output(command, text=True, timeout=10).strip()
    (batch / "tool-inspection.json").write_text(
        json.dumps({"tools": tools, "commands": commands}, indent=2) + "\n"
    )
    store = RunStore(output / "store")
    if args.reuse_package_summary:
        upstream = json.loads(args.reuse_package_summary.read_text())["upstream"]
    else:
        upstream = package_run(batch / "package", args.cache.resolve(), store, tools)
    summary = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "batch": str(batch),
        "upstream": upstream,
        "package_reused": bool(args.reuse_package_summary),
        "limitations": [
            "This phase packages actual pinned bytes; it does not yet evaluate consumer applicability or execute upstream full test suites.",
            "Synthetic throwing header is separately labeled and not attributed to fmt/utfcpp.",
        ],
    }
    (batch / "package-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "latest-package.json").write_text(json.dumps(summary, indent=2) + "\n")
    if args.phase == "all":
        package_store = RunStore(Path(upstream["run_path"]).parents[1])
        package_snapshot = package_store.open_run(
            upstream["run_id"], manifest_sha256=upstream["manifest_sha256"]
        )
        maintainer, maintainer_summary = consumer_run(
            batch / "maintainer",
            upstream,
            package_snapshot,
            store,
            tools,
            scenario="maintainer",
            maintainer=True,
        )
        foreign = export_bundle(
            {"upstream": maintainer}, batch / "upstream-transfer"
        ).open_run("upstream")
        cases = []
        retained = {"upstream": maintainer}
        for scenario in [
            "clean",
            "missing-local-test",
            "incompatible-cxx20",
            "no-exceptions",
            "changed-package",
        ]:
            local, case = consumer_run(
                batch / scenario,
                upstream,
                package_snapshot,
                store,
                tools,
                scenario=scenario,
                fallback=maintainer_summary["matrices"],
            )
            if (
                local.manifest["source"]["digest"]
                == maintainer.manifest["source"]["digest"]
            ):
                raise AssertionError(
                    "Maintainer and application source scopes were incorrectly equated"
                )
            comparisons = {}
            for subject in upstream["subjects"]:
                identifier = subject["id"]
                result = compare_consumers(
                    foreign,
                    local,
                    upstream_subject_id=identifier,
                    local_subject_id=identifier,
                    upstream_matrix_id=identifier + "-consumers",
                    local_matrix_id=identifier + "-consumers",
                    generated_at=datetime.now(timezone.utc).isoformat(),
                )
                local = persist_consumer_documents(
                    local,
                    [("consumer_comparison", result.document)],
                    workspace=Path(case["workspace"]),
                    store=store,
                    raw_artifacts=result.artifacts,
                )
                comparisons[identifier] = result.document
            local.verify()
            main_cases = [document["cases"][0] for document in comparisons.values()]
            if scenario == "clean":
                assert all(
                    row["status"] == "compatible"
                    and row["local_test_status"] == "passed"
                    and not row["missing_local_checks"]
                    for row in main_cases
                ), main_cases
            elif scenario == "missing-local-test":
                assert all(
                    row["status"] == "compatible"
                    and row["local_test_status"] == "unknown"
                    and "consumer-workload-not-selected" in row["missing_local_checks"]
                    for row in main_cases
                ), main_cases
            elif scenario in {"incompatible-cxx20", "changed-package"}:
                assert all(
                    row["status"] == "incompatible"
                    and row["local_test_status"] == "passed"
                    for row in main_cases
                ), main_cases
            else:
                assert case["compiler_build_status"] == "failed", case
                assert all(
                    row["status"] == "unknown" and row["local_test_status"] == "unknown"
                    for row in main_cases
                ), main_cases
            case.update(
                comparison_run_id=local.run_id,
                comparison_manifest_sha256=local.manifest_sha256,
                comparison_run_path=str(local.path),
                comparisons=comparisons,
            )
            (batch / scenario / "comparison-summary.json").write_text(
                json.dumps(case, indent=2) + "\n"
            )
            retained[scenario] = local
            cases.append(case)
        transfer = export_bundle(retained, batch / "review-transfer")
        transfer.verify()
        summary.update(
            maintainer=maintainer_summary,
            cases=cases,
            review_transfer=str(transfer.path),
            limitations=[
                "Actual selected Linux/GCC14.2/ld2.44/CTest3.31.6 cases only; not upstream full test suites or other platforms.",
                "Compatible means scoped configuration correspondence for selected distributed bytes, never an application-test/release/certification pass.",
                "Imported upstream raw fields stay unauthenticated claims with source freshness not rechecked; each local run retains its own source identity.",
                "Template names describe authored selected test scope, not exhaustive semantic instantiation coverage.",
                "Synthetic throwing-header/no-exceptions and changed-package cases are intentionally seeded and not attributed upstream defects.",
            ],
        )
        (batch / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        (output / "latest-demo.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
