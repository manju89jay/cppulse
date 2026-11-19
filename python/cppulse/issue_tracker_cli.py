"""Explicit read-only issue collection into a new, retained local invocation.

This boundary does not approve financial claims or mutate a tracker. Completed
collection means available observations, not authenticated savings or a complete
production delivery. Failed/cancelled invocations retain every created artifact.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any, NoReturn

from cppulse.errors import ContractError, CppulseError, IntegrityError
from cppulse.identities import canonical_json_bytes
from cppulse.issue_tracker import (
    MAX_REQUEST_BYTES,
    collect,
    validate_report,
    validate_request,
)
from cppulse.run_store import _directory, _read

MAX_REPORT_BYTES = 32 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 16 * 1024


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ContractError("Invalid issue CLI arguments: " + message[:1024])


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("Duplicate issue request field")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ContractError("Nonfinite issue request number")


def _float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ContractError("Nonfinite issue request number")
    return result


def _int(value: str) -> int:
    if len(value) > 20:
        raise ContractError("Issue request integer exceeds supported range")
    return int(value)


def _path(value: Path) -> Path:
    if "\x00" in str(value) or ".." in value.parts:
        raise ContractError("Issue paths cannot contain NUL or directory traversal")
    return value.absolute()


def _request(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = _read(_path(path), max_bytes=MAX_REQUEST_BYTES)
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=_float,
            parse_int=_int,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("Issue request must be bounded strict UTF-8 JSON") from exc
    validate_request(document)
    return raw, document


def _write(directory: int, name: str, content: bytes) -> dict[str, Any]:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(directory)
    return {
        "path": name,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


@dataclass
class _OwnedOutput:
    path: Path
    descriptor: int

    def verify(self) -> None:
        with _directory(self.path) as current:
            observed, expected = os.fstat(current), os.fstat(self.descriptor)
            if (observed.st_dev, observed.st_ino) != (expected.st_dev, expected.st_ino):
                raise IntegrityError("Owned issue output directory changed")


def _reserve(path: Path) -> _OwnedOutput:
    selected = _path(path)
    with _directory(selected.parent, create=True) as parent:
        os.mkdir(selected.name, mode=0o700, dir_fd=parent)
        descriptor = os.open(
            selected.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
    return _OwnedOutput(selected, descriptor)


def _file(directory: int, name: str, bound: int, prefix: str = "") -> dict[str, Any]:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
    )
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > bound:
            raise IntegrityError("Issue artifact is not a bounded regular file")
        digest, size = hashlib.sha256(), 0
        while chunk := stream.read(min(64 * 1024, bound + 1 - size)):
            size += len(chunk)
            if size > bound:
                raise IntegrityError("Issue artifact grew beyond its bound")
            digest.update(chunk)
        after = os.fstat(stream.fileno())

        def facts(value: os.stat_result) -> tuple[int, int, int, int, int]:
            return (
                value.st_dev,
                value.st_ino,
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
            )

        if facts(before) != facts(after) or size != after.st_size:
            raise IntegrityError("Issue artifact changed while hashing")
    return {"path": prefix + name, "size_bytes": size, "sha256": digest.hexdigest()}


def _inventory(owner: _OwnedOutput, request: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = []
    with os.scandir(owner.descriptor) as entries:
        for entry in entries:
            if entry.name == "request.original.json":
                artifacts.append(_file(owner.descriptor, entry.name, MAX_REQUEST_BYTES))
            elif entry.name == "observations":
                child = os.open(
                    entry.name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=owner.descriptor,
                )
                try:
                    allowed = {
                        f"page-{index:03}.body": request["limits"]["page_bytes"]
                        for index in range(1, request["limits"]["pages"] + 1)
                    }
                    allowed.update(
                        {
                            "request.json": MAX_REQUEST_BYTES,
                            "report.json": MAX_REPORT_BYTES,
                        }
                    )
                    with os.scandir(child) as retained:
                        for item in retained:
                            if item.name not in allowed:
                                raise IntegrityError(
                                    "Unexpected issue observation artifact"
                                )
                            artifacts.append(
                                _file(
                                    child,
                                    item.name,
                                    allowed[item.name],
                                    "observations/",
                                )
                            )
                finally:
                    os.close(child)
            else:
                raise IntegrityError("Unexpected owned issue invocation artifact")
    return sorted(artifacts, key=lambda artifact: artifact["path"])


def _binding(
    report: dict[str, Any], request: dict[str, Any], artifacts: list[dict[str, Any]]
) -> None:
    index = {artifact["path"]: artifact for artifact in artifacts}
    expected = {
        "observations/report.json": canonical_json_bytes(report),
        "observations/request.json": canonical_json_bytes(request),
    }
    for path, content in expected.items():
        if (
            path not in index
            or index[path]["sha256"] != hashlib.sha256(content).hexdigest()
            or index[path]["size_bytes"] != len(content)
        ):
            raise IntegrityError(
                "Retained issue report/request differs from validated projection"
            )
    for page in report["pages"]:
        artifact = index.get("observations/" + page["path"])
        if (
            artifact is None
            or artifact["sha256"] != page["sha256"]
            or artifact["size_bytes"] != page["size_bytes"]
        ):
            raise IntegrityError(
                "Retained issue page differs from validated projection"
            )
    if report["status"] == "complete":
        pages = {path for path in index if path.endswith(".body")}
        if pages != {"observations/" + page["path"] for page in report["pages"]}:
            raise IntegrityError("Unaccounted issue pages cannot imply complete scope")


def _finish(
    owner: _OwnedOutput,
    request: dict[str, Any],
    raw: bytes,
    report: dict[str, Any] | None,
    status: str,
    code: int,
    diagnostics: list[str],
) -> tuple[int, dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    inventory_status = "complete"
    try:
        owner.verify()
        artifacts = _inventory(owner, request)
        original = next(
            (item for item in artifacts if item["path"] == "request.original.json"),
            None,
        )
        if (
            original is None
            or original["sha256"] != hashlib.sha256(raw).hexdigest()
            or original["size_bytes"] != len(raw)
        ):
            raise IntegrityError(
                "Retained original issue request differs from selected input bytes"
            )
        if report is not None:
            validate_report(
                report, expected_request=request, output=owner.path / "observations"
            )
            _binding(report, request, artifacts)
        owner.verify()
    except (CppulseError, OSError, ValueError, RuntimeError, TypeError) as exc:
        inventory_status = "incomplete"
        diagnostics.append(
            f"Artifact verification failed: {type(exc).__name__}: {str(exc)[:1024]}"
        )
        if code != 130:
            status, code = "failed", 2
    if diagnostics:
        content = ("\n".join(diagnostics) + "\n").encode("utf-8", errors="replace")[
            :MAX_DIAGNOSTIC_BYTES
        ]
        artifacts.append(_write(owner.descriptor, "diagnostics.txt", content))
    identity = os.fstat(owner.descriptor)
    outcome = {
        "version": "1.0.0",
        "method": "cppulse-issues-cli-v1",
        "status": status,
        "exit_status": code,
        "request_original_sha256": hashlib.sha256(raw).hexdigest(),
        "request_canonical_sha256": hashlib.sha256(
            canonical_json_bytes(request)
        ).hexdigest(),
        "output_identity": {"device": identity.st_dev, "inode": identity.st_ino},
        "artifact_inventory_status": inventory_status,
        "artifacts": sorted(artifacts, key=lambda artifact: artifact["path"]),
        "report_status": (
            report.get("status")
            if isinstance(report, dict)
            and report.get("status") in {"complete", "partial", "unavailable"}
            else None
        ),
        "limitations": [
            "Retained local integrity receipts are not producer/financial authentication.",
            "Only the selected public read-only issue scope is requested; no tracker mutations or inferred financial approval.",
        ],
    }
    artifact = _write(
        owner.descriptor, "outcome.json", canonical_json_bytes(outcome) + b"\n"
    )
    return code, {
        "version": "1.0.0",
        "status": status,
        "exit_status": code,
        "output": str(owner.path),
        "outcome": str(owner.path / "outcome.json"),
        "outcome_sha256": artifact["sha256"],
        "report_status": outcome["report_status"],
    }


def _cancelled_finalization(
    owner: _OwnedOutput, request: dict[str, Any], raw: bytes
) -> dict[str, Any]:
    """Retain a late cancellation without replacing an already published outcome."""
    message = b"Issue invocation cancelled during finalization; all owned artifacts retained.\n"
    try:
        diagnostic = _write(owner.descriptor, "diagnostics.txt", message)
    except FileExistsError:
        diagnostic = _write(owner.descriptor, "diagnostics.cancelled.txt", message)
    outcome = {
        "version": "1.0.0",
        "method": "cppulse-issues-cli-v1",
        "status": "cancelled",
        "exit_status": 130,
        "request_original_sha256": hashlib.sha256(raw).hexdigest(),
        "request_canonical_sha256": hashlib.sha256(
            canonical_json_bytes(request)
        ).hexdigest(),
        "artifact_inventory_status": "incomplete",
        "artifacts": [diagnostic],
        "report_status": None,
        "limitations": [
            "Cancellation prevented a complete artifact inventory; existing producer observations are retained without a completed CLI acceptance claim."
        ],
    }
    content = canonical_json_bytes(outcome) + b"\n"
    try:
        artifact = _write(owner.descriptor, "outcome.json", content)
    except FileExistsError:
        artifact = _write(owner.descriptor, "outcome.cancelled.json", content)
    return {
        "version": "1.0.0",
        "status": "cancelled",
        "exit_status": 130,
        "output": str(owner.path),
        "outcome": str(owner.path / artifact["path"]),
        "outcome_sha256": artifact["sha256"],
        "report_status": None,
    }


def main(argv: list[str] | None = None) -> int:
    """Read an explicit request, preserve one new invocation, and return its status."""
    owner: _OwnedOutput | None = None
    request: dict[str, Any] | None = None
    raw = b""
    report = None
    diagnostics: list[str] = []
    status, code = "invalid", 2
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--request", required=True, type=Path)
        parser.add_argument("--output", required=True, type=Path)
        args = parser.parse_args(argv)
        if os.name != "posix":
            raise ContractError(
                "Issue CLI no-follow storage is qualified only on POSIX"
            )
        raw, request = _request(args.request)
        owner = _reserve(args.output)
        _write(owner.descriptor, "request.original.json", raw)
        owner.verify()  # Every output ancestor is checked before any provider GET.
        report = collect(deepcopy(request), owner.path / "observations")
        validate_report(
            report, expected_request=request, output=owner.path / "observations"
        )
        status = report["status"]
        code = 0 if status == "complete" else 3
    except KeyboardInterrupt:
        status, code = "cancelled", 130
        diagnostics.append("Issue collection cancelled; partial artifacts are retained")
    except (CppulseError, OSError, ValueError, RuntimeError, TypeError) as exc:
        status, code = ("failed" if owner is not None else "invalid"), 2
        diagnostics.append(f"{type(exc).__name__}: {str(exc)[:2048]}")
    try:
        if owner is not None and request is not None:
            code, summary = _finish(
                owner, request, raw, report, status, code, diagnostics
            )
        else:
            summary = {
                "version": "1.0.0",
                "status": status,
                "exit_status": code,
                "output": None,
                "outcome_sha256": None,
            }
        print(json.dumps(summary, allow_nan=False))
        if diagnostics:
            print("cppulse issues: " + diagnostics[0][:1024], file=sys.stderr)
        return code
    except KeyboardInterrupt:
        summary = {
            "status": "cancelled",
            "exit_status": 130,
            "output": None if owner is None else str(owner.path),
            "reason": "Cancellation during finalization; owned artifacts retained",
        }
        if owner is not None and request is not None:
            try:
                summary = _cancelled_finalization(owner, request, raw)
            except (CppulseError, OSError, ValueError, RuntimeError, TypeError):
                summary["reason"] = (
                    "Cancellation outcome could not be fully written; existing artifacts are retained"
                )
        print(json.dumps(summary))
        return 130
    except (CppulseError, OSError, ValueError, RuntimeError, TypeError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "exit_status": 2,
                    "output": None if owner is None else str(owner.path),
                    "reason": f"Outcome publication failed: {type(exc).__name__}",
                }
            )
        )
        print(
            f"cppulse issues: outcome publication failed: {str(exc)[:1024]}",
            file=sys.stderr,
        )
        return 2
    finally:
        if owner is not None:
            os.close(owner.descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
