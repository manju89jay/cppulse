"""Collect one explicitly selected recipe into a checked local run snapshot.

Process outcomes, normalized evidence and source freshness remain separate facts.
Selected commands are trusted user code; this module is not an execution sandbox.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
from uuid import uuid4

from cppulse import __version__
from cppulse.adapters.test_results import TestReport, parse_test_report
from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.execution import (
    CancellationToken,
    CollectionResult,
    ProcessLimits,
    StepResult,
    run_recipe,
)
from cppulse.identities import (
    digest_json,
    file_identity,
    verify_inputs,
)
from cppulse.run_store import RunSnapshot, RunStore

_VERSION = "1.0.0"
_SCOPE_LIMIT = "Source scope is explicitly declared; it is not dynamic coverage or proof that every listed source/header contributed to a binary."
_TOOL_LIMIT = "Executable hashes identify selected files, not their interpreter, runtime dependency closure or producer authenticity."


def _control_bytes(document: dict[str, Any], limit: int) -> bytes:
    content = (
        json.dumps(
            document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")
    if len(content) > limit:
        raise IntegrityError(f"Control JSON exceeds max_metadata_bytes={limit}")
    return content


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _id(label: str) -> str:
    return "a-" + hashlib.sha256(label.encode()).hexdigest()


def _stat(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _public_stat(info: os.stat_result) -> dict[str, int]:
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


@dataclass(frozen=True)
class _Frozen:
    id: str
    path: Path
    destination: str
    sha256: str
    size_bytes: int
    media_type: str


class _MaterialError(Exception):
    def __init__(self, reason: str, usability: str = "missing") -> None:
        self.usability = usability
        super().__init__(reason)


class _Capture:
    """Private immutable copies bound to observed facts before store allocation."""

    def __init__(self, root: Path, cap: int, metadata_cap: int) -> None:
        self.root = root
        self.cap = cap
        self.metadata_cap = metadata_cap
        self.files: dict[str, _Frozen] = {}
        self.documents: dict[str, tuple[dict[str, Any], str | None]] = {}
        self.issues: dict[str, list[str]] = {}
        self.diagnostics: dict[str, list[str]] = {}

    def document(
        self, key: str, document: dict[str, Any], contract: str | None = None
    ) -> str:
        _control_bytes(document, self.metadata_cap)
        artifact_id = _id(key)
        self.documents[artifact_id] = (deepcopy(document), contract)
        return artifact_id

    def issue(self, step: str, reason: str, *, key: str = "material") -> None:
        self.issues.setdefault(step, []).append(reason)
        artifact_id = self.document(
            f"diagnostic:{step}:{key}:{len(self.issues[step])}",
            {"status": "unavailable", "reason": reason, "limit_bytes": self.cap},
        )
        self.diagnostics.setdefault(step, []).append(artifact_id)

    def freeze(
        self,
        key: str,
        root: Path,
        relative: str,
        *,
        expected: dict[str, Any] | None = None,
        truncate: bool = False,
        media_type: str = "application/octet-stream",
    ) -> _Frozen:
        selected = root / file_identity(root, relative)
        before_path = selected.lstat()
        descriptor = os.open(
            selected,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        destination = self.root / (_id(key) + ".blob")
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or _stat(before) != _stat(before_path):
                raise _MaterialError(
                    "Material changed while opening its snapshot", "mismatched"
                )
            if before.st_size > self.cap and not truncate:
                raise _MaterialError(
                    f"Artifact {relative!r} exceeds max_artifact_bytes={self.cap}; binary bytes were not retained"
                )
            content = source.read(self.cap + 1)
            after = os.fstat(source.fileno())
        current = root / file_identity(root, relative)
        if _stat(before) != _stat(after) or _stat(after) != _stat(current.lstat()):
            raise _MaterialError("Material changed during snapshot", "mismatched")
        if len(content) > self.cap:
            if not truncate:
                raise _MaterialError(
                    "Material exceeded its snapshot bound", "mismatched"
                )
            content = content[: self.cap]
        sha = hashlib.sha256(content).hexdigest()
        if expected is not None and (
            expected["sha256"] != sha
            or expected["size_bytes"] != len(content)
            or ("stat" in expected and expected["stat"] != _public_stat(after))
        ):
            raise _MaterialError(
                f"Material {relative!r} differs from its observed execution facts",
                "mismatched",
            )
        destination.write_bytes(content)
        frozen = _Frozen(
            _id(key),
            destination,
            "artifacts/" + _id(key) + ".blob",
            sha,
            len(content),
            media_type,
        )
        self.files[frozen.id] = frozen
        return frozen


def _manifest(
    plan: dict[str, Any],
    source: dict[str, Any],
    contexts: list[dict[str, Any]],
    *,
    run_id: str,
    status: str,
    stages: list[dict[str, Any]],
    started: str,
    finished: str,
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "version": "2.0.0",
        "run_id": run_id,
        "status": status,
        "source": deepcopy(source),
        "contexts": deepcopy(contexts),
        "stages": deepcopy(stages),
        "artifacts": [],
        "started_at": started,
        "finished_at": finished,
        "config_digest": digest_json(plan),
        "versions": {
            "cppulse": __version__,
            "collector": _VERSION,
            "ctest-junit-adapter": "1.0.0",
        },
        "limitations": list(dict.fromkeys(limitations)),
    }


def _not_attempted(
    plan: dict[str, Any],
    source: dict[str, Any],
    work: Path,
    reason: str,
    cancel: CancellationToken,
) -> CollectionResult:
    stamp = _now()
    results = []
    for step in plan["recipe"]["steps"]:
        directory = work / _id(step["id"])
        directory.mkdir(parents=True)
        stdout, stderr = directory / "stdout.log", directory / "stderr.log"
        stdout.touch()
        stderr.touch()
        results.append(
            StepResult(
                {
                    "version": "2.0.0",
                    "id": step["id"],
                    "source_digest": source["digest"],
                    "context_id": step["context_id"],
                    "producer": {"name": "cppulse.executor", "version": __version__},
                    "argv": deepcopy(step["argv"]),
                    "cwd": step["cwd"],
                    "status": "not_attempted",
                    "reason": reason,
                    "exit_code": None,
                    "signal": None,
                    "started_at": stamp,
                    "finished_at": stamp,
                    "artifact_ids": [],
                    "log_artifact_ids": [],
                    "depends_on": deepcopy(step["depends_on"]),
                },
                stdout,
                stderr,
            )
        )
    return CollectionResult(results, stamp, stamp, cancel.is_cancelled(), 0, [reason])


def _tool_problem(result: StepResult) -> str | None:
    """Verify a selected host executable without source-path spelling rules."""
    fact = result.executable_fact
    if fact is None:
        return "No executable identity was observed"
    try:
        path = Path(fact["path"])
        if not path.is_absolute() or path.resolve(strict=True) != path:
            return "Selected executable path changed after its command"
        before_path = path.lstat()
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or _stat(before) != _stat(before_path):
                return "Selected executable changed while opening its identity"
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
            after = os.fstat(stream.fileno())
        if _stat(before) != _stat(after) or _stat(after) != _stat(path.lstat()):
            return "Selected executable changed while recording its identity"
        if (
            hasher.hexdigest() != fact["sha256"]
            or after.st_size != fact["size_bytes"]
            or fact.get("stat") != _public_stat(after)
        ):
            return "Selected executable changed after its command"
    except (OSError, RuntimeError, ValueError) as error:
        return "Selected executable is unavailable after its command: " + str(error)
    return None


def _inputs_stable(result: StepResult) -> bool:
    return result.input_facts == result.input_after_facts


def _freeze_results(
    result: CollectionResult,
    workspace: Path,
    work: Path,
    capture: _Capture,
    sources: dict[str, _Frozen],
) -> tuple[
    dict[str, dict[str, _Frozen]],
    dict[str, dict[str, _Frozen]],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    inputs: dict[str, dict[str, _Frozen]] = {}
    outputs: dict[str, dict[str, _Frozen]] = {}
    logs: dict[str, list[str]] = {}
    problems: dict[str, list[str]] = {}
    produced = {
        fact["path"]: fact for item in result.steps for fact in item.output_facts
    }
    for item in result.steps:
        step = item.receipt["id"]
        inputs[step], outputs[step], logs[step], problems[step] = {}, {}, [], []
        for stream, path in [
            ("stdout", item.stdout_path),
            ("stderr", item.stderr_path),
        ]:
            try:
                frozen = capture.freeze(
                    f"log:{step}:{stream}",
                    work,
                    path.relative_to(work).as_posix(),
                    truncate=True,
                    media_type="text/plain",
                )
                logs[step].append(frozen.id)
                if path.stat().st_size > frozen.size_bytes:
                    capture.issue(
                        step,
                        f"Retained {stream} was further capped to max_artifact_bytes; the archived log is a prefix",
                        key=stream,
                    )
                    problems[step].append("Captured log could not be retained in full")
            except (OSError, IntegrityError, InputChanged, _MaterialError) as error:
                capture.issue(
                    step, "Log snapshot unavailable: " + str(error), key=stream
                )
                problems[step].append("Captured log snapshot is unavailable")
        for label, facts, target in [
            ("input", item.input_facts, inputs[step]),
            ("output", item.output_facts, outputs[step]),
        ]:
            for fact in facts:
                relative = fact["path"]
                original = produced.get(relative) if label == "input" else None
                if original is not None and any(
                    original.get(key) != fact.get(key)
                    for key in ("sha256", "size_bytes", "stat")
                ):
                    reason = f"Declared input {relative!r} differs from its producing step output"
                    capture.issue(step, reason, key="producer:" + relative)
                    problems[step].append(reason)
                try:
                    selected_source = (
                        sources.get(relative) if label == "input" else None
                    )
                    if selected_source is not None and (
                        selected_source.sha256,
                        selected_source.size_bytes,
                    ) == (fact["sha256"], fact["size_bytes"]):
                        frozen = selected_source
                    else:
                        frozen = capture.freeze(
                            f"{label}:{step}:{relative}",
                            workspace,
                            relative,
                            expected=fact,
                        )
                    target[relative] = frozen
                except (OSError, IntegrityError, InputChanged, _MaterialError) as error:
                    capture.issue(
                        step,
                        f"{label.title()} {relative!r} snapshot unavailable: {error}",
                        key=f"{label}:{relative}",
                    )
                    problems[step].append(str(error))
        if item.receipt["status"] not in {"skipped", "not_attempted", "cancelled"}:
            if not _inputs_stable(item):
                problems[step].append(
                    "Declared inputs changed during command execution"
                )
            tool = _tool_problem(item)
            if tool:
                problems[step].append(tool)
    return inputs, outputs, logs, problems


def _ctest_version(
    item: StepResult, capture: _Capture, logs: dict[str, list[str]]
) -> str | None:
    if item.receipt["status"] != "passed" or item.logs_truncated:
        return None
    key = _id(f"log:{item.receipt['id']}:stdout")
    frozen = capture.files.get(key)
    if frozen is None or key not in logs[item.receipt["id"]]:
        return None
    try:
        text = frozen.path.read_text(encoding="utf-8", errors="strict")
    except UnicodeError:
        return None
    matched = re.match(r"ctest version ([0-9]+\.[0-9]+\.[0-9]+)(?:\r?\n|$)", text)
    return matched.group(1) if matched else None


def _inventory(item: StepResult, capture: _Capture) -> list[dict[str, Any]]:
    if item.receipt["status"] != "passed" or item.logs_truncated:
        raise _MaterialError(
            "CTest inventory step did not retain complete successful stdout",
            "unsupported",
        )
    frozen = capture.files.get(_id(f"log:{item.receipt['id']}:stdout"))
    if frozen is None:
        raise _MaterialError("CTest command inventory stdout is unavailable")
    try:
        document = json.loads(frozen.path.read_bytes())
    except (ValueError, UnicodeError) as error:
        raise _MaterialError(
            "CTest inventory is malformed JSON", "malformed"
        ) from error
    if (
        not isinstance(document, dict)
        or document.get("kind") != "ctestInfo"
        or document.get("version") != {"major": 1, "minor": 0}
        or any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in document.get("version", {}).values()
        )
        or not isinstance(document.get("tests"), list)
    ):
        raise _MaterialError(
            "Unsupported CTest inventory kind/version/array shape", "unsupported"
        )
    names = set()
    for case in document["tests"]:
        if (
            not isinstance(case, dict)
            or not isinstance(case.get("name"), str)
            or not case["name"]
            or not isinstance(case.get("command"), list)
            or not case["command"]
            or any(
                not isinstance(argument, str) or not argument or "\x00" in argument
                for argument in case["command"]
            )
        ):
            raise _MaterialError(
                "CTest inventory test name/command is malformed", "malformed"
            )
        if case["name"] in names:
            raise _MaterialError("CTest inventory names are ambiguous", "mismatched")
        names.add(case["name"])
    return document["tests"]


def _ctest_selection(
    item: StepResult, mode: str, workspace: Path
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Accept only reviewed CTest run/selection options; never add a probe."""
    arguments = item.receipt["argv"][1:]
    cwd = Path(item.receipt["cwd"])
    selected = []
    seen_mode = 0
    position = 0
    selectors = {
        "-C": "config",
        "--build-config": "config",
        "-R": "include",
        "--tests-regex": "include",
        "-E": "exclude",
        "--exclude-regex": "exclude",
        "-L": "label",
        "--label-regex": "label",
        "-LE": "exclude-label",
        "--label-exclude": "exclude-label",
        "-I": "indices",
        "--tests-information": "indices",
    }
    while position < len(arguments):
        argument = arguments[position]
        if argument in {"--show-only=json-v1"}:
            if mode != "inventory":
                raise _MaterialError(
                    "CTest test invocation requested inventory mode", "unsupported"
                )
            seen_mode += 1
        elif argument == "--output-junit" or argument.startswith("--output-junit="):
            if mode != "tests":
                raise _MaterialError(
                    "CTest inventory invocation requested report output", "unsupported"
                )
            if argument == "--output-junit":
                position += 1
                if position >= len(arguments) or not arguments[position]:
                    raise _MaterialError(
                        "CTest JUnit output option has no path", "malformed"
                    )
            seen_mode += 1
        elif argument == "--test-dir" or argument.startswith("--test-dir="):
            if argument == "--test-dir":
                position += 1
                if position >= len(arguments):
                    raise _MaterialError(
                        "CTest test-directory option has no path", "malformed"
                    )
                value = arguments[position]
            else:
                value = argument.split("=", 1)[1]
            cwd = Path(value) if Path(value).is_absolute() else cwd / value
        elif argument in selectors:
            position += 1
            if position >= len(arguments):
                raise _MaterialError("CTest selection option has no value", "malformed")
            selected.append((selectors[argument], arguments[position]))
        elif argument in {
            "--output-on-failure",
            "-V",
            "--verbose",
            "-VV",
            "--extra-verbose",
            "--no-tests=error",
            "--no-tests=ignore",
        }:
            if mode != "tests":
                raise _MaterialError("Unreviewed CTest inventory option", "unsupported")
        elif argument in {"-j", "--parallel"}:
            position += 1
            if position >= len(arguments) or not re.fullmatch(
                r"[1-9][0-9]*", arguments[position]
            ):
                raise _MaterialError(
                    "CTest parallel count must be explicit and positive", "unsupported"
                )
        else:
            raise _MaterialError(
                f"Unreviewed CTest invocation option: {argument}", "unsupported"
            )
        position += 1
    if seen_mode != 1:
        raise _MaterialError(
            "Expected exactly one explicit CTest inventory/report mode", "unsupported"
        )
    directory = cwd.resolve()
    if not directory.is_relative_to(workspace):
        raise _MaterialError(
            "CTest effective test directory is outside the selected workspace",
            "unsupported",
        )
    return str(directory), tuple(selected)


