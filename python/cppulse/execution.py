"""Execute explicitly selected local recipes with bounded, observed receipts.

This is trusted command execution, not a sandbox: selected commands inherit the
environment and may themselves run Git or access the network. Bounds cover jobs,
wall time, and retained stdout/stderr, not memory, CPU, or arbitrary escaped
processes. File hashes identify bytes; observed filesystem freshness is not
authentication. Cached no-op builds need a fresh output directory or an explicit
clean build: unchanged preexisting outputs are not accepted as collected evidence.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import selectors
import shutil
import signal
import stat
import subprocess
import threading
import time
from typing import Any, BinaryIO

from cppulse import __version__
from cppulse.contracts import validate
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.identities import snapshot_inputs


@dataclass(frozen=True)
class ProcessLimits:
    """Per-step combined stdout/stderr retention and termination grace."""

    max_log_bytes: int = 1024 * 1024
    termination_grace_seconds: float = 1.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_log_bytes, bool)
            or not isinstance(self.max_log_bytes, int)
            or not 1 <= self.max_log_bytes <= 64 * 1024 * 1024
        ):
            raise ContractError("max_log_bytes must be between 1 and 67108864")
        if (
            isinstance(self.termination_grace_seconds, bool)
            or not isinstance(self.termination_grace_seconds, (int, float))
            or not math.isfinite(self.termination_grace_seconds)
            or self.termination_grace_seconds <= 0
        ):
            raise ContractError("termination_grace_seconds must be finite and positive")


class CancellationToken:
    """Thread-safe cooperative cancellation shared by scheduler and workers."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation; workers terminate and drain their process groups."""
        self._event.set()

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._event.is_set()


@dataclass
class StepResult:
    """One actual command receipt with local material and log observations.

    Byte counts are bytes drained from each pipe, including discarded bytes.
    A combined storage cap can retain less. A pipe escaping process-group cleanup
    is reported explicitly; in that case counts cover only the observed scope.
    Input/output facts include content identity and separate filesystem stat facts.
    """

    receipt: dict[str, Any]
    stdout_path: Path
    stderr_path: Path
    input_facts: list[dict[str, Any]] = field(default_factory=list)
    input_after_facts: list[dict[str, Any]] = field(default_factory=list)
    output_facts: list[dict[str, Any]] = field(default_factory=list)
    preexisting_output_facts: list[dict[str, Any]] = field(default_factory=list)
    executable_fact: dict[str, Any] | None = None
    material_status: str = "not_collected"
    limitations: list[str] = field(default_factory=list)
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    captured_bytes: int = 0
    logs_truncated: bool = False


@dataclass
class CollectionResult:
    """Recipe results in declaration order, independently of completion order."""

    steps: list[StepResult]
    started_at: str
    finished_at: str
    cancelled: bool
    max_parallel_steps: int
    limitations: list[str] = field(default_factory=list)


@dataclass
class ProcessOutcome:
    """Observed process exit and bounded log capture, without inferred resources."""
    status: str
    reason: str
    returncode: int | None
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    captured_bytes: int = 0
    limitations: list[str] = field(default_factory=list)



# Retained for existing private callers.
_ProcessOutcome = ProcessOutcome

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _relative(value: str, *, allow_dot: bool = False) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
        or path.as_posix() != value
        or (value == "." and not allow_dot)
    ):
        raise ContractError(f"Expected a canonical workspace-relative path: {value!r}")
    reserved = {"con", "prn", "aux", "nul"} | {
        prefix + str(number) for prefix in ["com", "lpt"] for number in range(1, 10)
    }
    for part in path.parts:
        if (
            any(
                ord(character) < 32
                or 127 <= ord(character) <= 159
                or character in '<>:"|?*'
                for character in part
            )
            or part.endswith((".", " "))
            or part.split(".", 1)[0].casefold() in reserved
        ):
            raise ContractError(f"Expected a portable workspace path: {value!r}")
    return path


