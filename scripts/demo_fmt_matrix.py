"""Fetch one locked fmt checkout explicitly, or run the offline consumer example."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from typing import Any

from cppulse.consumer import (
    declare_consumer_matrix,
    describe_distribution,
    normalize_consumer_usage,
    parse_gcc_depfile,
    parse_gnu_linker_map,
    persist_consumer_documents,
)
from cppulse.identities import context_identity
from cppulse.run_store import RunSnapshot, RunStore

from demo_consumer import (
    build_binding,
    retained_facts,
    selected_tool,
    step,
    test_binding,
)
from run_real_corpus import pinned_revision

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/fmt-consumer-matrix"
COMPILED, HEADER_ONLY = "fmt-compiled", "fmt-header-only"
CONTEXTS = (COMPILED, HEADER_ONLY)
HEADER = "include/fmt/format.h"
ARCHIVE = "lib/libfmt.a"
TEST_NAME = "authored_fmt_workload"
OUTPUT = "answer=0042"


def require(condition: bool, reason: str) -> None:
    """Keep the example's evidence checks active even with optimized Python."""
    if not condition:
        raise RuntimeError(reason)


def save_json(path: Path, value: Any) -> None:
    """Retain readable declarations and observed results."""
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def record(
    argv: list[str], cwd: Path, log: Path, *, expected: int = 0
) -> subprocess.CompletedProcess[str]:
    """Run one selected command and retain its actual result before checking it."""
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=180)
    save_json(
        log,
        {
            "argv": argv,
            "cwd": str(cwd),
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    require(result.returncode == expected, f"Unexpected command exit; see {log}")
    return result


def fmt_lock() -> dict[str, str]:
    """Read the single selected corpus row."""
    corpus = json.loads((ROOT / "demo/corpus-lock.json").read_text(encoding="utf-8"))
    return next(project for project in corpus["projects"] if project["id"] == "fmt")


def fetch(output: Path) -> None:
    """Acquire the locked public fmt tag and reject a different revision."""
    project = fmt_lock()
    output.mkdir(parents=True, exist_ok=False)
    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        project["tag"],
        project["repository"],
        str(output / "fmt"),
    ]
    record(command, output, output / "fetch.json")
    pinned_revision(output / "fmt", project["revision"])
    save_json(output / "source-lock.json", project)
    print(project["revision"])


def package(source: Path, output: Path, tools: dict[str, str]) -> Path:
    """Build the exact pinned source archive and inventory installed bytes."""
    project = fmt_lock()
    revision = pinned_revision(source, project["revision"])
    pinned_archive = output / "fmt-source.tar"
    archive_argv = ["git", "-C", str(source), "archive", "--format=tar", revision]
    with pinned_archive.open("wb") as stream:
        subprocess.run(archive_argv, stdout=stream, check=True, timeout=180)
    origin = output / "source"
    with tarfile.open(pinned_archive, mode="r:") as archive:
        archive.extractall(origin, filter="data")
    distribution = output / "distribution"
    record(
        [
            tools["cmake"],
            "-S",
            "source",
            "-B",
            "fmt-build",
            f"-DCMAKE_INSTALL_PREFIX={distribution}",
            "-DCMAKE_INSTALL_LIBDIR=lib",
            f"-DCMAKE_CXX_COMPILER={tools['compiler']}",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_SHARED_LIBS=OFF",
            "-DFMT_TEST=OFF",
            "-DFMT_DOC=OFF",
            "-DFMT_FUZZ=OFF",
        ],
        output,
        output / "fmt-configure.json",
    )
    record(
        [tools["cmake"], "--build", "fmt-build", "--parallel", "1"],
        output,
        output / "fmt-build.json",
    )
    record(
        [tools["cmake"], "--install", "fmt-build"],
        output,
        output / "fmt-install.json",
    )
    files = sorted((distribution / "include/fmt").glob("*.h"))
    require(
        (distribution / ARCHIVE).is_file(), "fmt did not produce its static archive"
    )
    require((distribution / HEADER) in files, "fmt format.h was not installed")
    require(
        all(
            path.read_bytes() == (origin / "include/fmt" / path.name).read_bytes()
            for path in files
        ),
        "Installed fmt headers differ from the locked source",
    )
    pinned_revision(source, revision)
    save_json(
        output / "package-provenance.json",
        {
            "lock": project,
            "archive_argv": archive_argv,
            "archive_sha256": sha256(pinned_archive.read_bytes()).hexdigest(),
            "distribution": {
                path.relative_to(distribution)
                .as_posix(): sha256(path.read_bytes())
                .hexdigest()
                for path in [*files, distribution / ARCHIVE]
            },
        },
    )
    return distribution


def recipe(
    workspace: Path,
    contexts: tuple[str, ...],
    headers: list[str],
    tools: dict[str, str],
    compiler: dict[str, str],
    target: str,
    *,
    fail: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Describe separate compiler and CTest commands for each observed context."""
    steps, bindings, identities = [], [], []
    for context in contexts:
        compiled = context == COMPILED
        directory = f"build/{context}"
        (workspace / directory).mkdir(parents=True)
        binary = f"{directory}/consumer"
        depfile = f"{directory}/main.d"
        map_path = f"{directory}/main.map"
        subject_inputs = [*headers, "package/" + ARCHIVE] if compiled else headers
        flags = [
            "-std=c++17",
            "-O0",
            "-g0",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-v",
            "-Ipackage/include",
        ]
        if not compiled:
            flags.append("-DFMT_HEADER_ONLY=1")
        build_argv = [
            tools["compiler"],
            *flags,
            "-MMD",
            "-MF",
            depfile,
            "main.cpp",
            *(["package/" + ARCHIVE] if compiled else []),
            "-Wl,-v,-Map," + map_path,
            "-o",
            binary,
        ]
        test = context + "-tests"
        report = f"{directory}/ctest"
        execution_log = f"{report}/Testing/Temporary/LastTest.log"
        version = context + "-ctest-version"

        def add(identifier: str, argv: list[str], **kwargs: Any) -> None:
            steps.append({**step(identifier, argv, **kwargs), "context_id": context})

        compiled_test_output = "answer=9999" if fail and not compiled else OUTPUT
        ctest_file = report + "/CTestTestfile.cmake"
        add(
            context + "-macros",
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
        )
        add(context + "-target", [tools["compiler"], "-dumpmachine"])
        add(
            context + "-build",
            build_argv,
            inputs=["main.cpp", *subject_inputs],
            outputs=[binary, depfile, map_path],
            depends_on=[context + "-macros", context + "-target"],
        )
        add(
            context + "-header",
            [
                tools["compiler"],
                *flags,
                "-MMD",
                "-MF",
                f"{directory}/header.d",
                "-c",
                "self-containment.cpp",
                "-o",
                f"{directory}/header.o",
            ],
            inputs=["self-containment.cpp", *headers],
            outputs=[f"{directory}/header.d", f"{directory}/header.o"],
        )
        add(
            context + "-configure",
            [
                tools["cmake"],
                "-S",
                ".",
                "-B",
                report,
                f"-DCPPULSE_SELECTED_BINARY={workspace / binary}",
                f"-DCPPULSE_EXPECTED_OUTPUT={compiled_test_output}",
            ],
            inputs=["CMakeLists.txt"],
            outputs=[ctest_file],
        )
        add(version, [tools["ctest"], "--version"])
        add(
            test + "-inventory",
            [tools["ctest"], "--show-only=json-v1"],
            cwd=report,
            inputs=[binary, ctest_file],
            depends_on=[
                context + "-configure",
                context + "-build",
                context + "-header",
            ],
        )
        add(
            test,
            [tools["ctest"], "--output-on-failure", "--output-junit", "junit.xml"],
            cwd=report,
            inputs=[binary, ctest_file],
            outputs=[report + "/junit.xml", execution_log],
            depends_on=[test + "-inventory", version],
        )
        bindings.extend(
            [
                build_binding(
                    context + "-build", context + "-build", ["main.cpp"], [binary]
                ),
                build_binding(
                    context + "-header",
                    context + "-header",
                    ["self-containment.cpp"],
                    [f"{directory}/header.o"],
                ),
                {
                    **test_binding(test, test, ["main.cpp"], binary, report),
                    "producer_version_step_id": version,
                },
            ]
        )
        identities.append(
            context_identity(
                {
                    "id": context,
                    "compiler": compiler,
                    "argv": build_argv,
                    "working_directory": ".",
                    "language_standard": "c++17",
                    "target": target,
                    "provenance": "inferred",
                    "dependencies": [],
                    "limitations": [
                        "Selected GCC invocation; see retained flags and execution."
                    ],
                }
            )
        )
    plan = {
        "version": "2.0.0",
        "id": "selected-fmt-consumers",
        "recipe": {
            "version": "2.0.0",
            "id": "selected-fmt-consumers",
            "jobs": 1,
            "contexts": list(contexts),
            "steps": steps,
        },
        "bindings": bindings,
        "limits": {
            "max_log_bytes": 1048576,
            "max_artifact_bytes": 67108864,
            "max_metadata_bytes": 16777216,
            "termination_grace_seconds": 1,
        },
    }
    return plan, identities


def document_set(
    raw: RunSnapshot,
    headers: list[str],
    selected: tuple[str, ...],
    compiler: dict[str, str],
    target: str,
    *,
    fail: bool,
) -> list[tuple[str, dict[str, Any]]]:
    """Check retained compiler/test facts against both declared matrix lanes."""
    facts = retained_facts(raw)
    documents = []
    require(
        {row["id"] for row in raw.manifest["contexts"]} == set(selected),
        "Collected contexts differ from the selected recipe",
    )
    for context in CONTEXTS:
        compiled = context == COMPILED
        observed = context in selected
        prefix = f"build/{context}"
        test = context + "-tests"
        usage_id = context + "-workload-use"
        build = facts[context + "-build"] if observed else facts[COMPILED + "-build"]
        inputs = {
            row["path"]: row["artifact_id"]
            for row in build["binding"]["input_artifacts"]
        }
        distribution = {
            path.removeprefix("package/"): inputs[path]
            for path in ([*headers, "package/" + ARCHIVE] if compiled else headers)
        }
        subject = describe_distribution(
            raw,
            subject_id=context + "-distribution",
            kind="compiled" if compiled else "header-only",
            distribution_files=distribution,
            limitations=[
                "Installed fmt 10.2.1 distribution view with selected package paths."
            ],
        )
        documents.append(("distribution_subject", subject))
        expected = {
            "compiler": compiler,
            "target": target,
            "os": "linux",
            "abi": None,
            "language_standard": "c++17",
            "exceptions": True,
            "rtti": True,
            "macros": {} if compiled else {"FMT_HEADER_ONLY": "1"},
            "linking": "static" if compiled else "header-only",
            "dependencies": [],
            "sanitizers": [],
        }
        if observed:
            outputs = {
                row["path"]: row["artifact_id"]
                for row in build["binding"]["output_artifacts"]
            }
            depfile, link_map = (
                outputs[f"{prefix}/main.d"],
                outputs[f"{prefix}/main.map"],
            )
            required = [distribution[HEADER]]
            if compiled:
                required.append(distribution[ARCHIVE])
            usage = normalize_consumer_usage(
                raw,
                subject,
                usage_id=usage_id,
                receipt_id=context + "-build",
                configuration_probe_receipt_id=context + "-macros",
                target_probe_receipt_id=context + "-target",
                required_artifact_ids=required,
                depfile_artifact_ids=[depfile],
                link_map_artifact_id=link_map,
            )
            documents.append(("consumer_usage", usage))
            target_file, deps = parse_gcc_depfile(raw.read_bytes(depfile))
            archives = parse_gnu_linker_map(raw.read_bytes(link_map))
            archive_input = "package/" + ARCHIVE
            macro_flag = "-DFMT_HEADER_ONLY=1"
            build_argv = build["receipt"]["argv"]
            require(
                target_file == f"{prefix}/consumer"
                and {"main.cpp", "package/" + HEADER} <= set(deps)
                and all(
                    (macro_flag in facts[context + kind]["receipt"]["argv"])
                    == (not compiled)
                    for kind in ("-build", "-header", "-macros")
                )
                and (archive_input in build_argv) == compiled
                and bool(archives.get(archive_input)) == compiled,
                f"{context}: actual source/macro/archive selection differs from the lane",
            )
            require(
                raw.read_bytes(inputs["main.cpp"])
                == (EXAMPLE / "main.cpp").read_bytes(),
                f"{context}: checked compiler input is not the authored source",
            )
            header = facts[context + "-header"]
            header_outputs = {
                row["path"]: row["artifact_id"]
                for row in header["binding"]["output_artifacts"]
            }
            header_target, header_deps = parse_gcc_depfile(
                raw.read_bytes(header_outputs[f"{prefix}/header.d"])
            )
            require(
                header["receipt"]["status"] == "passed"
                and "-c" in header["receipt"]["argv"]
                and header_target == f"{prefix}/header.o"
                and set(header_deps) >= {"self-containment.cpp", "package/" + HEADER},
                f"{context}: missing separate fmt header compile",
            )
            probe_log = facts[context + "-macros"]["binding"]["log_artifacts"]["stdout"]
            macros = {
                name: value
                for line in raw.read_bytes(probe_log).decode().splitlines()
                if line.startswith("#define ") and line.count(" ") >= 2
                for name, value in [line.removeprefix("#define ").split(" ", 1)]
            }
            abi_names = ["__GXX_ABI_VERSION", "__GLIBCXX__", "_GLIBCXX_USE_CXX11_ABI"]
            expected["abi"] = "observed-macros-v1:" + ";".join(
                f"{name}={macros[name]}" for name in abi_names
            )
            identities = {row["id"]: row for row in raw.manifest["artifacts"]}
            expected["dependencies"] = [
                {
                    "id": "input-" + sha256(path.encode()).hexdigest(),
                    "sha256": identities[inputs[path]]["sha256"],
                    "availability": "available",
                }
                for path in sorted(
                    (set(deps) - {"main.cpp"})
                    | ({archive_input} if compiled else set())
                )
            ]
            require(
                usage["status"] == "verified"
                and usage["observed_configuration"] == expected
                and {row["distribution_artifact_id"] for row in usage["records"]}
                == set(required),
                f"{context}: use proof differs from the declared matrix: {usage}",
            )
            inventory = json.loads(
                raw.read_bytes(
                    facts[test + "-inventory"]["binding"]["log_artifacts"]["stdout"]
                )
            )
            should_fail = fail and not compiled
            expected_output = "answer=9999" if should_fail else OUTPUT
            receipt = facts[test]["receipt"]
            require(
                [(row["name"], row["command"]) for row in inventory["tests"]]
                == [
                    (
                        TEST_NAME,
                        [
                            str(Path(receipt["cwd"]).parents[2] / prefix / "consumer"),
                            expected_output,
                        ],
                    )
                ]
                and receipt["context_id"] == context
                and receipt["status"] == ("failed" if should_fail else "passed")
                and receipt["exit_code"] == (8 if should_fail else 0)
                and receipt["tests"]
                == {
                    "total": 1,
                    "passed": int(not should_fail),
                    "failed": int(should_fail),
                    "skipped": 0,
                    "errors": 0,
                },
                f"{context}: CTest did not execute exactly the authored selected case: {receipt}",
            )
        else:
            require(
                not any(
                    row["receipt"]["context_id"] == context for row in facts.values()
                ),
                f"{context}: missing lane unexpectedly has execution facts",
            )
        matrix = declare_consumer_matrix(
            raw,
            subject,
            matrix_id=context + "-matrix",
            cases=[
                {
                    "id": "authored-format",
                    "required": True,
                    "context_id": context,
                    "configuration": expected,
                    "tests": [test],
                    "instantiations": ["Selected integer formatting via fmt::format"],
                    "self_containment_headers": [HEADER],
                    "usage_ids": [usage_id],
                }
            ],
            limitations=[
                "Package use, the named workload and a separate header compile are checked by the example; the policy gates test outcomes and required contexts."
            ],
        )
        documents.append(("consumer_matrix", matrix))
    return documents


def selected_run(store: RunStore, reference: dict[str, Any]) -> RunSnapshot:
    """Open and verify the run selected by its own immutable public pins."""
    run = store.open_run(
        reference["run_id"], manifest_sha256=reference["manifest_sha256"]
    )
    run.verify()
    require(
        run.manifest["source"]["digest"] == reference["source_digest"],
        "Run reference source differs from the verified manifest",
    )
    return run


def check_argv(console: str, directory: Path, run: RunSnapshot) -> list[str]:
    """Select one immutable run explicitly for the finite test policy."""
    return [
        console,
        "check",
        "--store",
        str(directory / "store"),
        "--workspace",
        str(directory / "workspace"),
        "--policy",
        str(EXAMPLE / "policy.json"),
        "--run-id",
        run.run_id,
        "--manifest-sha256",
        run.manifest_sha256,
    ]


def scenario(
    output: Path,
    distribution: Path,
    name: str,
    status: str,
    exit_code: int,
    observations: tuple[str, ...],
    tools: dict[str, str],
    compiler: dict[str, str],
    target: str,
) -> tuple[RunSnapshot, dict[str, Any]]:
    """Collect, normalize and publicly assess one fresh scenario in its own store."""
    directory = output / name
    workspace = directory / "workspace"
    workspace.mkdir(parents=True)
    file_names = [
        "CMakeLists.txt",
        "main.cpp",
        "self-containment.cpp",
        "configuration-probe.cpp",
        "package-provenance.json",
    ]
    for file in file_names[:3]:
        shutil.copy2(EXAMPLE / file, workspace / file)
    shutil.copy2(
        ROOT / "demo/package-consumer/configuration-probe.cpp",
        workspace / "configuration-probe.cpp",
    )
    shutil.copy2(
        output / "package-provenance.json", workspace / "package-provenance.json"
    )
    shutil.copytree(distribution / "include", workspace / "package/include")
    (workspace / "package/lib").mkdir()
    shutil.copy2(distribution / ARCHIVE, workspace / "package" / ARCHIVE)
    headers = sorted(
        path.relative_to(workspace).as_posix()
        for path in (workspace / "package/include/fmt").glob("*.h")
    )
    plan, contexts = recipe(
        workspace,
        observations,
        headers,
        tools,
        compiler,
        target,
        fail=name == "known-failure",
    )
    request = {
        "version": "2.0.0",
        "id": "finite-fmt-consumers",
        "source": {
            "kind": "application",
            "files": [*file_names, *headers, "package/" + ARCHIVE],
            "inventory_complete": True,
            "limitations": [
                "Author-selected workspace sources and distribution bytes only."
            ],
        },
        "contexts": contexts,
        "plan": plan,
        "normalizers": [],
    }
    request_file = directory / "collection-request.json"
    save_json(request_file, request)
    store = RunStore(directory / "store")
    result = record(
        [
            tools["console"],
            "collect",
            "--request",
            str(request_file),
            "--workspace",
            str(workspace),
            "--store",
            str(directory / "store"),
        ],
        directory,
        directory / "collect.json",
    )
    selection = json.loads(result.stdout)
    raw = selected_run(store, selection["final_run"])
    docs = document_set(
        raw, headers, observations, compiler, target, fail=name == "known-failure"
    )
    derived = persist_consumer_documents(raw, docs, workspace=workspace, store=store)
    derived.verify()
    result = record(
        check_argv(tools["console"], directory, derived),
        directory,
        directory / "check.json",
        expected=exit_code,
    )
    checked = json.loads(result.stdout)
    require(checked["status"] == status, f"{name}: unexpected policy outcome")
    assessed = selected_run(store, checked["run"])
    artifact_id = checked["assessment_artifact_id"]
    assessment = assessed.read_json(artifact_id)
    for format in ("json", "html"):
        record(
            [
                tools["console"],
                "report",
                "--input",
                str(directory / "store"),
                "--evidence",
                "--run-id",
                assessed.run_id,
                "--manifest-sha256",
                assessed.manifest_sha256,
                "--assessment-artifact-id",
                artifact_id,
                "--format",
                format,
                "--output",
                str(directory / f"report.{format}"),
            ],
            directory,
            directory / f"report-{format}-command.json",
        )
    view = json.loads((directory / "report.json").read_bytes())
    html = (directory / "report.html").read_text(encoding="utf-8")
    controls = {row["id"]: row["status"] for row in assessment["controls"]}
    header_outcome = {
        "passing": "passed",
        "known-failure": "failed",
        "missing-configuration": "unknown",
    }[name]
    shown = {
        (row["kind"], row["id"]): json.loads(row["raw_json"])
        for row in view["facts"]
        if row["kind"] in {"distribution_subject", "consumer_usage", "consumer_matrix"}
    }
    require(
        view["run"]["manifest_sha256"] == assessed.manifest_sha256
        and view["run"]["source_digest"] == assessed.manifest["source"]["digest"]
        and json.loads(view["assessment"]["raw_json"]) == assessment
        and view["assessment"]["display"]["gate"] == status
        and {row["id"] for row in view["contexts"]} == set(observations)
        and controls
        == {
            "compiled-workload": "passed",
            "header-only-workload": header_outcome,
            "consumer-contexts": "unknown" if header_outcome == "unknown" else "passed",
        }
        and shown == {(kind, row["id"]): row for kind, row in docs}
        and assessed.manifest_sha256 in html
        and artifact_id in html,
        f"{name}: evidence reports disagree with the pinned assessment",
    )
    return derived, checked


def main() -> None:
    """Acquire explicitly, or perform the self-checking offline fmt trial."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    acquire = modes.add_parser("fetch", help="explicit public dependency setup")
    acquire.add_argument("--output", type=Path, required=True)
    trial = modes.add_parser(
        "run", help="offline collection, policy and negative controls"
    )
    trial.add_argument("--output", type=Path, required=True)
    trial.add_argument("--fmt-source", type=Path, required=True)
    trial.add_argument("--compiler", default="g++-14")
    trial.add_argument("--cmake", default="cmake")
    trial.add_argument("--ctest", default="ctest")
    trial.add_argument("--console", default="cppulse")
    args = parser.parse_args()
    output = args.output.absolute()
    if args.mode == "fetch":
        fetch(output)
        return
    tools = {
        name: selected_tool(getattr(args, name))
        for name in ("compiler", "cmake", "ctest", "console")
    }
    output.mkdir(parents=True, exist_ok=False)
    compiler_version = record(
        [tools["compiler"], "-dumpfullversion"],
        output,
        output / "compiler-version.json",
    ).stdout.strip()
    target = record(
        [tools["compiler"], "-dumpmachine"], output, output / "target.json"
    ).stdout.strip()
    version = record(
        [tools["ctest"], "--version"], output, output / "ctest-version.json"
    )
    require(
        compiler_version == "14.2.0"
        and version.stdout.splitlines()[0] == "ctest version 3.31.6",
        "Select GCC 14.2.0 and CTest 3.31.6 for this example",
    )
    compiler = {
        "name": "GNU",
        "version": compiler_version,
        "sha256": sha256(Path(tools["compiler"]).read_bytes()).hexdigest(),
    }
    distribution = package(args.fmt_source.resolve(strict=True), output, tools)
    run, passed = scenario(
        output, distribution, "passing", "passed", 0, CONTEXTS, tools, compiler, target
    )
    _, failed = scenario(
        output,
        distribution,
        "known-failure",
        "failed",
        1,
        CONTEXTS,
        tools,
        compiler,
        target,
    )
    _, missing = scenario(
        output,
        distribution,
        "missing-configuration",
        "insufficient_evidence",
        3,
        (COMPILED,),
        tools,
        compiler,
        target,
    )
    passing = output / "passing"
    store = RunStore.open_existing(passing / "store")
    completed = store.resolve_latest().manifest_sha256
    authored = passing / "workspace/main.cpp"
    original = authored.read_bytes()
    try:
        authored.write_bytes(original + b"\n// Deliberate stale-source control.\n")
        stale = json.loads(
            record(
                check_argv(tools["console"], passing, run),
                passing,
                output / "stale-source.json",
                expected=3,
            ).stdout
        )
        require(
            stale["error"]["code"] == "STALE_SOURCE"
            and stale["assessment_artifact_id"] is None
            and store.resolve_latest().manifest_sha256 == completed,
            "Changed workspace source acquired a current assessment",
        )
    finally:
        authored.write_bytes(original)
    run.verify()
    summary = {
        "passing": passed,
        "known_failure": failed,
        "missing_configuration": missing,
        "stale_source": stale,
    }
    save_json(output / "summary.json", summary)
    print(
        json.dumps(
            {
                "fmt": fmt_lock()["revision"],
                "output": str(output),
                "exits": [item["exit_code"] for item in summary.values()],
            }
        )
    )


if __name__ == "__main__":
    main()