def _proof(
    binding: dict[str, Any],
    item: StepResult,
    by_id: dict[str, StepResult],
    capture: _Capture,
    inputs: dict[str, dict[str, _Frozen]],
    problems: dict[str, list[str]],
    report: TestReport,
    execution_log: Any,
    workspace: Path,
    steps: dict[str, dict[str, Any]],
) -> None:
    inventory_step = by_id[binding["inventory_step_id"]]
    version_step = by_id[binding["producer_version_step_id"]]
    selected = [version_step, inventory_step, item]
    facts = [entry.executable_fact for entry in selected]
    if (
        any(entry is None for entry in facts)
        or len(
            {
                (fact["path"], fact["sha256"], fact["size_bytes"])
                for fact in facts
                if fact is not None
            }
        )
        != 1
    ):
        raise _MaterialError(
            "CTest version, inventory and test steps did not observe the same executable identity",
            "mismatched",
        )
    if any(
        entry.receipt["status"] != "passed" for entry in [version_step, inventory_step]
    ) or any(problems[entry.receipt["id"]] for entry in selected):
        raise _MaterialError(
            "CTest proof step material/executable binding is unavailable", "mismatched"
        )
    if _ctest_selection(inventory_step, "inventory", workspace) != _ctest_selection(
        item, "tests", workspace
    ):
        raise _MaterialError(
            "CTest inventory and test invocation directory/config/selection differ",
            "mismatched",
        )
    if steps[inventory_step.receipt["id"]].get("environment", {}) != steps[
        item.receipt["id"]
    ].get("environment", {}):
        raise _MaterialError(
            "CTest inventory and test explicit environments differ", "unsupported"
        )
    inventory = _inventory(inventory_step, capture)
    named = {entry["name"]: entry for entry in inventory}
    executed = {entry.name: entry for entry in execution_log.records}
    if set(executed) - {case.name for case in report.cases}:
        raise _MaterialError(
            "Actual CTest execution log contains cases absent from JUnit", "mismatched"
        )
    if any(case.name not in named for case in report.cases):
        raise _MaterialError(
            "JUnit case names do not match the explicit CTest inventory", "mismatched"
        )
    # A zero/all-skipped report is an observed lack of verification, not a pass.
    if report.passed == 0 and report.failed == 0 and report.errors == 0:
        return
    invoked = set()
    inventory_directory = _ctest_selection(inventory_step, "inventory", workspace)[0]
    for case in report.cases:
        if case.status == "skipped":
            continue
        actual = executed.get(case.name)
        if actual is None or actual.outcome == "notrun":
            raise _MaterialError(
                "A non-skipped JUnit case has no actual CTest execution record",
                "mismatched",
            )
        if actual.outcome == "passed" and case.status in {"failed", "error"}:
            raise _MaterialError(
                "Failed JUnit case contradicts the actual CTest execution log",
                "mismatched",
            )
        if actual.outcome == "failed" and case.status == "passed":
            raise _MaterialError(
                "Passed JUnit case contradicts the actual CTest execution log",
                "mismatched",
            )
        declared = named[case.name]
        if tuple(declared["command"]) != tuple(actual.actual_argv):
            raise _MaterialError(
                "Actual CTest command differs from the explicit inventory", "mismatched"
            )
        properties = declared.get("properties", [])
        if not isinstance(properties, list) or any(
            not isinstance(prop, dict) or not isinstance(prop.get("name"), str)
            for prop in properties
        ):
            raise _MaterialError(
                "CTest inventory properties are malformed", "malformed"
            )
        working_directories = [
            prop.get("value")
            for prop in properties
            if prop["name"] == "WORKING_DIRECTORY"
        ]
        if len(working_directories) > 1 or any(
            not isinstance(value, str) or not value for value in working_directories
        ):
            raise _MaterialError(
                "CTest inventory working directory is ambiguous", "malformed"
            )
        expected_directory = Path(
            working_directories[0] if working_directories else inventory_directory
        )
        if not expected_directory.is_absolute():
            expected_directory = Path(inventory_directory) / expected_directory
        if (
            not Path(actual.working_directory).is_absolute()
            or Path(actual.working_directory).resolve() != expected_directory.resolve()
        ):
            raise _MaterialError(
                "Actual CTest working directory differs from its inventory",
                "mismatched",
            )
        command = actual.actual_argv[0]
        candidate = Path(command)
        if not candidate.is_absolute():
            candidate = Path(actual.working_directory) / candidate
        try:
            invoked.add(file_identity(workspace, candidate))
        except (OSError, IntegrityError, InputChanged):
            continue
    for relative in binding["exercised_inputs"]:
        if relative not in invoked:
            raise _MaterialError(
                f"Selected binary {relative!r} was not directly invoked by matched CTest cases; wrappers are unsupported",
                "mismatched",
            )
        test_input = inputs[item.receipt["id"]].get(relative)
        inventory_input = inputs[inventory_step.receipt["id"]].get(relative)
        if (
            test_input is None
            or inventory_input is None
            or test_input.size_bytes == 0
            or (test_input.sha256, test_input.size_bytes)
            != (inventory_input.sha256, inventory_input.size_bytes)
        ):
            raise _MaterialError(
                "Exercised binary did not retain identical inventory/test input bytes",
                "mismatched",
            )


