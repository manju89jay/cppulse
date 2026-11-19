"""Bounded Linux file/process observations, explicitly without cache authority."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import subprocess
import time
from typing import Any

from cppulse.contracts.query_observation import validate_query_document
from cppulse.errors import ContractError, IntegrityError
from cppulse.identities import canonical_json_bytes, digest_json
from cppulse.run_store import _directory, _read, _stream_file

_PREFIX = re.compile(r"^(?:\[pid\s+)?(\d+)\]?\s+(.*)$")
_CALL = re.compile(r"^([a-zA-Z_][a-zA-Z_0-9]*)\((.*)\)\s+=\s+(.*)$")
_STRING = re.compile(r'^"(?:[^"\\]|\\.)*"$')
_DIRECT = {
    "access",
    "stat",
    "lstat",
    "readlink",
    "execve",
    "chdir",
    "mkdir",
    "rmdir",
    "unlink",
    "chmod",
    "chown",
    "statfs",
}
_AT = {
    "openat",
    "openat2",
    "newfstatat",
    "faccessat",
    "faccessat2",
    "readlinkat",
    "mkdirat",
    "unlinkat",
    "statx",
}
_PROCESS = {
    "clone",
    "clone3",
    "fork",
    "vfork",
    "wait4",
    "waitid",
    "exit",
    "exit_group",
    "kill",
    "tgkill",
    "getpid",
    "gettid",
    "execveat",
}


def _pid(value: str | bytes) -> int | None:
    # Linux pid_t is a positive signed 32-bit value. Bound before int() so
    # hostile numeric text cannot hit Python's global conversion limit.
    if isinstance(value, bytes):
        if not 1 <= len(value) <= 10 or not value.isdigit():
            return None
        number = int(value)
    else:
        if not 1 <= len(value) <= 10 or not value.isascii() or not value.isdigit():
            return None
        number = int(value)
    return number if 1 <= number <= 2147483647 else None


def _split(text: str) -> list[str]:
    values, start, stack, quote, escaped = [], 0, [], False, False
    matching = {")": "(", "]": "[", "}": "{", ">": "<"}
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = False
            continue
        if char == '"':
            quote = True
        elif char in "([{<":
            stack.append(char)
            if len(stack) > 32:
                raise ValueError("Argument nesting exceeds bound")
        elif char in ")]}>":
            if not stack or stack.pop() != matching[char]:
                raise ValueError("Unbalanced argument framing")
        elif char == "," and not stack:
            values.append(text[start:index].strip())
            start = index + 1
    if quote or stack:
        raise ValueError("Incomplete argument framing")
    if text[start:].strip():
        values.append(text[start:].strip())
    if len(values) > 64:
        raise ValueError("Too many syscall arguments")
    return values


def _string(token: str) -> str:
    if not _STRING.fullmatch(token):
        raise ValueError("Unsupported/truncated C string")
    index = 1
    while index < len(token) - 1:
        if token[index] != "\\":
            index += 1
            continue
        escape = re.match(
            r"\\(?:[\\\"'?abfnrtv]|[0-7]{1,3}|x[0-9a-fA-F]{2})", token[index:]
        )
        if escape is None:
            raise ValueError("Unknown C string escape")
        index += len(escape[0])
    raw = ast.literal_eval("b" + token)
    value = raw.decode("utf-8", errors="strict")
    if "\x00" in value or len(raw) > 4096:
        raise ValueError("Invalid pathname bytes")
    return value


def parse_query_trace(raw: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    """Parse a finite strace6.13 stream without interpreting it as closure."""
    events: list[dict[str, Any]] = []
    pending: dict[int, str] = {}
    processes: set[int] = set()
    exits: dict[str, int | None] = {}
    exit_requests: dict[int, int] = {}
    reasons: list[str] = []
    incomplete = False

    def issue(reason: str, *, truncated: bool = False) -> None:
        nonlocal incomplete
        incomplete |= truncated
        if reason not in reasons and len(reasons) < 128:
            reasons.append(reason)

    if len(raw) > limits["max_trace_bytes"]:
        raw = raw[: limits["max_trace_bytes"]]
        issue("Trace byte limit exceeded", truncated=True)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        text = raw.decode("utf-8", errors="replace")
        issue("Non-UTF8 trace bytes")
    if text and not text.endswith("\n"):
        issue("Trace has an incomplete final line", truncated=True)
    for sequence, line in enumerate(text.splitlines(), 1):
        if len(events) >= limits["max_events"]:
            issue("Event limit exceeded", truncated=True)
            break
        if len(line.encode()) > limits["max_line_bytes"]:
            issue("Trace line limit exceeded", truncated=True)
            break
        match = _PREFIX.match(line)
        if match is None:
            issue("Unframed tracer/native diagnostic")
            continue
        pid, body = _pid(match[1]), match[2]
        if pid is None:
            issue("Unsupported process identifier numeric domain")
            continue
        processes.add(pid)
        if len(processes) > limits["max_processes"]:
            issue("Process observation limit exceeded", truncated=True)
            processes.remove(pid)
            break
        if str(pid) in exits:
            issue("Event after terminal process observation")
        terminal = re.fullmatch(r"\+\+\+ exited with (\d+) \+\+\+", body)
        killed = re.fullmatch(
            r"\+\+\+ killed by SIG[A-Z0-9]+(?: \(core dumped\))? \+\+\+", body
        )
        if terminal or killed:
            if str(pid) in exits:
                issue("Duplicate terminal process observation")
            if terminal and (len(terminal[1]) > 3 or int(terminal[1]) > 255):
                issue("Unsupported terminal exit numeric domain")
                continue
            observed_exit = int(terminal[1]) if terminal else None
            if (
                terminal
                and pid in exit_requests
                and observed_exit != exit_requests[pid]
            ):
                issue("Terminal exit contradicts observed exit syscall")
            if str(pid) not in exits:
                exits[str(pid)] = observed_exit
            continue
        if body.startswith("--- SIG"):
            continue
        if body.endswith(" <unfinished ...>"):
            if pid in pending:
                issue("Nested unfinished syscall")
            pending[pid] = body.removesuffix(" <unfinished ...>")
            continue
        resumed = re.match(r"^<\.\.\. ([a-zA-Z_0-9]+) resumed>(.*)$", body)
        if resumed:
            prefix = pending.pop(pid, None)
            if prefix is None or not prefix.startswith(resumed[1] + "("):
                issue("Orphan/mismatched resumed syscall")
                continue
            body = prefix + resumed[2]
        call = _CALL.fullmatch(body)
        if call is None:
            issue("Unsupported syscall framing")
            continue
        operation, argument_text, result = call.groups()
        try:
            arguments = _split(argument_text)
        except (ValueError, SyntaxError):
            issue("Unsupported syscall arguments")
            continue
        if operation in {"clone", "clone3", "fork", "vfork"}:
            child = re.match(r"([1-9][0-9]*)(?:\s|$)", result)
            if child:
                child_pid = _pid(child[1])
                if child_pid is None:
                    issue("Unsupported created process identifier numeric domain")
                else:
                    processes.add(child_pid)
                    if len(processes) > limits["max_processes"]:
                        issue(
                            "Created process observation limit exceeded", truncated=True
                        )
                        processes.remove(child_pid)
                        break
        if operation in {"exit", "exit_group"}:
            if len(arguments) != 1 or re.fullmatch(r"-?[0-9]+", arguments[0]) is None:
                issue("Unsupported process exit argument")
            elif len(arguments[0]) > 11:
                issue("Unsupported exit syscall numeric domain")
            else:
                value = int(arguments[0])
                if not -2147483648 <= value <= 2147483647:
                    issue("Unsupported exit syscall numeric domain")
                else:
                    exit_requests[pid] = value & 255
        if result == "?":
            if operation not in {"exit", "exit_group"}:
                issue("Unknown syscall result")
        elif re.match(r"^(?:-?[0-9]+|0x[0-9a-fA-F]+)(?:\s|<|$)", result) is None:
            issue("Unsupported syscall result")
        path, resolution = None, "not-a-path-query"
        errno_match = re.match(r"-1 ([A-Z][A-Z0-9_]+)\b", result)
        errno = errno_match[1] if errno_match else None
        if operation not in {"exit", "exit_group"} and (
            result.startswith("?") or "ERESTART" in result
        ):
            issue("Interrupted syscall lacks a final result")
        try:
            if operation in _DIRECT or operation == "open":
                path = _string(arguments[0])
                resolution = "absolute" if path.startswith("/") else "unsupported"
            elif operation in _AT:
                path = _string(arguments[1])
                if path.startswith("/"):
                    resolution = "absolute"
                else:
                    descriptor = re.fullmatch(
                        r"(?:AT_FDCWD|\d+)<(/[^<>]*)>", arguments[0]
                    )
                    if descriptor and path:
                        path = str(PurePosixPath(descriptor[1]) / path)
                        resolution = "observed-dirfd"
                    elif (
                        descriptor
                        and not path
                        and any("AT_EMPTY_PATH" in item for item in arguments[2:])
                    ):
                        path = descriptor[1]
                        resolution = "descriptor"
                    else:
                        resolution = "unsupported"
            elif operation not in _PROCESS:
                issue("Unsupported syscall operation: " + operation)
        except (ValueError, SyntaxError, IndexError, UnicodeError):
            resolution = "unsupported"
            issue("Unsupported pathname encoding/framing")
        if resolution == "unsupported":
            issue("Unresolved relative/descriptor pathname")
        if path is not None and ".." in PurePosixPath(path).parts:
            issue("Lexical parent traversal requires further resolution")
        events.append(
            {
                "sequence": sequence,
                "pid": pid,
                "operation": operation,
                "arguments": arguments,
                "result": result,
                "path": path,
                "errno": errno,
                "resolution": resolution,
            }
        )
    if pending:
        issue("Unfinished syscalls at end of trace", truncated=True)
    if not processes or set(exits) != {str(pid) for pid in processes}:
        issue("Observed processes lack terminal records", truncated=True)
    return {
        "status": (
            "incomplete"
            if incomplete
            else ("unsupported" if reasons else "complete_observation")
        ),
        "reasons": reasons,
        "events": events,
        "processes": sorted(processes),
        "exits": exits,
        "pending_count": len(pending),
    }


def _seal(pin: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    fd = os.memfd_create("cppulse-query-tool", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:

        def write(chunk: bytes) -> None:
            remaining = memoryview(chunk)
            while remaining:
                size = os.write(fd, remaining)
                if not size:
                    raise OSError("No progress writing executable snapshot")
                remaining = remaining[size:]

        size, digest = _stream_file(
            Path(pin["path"]), write=write, max_bytes=16 * 1024**2
        )
        if size != pin["size_bytes"] or digest != pin["sha256"]:
            raise IntegrityError("Selected trace tool bytes changed")
        os.fchmod(fd, 0o700)
        fcntl.fcntl(fd, getattr(fcntl, "F_ADD_SEALS", 1033), 15)
        if fcntl.fcntl(fd, getattr(fcntl, "F_GET_SEALS", 1034)) != 15:
            raise IntegrityError("Executable snapshot sealing failed")
        return fd, {
            "path": f"/proc/{os.getpid()}/fd/{fd}",
            "sha256": digest,
            "size_bytes": size,
            "seals": 15,
            "method": "linux-sealed-memfd-sha256-v1",
        }
    except BaseException:
        os.close(fd)
        raise


def _run(
    argv: list[str],
    cwd: Path,
    environment: dict[str, str],
    output: Path,
    limits: dict[str, Any],
) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic() + limits["wall_seconds"]
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    counts = {"stdout": 0, "trace": 0}
    captured = {"stdout": 0, "trace": 0}
    status = "passed"
    reason = ""
    pids = set()
    line = b""
    events = 0
    stopping = None
    try:
        with (
            selectors.DefaultSelector() as selector,
            (output / "stdout.log").open("xb") as stdout,
            (output / "trace.log").open("xb") as trace,
        ):
            streams = {"stdout": stdout, "trace": trace}
            for name, pipe in [("stdout", process.stdout), ("trace", process.stderr)]:
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                now = time.monotonic()
                if now >= deadline and stopping is None:
                    status = "timed_out"
                    reason = "Wall limit exceeded"
                    stopping = now
                if stopping is not None:
                    try:
                        os.killpg(
                            process.pid,
                            signal.SIGTERM if now - stopping < 0.25 else signal.SIGKILL,
                        )
                    except ProcessLookupError:
                        pass
                    if now - stopping > 1.25:
                        status = "incomplete"
                        reason += "; pipe drain incomplete"
                        break
                for key, _ in selector.select(0.025):
                    try:
                        chunk = os.read(key.fileobj.fileno(), 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    name = key.data
                    counts[name] += len(chunk)
                    cap = limits[
                        "max_stdout_bytes" if name == "stdout" else "max_trace_bytes"
                    ]
                    kept = chunk[: max(0, cap - captured[name])]
                    streams[name].write(kept)
                    captured[name] += len(kept)
                    if counts[name] > cap and stopping is None:
                        status = "output_limit"
                        reason = name + " byte limit exceeded"
                        stopping = time.monotonic()
                    if name == "trace" and stopping is None:
                        line += chunk
                        while b"\n" in line:
                            item, line = line.split(b"\n", 1)
                            events += 1
                            match = re.match(rb"(?:\[pid\s+)?(\d+)\]?\s", item)
                            if match:
                                observed_pid = _pid(match[1])
                                if observed_pid is None:
                                    status = "event_limit"
                                    reason = (
                                        "Unsupported process identifier numeric domain"
                                    )
                                    stopping = time.monotonic()
                                    break
                                pids.add(observed_pid)
                                child = re.search(
                                    rb"(?:clone3?|fork|vfork)(?:\(| resumed>).* = ([1-9][0-9]*)$",
                                    item,
                                )
                                if child:
                                    child_pid = _pid(child[1])
                                    if child_pid is None:
                                        status = "event_limit"
                                        reason = (
                                            "Unsupported created process numeric domain"
                                        )
                                        stopping = time.monotonic()
                                        break
                                    pids.add(child_pid)
                            if (
                                len(item) > limits["max_line_bytes"]
                                or events > limits["max_events"]
                                or len(pids) > limits["max_processes"]
                            ):
                                status = "event_limit"
                                reason = "Line/event/process observation bound exceeded"
                                stopping = time.monotonic()
                                break
                        if len(line) > limits["max_line_bytes"] and stopping is None:
                            status = "event_limit"
                            reason = "Unterminated trace line bound exceeded"
                            stopping = time.monotonic()
            process.wait(timeout=2)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    finally:
        for pipe in (process.stdout, process.stderr):
            if pipe is not None and not pipe.closed:
                pipe.close()
    if status == "passed" and process.returncode != 0:
        status = "failed"
        reason = "Observed tracer exit was nonzero"
    return {
        "argv": argv,
        "cwd": str(cwd),
        "environment": environment,
        "pid": process.pid,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reason": reason,
        "exit_status": process.returncode,
        "observed_bytes": counts,
        "captured_bytes": captured,
        "scope": "owned tracer process/group and drained pipes; not a security sandbox",
    }


def collect_query_observation(
    request: dict[str, Any], output: Path, *, execute_selected_tools: bool = False
) -> dict[str, Any]:
    """Run selected trusted tools and retain finite descriptive observations."""
    validate_query_document("request", request)
    if not execute_selected_tools:
        raise ContractError("Explicit selected-tool execution is required")
    if os.name != "posix" or not hasattr(os, "memfd_create"):
        raise ContractError(
            "Query observation currently requires Linux sealed executable descriptors"
        )
    output = Path(output).absolute()
    selected_report = request["native_report_relative_path"]
    if selected_report is not None:
        relative = PurePosixPath(selected_report)
        if (
            not relative.parts
            or relative.is_absolute()
            or str(relative) != selected_report
            or ".." in relative.parts
        ):
            raise ContractError(
                "Native report must use a canonical owned relative path"
            )
        argv = request["invocation"]["argv"]
        if argv.count("--output") != 1 or (
            argv[argv.index("--output") + 1]
            if argv.index("--output") + 1 < len(argv)
            else None
        ) != str((output / selected_report).parent):
            raise ContractError("Native report path must match selected output argv")
        if (
            "--file-size-bytes" not in argv
            or (
                argv[argv.index("--file-size-bytes") + 1]
                if argv.index("--file-size-bytes") + 1 < len(argv)
                else None
            )
            != "8388608"
        ):
            raise ContractError(
                "Observed native report requires explicit finite file output limit"
            )
    with _directory(output.parent) as parent:
        os.mkdir(output.name, mode=0o700, dir_fd=parent)
    (output / "request.json").write_bytes(canonical_json_bytes(request))
    fds = []
    try:
        tools = {}
        for key in ("tracer", "native"):
            fd, tools[key] = _seal(request[key])
            fds.append(fd)
        version_dir = output / "version"
        version_dir.mkdir()
        version_limits = {
            **request["limits"],
            "wall_seconds": min(5, request["limits"]["wall_seconds"]),
            "max_trace_bytes": 4096,
            "max_stdout_bytes": 4096,
        }
        version = _run(
            [tools["tracer"]["path"], "--version"],
            Path(request["invocation"]["cwd"]),
            request["invocation"]["environment"],
            version_dir,
            version_limits,
        )
        version_raw = _read(version_dir / "stdout.log", max_bytes=4096)
        if (
            version["status"] != "passed"
            or not version_raw.decode().splitlines()
            or version_raw.decode().splitlines()[0] != request["tracer"]["version"]
        ):
            raise ContractError("Unsupported selected tracer version")
        tools["tracer"]["version_receipt"] = version

        actual = [tools["native"]["path"], *request["invocation"]["argv"][1:]]
        command = [
            tools["tracer"]["path"],
            "--always-show-pid",
            "-f",
            "-q",
            "-s",
            "4096",
            "-x",
            "-yy",
            "-v",
            "-e",
            "trace=%file,%process",
            *actual,
        ]
        receipt = _run(
            command,
            Path(request["invocation"]["cwd"]),
            request["invocation"]["environment"],
            output,
            request["limits"],
        )
        raw = _read(
            output / "trace.log", max_bytes=request["limits"]["max_trace_bytes"]
        )
        parsed = parse_query_trace(raw, request["limits"])
        status = (
            parsed["status"]
            if receipt["status"] in {"passed", "failed"}
            else "incomplete"
        )
        native = []
        for event in parsed["events"]:
            if (
                event["operation"] == "execve"
                and event["path"] == actual[0]
                and event["result"] == "0"
            ):
                native.append(
                    {
                        "pid": event["pid"],
                        "actual_execve_arguments": event["arguments"],
                        "declared_argv": request["invocation"]["argv"],
                        "observed_exit_status": parsed["exits"].get(str(event["pid"])),
                        "binding": "selected immutable executable bytes; runtime libraries unverified",
                    }
                )
        if not native and status == "complete_observation":
            status = "unsupported"
        parser = None
        native_path = request["native_report_relative_path"]
        if native_path is not None:
            try:
                native_raw = _read(output / native_path, max_bytes=8 * 1024**2)
                native_report = json.loads(native_raw)
                from cppulse.contracts import validate

                validate("findings", native_report, version="prototype_v1")
                parser = native_report["metadata"]["analysis"]["parser"]
            except (IntegrityError, ContractError, ValueError, KeyError, TypeError):
                status = "incomplete"
        artifacts = []
        names = [
            "request.json",
            "stdout.log",
            "trace.log",
            "version/stdout.log",
            "version/trace.log",
        ] + ([native_path] if native_path else [])
        for name in names:
            path = output / name
            if path.is_file() and not path.is_symlink():
                content = _read(path, max_bytes=8 * 1024**2)
                artifacts.append(
                    {
                        "path": name,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "size_bytes": len(content),
                    }
                )

        report = {
            "version": "0.1.0",
            "request_sha256": digest_json(request),
            "source_digest": request["source_digest"],
            "closure": "unqualified",
            "cache_eligible": False,
            "capture_status": status,
            "limits": request["limits"],
            "tool_bindings": tools,
            "tracer_receipt": receipt,
            "native_execution_observations": native,
            "native_parser": parser,
            "parsed": parsed,
            "artifacts": artifacts,
            "limitations": [
                "Selected source identity is a caller claim; no source freshness/authentication is established.",
                "Runtime/library mmap bytes, clock/vDSO/CPUID, VFS/PCH and complete input closure remain unverified.",
                "Negative paths are observed lookup outcomes; ancestor identities and reuse guards are not established.",
                "Complete observation describes supported trace framing/process terminals only; it never means closed inputs.",
                "PID/event limits bound observed records and trigger owned-group cleanup; no PID/cgroup or escaped-descendant containment is established.",
            ],
        }
        validate_query_document("report", report)
        validate_query_report(request, report, output)
        (output / "report.json").write_bytes(canonical_json_bytes(report))
        return report
    finally:
        for fd in fds:
            os.close(fd)


def validate_query_report(
    request: dict[str, Any], report: dict[str, Any], root: Path
) -> None:
    """Replay finite observations against exact retained request and trace bytes."""
    validate_query_document("request", request)
    validate_query_document("report", report)
    if (
        report["request_sha256"] != digest_json(request)
        or report["source_digest"] != request["source_digest"]
        or report["limits"] != request["limits"]
    ):
        raise ContractError("Query report changes selected request/context/limits")
    expected_names = {
        "request.json",
        "stdout.log",
        "trace.log",
        "version/stdout.log",
        "version/trace.log",
    }
    if request["native_report_relative_path"] and any(
        row["path"] == request["native_report_relative_path"]
        for row in report["artifacts"]
    ):
        expected_names.add(request["native_report_relative_path"])
    artifacts = {row["path"]: row for row in report["artifacts"]}
    if set(artifacts) != expected_names or len(artifacts) != len(report["artifacts"]):
        raise ContractError("Query retained inventory omits or duplicates material")
    payload = {}
    for name, record in artifacts.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
            raise ContractError("Query artifact path escapes owned output")
        content = _read(Path(root) / name, max_bytes=8 * 1024**2)
        if (
            len(content) != record["size_bytes"]
            or hashlib.sha256(content).hexdigest() != record["sha256"]
        ):
            raise IntegrityError("Query retained artifact bytes changed")
        payload[name] = content
    if payload["request.json"] != canonical_json_bytes(request):
        raise ContractError("Query original request bytes differ")
    parsed = parse_query_trace(payload["trace.log"], request["limits"])
    if parsed != report["parsed"]:
        raise ContractError("Query parsed observations do not replay from raw trace")
    for key in ("native", "tracer"):
        tool = report["tool_bindings"].get(key, {})
        if (
            any(
                tool.get(field) != request[key][field]
                for field in ("sha256", "size_bytes")
            )
            or tool.get("seals") != 15
            or tool.get("method") != "linux-sealed-memfd-sha256-v1"
        ):
            raise ContractError("Query selected executable byte binding differs")
        if re.fullmatch(r"/proc/[1-9][0-9]*/fd/[0-9]+", tool.get("path", "")) is None:
            raise ContractError("Invalid selected executable descriptor path")
    tools = report["tool_bindings"]
    native_descriptor = tools["native"]["path"].split("/")
    tracer_descriptor = tools["tracer"]["path"].split("/")
    if (
        native_descriptor[2] != tracer_descriptor[2]
        or native_descriptor[-1] == tracer_descriptor[-1]
    ):
        raise ContractError(
            "Selected executable descriptors need distinct held bytes from one supervisor"
        )
    actual = [tools["native"]["path"], *request["invocation"]["argv"][1:]]
    expected = [
        tools["tracer"]["path"],
        "--always-show-pid",
        "-f",
        "-q",
        "-s",
        "4096",
        "-x",
        "-yy",
        "-v",
        "-e",
        "trace=%file,%process",
        *actual,
    ]
    receipt = report["tracer_receipt"]
    if (
        receipt.get("argv") != expected
        or receipt.get("cwd") != request["invocation"]["cwd"]
        or receipt.get("environment") != request["invocation"]["environment"]
    ):
        raise ContractError("Query process receipt changes actual selected invocation")
    if receipt["status"] == "passed" and receipt["exit_status"] != 0:
        raise ContractError("Passed tracer receipt has a nonzero observed exit")
    if receipt["status"] == "failed" and receipt["exit_status"] in {0, None}:
        raise ContractError("Failed tracer receipt lacks a nonzero observed exit")
    for stream, name in [("stdout", "stdout.log"), ("trace", "trace.log")]:
        retained = len(payload[name])
        if (
            receipt.get("captured_bytes", {}).get(stream) != retained
            or receipt.get("observed_bytes", {}).get(stream, -1) < retained
            or (
                receipt["status"] in {"passed", "failed"}
                and receipt["observed_bytes"][stream] != retained
            )
        ):
            raise ContractError("Query process stream counts contradict retained bytes")
    try:
        version_lines = payload["version/stdout.log"].decode().splitlines()
    except UnicodeError as exc:
        raise ContractError("Query tracer version stream is not UTF8") from exc
    if not version_lines or version_lines[0] != request["tracer"]["version"]:
        raise ContractError("Query selected tracer version differs")
    version = tools["tracer"].get("version_receipt", {})
    if (
        version.get("argv") != [tools["tracer"]["path"], "--version"]
        or version.get("cwd") != request["invocation"]["cwd"]
        or version.get("environment") != request["invocation"]["environment"]
        or version.get("status") != "passed"
        or version.get("exit_status") != 0
    ):
        raise ContractError("Query tracer version receipt is inconsistent")
    for stream, name in [
        ("stdout", "version/stdout.log"),
        ("trace", "version/trace.log"),
    ]:
        retained = len(payload[name])
        if (
            version["captured_bytes"][stream] != retained
            or version["observed_bytes"][stream] != retained
        ):
            raise ContractError(
                "Tracer version stream counts contradict retained bytes"
            )
    native = []
    for event in parsed["events"]:
        if (
            event["operation"] == "execve"
            and event["path"] == actual[0]
            and event["result"] == "0"
        ):
            try:
                observed = [
                    _string(token) for token in _split(event["arguments"][1][1:-1])
                ]
            except (ValueError, SyntaxError, IndexError, UnicodeError) as exc:
                raise ContractError("Native observed argv cannot be decoded") from exc
            try:
                environment_items = [
                    _string(token) for token in _split(event["arguments"][2][1:-1])
                ]
            except (ValueError, SyntaxError, IndexError, UnicodeError) as exc:
                raise ContractError(
                    "Native observed environment cannot be decoded"
                ) from exc
            expected_environment = {
                key + "=" + value
                for key, value in request["invocation"]["environment"].items()
            }
            if (
                len(environment_items) != len(expected_environment)
                or set(environment_items) != expected_environment
            ):
                raise ContractError(
                    "Native observed environment differs from selected environment"
                )
            if observed != actual:
                raise ContractError(
                    "Native observed execve argv differs from selected invocation"
                )
            native.append(
                {
                    "pid": event["pid"],
                    "actual_execve_arguments": event["arguments"],
                    "declared_argv": request["invocation"]["argv"],
                    "observed_exit_status": parsed["exits"].get(str(event["pid"])),
                    "binding": "selected immutable executable bytes; runtime libraries unverified",
                }
            )
    if native != report["native_execution_observations"]:
        raise ContractError(
            "Query native execution observations do not match raw trace"
        )
    status = (
        parsed["status"] if receipt["status"] in {"passed", "failed"} else "incomplete"
    )
    if not native and status == "complete_observation":
        status = "unsupported"
    parser = None
    if request["native_report_relative_path"]:
        from cppulse.contracts import validate

        try:
            native_report = json.loads(payload[request["native_report_relative_path"]])
            validate("findings", native_report, version="prototype_v1")
            parser = native_report["metadata"]["analysis"]["parser"]
        except (ValueError, KeyError, TypeError, ContractError):
            status = "incomplete"
    if parser != report["native_parser"] or status != report["capture_status"]:
        raise ContractError(
            "Query report qualification does not reproduce retained observations"
        )
