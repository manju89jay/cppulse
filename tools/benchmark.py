#!/usr/bin/env python3
"""Measure explicit local commands; never infer correctness from elapsed time.

This runner records actual repetitions and resource availability. A suite is an
explicit execution request. Its success means the declared commands returned
their expected exits, not that their outputs are semantically equivalent or
that cppulse satisfies a release performance budget.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Case:
    """One explicitly requested finite command measurement."""

    id: str
    argv: tuple[str, ...]
    cwd: Path
    repetitions: int
    timeout_seconds: float
    expected_exit: int


@dataclass
class Measurement:
    """Observed process facts, including unavailable-resource explanations."""

    case_id: str
    repetition: int
    argv: list[str]
    cwd: str
    status: str
    returncode: int | None
    expected_exit: int
    wall_seconds: float
    cpu_seconds: float | None
    peak_rss_bytes: int | None
    resource_scope: str
    log: str
    reason: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _schema(name: str) -> dict[str, Any]:
    return json.loads(
        (Path(__file__).parent / "contracts" / f"{name}.schema.json").read_text()
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate benchmark JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Nonfinite benchmark number: {value}")


def _read_suite(path: Path) -> tuple[dict[str, Any], str, list[Case]]:
    if not path.is_file():
        raise ValueError("Benchmark suite must be a regular file")
    with path.open("rb") as stream:
        content = stream.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError("Benchmark suite exceeds the 1 MiB bound")
    document = json.loads(
        content, object_pairs_hook=_unique_object, parse_constant=_reject_constant
    )
    jsonschema.validate(document, _schema("benchmark-suite"))
    identifiers: set[str] = set()
    cases: list[Case] = []
    for row in document["cases"]:
        if row["id"] in identifiers:
            raise ValueError(f"Duplicate benchmark case: {row['id']}")
        identifiers.add(row["id"])
        if any("\0" in part for part in [*row["argv"], row["cwd"]]):
            raise ValueError("Benchmark arguments and directories cannot contain NUL")
        cwd = Path(row["cwd"])
        if not cwd.is_absolute():
            cwd = path.parent / cwd
        cwd = cwd.resolve(strict=True)
        if not cwd.is_dir():
            raise ValueError(f"Benchmark working directory is not a directory: {cwd}")
        cases.append(
            Case(
                id=row["id"],
                argv=tuple(row["argv"]),
                cwd=cwd,
                repetitions=row["repetitions"],
                timeout_seconds=float(row["timeout_seconds"]),
                expected_exit=row.get("expected_exit", 0),
            )
        )
    return document, hashlib.sha256(content).hexdigest(), cases


def _wait(
    process: subprocess.Popen[bytes], timeout: float
) -> tuple[int, float | None, int | None, str]:
    if os.name == "posix" and hasattr(os, "wait4"):
        deadline = time.monotonic() + timeout
        while True:
            pid, status, usage = os.wait4(process.pid, os.WNOHANG)
            if pid:
                process.returncode = os.waitstatus_to_exitcode(status)
                cpu = usage.ru_utime + usage.ru_stime
                if sys.platform.startswith("linux"):
                    rss = int(usage.ru_maxrss * 1024)
                elif sys.platform == "darwin":
                    rss = int(usage.ru_maxrss)
                else:
                    rss = None
                return (
                    process.returncode,
                    cpu,
                    rss,
                    "wait4 child accounting, including descendants reaped by that child; "
                    "peak RSS is not the sum of concurrently running processes",
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, timeout)
            time.sleep(min(0.01, remaining))
    return (
        process.wait(timeout=timeout),
        None,
        None,
        "Wall time only; per-process CPU and peak RSS are unavailable on this host",
    )


def wait_process(
    process: subprocess.Popen[bytes], timeout: float
) -> tuple[int, float | None, int | None, str]:
    """Wait within the explicit budget and return scoped observed resources."""
    return _wait(process, timeout)


def _stop(
    process: subprocess.Popen[bytes],
) -> tuple[int, float | None, int | None, str]:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    return _wait(process, 10)


def _measure(case: Case, repetition: int, output: Path) -> Measurement:
    log = output / f"{case.id}-{repetition:03d}.log"
    row = Measurement(
        case_id=case.id,
        repetition=repetition,
        argv=list(case.argv),
        cwd=str(case.cwd),
        status="blocked",
        returncode=None,
        expected_exit=case.expected_exit,
        wall_seconds=0,
        cpu_seconds=None,
        peak_rss_bytes=None,
        resource_scope="No process measurement was available",
        log=str(log),
        reason=None,
    )
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    with log.open("wb") as stream:
        try:
            process = subprocess.Popen(
                list(case.argv),
                cwd=case.cwd,
                stdout=stream,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=os.name == "posix",
            )
            code, cpu, rss, scope = wait_process(process, case.timeout_seconds)
            row.returncode = code
            row.cpu_seconds, row.peak_rss_bytes, row.resource_scope = cpu, rss, scope
            row.status = "passed" if code == case.expected_exit else "failed"
            if row.status == "failed":
                row.reason = f"Observed exit {code}; expected {case.expected_exit}"
        except subprocess.TimeoutExpired:
            assert process is not None
            code, cpu, rss, scope = _stop(process)
            row.returncode = code
            row.cpu_seconds, row.peak_rss_bytes, row.resource_scope = cpu, rss, scope
            row.status = "failed"
            row.reason = f"Command exceeded timeout of {case.timeout_seconds} seconds"
        except KeyboardInterrupt:
            if process is not None:
                code, cpu, rss, scope = _stop(process)
                row.returncode = code
                row.cpu_seconds, row.peak_rss_bytes, row.resource_scope = (
                    cpu,
                    rss,
                    scope,
                )
            row.status = "interrupted"
            row.reason = "Explicit cancellation; remaining work was not measured"
        except (FileNotFoundError, PermissionError) as error:
            row.reason = str(error)
            stream.write((str(error) + "\n").encode())
        except OSError as error:
            row.status = "failed"
            row.reason = str(error)
            stream.write((str(error) + "\n").encode())
    row.wall_seconds = time.monotonic() - started
    return row


def _summary(measurements: list[Measurement]) -> tuple[str, int]:
    states = {row.status for row in measurements}
    if "interrupted" in states:
        return "interrupted", 130
    if "failed" in states:
        return "failed", 1
    if "blocked" in states:
        return "blocked", 2
    return "passed", 0


def run_suite(suite: Path, output: Path) -> dict[str, Any]:
    """Execute a selected suite once and preserve each actual repetition.

    Args:
        suite: A versioned explicit-command JSON recipe.
        output: A new directory; previous measurements are never overwritten.

    Returns:
        A validated measurement result, with failures and unavailable work intact.

    Raises:
        ValueError: If identities or execution requests are invalid.
        FileExistsError: If the evidence directory already exists.
    """
    suite = suite.resolve(strict=True)
    document, suite_hash, cases = _read_suite(suite)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {
        "version": "1.0.0",
        "suite_id": document["id"],
        "suite_sha256": suite_hash,
        "started_at": _now(),
        "finished_at": _now(),
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "hostname": platform.node(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "status": "blocked",
        "exit_status": 2,
        "measurements": [],
        "limitations": [
            "Only the selected commands and repetitions were measured. Command success does not establish semantic equivalence, detector accuracy or release qualification.",
            "No performance budget or regression threshold is inferred from these measurements. Representative cold/warm/edit suites and repeated reference-host comparisons are separate requirements.",
            "wait4 resource availability and units are platform-specific; unavailable CPU/RSS are null. Peak RSS is not aggregate concurrent process-tree memory.",
            "POSIX timeout/cancellation terminates the selected process group. On other hosts only the immediate process is terminated; descendant lifetime is not qualified.",
            "The environment record is descriptive. It neither records all machine load nor authenticates the producer.",
        ],
    }
    measurements: list[Measurement] = []
    interrupted = False
    for case in cases:
        for repetition in range(1, case.repetitions + 1):
            measurements.append(_measure(case, repetition, output))
            result["measurements"] = [asdict(row) for row in measurements]
            result["status"], result["exit_status"] = _summary(measurements)
            result["finished_at"] = _now()
            jsonschema.validate(result, _schema("benchmark-result"))
            temporary = output / ".benchmark-results.json.tmp"
            temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
            temporary.replace(output / "benchmark-results.json")
            interrupted = measurements[-1].status == "interrupted"
            if interrupted:
                break
        if interrupted:
            break
    return result


def main(argv: list[str] | None = None) -> int:
    """Run only a selected local suite and print its recorded result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_suite(args.suite, args.output_dir)
    except (OSError, ValueError, jsonschema.ValidationError) as error:
        parser.exit(2, f"Benchmark request invalid: {error}\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return int(result["exit_status"])


if __name__ == "__main__":
    raise SystemExit(main())
