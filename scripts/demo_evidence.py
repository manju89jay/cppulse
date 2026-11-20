"""Run the synthetic native evidence demo using only public cppulse commands.

Copy this file, its sibling demo_policy.py, and the selected fixture to use the
same harness outside a checkout. It never bootstraps a Python import path, runs
Git, installs tools, contacts a service, or changes project refs.
"""

from __future__ import annotations

import argparse
from collections import Counter
from importlib import resources
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Any
from uuid import uuid4

import cppulse
from cppulse.contracts import validate
from cppulse.identities import hash_artifact, snapshot_inputs
from cppulse.run_store import RunSnapshot, RunStore

from demo_policy import (
    BUILD_JOB,
    CONFIG,
    DATABASE,
    NATIVE_JOB,
    REGISTRY,
    REPORT,
    REQUESTED_RULES,
    RESOURCES,
    documents,
    inspect_tools,
    make_plan,
    native_roles,
    now,
    prepare_workspace,
    selected_policy,
    write_json,
)

SCENARIOS = ("clean", "findings", "missing-tests")
EXPECTED = {
    "clean": (0, "passed"),
    "findings": (1, "failed"),
    "missing-tests": (3, "insufficient_evidence"),
}


def make_request(
    scenario: str,
    workspace: Path,
    source: dict[str, Any],
    resource_files: list[str],
    tools: dict[str, Any],
) -> dict[str, Any]:
    """Construct one finite public request with explicit owned-directory cleanup."""
    plan, contexts = make_plan(scenario, workspace, tools, resource_files)
    steps = plan["recipe"]["steps"]
    control_inputs = [
        path
        for path in ["cmake/Cppulse.cmake", "tools/cppulse"]
        if (workspace / path).is_file()
    ]
    for step in steps:
        if step["id"].startswith("configure-"):
            step["depends_on"].append("clean-owned-generated")
            step["inputs"] = list(dict.fromkeys([*step["inputs"], *control_inputs]))
    steps.insert(
        0,
        {
            "id": "clean-owned-generated",
            "context_id": BUILD_JOB,
            "argv": [
                tools["cmake"],
                "-E",
                "rm",
                "-rf",
                "build",
                "native-build",
                "native-report",
            ],
            "cwd": ".",
            "depends_on": [],
            "inputs": [],
            "outputs": [],
            "timeout_seconds": 30,
        },
    )

    def role(path: str, direction: str = "input") -> dict[str, str]:
        return {"step_id": "native-analysis", "role": direction, "path": path}

    request = {
        "version": "2.0.0",
        "id": "public-native-demo-" + scenario,
        "source": {
            "kind": source["kind"],
            "files": sorted(row["path"] for row in source["files"]),
            "inventory_complete": source["inventory_complete"],
            "limitations": [
                *source["limitations"],
                "Synthetic demonstration fixture and finite selected Clang builtin tree; host compiler headers/runtime are not a complete dependency closure.",
                "Cleanup is authorized only for this harness-owned workspace's build, native-build and native-report directories.",
            ],
        },
        "contexts": contexts,
        "plan": plan,
        "normalizers": [
            {
                "id": "public-native-analysis",
                "kind": "native_analysis",
                "normalizer_version": "1.0.0",
                "step_id": "native-analysis",
                "report": role(REPORT, "output"),
                "registry": role(REGISTRY),
                "config": role(CONFIG),
                "compilation_database": role(DATABASE),
                "resource_manifest": role(RESOURCES),
                "requested_files": ["main.cpp"],
                "requested_rules": REQUESTED_RULES,
            }
        ],
    }
    validate("collection_request", request)
    return request


def cmake_quote(value: Path | str) -> str:
    """Quote a literal argument in private CMake source, never a shell command."""
    return (
        '"'
        + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
        + '"'
    )


