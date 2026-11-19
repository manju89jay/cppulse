"""Private runtime input declarations; no source reads, execution or closure proof."""
from pathlib import Path, PurePosixPath
import hashlib
import json
from typing import Any
import jsonschema
from cppulse.contracts.frozen_input import (
    _EXACT_INTEGER_VALIDATOR,
    validate_frozen_input,
)
from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes

_RESERVED = ("/proc", "/sys", "/dev", "/run")
_ENGINE_FILES = {"/etc/hosts", "/etc/hostname", "/etc/resolv.conf"}


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _absolute(value: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise ContractError("Runtime path must be a UTF-8 string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ContractError("Runtime path is not valid UTF-8") from error
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("//")
        or "\x00" in value
        or not path.is_absolute()
        or ".." in path.parts
        or str(path) != value
        or path == PurePosixPath("/")
        or len(encoded) > 4096
        or len(path.parts) > 65
    ):
        raise ContractError("Noncanonical runtime path")
    return path


def _destination(value: str) -> PurePosixPath:
    path = _absolute(value)
    if value in _ENGINE_FILES or any(
        path == PurePosixPath(p) or PurePosixPath(p) in path.parents for p in _RESERVED
    ):
        raise ContractError("Implicit dynamic mount cannot be frozen input")
    return path


def validate_runtime_manifest(document: dict[str, Any]) -> None:
    schema = json.loads(
        (
            Path(__file__).with_name("schemas")
            / "runtime_private"
            / "manifest.schema.json"
        ).read_bytes()
    )
    try:
        _EXACT_INTEGER_VALIDATOR(schema).validate(document)
        if len(canonical_json_bytes(document)) > 8 * 1024**2:
            raise ValueError("Runtime declaration exceeds byte boundary")
        rows = document["files"]
        paths = [row["container_path"] for row in rows]
        if paths != sorted(paths) or len(set(paths)) != len(paths):
            raise ValueError("Runtime destinations must be sorted and unique")
        native = [row for row in rows if row["role"] == "native"]
        loader = [row for row in rows if row["role"] == "loader_candidate"]
        if len(native) != 1 or len(loader) != 1:
            raise ValueError(
                "Exactly one declared native and loader candidate required"
            )
        if sum(row["role"] == "supervisor" for row in rows) > 1:
            raise ValueError("At most one declared runtime supervisor supported")
        if (
            native[0]["container_path"] != document["native_container_path"]
            or loader[0]["container_path"] != document["loader_candidate_path"]
        ):
            raise ValueError("Runtime role path changed")
        sources: dict[str, tuple[Any, ...]] = {}
        total = 0
        for row in rows:
            _absolute(row["source_path"])
            path = _destination(row["container_path"])
            if (
                row["content"]["size_bytes"] < 1
                or row["content"]["size_bytes"] > 256 * 1024**2
            ):
                raise ValueError(
                    "Runtime source exceeds supported single-file boundary"
                )
            if not row["mode"] & 0o400 or (
                row["role"] in {"native", "loader_candidate", "supervisor"}
                and not row["mode"] & 0o100
            ):
                raise ValueError(
                    "Declared runtime mode prevents normalized-user access"
                )
            identity = (
                row["content"]["sha256"],
                row["content"]["size_bytes"],
                row["mode"],
                row["mtime_ns"],
            )
            if (
                row["source_path"] in sources
                and sources[row["source_path"]] != identity
            ):
                raise ValueError("Conflicting declared aliases of one source")
            sources[row["source_path"]] = identity
            if any(str(parent) in paths for parent in path.parents):
                raise ValueError("Runtime file cannot be ancestor of another file")
            total += row["content"]["size_bytes"]
        if (
            len(rows) > document["limits"]["max_entries"]
            or total > document["limits"]["max_payload_bytes"]
        ):
            raise ValueError("Materialized runtime destinations exceed selected budget")
    except (
        jsonschema.ValidationError,
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise ContractError("Invalid declared runtime manifest") from error


def validate_namespace(
    document: dict[str, Any],
    captures: list[dict[str, Any]],
    directories: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check one combined destination trie; still no artifact/ELF verification."""
    validate_runtime_manifest(document)
    if not isinstance(captures, list) or not isinstance(directories, list):
        raise ContractError("Namespace components must be explicit arrays")
    if len(captures) > 16 or len(directories) > document["limits"]["max_entries"]:
        raise ContractError("Namespace component boundary exceeded")
    entries: dict[str, dict[str, Any]] = {}

    def put(
        path: str, kind: str, mode: int, mtime_ns: int, content: dict[str, Any] | None
    ) -> None:
        _destination(path)
        needed = 0o500 if kind == "directory" else 0o400
        if mode & needed != needed:
            raise ContractError(
                "Normalized user cannot access selected namespace entry"
            )
        if path in entries:
            raise ContractError(
                "Duplicate destination; implicit last-wins overlay forbidden"
            )
        if len(entries) >= document["limits"]["max_entries"]:
            raise ContractError("Combined namespace exceeds entry boundary")
        entries[path] = {
            "path": path,
            "kind": kind,
            "mode": mode,
            "mtime_ns": mtime_ns,
            "uid": 1000,
            "gid": 1000,
            "content": dict(content) if content is not None else None,
        }

    for row in document["files"]:
        put(
            row["container_path"],
            "regular",
            row["mode"],
            row["mtime_ns"],
            row["content"],
        )
    for capture in captures:
        validate_frozen_input("capture", capture)
        for row in capture["entries"]:
            if row["kind"] not in {"regular", "directory"}:
                raise ContractError("Unsupported captured namespace member")
            put(row["path"], row["kind"], row["mode"], row["mtime_ns"], row["content"])
    for row in directories:
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "mode", "mtime_ns", "uid", "gid", "origin"}
            or row["origin"] != "synthesized"
            or not isinstance(row["mode"], int)
            or isinstance(row["mode"], bool)
            or not 0 <= row["mode"] <= 511
            or row["mode"] & 0o500 != 0o500
            or not _integer(row["mtime_ns"])
            or row["mtime_ns"] != 0
            or not _integer(row["uid"])
            or row["uid"] != 1000
            or not _integer(row["gid"])
            or row["gid"] != 1000
        ):
            raise ContractError("Invalid explicit synthesized directory metadata")
        put(row["path"], "directory", row["mode"], row["mtime_ns"], None)
    for path in entries:
        for parent in PurePosixPath(path).parents:
            if parent == PurePosixPath("/"):
                break
            if (
                str(parent) not in entries
                or entries[str(parent)]["kind"] != "directory"
            ):
                raise ContractError("Namespace omits a parent or descends through file")
    payload = sum(
        row["content"]["size_bytes"] for row in entries.values() if row["content"]
    )
    if payload > document["limits"]["max_payload_bytes"]:
        raise ContractError("Combined namespace payload exceeds selected budget")
    normalized = [entries[key] for key in sorted(entries)]
    return {
        "cache_eligible": False,
        "closure": "unqualified",
        "payload_bytes": payload,
        "entry_count": len(normalized),
        "semantic_namespace_sha256": hashlib.sha256(
            canonical_json_bytes(normalized)
        ).hexdigest(),
        "entries": normalized,
    }


def validate_runtime_layer(document: dict[str, Any]) -> None:
    """Validate retained bytes and their semantic identity, never execution."""
    schema_path = (
        Path(__file__).with_name("schemas") / "runtime_private" / "layer.schema.json"
    )
    try:
        _EXACT_INTEGER_VALIDATOR(json.loads(schema_path.read_bytes())).validate(
            document
        )
        if len(canonical_json_bytes(document)) > 8 * 1024**2:
            raise ValueError("Runtime layer receipt exceeds byte boundary")
        validate_frozen_input("archive", document["archive"])
        ownership = document["archive"]["ownership"]
        normalized = [
            {**row, "uid": ownership["uid"], "gid": ownership["gid"]}
            for row in document["archive"]["entries"]
        ]
        expected = hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()
        if expected != document["semantic_namespace_sha256"]:
            raise ValueError("Runtime layer semantic identity differs from entries")
    except (
        jsonschema.ValidationError,
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise ContractError("Invalid retained runtime layer") from error