def _selected_path(
    workspace: Path, relative: str, *, directory: bool = False, missing: bool = False
) -> Path:
    """Check existing components without following any workspace symlink."""
    path = _relative(relative, allow_dot=directory)
    current = workspace
    for index, part in enumerate(path.parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                return workspace / path
            raise
        if stat.S_ISLNK(info.st_mode):
            raise IntegrityError(
                "Symlink workspace components are not allowed", path=relative
            )
        if index < len(path.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise IntegrityError("Workspace parent is not a directory", path=relative)
    if not path.parts:
        info = workspace.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise IntegrityError(
            (
                "Working directory is not a directory"
                if directory
                else "Material is not a regular file"
            ),
            path=relative,
        )
    return current


def _stat_facts(info: os.stat_result) -> dict[str, int]:
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


def _file_fact(workspace: Path, relative: str) -> dict[str, Any]:
    """Tie a stable public content snapshot to separate pre/post stat facts."""
    selected = _selected_path(workspace, relative)
    before = selected.lstat()
    record = snapshot_inputs(workspace, [relative])["files"][0]
    after = _selected_path(workspace, relative).lstat()
    if (
        _stat_facts(before) != _stat_facts(after)
        or before.st_mode != after.st_mode
        or before.st_size != after.st_size
        or record["size_bytes"] != after.st_size
    ):
        raise InputChanged("Material changed while recording its facts", path=relative)
    return {**record, "stat": _stat_facts(after)}


def _validate_selection(
    recipe: dict[str, Any], source: dict[str, Any], contexts: list[dict[str, Any]]
) -> None:
    """Reject malformed selection and producer races before any launch."""
    validate("recipe", recipe)
    validate("source", source)
    context_ids = set()
    for context in contexts:
        validate("context", context)
        if context["id"] in context_ids:
            raise ContractError("Context identity is duplicated")
        context_ids.add(context["id"])
    if not set(recipe["contexts"]) <= context_ids:
        raise ContractError("Recipe refers to an unselected context")
    if recipe["jobs"] > 32:
        raise ContractError("At most 32 concurrent recipe jobs are supported")
    steps = {step["id"]: step for step in recipe["steps"]}
    outputs: dict[str, tuple[str, str]] = {}
    source_paths = {item["path"] for item in source["files"]}
    for step in steps.values():
        _relative(step["cwd"], allow_dot=True)
        if any("\x00" in argument for argument in step["argv"]):
            raise ContractError("Command arguments cannot contain NUL")
        for key, value in step.get("environment", {}).items():
            if (
                not isinstance(key, str)
                or not key
                or "=" in key
                or "\x00" in key
                or "\x00" in value
            ):
                raise ContractError("Invalid explicit environment entry")
            if re.search(r"token|pass(?:word|wd)|secret|api[_-]?key", key, re.I):
                raise ContractError(
                    "Sensitive explicit environment names are not accepted"
                )
        if not math.isfinite(step["timeout_seconds"]):
            raise ContractError("Command timeout must be finite")
        for relative in step["inputs"] + step["outputs"]:
            _relative(relative)
        for relative in step["outputs"]:
            folded = relative.casefold()
            if any(part.casefold() == ".git" for part in PurePosixPath(relative).parts):
                raise ContractError("Declared output cannot overwrite Git metadata")
            if folded in outputs:
                raise ContractError(
                    "Declared output has multiple or case-aliased owners"
                )
            if any(relative.casefold() == path.casefold() for path in source_paths):
                raise ContractError("Declared output cannot overwrite selected source")
            outputs[folded] = (relative, step["id"])
    for folded in outputs:
        if any(
            parent.as_posix() in outputs for parent in PurePosixPath(folded).parents
        ):
            raise ContractError("Declared output file/directory identities overlap")
    for step in steps.values():
        ancestors = set()
        pending = list(step["depends_on"])
        while pending:
            dependency = pending.pop()
            if dependency not in ancestors:
                ancestors.add(dependency)
                pending.extend(steps[dependency]["depends_on"])
        cwd = step["cwd"].casefold()
        if any(cwd == output or cwd.startswith(output + "/") for output in outputs):
            raise ContractError("Working directory overlaps an output file")
        for relative in step["inputs"]:
            generated = outputs.get(relative.casefold())
            if generated is not None:
                if generated[0] != relative or generated[1] not in ancestors:
                    raise ContractError(
                        "Generated input requires its canonical ancestor producer"
                    )
                if steps[generated[1]]["context_id"] != step["context_id"]:
                    raise ContractError(
                        "Generated input must retain its producer context"
                    )
            elif relative not in source_paths:
                raise ContractError(
                    f"Input is outside the selected source inventory: {relative}"
                )


def _receipt(
    step: dict[str, Any], source: dict[str, Any], workspace: Path
) -> dict[str, Any]:
    stamp = _now()
    return {
        "version": "2.0.0",
        "id": step["id"],
        "source_digest": source["digest"],
        "context_id": step["context_id"],
        "producer": {"name": "cppulse.executor", "version": __version__},
        "argv": list(step["argv"]),
        "cwd": str(workspace / step["cwd"]),
        "status": "not_attempted",
        "reason": "Command has not started",
        "exit_code": None,
        "signal": None,
        "started_at": stamp,
        "finished_at": stamp,
        "artifact_ids": [],
        "log_artifact_ids": [],
        "depends_on": list(step["depends_on"]),
    }


def _executable_fact(step: dict[str, Any], cwd: Path) -> dict[str, Any]:
    """Observe the selected executable without running implicit version commands."""
    command = step["argv"][0]
    environment = dict(os.environ)
    environment.update(step.get("environment", {}))
    if "/" in command:
        selected = Path(command)
        if not selected.is_absolute():
            selected = cwd / selected
    else:
        search = os.pathsep.join(
            str(Path(part) if Path(part).is_absolute() else cwd / part)
            for part in environment.get("PATH", os.defpath).split(os.pathsep)
        )
        found = shutil.which(command, path=search)
        if found is None:
            raise FileNotFoundError(f"Selected executable is unavailable: {command}")
        selected = Path(found)
    try:
        resolved = selected.resolve(strict=True)
    except RuntimeError as exc:
        raise IntegrityError(f"Selected executable cannot be resolved: {exc}") from exc
    if not os.access(resolved, os.X_OK):
        raise PermissionError(f"Selected executable is not executable: {resolved}")
    before = resolved.lstat()
    descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _stat_facts(before) != _stat_facts(
            opened
        ):
            raise IntegrityError("Selected executable is not a stable regular file")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        current = resolved.lstat()
        if (
            _stat_facts(before) != _stat_facts(after)
            or _stat_facts(after) != _stat_facts(current)
            or before.st_mode != after.st_mode
            or after.st_mode != current.st_mode
            or size != after.st_size
        ):
            raise InputChanged("Selected executable changed while its bytes were read")
        return {
            "path": str(resolved),
            "sha256": digest.hexdigest(),
            "size_bytes": size,
            "stat": _stat_facts(after),
        }
    finally:
        os.close(descriptor)


def _group_exists(process_id: int) -> bool:
    try:
        os.killpg(process_id, 0)
        return True
    except ProcessLookupError:
        return False


def _signal_group(process_id: int, value: int) -> None:
    try:
        os.killpg(process_id, value)
    except ProcessLookupError:
        pass


def run_bounded_process(
    argv: list[str],
    *,
    cwd: Path,
    stdout: BinaryIO,
    stderr: BinaryIO,
    timeout_seconds: float,
    limits: ProcessLimits | None = None,
    cancel: CancellationToken | None = None,
    environment: dict[str, str] | None = None,
) -> ProcessOutcome:
    """Run actual argv with wall/log bounds and owned POSIX group cancellation.

    This primitive makes no CPU or memory enforcement claim. Native producers
    must apply and report their own guards before doing analysis work.
    """
    if os.name != "posix":
        raise ContractError("Bounded process supervision is qualified only on POSIX")
    if not argv or any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise ContractError("An explicit nonempty argv without NUL is required")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ContractError("timeout_seconds must be finite and positive")
    selected_cancel = cancel or CancellationToken()
    if selected_cancel.is_cancelled():
        return ProcessOutcome("cancelled", "Cancellation requested before launch", None)
    return _run_process(
        {"argv": argv, "timeout_seconds": timeout_seconds, "environment": environment or {}},
        cwd, stdout, stderr, limits or ProcessLimits(), selected_cancel,
    )


def _run_process(
    step: dict[str, Any],
    cwd: Path,
    stdout: BinaryIO,
    stderr: BinaryIO,
    limits: ProcessLimits,
    cancel: CancellationToken,
) -> _ProcessOutcome:
    """Drain both pipes while enforcing timeout and POSIX process-group cleanup."""
    environment = dict(os.environ)
    environment.update(step.get("environment", {}))
    try:
        process = subprocess.Popen(
            step["argv"],
            shell=False,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        return _ProcessOutcome("error", f"Command could not start: {exc}", None)
    outcome = _ProcessOutcome("passed", "", None)
    deadline = time.monotonic() + step["timeout_seconds"]
    stopping_at: float | None = None
    killed_at: float | None = None
    exited_at: float | None = None
    streams = {"stdout": stdout, "stderr": stderr}
    log_write_failed = False
    selector = selectors.DefaultSelector()
    try:
        for name, pipe in [("stdout", process.stdout), ("stderr", process.stderr)]:
            assert pipe is not None
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        while True:
            current = time.monotonic()
            returncode = process.poll()
            if returncode is not None and exited_at is None:
                exited_at = current
            if stopping_at is None:
                if cancel.is_cancelled():
                    outcome.status, outcome.reason = (
                        "cancelled",
                        "Cancellation requested",
                    )
                    stopping_at = current
                elif returncode is None and current >= deadline:
                    outcome.status, outcome.reason = (
                        "timed_out",
                        "Command exceeded its wall-time limit",
                    )
                    stopping_at = current
                elif (
                    exited_at is not None
                    and current - exited_at >= 0.05
                    and (selector.get_map() or _group_exists(process.pid))
                ):
                    outcome.status, outcome.reason = (
                        "error",
                        "Command left a background process or open pipe",
                    )
                    stopping_at = current
                if stopping_at is not None:
                    _signal_group(process.pid, signal.SIGTERM)
            if stopping_at is not None and killed_at is None:
                if current - stopping_at >= limits.termination_grace_seconds:
                    _signal_group(process.pid, signal.SIGKILL)
                    killed_at = current
            if not selector.get_map() and returncode is not None:
                if stopping_at is None:
                    if not _group_exists(process.pid):
                        break
                elif killed_at is not None or not _group_exists(process.pid):
                    break
            if killed_at is not None and current - killed_at > max(
                0.2, limits.termination_grace_seconds
            ):
                if selector.get_map():
                    outcome.limitations.append(
                        "Pipe drain ended after process-group cleanup; byte counts cover only observed bytes, "
                        "and an escaped descendant may retain a pipe."
                    )
                break
            for key, _ in selector.select(timeout=0.025):
                pipe = key.fileobj
                try:
                    chunk = os.read(pipe.fileno(), 64 * 1024)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(pipe)
                    pipe.close()
                    continue
                if key.data == "stdout":
                    outcome.stdout_bytes += len(chunk)
                else:
                    outcome.stderr_bytes += len(chunk)
                retained = chunk[
                    : max(0, limits.max_log_bytes - outcome.captured_bytes)
                ]
                if retained and not log_write_failed:
                    try:
                        while retained:
                            written = streams[key.data].write(retained)
                            if not written:
                                raise OSError("Log storage made no write progress")
                            outcome.captured_bytes += written
                            retained = retained[written:]
                    except OSError as exc:
                        log_write_failed = True
                        outcome.status, outcome.reason = (
                            "error",
                            f"Log storage failed: {exc}",
                        )
                        outcome.limitations.append(
                            "Log storage failed; pipes continued draining, and captured_bytes counts only successfully written bytes."
                        )
        outcome.returncode = process.wait(
            timeout=max(0.2, limits.termination_grace_seconds)
        )
    except (OSError, subprocess.SubprocessError) as exc:
        outcome.status, outcome.reason = "error", f"Process supervision failed: {exc}"
        _signal_group(process.pid, signal.SIGKILL)
        outcome.returncode = process.wait()
    finally:
        selector.close()
        for pipe in [process.stdout, process.stderr]:
            if pipe is not None:
                pipe.close()
        if process.poll() is None:
            _signal_group(process.pid, signal.SIGKILL)
            process.wait()
    if outcome.status == "passed" and outcome.returncode != 0:
        if outcome.returncode is not None and outcome.returncode < 0:
            outcome.status = "error"
            outcome.reason = f"Command terminated by signal {-outcome.returncode}"
        else:
            outcome.status = "failed"
            outcome.reason = f"Command exited with code {outcome.returncode}"
    return outcome


def _collect_outputs(result: StepResult, step: dict[str, Any], workspace: Path) -> None:
    before = {item["path"]: item for item in result.preexisting_output_facts}
    missing = []
    invalid = []
    for relative in step["outputs"]:
        try:
            fact = _file_fact(workspace, relative)
            previous = before.get(relative)
            freshness = "created" if previous is None else "modified"
            if previous is not None and previous == fact:
                freshness = "unchanged"
                invalid.append(relative)
            result.output_facts.append({**fact, "freshness": freshness})
        except FileNotFoundError:
            missing.append(relative)
        except (IntegrityError, InputChanged, OSError) as exc:
            invalid.append(relative)
            result.limitations.append(f"Output {relative!r} is invalid: {exc}")
    if missing:
        result.limitations.append("Declared outputs are missing: " + ", ".join(missing))
    if invalid:
        result.limitations.append(
            "Declared outputs are invalid or unchanged; cached no-op output reuse is unsupported: "
            + ", ".join(invalid)
        )
    result.material_status = (
        "invalid" if invalid else "missing" if missing else "available"
    )


def _collect_input_after(result: StepResult, workspace: Path) -> bool:
    """Record post-process input observations without rewriting process outcome."""
    stable = True
    for before in result.input_facts:
        try:
            after = _file_fact(workspace, before["path"])
            result.input_after_facts.append(after)
            if before != after:
                stable = False
                result.limitations.append(
                    f"Declared input changed during execution: {before['path']}"
                )
        except (IntegrityError, InputChanged, OSError) as exc:
            stable = False
            result.limitations.append(
                f"Declared input unavailable or unsafe after execution: {before['path']}: {exc}"
            )
    return stable


def _execute_step(
    step: dict[str, Any],
    workspace: Path,
    source: dict[str, Any],
    result: StepResult,
    limits: ProcessLimits,
    cancel: CancellationToken,
) -> StepResult:
    result.receipt["started_at"] = _now()
    try:
        if cancel.is_cancelled():
            result.receipt.update(
                status="cancelled",
                reason="Cancellation requested before command launch",
            )
            return result
        if os.name != "posix":
            raise IntegrityError(
                "This executor requires POSIX process-group supervision"
            )
        cwd = _selected_path(workspace, step["cwd"], directory=True)
        result.input_facts = [_file_fact(workspace, path) for path in step["inputs"]]
        selected_inputs = {item["path"]: item for item in source["files"]}
        for fact in result.input_facts:
            expected = selected_inputs.get(fact["path"])
            if expected is not None and any(
                fact[key] != expected[key] for key in ["sha256", "size_bytes"]
            ):
                raise InputChanged(
                    "Declared input no longer matches the selected source",
                    path=fact["path"],
                )
        result.executable_fact = _executable_fact(step, cwd)
        for relative in step["outputs"]:
            _selected_path(workspace, relative, missing=True)
            try:
                result.preexisting_output_facts.append(_file_fact(workspace, relative))
            except FileNotFoundError:
                pass
        with (
            result.stdout_path.open("wb", buffering=0) as stdout,
            result.stderr_path.open("wb", buffering=0) as stderr,
        ):
            outcome = _run_process(step, cwd, stdout, stderr, limits, cancel)
            # Preserve observations even if closing the log file later fails.
            result.receipt.update(status=outcome.status, reason=outcome.reason)
            if outcome.returncode is not None:
                if outcome.returncode < 0:
                    result.receipt["signal"] = -outcome.returncode
                else:
                    result.receipt["exit_code"] = outcome.returncode
            result.stdout_bytes = outcome.stdout_bytes
            result.stderr_bytes = outcome.stderr_bytes
            result.captured_bytes = outcome.captured_bytes
            result.logs_truncated = (
                outcome.stdout_bytes + outcome.stderr_bytes > outcome.captured_bytes
            )
            result.limitations.extend(outcome.limitations)
        if result.logs_truncated:
            if result.captured_bytes >= limits.max_log_bytes:
                result.limitations.append(
                    "Combined stdout/stderr retention limit reached; pipes were drained and excess bytes discarded."
                )
            else:
                result.limitations.append(
                    "Logs are incomplete due to storage or pipe-drain failure; byte counts describe observed scope."
                )
        if outcome.returncode is not None:
            inputs_stable = _collect_input_after(result, workspace)
            _collect_outputs(result, step, workspace)
            if not inputs_stable:
                result.material_status = "invalid"
        try:
            executable_after = _executable_fact(step, cwd)
            if executable_after != result.executable_fact:
                raise InputChanged(
                    "Selected executable changed during command execution"
                )
        except (IntegrityError, InputChanged, OSError) as exc:
            result.receipt.update(
                status="error",
                reason=f"Executable identity unavailable or changed: {exc}",
            )
            result.material_status = "invalid"
            result.limitations.append(
                "Observed executable identity changed or became unavailable during execution."
            )
    except (IntegrityError, InputChanged, OSError) as exc:
        result.receipt.update(
            status="error", reason=f"Operational prerequisite/material error: {exc}"
        )
        if (
            result.receipt["exit_code"] is not None
            or result.receipt["signal"] is not None
        ):
            result.limitations.append(
                "Post-process log or material operation failed; observed process exit facts are retained."
            )
    finally:
        result.receipt["finished_at"] = _now()
        validate("execution_receipt", result.receipt)
    return result


def run_recipe(
    recipe: dict[str, Any],
    workspace: Path,
    source: dict[str, Any],
    contexts: list[dict[str, Any]],
    work_dir: Path,
    limits: ProcessLimits | None = None,
    cancel: CancellationToken | None = None,
) -> CollectionResult:
    """Run an explicit DAG, continuing independent branches after failures.

    Args:
        recipe: Valid recipe v2 with at most 32 jobs; argv is never shell-expanded.
        workspace: Selected existing source root; cwd/inputs/outputs are relative to it.
        source: Valid finite source snapshot. Non-generated inputs must be listed.
        contexts: Valid selected contexts including every referenced context identity.
        work_dir: Local logs root; existing step directories are never overwritten.
        limits: Combined per-step retained stdout/stderr bytes and termination grace.
        cancel: Optional token. KeyboardInterrupt requests cancellation and drains workers.

    Returns:
        Declaration-ordered receipts, file facts and bounded local log paths.
        Exit zero remains passed even when declared material is missing or stale;
        those material states block dependents and must not become usable evidence.

    Raises:
        ContractError: Selection is invalid before any process is launched.
        OSError: The selected workspace or exclusively owned logs cannot be prepared.

    Source post-verification belongs to the aggregate collector. This function
    does not claim repository immutability or a hostile-command sandbox.
    """
    _validate_selection(recipe, source, contexts)
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir():
        raise ContractError("Selected workspace must be an existing directory")
    limits = limits or ProcessLimits()
    cancel = cancel or CancellationToken()
    started_at = _now()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    work_dir = work_dir.resolve(strict=True)
    prepared = {}
    for step in recipe["steps"]:
        directory = work_dir / step["id"]
        directory.mkdir()
        stdout_path, stderr_path = directory / "stdout.log", directory / "stderr.log"
        stdout_path.touch(exist_ok=False)
        stderr_path.touch(exist_ok=False)
        prepared[step["id"]] = StepResult(
            _receipt(step, source, workspace), stdout_path, stderr_path
        )
    completed: dict[str, StepResult] = {}
    pending = list(recipe["steps"])
    active: dict[Future[StepResult], str] = {}
    max_parallel = 0
    with ThreadPoolExecutor(
        max_workers=recipe["jobs"], thread_name_prefix="cppulse-step"
    ) as pool:
        while pending or active:
            try:
                for step in list(pending):
                    if cancel.is_cancelled():
                        item = prepared[step["id"]]
                        item.receipt.update(
                            status="cancelled",
                            reason="Cancellation requested before scheduling",
                            finished_at=_now(),
                        )
                        validate("execution_receipt", item.receipt)
                        completed[step["id"]] = item
                        pending.remove(step)
                        continue
                    if not set(step["depends_on"]) <= completed.keys():
                        continue
                    unavailable = [
                        dependency
                        for dependency in step["depends_on"]
                        if completed[dependency].receipt["status"] != "passed"
                        or completed[dependency].material_status != "available"
                    ]
                    if unavailable:
                        item = prepared[step["id"]]
                        item.receipt.update(
                            status="skipped",
                            reason="Dependency outcome/material unavailable: "
                            + ", ".join(unavailable),
                            finished_at=_now(),
                        )
                        validate("execution_receipt", item.receipt)
                        completed[step["id"]] = item
                        pending.remove(step)
                        continue
                    if len(active) >= recipe["jobs"]:
                        break
                    future = pool.submit(
                        _execute_step,
                        step,
                        workspace,
                        source,
                        prepared[step["id"]],
                        limits,
                        cancel,
                    )
                    active[future] = step["id"]
                    pending.remove(step)
                    max_parallel = max(max_parallel, len(active))
                if active:
                    finished, _ = wait(
                        active, timeout=0.05, return_when=FIRST_COMPLETED
                    )
                    for future in finished:
                        item = future.result()
                        completed[active[future]] = item
                        del active[future]
            except KeyboardInterrupt:
                cancel.cancel()
    return CollectionResult(
        steps=[completed[step["id"]] for step in recipe["steps"]],
        started_at=started_at,
        finished_at=_now(),
        cancelled=cancel.is_cancelled(),
        max_parallel_steps=max_parallel,
        limitations=[
            "Selected commands execute with inherited environment and user permissions; this is not a sandbox.",
            "Only POSIX process groups, wall time, selected-step concurrency and retained logs are bounded; CPU/memory are not limited.",
            "Executable identity covers the selected argv[0] file; interpreter and runtime dependency closures are not collected.",
            "Unchanged preexisting outputs are invalid; use fresh build directories or explicit clean builds.",
        ],
    )
