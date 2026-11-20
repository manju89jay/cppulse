"""Finite ELF/DWARF comparisons with an explicit, hash-pinned libabigail 2.6 tool.

This adapter runs the selected analysis tool, never the analyzed libraries.
Its local integrity receipts do not authenticate source or certify compatibility.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
from importlib import resources
import json
import math
import os
import re
from pathlib import Path
import selectors
import signal
import stat
import struct
import subprocess
import sys
import time
from typing import Any

import jsonschema

from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes

MAX_REQUEST_BYTES = 1024 * 1024
MAX_LIBRARY_BYTES = 512 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 512 * 1024 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate(document: dict[str, Any], name: str) -> None:
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas", "abi_private", name + ".schema.json")
        .read_bytes()
    )
    try:
        jsonschema.Draft7Validator(schema).validate(document)
        canonical_json_bytes(document)
    except (jsonschema.ValidationError, ValueError, TypeError, OverflowError) as exc:
        raise ContractError(f"Invalid ABI {name}: {exc}") from exc


def validate_request(document: dict[str, Any]) -> None:
    """Validate a finite explicit tool, limits and uniquely named comparison pairs."""
    _validate(document, "request")
    if len(canonical_json_bytes(document)) > MAX_REQUEST_BYTES:
        raise ContractError("ABI request exceeds byte bound")
    if not math.isfinite(document["limits"]["wall_seconds"]):
        raise ContractError("ABI wall limit must be finite")
    ids = [pair["id"] for pair in document["pairs"]]
    if len(set(ids)) != len(ids):
        raise ContractError("Duplicate ABI pair IDs")
    for entry in [
        document["tool"],
        document["reader"],
        *[pair[key] for pair in document["pairs"] for key in ("old", "new")],
    ]:
        if any(
            ord(character) < 32 or ord(character) == 127 for character in entry["path"]
        ):
            raise ContractError("ABI paths must not contain control characters")
        if not Path(entry["path"]).is_absolute():
            raise ContractError("ABI tool and input paths must be absolute")
    library_directory = document["tool"]["library_directory"]
    if library_directory is not None and any(
        ord(character) < 32 or ord(character) == 127 for character in library_directory
    ):
        raise ContractError("ABI paths must not contain control characters")
    if library_directory is not None and not Path(library_directory).is_absolute():
        raise ContractError("ABI library directory must be absolute")


def _finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _dwarf_valid(outcome: dict[str, Any]) -> bool:
    if (
        outcome["returncode"] != 0
        or outcome["timed_out"]
        or outcome["log_truncated"]
        or "Warning:" in outcome["log"]
        or "Error:" in outcome["log"]
    ):
        return False
    # An unused abbreviation may name a compile-unit tag even when all actual
    # DIEs are null. Check each actual info CU block, never the abbrev table.
    info = outcome["log"].split("Contents of the .debug_abbrev section:", 1)[0]
    units = re.split(r"(?m)^[ \t]*Compilation Unit @ offset [^\n]+:[ \t]*$", info)
    if len(units) < 2:
        return False
    root_pattern = r"(?m)^[ \t]*<0><[0-9a-f]+>:[ \t]+Abbrev Number:[ \t]+[1-9][0-9]*[ \t]+\(DW_TAG_compile_unit\)[ \t]*$"
    all_roots_pattern = r"(?m)^[ \t]*<0><[0-9a-f]+>:.*$"
    return all(
        len(re.findall(root_pattern, unit)) == 1
        and len(re.findall(all_roots_pattern, unit)) == 1
        for unit in units[1:]
    )


def validate_report(
    document: dict[str, Any], *, expected_request: dict[str, Any] | None = None
) -> None:
    """Validate structural and cross-field status consistency of a private receipt."""
    _validate(document, "report")
    ids = [result["id"] for result in document["results"]]
    if len(set(ids)) != len(ids):
        raise ContractError("Duplicate ABI result IDs")
    if (
        sum(
            result[key]["bytes"]
            for result in document["results"]
            for key in ("old", "new")
        )
        > MAX_TOTAL_INPUT_BYTES
    ):
        raise ContractError(
            "ABI aggregate input receipts exceed the producer byte bound"
        )
    libraries = document["tool"]["libraries"]
    library_paths = [Path(row["path"]) for row in libraries]
    if (
        len(set(library_paths)) != len(library_paths)
        or sum(row["bytes"] for row in libraries) > MAX_LIBRARY_BYTES
        or any(
            not path.is_absolute()
            or not path.match("*.so*")
            or any(ord(char) < 32 or ord(char) == 127 for char in row["path"])
            or re.fullmatch(r"[a-f0-9]{64}", row["sha256"]) is None
            for path, row in zip(library_paths, libraries)
        )
    ):
        raise ContractError(
            "ABI library inventory has invalid identities or byte bounds"
        )
    if expected_request is not None:
        validate_request(expected_request)
        if document["request_sha256"] != _sha(canonical_json_bytes(expected_request)):
            raise ContractError("ABI request digest does not match expected request")
        if document["limits"] != expected_request["limits"]:
            raise ContractError("ABI report limits differ from expected request")
        selected_directory = expected_request["tool"]["library_directory"]
        if (selected_directory is None and libraries) or (
            selected_directory is not None
            and any(path.parent != Path(selected_directory) for path in library_paths)
        ):
            raise ContractError("ABI library inventory differs from selected directory")
        for producer in ("tool", "reader"):
            for key in ("path", "sha256", "version"):
                if document[producer][key] != expected_request[producer][key]:
                    raise ContractError("ABI tool does not match expected request")
        if ids != [pair["id"] for pair in expected_request["pairs"]]:
            raise ContractError("ABI results do not match expected request pairs")
        for result, pair in zip(document["results"], expected_request["pairs"]):
            for key in ("old", "new"):
                if any(
                    result[key][field] != pair[key][field]
                    for field in ("path", "sha256")
                ):
                    raise ContractError(
                        "ABI input receipt does not match expected request"
                    )
    complete = True
    codes = {
        "no_changes_reported": 0,
        "changes_reported": 4,
        "incompatible_changes_reported": 12,
    }
    for result in document["results"]:
        if not _finite(result["elapsed_seconds"]):
            raise ContractError("Nonfinite ABI elapsed time")
        if _sha(result["log"].encode()) != result["log_sha256"]:
            raise ContractError("ABI log digest mismatch")
        if len(result["log"].encode()) > document["limits"]["log_bytes"]:
            raise ContractError("ABI log exceeds bound")
        if any(
            result[key]["bytes"] > document["limits"]["input_bytes"]
            for key in ("old", "new")
        ):
            raise ContractError("ABI input receipt exceeds declared bound")
        used_log_bytes = len(result["log"].encode())
        preflight_ids = [stage["input"] for stage in result["preflight"]]
        if preflight_ids not in ([], ["old"], ["old", "new"]):
            raise ContractError("ABI preflight order or identities are inconsistent")
        for stage in result["preflight"]:
            used_log_bytes += len(stage["log"].encode())
            if _sha(stage["log"].encode()) != stage["log_sha256"]:
                raise ContractError("ABI preflight log digest mismatch")
            if not _finite(stage["elapsed_seconds"]):
                raise ContractError("Nonfinite ABI preflight elapsed time")
            if stage["status"] == "validated" and not _dwarf_valid(stage):
                raise ContractError("ABI preflight validation contradicts execution")
        if used_log_bytes > document["limits"]["log_bytes"]:
            raise ContractError("ABI combined logs exceed bound")
        if result["status"] in codes:
            if preflight_ids != ["old", "new"] or any(
                stage["status"] != "validated" for stage in result["preflight"]
            ):
                raise ContractError(
                    "ABI complete result requires both DWARF validations"
                )
            if result["reason"] != "complete_tool_exit_bits":
                raise ContractError("ABI complete status lacks complete tool reason")
            if (
                result["returncode"] != codes[result["status"]]
                or result["timed_out"]
                or result["log_truncated"]
            ):
                raise ContractError("ABI status contradicts execution outcome")
        else:
            complete = False
        if result["timed_out"] or result["log_truncated"]:
            if result["status"] != "unusable":
                raise ContractError(
                    "Incomplete ABI execution cannot report compatibility"
                )
    if document["status"] != ("reported" if complete else "incomplete"):
        raise ContractError("ABI aggregate status contradicts results")


def _read(path: Path, bound: int) -> bytes:
    try:
        # Nonblocking open also handles special-file rejection without hanging
        # on a FIFO before fstat can inspect its type.
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ContractError("ABI input must be a regular file")
            data = stream.read(bound + 1)
    except (OSError, ValueError) as exc:
        raise ContractError(f"Cannot read ABI file: {path}: {exc}") from exc
    if len(data) > bound:
        raise ContractError(f"ABI input exceeds byte bound: {path}")
    return data


def _pinned(entry: dict[str, Any], bound: int) -> bytes:
    data = _read(Path(entry["path"]), bound)
    if _sha(data) != entry["sha256"]:
        raise ContractError(f'ABI input hash mismatch: {entry["path"]}')
    return data


def _elf_scope(data: bytes) -> tuple[bool, str, int | None]:
    """Check bounded in-file ELF shared-object/DWARF scope before tool fast paths."""
    try:
        if data[:4] != b"\x7fELF" or data[4] not in (1, 2) or data[5] not in (1, 2):
            return False, "unsupported_elf_header", None
        endian = "<" if data[5] == 1 else ">"
        wide = data[4] == 2
        fmt = endian + ("HHIQQQIHHHHHH" if wide else "HHIIIIIHHHHHH")
        header = struct.unpack_from(fmt, data, 16)
        kind, machine = header[:2]
        if kind != 3:
            return False, "only_elf_shared_objects_supported", machine
        section_offset, section_size, section_count, names_index = (
            header[5],
            header[10],
            header[11],
            header[12],
        )
        section_fmt = endian + ("IIQQQQIIQQ" if wide else "IIIIIIIIII")
        minimum = struct.calcsize(section_fmt)
        # Extended section numbering and separate debug files are intentionally
        # unsupported until they have their own real-version qualification.
        if not section_count or section_size < minimum or names_index >= section_count:
            return False, "unsupported_section_table", machine
        if section_offset + section_size * section_count > len(data):
            return False, "malformed_section_table", machine
        sections = [
            struct.unpack_from(section_fmt, data, section_offset + index * section_size)
            for index in range(section_count)
        ]
        names_header = sections[names_index]
        names_offset, names_size = names_header[4:6]
        if names_offset + names_size > len(data):
            return False, "malformed_section_names", machine
        names = data[names_offset : names_offset + names_size]
        present = set()
        for section in sections:
            name_offset = section[0]
            if name_offset >= len(names):
                return False, "malformed_section_name", machine
            end = names.find(b"\0", name_offset)
            if end < 0:
                return False, "malformed_section_name", machine
            name = names[name_offset:end]
            if name in (b".debug_info", b".debug_abbrev"):
                offset, size = section[4:6]
                if not size or offset + size > len(data) or section[2] & 0x800:
                    return False, "unsupported_embedded_dwarf", machine
                present.add(name)
        if present != {b".debug_info", b".debug_abbrev"}:
            return False, "missing_embedded_dwarf", machine
        return True, "embedded_dwarf_present", machine
    except (IndexError, struct.error):
        return False, "malformed_elf", None


def _capture(
    command: list[str], env: dict[str, str], cwd: Path, wall: float, log_limit: int
) -> dict[str, Any]:
    start = time.monotonic()
    captured = bytearray()
    timed_out = truncated = False
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        return {
            "returncode": None,
            "log": str(exc)[:log_limit],
            "timed_out": False,
            "log_truncated": False,
            "elapsed_seconds": time.monotonic() - start,
        }
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while selector.get_map():
            remaining = wall - (time.monotonic() - start)
            if remaining <= 0:
                timed_out = True
                break
            events = selector.select(min(remaining, 0.05))
            for key, _ in events:
                block = os.read(key.fd, min(65536, log_limit + 1 - len(captured)))
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                captured.extend(block)
                if len(captured) > log_limit:
                    truncated = True
                    break
            if truncated:
                break
        if timed_out or truncated:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        # A process may close its output before it exits. Its remaining execution
        # still consumes the same wall deadline.
        try:
            process.wait(timeout=max(0.001, wall - (time.monotonic() - start)))
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    except BaseException:
        # Cancellation is not a compatibility outcome, but must still terminate
        # the complete owned process group before propagating to the caller.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        raise
    finally:
        selector.close()
        process.stdout.close()
    log = bytes(captured[:log_limit]).decode("utf-8", errors="replace")
    log = log.encode()[:log_limit].decode("utf-8", errors="ignore")
    return {
        "returncode": process.returncode,
        "log": log,
        "timed_out": timed_out,
        "log_truncated": truncated,
        "elapsed_seconds": time.monotonic() - start,
    }


def compare(document: dict[str, Any], output_root: Path) -> dict[str, Any]:
    """Run copied, pinned inputs and publish a new receipt; refuse stale material.

    Only Linux ELF shared-object DWARF input and libabigail 2.6.0 are qualified.
    The output directory must not exist. Failed preparation retains diagnostic
    files in that new directory but never publishes a stale positive report.
    """
    document = copy.deepcopy(document)
    validate_request(document)
    if sys.platform != "linux":
        raise ContractError("ABI adapter supports Linux ELF/DWARF only")
    limits = document["limits"]
    tool_bytes = _pinned(document["tool"], 64 * 1024 * 1024)
    reader_bytes = _pinned(document["reader"], 64 * 1024 * 1024)
    if not tool_bytes.startswith(b"\x7fELF") or not reader_bytes.startswith(b"\x7fELF"):
        raise ContractError("ABI tool must be the pinned native ELF executable")
    try:
        output_root.mkdir(parents=True, exist_ok=False, mode=0o700)
    except OSError as exc:
        raise ContractError(f"ABI output must be a new directory: {exc}") from exc
    staging = output_root / "inputs"
    staging.mkdir(mode=0o700)
    tool = staging / "abidiff"
    tool.write_bytes(tool_bytes)
    tool.chmod(0o500)
    reader = staging / "readelf"
    reader.write_bytes(reader_bytes)
    reader.chmod(0o500)
    staged_material = [
        (tool, document["tool"]["sha256"], 64 * 1024 * 1024),
        (reader, document["reader"]["sha256"], 64 * 1024 * 1024),
    ]
    library_receipts = []
    pinned_libraries: list[tuple[Path, str]] = []
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "HOME": str(staging.absolute()),
    }
    library_directory = document["tool"]["library_directory"]
    if library_directory is not None:
        directory = Path(library_directory)
        if not directory.is_dir():
            raise ContractError("ABI library directory does not exist")
        candidates = sorted(directory.glob("*.so*"))
        if len(candidates) > 1024:
            raise ContractError("ABI library inventory exceeds file bound")
        copied_libraries = staging / "libraries"
        copied_libraries.mkdir(mode=0o700)
        total = 0
        for path in candidates:
            data = _read(path, MAX_LIBRARY_BYTES - total)
            total += len(data)
            digest = _sha(data)
            (copied_libraries / path.name).write_bytes(data)
            staged_material.append(
                (copied_libraries / path.name, digest, MAX_LIBRARY_BYTES)
            )
            library_receipts.append(
                {"path": str(path), "sha256": digest, "bytes": len(data)}
            )
            pinned_libraries.append((path, digest))
        env["LD_LIBRARY_PATH"] = str(copied_libraries.absolute())
    version = _capture([str(tool.absolute()), "--version"], env, staging, 5, 4096)
    if (
        version["returncode"] != 0
        or version["timed_out"]
        or version["log_truncated"]
        or version["log"].strip().split(":")[-1].strip() != "2.6.0"
    ):
        raise ContractError("Pinned ABI tool does not report supported version 2.6.0")
    reader_version = _capture(
        [str(reader.absolute()), "--version"], env, staging, 5, 4096
    )
    if (
        reader_version["returncode"] != 0
        or reader_version["timed_out"]
        or reader_version["log_truncated"]
        or not reader_version["log"].splitlines()
        or reader_version["log"].splitlines()[0]
        != "GNU readelf (GNU Binutils for Debian) 2.44"
    ):
        raise ContractError(
            "Pinned DWARF reader does not report supported GNU readelf 2.44"
        )
    originals: list[dict[str, Any]] = []
    total_input_bytes = 0
    results = []
    for pair in document["pairs"]:
        blobs = {}
        paths = []
        scopes = []
        for key in ("old", "new"):
            entry = pair[key]
            data = _pinned(
                entry,
                min(limits["input_bytes"], MAX_TOTAL_INPUT_BYTES - total_input_bytes),
            )
            total_input_bytes += len(data)
            originals.append(entry)
            scopes.append(_elf_scope(data))
            target = staging / f'{pair["id"]}-{key}.so'
            target.write_bytes(data)
            target.chmod(0o400)
            staged_material.append((target, entry["sha256"], limits["input_bytes"]))
            paths.append(str(target.absolute()))
            blobs[key] = {**entry, "bytes": len(data)}
        supported = all(scope[0] for scope in scopes) and scopes[0][2] == scopes[1][2]
        preflight = []
        pair_start = time.monotonic()
        used_log_bytes = 0
        preflight_problem = None
        if supported:
            for key, path in zip(("old", "new"), paths):
                if used_log_bytes >= limits["log_bytes"]:
                    preflight_problem = "unusable"
                    break
                checked = _capture(
                    [
                        str(reader.absolute()),
                        "--debug-dump=info",
                        "--debug-dump=abbrev",
                        "--dwarf-check",
                        path,
                    ],
                    env,
                    staging,
                    limits["wall_seconds"] - (time.monotonic() - pair_start),
                    max(1, limits["log_bytes"] - used_log_bytes),
                )
                used_log_bytes += len(checked["log"].encode())
                invalid = not _dwarf_valid(checked)
                check_status = (
                    "unusable"
                    if checked["timed_out"] or checked["log_truncated"]
                    else "unsupported"
                    if invalid
                    else "validated"
                )
                preflight.append(
                    {
                        "input": key,
                        "status": check_status,
                        **checked,
                        "log_sha256": _sha(checked["log"].encode()),
                    }
                )
                if check_status != "validated":
                    preflight_problem = check_status
                    break
            if preflight_problem is None and used_log_bytes >= limits["log_bytes"]:
                preflight_problem = "unusable"
            if preflight_problem is None:
                outcome = _capture(
                    [
                        str(tool.absolute()),
                        "--no-default-suppression",
                        "--fail-no-debug-info",
                        *paths,
                    ],
                    env,
                    staging,
                    limits["wall_seconds"] - (time.monotonic() - pair_start),
                    limits["log_bytes"] - used_log_bytes,
                )
            else:
                outcome = {
                    "returncode": None,
                    "log": "",
                    "timed_out": any(stage["timed_out"] for stage in preflight),
                    "log_truncated": any(stage["log_truncated"] for stage in preflight)
                    or used_log_bytes >= limits["log_bytes"],
                    "elapsed_seconds": time.monotonic() - pair_start,
                }
        else:
            reason = next(
                (scope[1] for scope in scopes if not scope[0]), "elf_machine_mismatch"
            )
            outcome = {
                "returncode": None,
                "log": "",
                "timed_out": False,
                "log_truncated": False,
                "elapsed_seconds": 0.0,
            }
        if not supported:
            status = "unsupported"
        elif preflight_problem is not None:
            status, reason = preflight_problem, "dwarf_validation_incomplete"
        elif outcome["timed_out"]:
            status, reason = "unusable", "wall_limit_exceeded"
        elif outcome["log_truncated"]:
            status, reason = "unusable", "log_limit_exceeded"
        elif outcome["returncode"] in (0, 4, 12):
            status = {
                0: "no_changes_reported",
                4: "changes_reported",
                12: "incompatible_changes_reported",
            }[outcome["returncode"]]
            reason = "complete_tool_exit_bits"
        else:
            status, reason = "unsupported", "tool_error_or_missing_debug_information"
        outcome["elapsed_seconds"] = time.monotonic() - pair_start
        results.append(
            {
                "id": pair["id"],
                "status": status,
                "reason": reason,
                "preflight": preflight,
                **blobs,
                **outcome,
                "log_sha256": _sha(outcome["log"].encode()),
            }
        )
    # Verify the actual selected copies as well as originals. An unchanged
    # original does not make a mutated staged tool/input the selected bytes.
    for path, digest, bound in staged_material:
        try:
            _pinned({"path": str(path), "sha256": digest}, bound)
        except ContractError as error:
            raise ContractError(
                "ABI staged material changed during analysis"
            ) from error
    # Retain selected copies and reject observed original drift during
    # the comparison so an old observation cannot look current at publication.
    for entry in originals:
        _pinned(entry, limits["input_bytes"])
    _pinned(document["tool"], 64 * 1024 * 1024)
    _pinned(document["reader"], 64 * 1024 * 1024)
    for path, digest in pinned_libraries:
        if _sha(_read(path, MAX_LIBRARY_BYTES)) != digest:
            raise ContractError("ABI runtime library changed during analysis")
    report = {
        "version": "1.0.0",
        "method": "libabigail-2.6-elf-dwarf-v1",
        "request_sha256": _sha(canonical_json_bytes(document)),
        "tool": {
            "path": document["tool"]["path"],
            "sha256": document["tool"]["sha256"],
            "version": "2.6.0",
            "libraries": library_receipts,
        },
        "reader": dict(document["reader"]),
        "source_binding": "unverified",
        "status": (
            "reported"
            if all(
                r["status"]
                in (
                    "no_changes_reported",
                    "changes_reported",
                    "incompatible_changes_reported",
                )
                for r in results
            )
            else "incomplete"
        ),
        "limits": dict(limits),
        "enforced_limits": ["input_bytes", "wall_seconds", "log_bytes"],
        "results": results,
        "limitations": [
            "Linux ELF/DWARF libabigail 2.6.0 comparison only; API, performance, fuzzing and dependency evidence are outside this receipt.",
            "No changes reported means this tool found no changes in the available debug and exported ABI scope; it is not universal ABI compatibility certification.",
            "Binary and tool integrity hashes and producer versions are not authentication; source binding is unverified without compiler receipt lineage.",
            "Input size, wall time and captured log bytes are enforced; CPU and address-space limits are not enforced.",
            "Explicit local library inventory is copied and hashed; system loader and implicit system runtime dependencies are not authenticated or fully inventoried.",
            "The selected tool executes with local user permissions; this is not a security sandbox for a malicious tool or malformed input.",
            "Staged and original byte rechecks detect observed drift; staging is not immutable and hashes do not prove atomic tool/input identity throughout execution.",
        ],
    }
    validate_report(report, expected_request=document)
    temporary = output_root / "report.json.tmp"
    temporary.write_bytes(canonical_json_bytes(report) + b"\n")
    temporary.replace(output_root / "report.json")
    return report


def main(argv: list[str] | None = None) -> int:
    """Compare an explicit request into a new local output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = json.loads(_read(args.request, MAX_REQUEST_BYTES))
        report = compare(document, args.output)
        print(
            json.dumps(
                {"status": report["status"], "report": str(args.output / "report.json")}
            )
        )
        return 0 if report["status"] == "reported" else 3
    except (ContractError, ValueError, OSError) as exc:
        print(f"ABI comparison failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