def _normalize(
    plan: dict[str, Any],
    result: CollectionResult,
    workspace: Path,
    capture: _Capture,
    inputs: dict[str, dict[str, _Frozen]],
    outputs: dict[str, dict[str, _Frozen]],
    logs: dict[str, list[str]],
    problems: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    by_id = {item.receipt["id"]: item for item in result.steps}
    selected_steps = {step["id"]: step for step in plan["recipe"]["steps"]}
    records, stages = [], []
    partial = False
    for binding in plan["bindings"]:
        item = by_id[binding["step_id"]]
        step = item.receipt["id"]
        process_status = item.receipt["status"]
        record = {
            "id": binding["id"],
            "context_id": item.receipt["context_id"],
            "producer": {"name": "cppulse.executor", "version": __version__},
            "origin": "execution",
            "kind": binding["kind"],
            "status": process_status,
            "usability": "missing",
            "artifact_ids": [],
            "receipt_id": step,
            "scope": {"files": deepcopy(binding["scope_files"])},
            "limitations": [_SCOPE_LIMIT, _TOOL_LIMIT, *item.limitations],
        }
        normalization_status = "passed"
        reason = "Observed material normalized separately from the process outcome"
        if process_status in {
            "skipped",
            "not_attempted",
            "cancelled",
            "timed_out",
            "error",
        }:
            normalization_status = (
                "skipped" if process_status == "skipped" else process_status
            )
            reason = item.receipt["reason"]
            record["limitations"].append(reason)
            partial |= process_status != "skipped"
        elif binding["kind"] == "build":
            selected = [outputs[step].get(path) for path in binding["exercised_inputs"]]
            facts = {fact["path"]: fact for fact in item.output_facts}
            if problems[step]:
                record.update(status="error", usability="mismatched")
                normalization_status, reason, partial = (
                    "error",
                    "; ".join(problems[step]),
                    True,
                )
            elif process_status == "failed":
                record["usability"] = "usable"
                record["limitations"].append(
                    "The observed nonzero build exit is usable failure evidence; no successful binary is asserted."
                )
            elif item.material_status != "available" or any(
                file is None or file.size_bytes == 0 for file in selected
            ):
                record.update(status="error", usability="missing")
                normalization_status, reason, partial = (
                    "error",
                    "Successful command did not retain nonempty selected outputs",
                    True,
                )
            elif any(
                facts.get(path, {}).get("freshness") not in {"created", "modified"}
                for path in binding["exercised_inputs"]
            ):
                record.update(status="error", usability="mismatched")
                normalization_status, reason, partial = (
                    "error",
                    "Successful build outputs were not observed fresh",
                    True,
                )
            else:
                record["usability"] = "usable"
        else:
            version = _ctest_version(
                by_id[binding["producer_version_step_id"]], capture, logs
            )
            producer = {
                "name": "ctest",
                "version": version or "unavailable",
                "sha256": (item.executable_fact or {}).get("sha256"),
            }
            record["producer"] = producer
            frozen = outputs[step].get(binding["report_path"])
            if frozen is None:
                record.update(status="error", usability="missing")
                normalization_status, reason, partial = (
                    "error",
                    "Declared test report was not retained",
                    True,
                )
            else:
                report = parse_test_report(
                    frozen.path,
                    binding["adapter"],
                    binding["adapter_version"],
                    producer=producer,
                )
                capture.document(f"normalization:{binding['id']}", report.as_dict())
                record["limitations"].extend(report.limitations)
                record.update(status=report.status, usability=report.usability)
                record["scope"]["tests"] = [case.identity for case in report.cases]
                try:
                    if (
                        report.usability == "usable" or report.report_sha256 is not None
                    ) and (
                        report.report_sha256,
                        report.size_bytes,
                    ) != (
                        frozen.sha256,
                        frozen.size_bytes,
                    ):
                        raise _MaterialError(
                            "Parsed report bytes differ from the archived descriptor",
                            "mismatched",
                        )
                    if report.counts is not None:
                        item.receipt["tests"] = report.counts
                    if report.usability != "usable":
                        raise _MaterialError(
                            "; ".join(report.limitations), report.usability
                        )
                    execution_file = outputs[step].get(binding["execution_log_path"])
                    if execution_file is None:
                        raise _MaterialError(
                            "Declared CTest execution log was not retained"
                        )
                    if item.material_status != "available":
                        raise _MaterialError(
                            "Test input/output freshness is unavailable",
                            (
                                "missing"
                                if item.material_status == "missing"
                                else "mismatched"
                            ),
                        )
                    from cppulse.adapters.ctest_log import parse_ctest_log

                    execution_log = parse_ctest_log(
                        execution_file.path, producer=producer
                    )
                    capture.document(
                        f"execution-normalization:{binding['id']}",
                        execution_log.as_dict(),
                    )
                    record["limitations"].extend(execution_log.limitations)
                    if (
                        execution_log.usability == "usable"
                        or execution_log.report_sha256 is not None
                    ) and (
                        execution_log.report_sha256,
                        execution_log.size_bytes,
                    ) != (
                        execution_file.sha256,
                        execution_file.size_bytes,
                    ):
                        raise _MaterialError(
                            "Parsed execution log bytes differ from the archived descriptor",
                            "mismatched",
                        )
                    if execution_log.usability != "usable":
                        raise _MaterialError(
                            "; ".join(execution_log.limitations),
                            execution_log.usability,
                        )
                    _proof(
                        binding,
                        item,
                        by_id,
                        capture,
                        inputs,
                        problems,
                        report,
                        execution_log,
                        workspace,
                        selected_steps,
                    )
                    if process_status == "failed" and report.status == "passed":
                        record["status"] = "failed"
                        record["limitations"].append(
                            "CTest exited nonzero despite passed report cases; process failure is preserved."
                        )
                except _MaterialError as error:
                    record.update(status="error", usability=error.usability)
                    normalization_status, reason, partial = "error", str(error), True
        if reason and normalization_status == "error":
            record["limitations"].append(reason)
        records.append(record)
        stages.append(
            {
                "id": "normalize-" + _id(binding["id"]),
                "status": normalization_status,
                "depends_on": ["execute-" + _id(step)],
                "reason": reason,
            }
        )
    return records, stages, partial


def _raw(
    item: StepResult,
    capture: _Capture,
    inputs: dict[str, _Frozen],
    outputs: dict[str, _Frozen],
    logs: list[str],
    problems: list[str],
) -> dict[str, Any]:
    """Retain versioned observed facts and separate private-copy binding state."""
    step = item.receipt["id"]
    issues = list(dict.fromkeys([*problems, *capture.issues.get(step, [])]))
    if item.material_status == "invalid":
        issues.append("Observed execution material is invalid")
    if not _inputs_stable(item):
        issues.append("Declared input facts differ before and after execution")
    if set(inputs) != {row["path"] for row in item.input_facts} or set(outputs) != {
        row["path"] for row in item.output_facts
    }:
        issues.append(
            "Not every observed material file has a retained private snapshot"
        )
    streams = {
        name: _id(f"log:{step}:{name}") if _id(f"log:{step}:{name}") in logs else None
        for name in ("stdout", "stderr")
    }
    if any(identifier is None for identifier in streams.values()):
        issues.append("Not every observed log stream has a retained private snapshot")
    retained_log_bytes = sum(
        capture.files[identifier].size_bytes
        for identifier in streams.values()
        if identifier is not None
    )
    if retained_log_bytes != item.captured_bytes:
        issues.append("Retained log bytes differ from observed captured bytes")
    binding_status = (
        "invalid"
        if issues
        else "verified" if item.executable_fact is not None else "not_collected"
    )
    return {
        "version": "2.0.0",
        "collector_version": _VERSION,
        "receipt": deepcopy(item.receipt),
        "input_facts": deepcopy(item.input_facts),
        "input_after_facts": deepcopy(item.input_after_facts),
        "output_facts": deepcopy(item.output_facts),
        "preexisting_output_facts": deepcopy(item.preexisting_output_facts),
        "executable_fact": deepcopy(item.executable_fact),
        "material_status": item.material_status,
        "limitations": list(item.limitations),
        "stdout_bytes": item.stdout_bytes,
        "stderr_bytes": item.stderr_bytes,
        "captured_bytes": item.captured_bytes,
        "logs_truncated": item.logs_truncated,
        "snapshot_limitations": capture.issues.get(item.receipt["id"], []),
        "binding": {
            "status": binding_status,
            "limitations": list(dict.fromkeys(issues)),
            "input_artifacts": [
                {"path": path, "artifact_id": frozen.id}
                for path, frozen in inputs.items()
            ],
            "output_artifacts": [
                {"path": path, "artifact_id": frozen.id}
                for path, frozen in outputs.items()
            ],
            "log_artifacts": streams,
        },
    }


def collect(
    plan: dict[str, Any],
    *,
    workspace: Path,
    source: dict[str, Any],
    contexts: list[dict[str, Any]],
    store: RunStore | Path,
    cancel: CancellationToken | None = None,
) -> RunSnapshot:
    """Run one validated explicit plan and publish its immutable observed facts.

    Normal nonzero command/test failures can form a completed collection. Missing
    successful material, unsupported normalization, mutations and operational
    failures form partial attempts; cancellation never promotes latest-completed.
    Unexpected publication errors propagate and preserve staging/private material.
    """
    plan, source, contexts = deepcopy(plan), deepcopy(source), deepcopy(contexts)
    stamp = _now()
    provisional = _manifest(
        plan,
        source,
        contexts,
        run_id=uuid4().hex,
        status="partial",
        stages=[],
        started=stamp,
        finished=stamp,
        limitations=[],
    )
    validate_bundle({"run_manifest": provisional, "collection_plan": plan})
    metadata_cap = int(plan["limits"]["max_metadata_bytes"])
    try:
        for document in [plan, source, *contexts, provisional]:
            _control_bytes(document, metadata_cap)
    except IntegrityError as error:
        raise ContractError(
            "Selected control metadata cannot fit its effective limit: " + str(error)
        ) from error
    workspace = Path(workspace).resolve(strict=True)
    token = cancel or CancellationToken()
    work = Path(tempfile.mkdtemp(prefix="cppulse-collection-"))
    capture = _Capture(
        work / "frozen", int(plan["limits"]["max_artifact_bytes"]), metadata_cap
    )
    capture.root.mkdir()
    try:
        initial_errors = verify_inputs(workspace, source)
        sources = {}
        for expected in source["files"]:
            try:
                sources[expected["path"]] = capture.freeze(
                    "source:" + expected["path"],
                    workspace,
                    expected["path"],
                    expected=expected,
                )
            except (OSError, IntegrityError, InputChanged, _MaterialError) as error:
                capture.issue("source", str(error), key=expected["path"])
        if initial_errors:
            result = _not_attempted(
                plan,
                source,
                work / "execution",
                "Selected source differs before collection: "
                + "; ".join(initial_errors),
                token,
            )
        else:
            runtime_recipe = deepcopy(plan["recipe"])
            runtime_recipe["jobs"] = int(runtime_recipe["jobs"])
            result = run_recipe(
                runtime_recipe,
                workspace,
                source,
                contexts,
                work / "execution",
                ProcessLimits(
                    max_log_bytes=int(plan["limits"]["max_log_bytes"]),
                    termination_grace_seconds=plan["limits"][
                        "termination_grace_seconds"
                    ],
                ),
                token,
            )
        inputs, outputs, logs, problems = _freeze_results(
            result, workspace, work, capture, sources
        )
        records, normalizations, partial = _normalize(
            plan, result, workspace, capture, inputs, outputs, logs, problems
        )
        source_errors = [*initial_errors, *verify_inputs(workspace, source)]
        partial |= bool(source_errors or capture.issues.get("source"))
        partial |= any(
            item.receipt["status"] in {"error", "timed_out", "not_attempted"}
            or problems[item.receipt["id"]]
            or (
                item.receipt["status"] == "passed"
                and item.material_status != "available"
            )
            for item in result.steps
        )
        limitations = [
            *source["limitations"],
            *result.limitations,
            _SCOPE_LIMIT,
            _TOOL_LIMIT,
        ]
        limitations.extend(
            reason for reasons in capture.issues.values() for reason in reasons
        )
        stages = [
            {
                "id": "execute-" + _id(item.receipt["id"]),
                "status": item.receipt["status"],
                "depends_on": [
                    "execute-" + _id(dependency)
                    for dependency in item.receipt["depends_on"]
                ],
                "reason": item.receipt["reason"],
            }
            for item in result.steps
        ] + normalizations
        for item in result.steps:
            step = item.receipt["id"]
            raw_id = _id("raw:" + step)
            item.receipt["artifact_ids"] = list(
                dict.fromkeys(
                    [
                        *[file.id for file in inputs[step].values()],
                        *[file.id for file in outputs[step].values()],
                        *capture.diagnostics.get(step, []),
                        raw_id,
                    ]
                )
            )
            item.receipt["log_artifact_ids"] = logs[step]
            validate("execution_receipt", item.receipt)
            facts = _raw(
                item, capture, inputs[step], outputs[step], logs[step], problems[step]
            )
            validate("execution_facts", facts)
            capture.document("raw:" + step, facts, "execution_facts")
        receipts = {item.receipt["id"]: item.receipt for item in result.steps}
        for record in records:
            receipt = receipts[record["receipt_id"]]
            record["artifact_ids"] = list(
                dict.fromkeys(receipt["artifact_ids"] + receipt["log_artifact_ids"])
            )
        evidence = {
            "version": "2.0.0",
            "source_digest": source["digest"],
            "records": records,
        }
        capture.document("selected-plan", plan, "collection_plan")
        runtime_store = store if isinstance(store, RunStore) else RunStore(store)

        def stale(errors: list[str]) -> None:
            nonlocal partial
            partial = True
            for record in records:
                record["usability"] = "stale"
                record["limitations"].append(
                    "Selected source changed; these are retained historical execution facts."
                )
            stages.append(
                {
                    "id": "source-" + _id(str(len(stages))),
                    "status": "error",
                    "depends_on": [],
                    "reason": "; ".join(errors),
                }
            )
            limitations.extend(errors)

        if source_errors:
            stale(source_errors)
        publication_change: list[str] = []

        def source_check() -> None:
            errors = verify_inputs(workspace, source)
            if errors:
                publication_change.extend(errors)
                raise InputChanged(
                    "Selected source changed during publication: " + "; ".join(errors)
                )

        def publish(*, check: bool) -> RunSnapshot:
            validate("evidence", evidence)
            with runtime_store.begin() as stage:
                for frozen in capture.files.values():
                    descriptor = stage.copy_artifact(
                        frozen.id, frozen.path, frozen.destination, frozen.media_type
                    )
                    if (descriptor["sha256"], descriptor["size_bytes"]) != (
                        frozen.sha256,
                        frozen.size_bytes,
                    ):
                        raise IntegrityError(
                            "Private frozen material changed before store copying"
                        )
                for artifact_id, (document, contract) in capture.documents.items():
                    path = "documents/" + artifact_id + ".json"
                    if contract is None:
                        local = capture.root / (artifact_id + ".json")
                        local.write_bytes(_control_bytes(document, metadata_cap))
                        stage.copy_artifact(
                            artifact_id, local, path, "application/json"
                        )
                    else:
                        _control_bytes(document, metadata_cap)
                        stage.write_json(
                            path, document, contract=contract, artifact_id=artifact_id
                        )
                for receipt in receipts.values():
                    _control_bytes(receipt, metadata_cap)
                    stage.write_json(
                        "receipts/" + _id(receipt["id"]) + ".json",
                        receipt,
                        contract="execution_receipt",
                        artifact_id=_id("receipt:" + receipt["id"]),
                    )
                _control_bytes(evidence, metadata_cap)
                stage.write_json(
                    "evidence/records.json",
                    evidence,
                    contract="evidence",
                    artifact_id=_id("evidence"),
                )
                status = (
                    "cancelled"
                    if result.cancelled
                    else "partial" if partial else "completed"
                )
                manifest = _manifest(
                    plan,
                    source,
                    contexts,
                    run_id=stage.run_id,
                    status=status,
                    stages=stages,
                    started=result.started_at,
                    finished=_now(),
                    limitations=limitations,
                )
                manifest["artifacts"] = stage.artifacts
                manifest["input_verification"] = "verified" if check else "unverified"
                if not check:
                    # Materialize the store's standard no-check declaration before
                    # bounding the exact manifest representation it will persist.
                    from cppulse.run_store import _NO_SOURCE_CHECK

                    if _NO_SOURCE_CHECK not in manifest["limitations"]:
                        manifest["limitations"].append(_NO_SOURCE_CHECK)
                _control_bytes(manifest, metadata_cap)
                return stage.publish(
                    manifest, source_check=source_check if check else None
                )

        try:
            snapshot = publish(check=not source_errors)
        except InputChanged:
            if not publication_change:
                raise
            stale(publication_change)
            limitations.append(
                "First publication was aborted on source mutation; frozen facts were republished without rerunning commands."
            )
            snapshot = publish(check=False)
    except BaseException as error:
        error.add_note("Private collection material retained at " + str(work))
        raise
    shutil.rmtree(work)
    return snapshot