def add_cmake_check(workspace: Path, store: Path, policy: Path) -> Path:
    """Copy the installed helper and add an explicitly selected real check target."""
    helper = workspace / "cmake/Cppulse.cmake"
    helper.parent.mkdir()
    helper.write_bytes(
        resources.files("cppulse").joinpath("data/Cppulse.cmake").read_bytes()
    )
    launcher = workspace / "tools/cppulse"
    launcher.parent.mkdir()
    launcher.write_text(
        "#!/bin/sh\n# Transparent demo launcher; inherits the selected environment.\n"
        + "exec "
        + shlex.quote(sys.executable)
        + ' -m cppulse.cli "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    with (workspace / "CMakeLists.txt").open("a", encoding="utf-8") as stream:
        stream.write(
            "\n# Opt-in evidence target: absent from the default build.\n"
            'include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/Cppulse.cmake")\n'
            "cppulse_add_check(\n"
            "  NAME cppulse_evidence_check\n"
            f"  EXECUTABLE {cmake_quote(launcher)}\n"
            f"  STORE {cmake_quote(store)}\n"
            '  WORKSPACE "${CMAKE_CURRENT_SOURCE_DIR}"\n'
            f"  POLICY {cmake_quote(policy)}\n"
            "  DEPENDS cppulse-policy-demo\n"
            "  EXPORT_COMPILE_COMMANDS\n)\n"
        )
    return launcher


def command_document(
    output: str, kind: str, *, validate_document: bool = True
) -> dict[str, Any]:
    """Find the actual typed public result in otherwise mixed CMake output."""
    decoder = json.JSONDecoder()
    candidates = []
    for offset, character in enumerate(output):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(output[offset:])
            if not isinstance(value, dict) or value.get("version") != "2.0.0":
                continue
            if validate_document:
                validate(kind, value)
            candidates.append(value)
        except (ValueError, RuntimeError):
            continue
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one {kind} JSON object; got {len(candidates)}")
    return candidates[0]


class Commands:
    """Retain exact actual command argv, cwd, environment overrides and streams."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True)
        self.records: list[dict[str, Any]] = []

    def run(
        self,
        name: str,
        argv: list[str],
        *,
        cwd: Path,
        expected: tuple[int, ...] = (0,),
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a real command with no shell and retain failed output before raising."""
        record = {
            "name": name,
            "argv": argv,
            "cwd": str(cwd),
            "environment_overrides": environment or {},
            "started_at": now(),
        }
        try:
            raw = subprocess.run(
                argv,
                cwd=cwd,
                env={**os.environ, **(environment or {})},
                capture_output=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired as failure:
            record.update(
                status="timeout",
                exit_code=None,
                capture_status="partial",
                error={"type": type(failure).__name__, "message": str(failure)},
            )
            self._retain(record, failure.stdout or b"", failure.stderr or b"")
            raise RuntimeError(f"{name}: timed out; see {self.directory}") from failure
        except OSError as failure:
            record.update(
                status="launch_error",
                exit_code=None,
                capture_status="unavailable",
                error={"type": type(failure).__name__, "message": str(failure)},
            )
            self._retain(record, b"", b"")
            raise RuntimeError(
                f"{name}: not launched; see {self.directory}"
            ) from failure
        result = subprocess.CompletedProcess(
            raw.args,
            raw.returncode,
            raw.stdout.decode("utf-8", errors="replace"),
            raw.stderr.decode("utf-8", errors="replace"),
        )
        record.update(
            status="completed", capture_status="complete", exit_code=result.returncode
        )
        self._retain(record, raw.stdout, raw.stderr)
        if result.returncode not in expected:
            raise RuntimeError(
                f"{name}: actual exit {result.returncode}, expected {expected}; see {self.directory}"
            )
        return result

    def _retain(self, record: dict[str, Any], stdout: bytes, stderr: bytes) -> None:
        """Keep observed streams and attempt facts even when no exit was observed."""
        record["finished_at"] = now()
        for key, content in [("stdout", stdout), ("stderr", stderr)]:
            path = self.directory / f"{record['name']}.{key}.log"
            path.write_bytes(content)
            record[key] = hash_artifact(
                path, record["name"] + "-" + key, path.name, "text/plain"
            )
        self.records.append(record)
        write_json(self.directory / "commands.json", {"commands": self.records})

    def cli(self, name: str, arguments: list[str], **kwargs: Any) -> dict[str, Any]:
        """Invoke the installed public dispatcher using this selected interpreter."""
        result = self.run(
            name, [sys.executable, "-m", "cppulse.cli", *arguments], **kwargs
        )
        return json.loads(result.stdout)


def open_pin(store: Path, reference: dict[str, Any]) -> RunSnapshot:
    """Open and verify one exact immutable run instead of resolving latest again."""
    snapshot = RunStore.open_existing(store).open_run(reference["run_id"])
    if snapshot.manifest_sha256 != reference["manifest_sha256"]:
        raise RuntimeError("Public command manifest pin changed")
    snapshot.verify()
    return snapshot


def pins(reference: dict[str, Any]) -> list[str]:
    """Return the explicit both-or-neither CLI pin arguments."""
    return [
        "--run-id",
        reference["run_id"],
        "--manifest-sha256",
        reference["manifest_sha256"],
    ]


def verify_native(snapshot: RunSnapshot, scenario: str) -> dict[str, Any]:
    """Check actual original native totals, paths, parser contexts and rule scope."""
    bundle = documents(snapshot)
    inventories = bundle.get("analysis_inventory", [])
    observations = bundle.get("observations", [])
    if len(inventories) != 1 or len(observations) != 1:
        raise RuntimeError(
            "Public normalization did not retain one native inventory/observation set"
        )
    inventory, observed = inventories[0], observations[0]
    if (
        inventory["requested_files"] != ["main.cpp"]
        or inventory["requested_rules"] != REQUESTED_RULES
    ):
        raise RuntimeError("Native selected scope differs from the demo request")
    if inventory["job_context_id"] != NATIVE_JOB or len(inventory["items"]) != 1:
        raise RuntimeError("Native job/file identities are not the selected fixture")
    item = inventory["items"][0]
    if (
        item["file"] != "main.cpp"
        or item["status"] != "analyzed"
        or item["context_match"] != "matched"
    ):
        raise RuntimeError("Native file was not parsed in a matched observed context")
    if "CPP-MEM-001" not in item["executed_rules"]:
        raise RuntimeError("Selected native rule execution was not observed")
    roles = native_roles(snapshot)
    original = snapshot.read_json(
        roles["report_artifact_id"], contract=("findings", "prototype_v1")
    )
    findings = original["findings"]
    if original["summary"]["total_findings"] != len(findings):
        raise RuntimeError("Original native report total does not equal its findings")
    for grouping, key in [("by_severity", "severity"), ("by_category", "category")]:
        counts = Counter(row[key] for row in findings)
        if any(
            value != counts.get(name, 0)
            for name, value in original["summary"][grouping].items()
        ):
            raise RuntimeError("Original native report grouped totals differ")
    repo = Path(original["metadata"]["repo_path"])
    if any(
        (
            Path(row["file"]) if Path(row["file"]).is_absolute() else repo / row["file"]
        ).resolve()
        != (repo / "main.cpp").resolve()
        for row in findings
    ):
        raise RuntimeError("Native finding path is not the selected fixture main.cpp")
    selected_count = sum(row["rule_id"] == "CPP-MEM-001" for row in findings)
    if observed.get("analysis_inventory_id") != inventory["id"] or len(
        observed["items"]
    ) != len(findings):
        raise RuntimeError(
            "Normalized observations do not retain the selected original report inventory/count"
        )
    if any(
        row["file"] != "main.cpp" or row["context_id"] != item["parse_context_id"]
        for row in observed["items"]
    ):
        raise RuntimeError(
            "Normalized observation path/context differs from selected main.cpp parse"
        )
    if (scenario == "findings") != (selected_count > 0):
        raise RuntimeError(
            "Actual selected-rule trigger differs from the intended synthetic case"
        )
    return {
        "report_artifact_id": roles["report_artifact_id"],
        "inventory_id": inventory["id"],
        "observation_ids": [row["id"] for row in observed["items"]],
        "findings": len(findings),
        "selected_rule_findings": selected_count,
        "parse_status": item["status"],
        "context_match": item["context_match"],
        "parse_context_id": item["parse_context_id"],
    }


def cmake_journey(
    commands: Commands,
    workspace: Path,
    store: Path,
    policy: Path,
    checked: dict[str, Any],
    tools: dict[str, Any],
    directory: Path,
) -> dict[str, Any]:
    """Exercise opt-in checks plus independently stale source and binary material."""
    common = [
        "--store",
        str(store),
        "--workspace",
        str(workspace),
        "--policy",
        str(policy),
    ]
    before = {entry.name for entry in (store / "runs").iterdir()}
    commands.run(
        "cmake-default-build", [tools["cmake"], "--build", "build"], cwd=workspace
    )
    after = {entry.name for entry in (store / "runs").iterdir()}
    if before != after:
        raise RuntimeError("Default CMake build unexpectedly ran a cppulse operation")
    result = commands.run(
        "cmake-opt-in-check",
        [tools["cmake"], "--build", "build", "--target", "cppulse_evidence_check"],
        cwd=workspace,
    )
    good = command_document(result.stdout, "check_result")
    if good["exit_code"] != 0 or good["status"] != "passed":
        raise RuntimeError(
            "Explicit CMake target did not preserve the clean policy result"
        )
    open_pin(store, good["run"])
    original = directory / "original-main.cpp"
    shutil.copyfile(workspace / "main.cpp", original)
    commands.run(
        "change-source",
        [
            sys.executable,
            "-c",
            "from pathlib import Path; p=Path('main.cpp'); p.write_bytes(p.read_bytes()+b'\\n// explicit stale-source demo\\n')",
        ],
        cwd=workspace,
    )
    stale_source = commands.cli(
        "check-stale-source",
        ["check", *common, *pins(checked["run"])],
        cwd=directory,
        expected=(3,),
    )
    validate("check_result", stale_source)
    if stale_source["error"]["code"] != "STALE_SOURCE":
        raise RuntimeError("Changed source was not rejected as STALE_SOURCE")
    open_pin(store, stale_source["run"])
    commands.run(
        "restore-source",
        [tools["cmake"], "-E", "copy", str(original), str(workspace / "main.cpp")],
        cwd=directory,
    )
    commands.run(
        "rebuild-restored-source", [tools["cmake"], "--build", "build"], cwd=workspace
    )
    restored = commands.cli(
        "check-restored-bytes", ["check", *common, *pins(checked["run"])], cwd=directory
    )
    if restored["status"] != "passed":
        raise RuntimeError(
            "Identical restored source/binary bytes failed retained-material verification"
        )
    commands.run(
        "change-binary",
        [
            sys.executable,
            "-c",
            "from pathlib import Path; p=Path('build/cppulse-policy-demo'); p.write_bytes(p.read_bytes()+b'cppulse-stale-binary-demo')",
        ],
        cwd=workspace,
    )
    result = commands.run(
        "cmake-check-stale-binary",
        [tools["cmake"], "--build", "build", "--target", "cppulse_evidence_check"],
        cwd=workspace,
        expected=(1, 2, 3),
    )
    stale_binary = command_document(result.stdout, "check_result")
    if (
        stale_binary["exit_code"] != 3
        or stale_binary["error"]["code"] != "STALE_OUTPUT"
    ):
        raise RuntimeError("CMake dependency/check hid the changed binary")
    open_pin(store, stale_binary["run"])
    latest = commands.cli(
        "explain-current-gap", ["explain", "--store", str(store)], cwd=directory
    )
    if latest["assessment"] is not None or latest["run"]["status"] != "partial":
        raise RuntimeError(
            "Current stale attempt incorrectly exposed a previous positive gate"
        )
    historical = commands.cli(
        "explain-historical-clean",
        ["explain", "--store", str(store), *pins(checked["run"])],
        cwd=directory,
    )
    if historical["assessment"]["display"]["gate"] != "passed":
        raise RuntimeError("The pinned historical clean decision was changed")
    return {
        "default_build_new_runs": len(after - before),
        "opt_in_check": good,
        "stale_source_check": stale_source,
        "restored_check": restored,
        "stale_binary_check": stale_binary,
        "cmake_stale_binary_exit": result.returncode,
        "latest_attempt": {
            "run_id": latest["run"]["id"],
            "manifest_sha256": latest["run"]["manifest_sha256"],
        },
        "historical_clean_gate": historical["assessment"]["display"]["gate"],
    }


def run_case(
    scenario: str,
    directory: Path,
    tools: dict[str, Any],
    fixture: Path,
    action_entrypoint: Path | None,
    formats: tuple[str, ...] = ("json", "html", "pdf"),
) -> dict[str, Any]:
    """Collect, assess, check, explain and render one actual synthetic scenario."""
    directory.mkdir()
    commands = Commands(directory / "commands")
    store, policy = directory / "store", directory / "policy.json"
    workspace, _, resource_files = prepare_workspace(
        directory, fixture, Path(tools["resource_directory"]), scenario
    )
    launcher = add_cmake_check(workspace, store, policy)
    selected_source = snapshot_inputs(
        workspace,
        sorted(
            path.relative_to(workspace).as_posix()
            for path in workspace.rglob("*")
            if path.is_file()
        ),
        inventory_complete=True,
    )
    request = make_request(scenario, workspace, selected_source, resource_files, tools)
    write_json(directory / "request.json", request)
    write_json(policy, selected_policy())
    common = ["--store", str(store), "--workspace", str(workspace)]
    collected = commands.cli(
        "collect",
        ["collect", *common, "--request", str(directory / "request.json")],
        cwd=directory,
        expected=((3,) if scenario == "missing-tests" else (0,)),
    )
    validate("workflow_result", collected)
    if collected["normalizers"][0]["status"] != "completed":
        raise RuntimeError("Public native normalizer did not complete")
    for name in ["raw_run", "final_run"]:
        open_pin(store, collected[name])
    native = verify_native(open_pin(store, collected["final_run"]), scenario)
    expected_exit, expected_gate = EXPECTED[scenario]
    assessed = commands.cli(
        "assess",
        ["assess", *common, "--policy", str(policy), *pins(collected["final_run"])],
        cwd=directory,
        expected=(expected_exit,),
    )
    validate("workflow_result", assessed)
    if assessed["policy_gate"] != expected_gate:
        raise RuntimeError(
            "Stored assessment gate differs from actual scenario expectation"
        )
    open_pin(store, assessed["final_run"])
    checked = commands.cli(
        "check",
        ["check", *common, "--policy", str(policy), *pins(assessed["final_run"])],
        cwd=directory,
        expected=(expected_exit,),
    )
    validate("check_result", checked)
    final = open_pin(store, checked["run"])
    view = commands.cli(
        "explain",
        ["explain", "--store", str(store), *pins(checked["run"])],
        cwd=directory,
    )
    validate("snapshot_view", view)
    if view["assessment"]["display"]["gate"] != expected_gate:
        raise RuntimeError("Explain did not preserve the stored policy gate")
    reports = {}
    for format in formats:
        path = directory / "reports" / ("evidence." + format)
        result = commands.cli(
            "report-" + format,
            [
                "report",
                "--input",
                str(store),
                "--evidence",
                "--format",
                format,
                "--output",
                str(path),
                *pins(checked["run"]),
            ],
            cwd=directory,
        )
        if (
            result["run_id"] != final.run_id
            or not path.is_file()
            or path.stat().st_size == 0
        ):
            raise RuntimeError(
                "Public report failed to preserve the selected run or output bytes"
            )
        if format == "json":
            report = json.loads(path.read_text())
            validate("snapshot_view", report)
            if report != view:
                raise RuntimeError("JSON report and explain disagree on the same pin")
        elif format == "html":
            text = path.read_text()
            if expected_gate not in text or final.manifest_sha256 not in text:
                raise RuntimeError("HTML omits the stored gate or manifest pin")
        else:
            if not path.read_bytes().startswith(b"%PDF-"):
                raise RuntimeError("PDF output is not an actual PDF")
        reports[format] = {
            "absolute_path": str(path),
            **hash_artifact(
                path,
                format,
                path.name,
                {
                    "json": "application/json",
                    "html": "text/html",
                    "pdf": "application/pdf",
                }[format],
            ),
        }
        if format == "pdf":
            extractor = shutil.which("pdftotext")
            if extractor:
                text_path = path.with_suffix(".txt")
                commands.run(
                    "verify-pdf-text",
                    [extractor, "-layout", str(path), str(text_path)],
                    cwd=directory,
                )
                text = text_path.read_text()
                if expected_gate not in text or final.manifest_sha256 not in text:
                    raise RuntimeError(
                        "Extracted PDF text omits the stored gate or manifest pin"
                    )
                reports[format]["text_verification"] = {
                    "status": "verified",
                    "absolute_path": str(text_path),
                    **hash_artifact(
                        text_path, "pdf-text", text_path.name, "text/plain"
                    ),
                }
            else:
                reports[format]["text_verification"] = {
                    "status": "not_run",
                    "reason": "Optional pdftotext is unavailable; nonempty PDF header was checked. Independent visual review remains separate.",
                }
    action = None
    if action_entrypoint is not None:
        result = commands.run(
            "local-action-wrapper",
            ["/bin/bash", str(action_entrypoint)],
            cwd=directory,
            expected=(expected_exit,),
            environment={
                "PATH": str(launcher.parent) + os.pathsep + os.environ.get("PATH", ""),
                "GITHUB_WORKSPACE": str(directory),
                "GITHUB_OUTPUT": str(directory / "local-action-output.txt"),
                "INPUT_REPO_PATH": str(workspace),
                "INPUT_STORE_PATH": str(store),
                "INPUT_POLICY_FILE": str(policy),
                "INPUT_FINDING_REQUEST": "",
                "INPUT_RUN_ID": checked["run"]["run_id"],
                "INPUT_MANIFEST_SHA256": checked["run"]["manifest_sha256"],
                "INPUT_POST_COMMENT": "false",
                "INPUT_BASE_REF": "",
                "INPUT_GENERATE_PDF": "false",
                "INPUT_FAIL_ON_REGRESSION": "false",
            },
        )
        action = command_document(result.stdout, "check_result")
        if action["exit_code"] != expected_exit:
            raise RuntimeError("Local Bash wrapper changed the public command exit")
        open_pin(store, action["run"])
        outputs = dict(
            line.split("=", 1)
            for line in (directory / "local-action-output.txt").read_text().splitlines()
        )
        retained_result = Path(outputs["result-path"])
        if (
            outputs["exit-code"] != str(expected_exit)
            or json.loads(retained_result.read_text()) != action
        ):
            raise RuntimeError(
                "Local wrapper output/result file does not match its actual public check"
            )
    integration = (
        cmake_journey(commands, workspace, store, policy, checked, tools, directory)
        if scenario == "clean"
        else None
    )
    return {
        "scenario": scenario,
        "workspace": str(workspace),
        "store": str(store),
        "request": str(directory / "request.json"),
        "policy": str(policy),
        "collection": collected,
        "assessment": assessed,
        "check": checked,
        "gate": expected_gate,
        "native": native,
        "controls": view["assessment"]["display"]["controls"],
        "reports": reports,
        "cmake": integration,
        "local_action": action,
        "commands": str(directory / "commands/commands.json"),
    }


def report_formats(value: str) -> tuple[str, ...]:
    """Validate an explicit nonempty unique list of requested report formats."""
    selected = tuple(value.split(","))
    if (
        not selected
        or len(set(selected)) != len(selected)
        or any(item not in {"json", "html", "pdf"} for item in selected)
    ):
        raise argparse.ArgumentTypeError("Select unique formats from json,html,pdf")
    return selected


def harness_inventory(action_entrypoint: Path | None) -> list[dict[str, Any]]:
    """Hash the two selected Python drivers and optional explicitly selected wrapper."""
    selected = [
        (Path(__file__).resolve(), "demo_evidence", "text/x-python"),
        (
            Path(__file__).resolve().with_name("demo_policy.py"),
            "demo_policy",
            "text/x-python",
        ),
    ]
    if action_entrypoint is not None:
        selected.append(
            (
                action_entrypoint.resolve(strict=True),
                "selected-action-entrypoint",
                "text/x-shellscript",
            )
        )
    return [
        {
            "absolute_path": str(path),
            **hash_artifact(path, identifier, path.name, media_type),
        }
        for path, identifier, media_type in selected
    ]


def main(argv: list[str] | None = None) -> int:
    """Run the requested cases and leave one exact fresh review summary pointer."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["analyzer", "resource-dir", "fixture", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--scenario", choices=["all", *SCENARIOS], default="all")
    parser.add_argument("--action-entrypoint", type=Path)
    parser.add_argument(
        "--formats", type=report_formats, default=("json", "html", "pdf")
    )
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    batch = output / "batches" / uuid4().hex
    batch.mkdir(parents=True)
    tools = inspect_tools(
        args.analyzer.resolve(strict=True), args.resource_dir.resolve(strict=True)
    )
    summary = {
        "version": "demo-evidence-v1",
        "requested_formats": list(args.formats),
        "batch": str(batch),
        "started_at": now(),
        "environment": {
            "python": sys.version,
            "interpreter": sys.executable,
            "cppulse_module": str(Path(cppulse.__file__).resolve()),
            "cppulse_version": cppulse.__version__,
            "cwd": str(Path.cwd()),
            "PYTHONPATH": os.environ.get("PYTHONPATH"),
        },
        "tools": tools,
        "harness": harness_inventory(args.action_entrypoint),
        "limitations": [
            "Clearly labeled synthetic C++ fixture; gates describe only the selected rule, file and two job contexts.",
            "The legacy full-four-document/ranking demo is separate. Ranking remains experimental.",
            "Native local workflow only; Docker/Compose and a hosted GitHub Action are not claimed.",
            "Current material hashes and retained command records identify bytes; they do not authenticate tools or prove a complete host dependency closure.",
        ],
        "cases": [],
    }
    if "pdf" not in args.formats:
        summary["limitations"].append(
            "PDF was explicitly not requested; no PDF capability or output is claimed by this batch."
        )
    write_json(batch / "summary.json", summary)
    try:
        for scenario in SCENARIOS if args.scenario == "all" else [args.scenario]:
            summary["cases"].append(
                run_case(
                    scenario,
                    batch / scenario,
                    tools,
                    args.fixture.resolve(strict=True),
                    (
                        args.action_entrypoint.resolve(strict=True)
                        if args.action_entrypoint
                        else None
                    ),
                    args.formats,
                )
            )
            write_json(batch / "summary.json", summary)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        summary.update(finished_at=now(), error=str(error))
        write_json(batch / "summary.json", summary)
        print(f"Demo failed: {error}; retained batch: {batch}", file=sys.stderr)
        return 1
    summary.update(
        finished_at=now(),
        status="verified",
        gate_counts=dict(Counter(case["gate"] for case in summary["cases"])),
    )
    write_json(batch / "summary.json", summary)
    write_json(output / "latest-demo.json", summary)
    print(
        json.dumps(
            {
                "status": "verified",
                "summary": str(batch / "summary.json"),
                "latest": str(output / "latest-demo.json"),
                "gate_counts": summary["gate_counts"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
