"""Private frozen-filesystem prerequisites; never cache closure authority."""

from __future__ import annotations

from importlib import resources
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

import jsonschema

from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes


# These private identities retain exact integer counts and nanosecond metadata.
# Integral floats accepted by generic JSON Schema cannot authorize PAX strings.
_EXACT_INTEGER_VALIDATOR = jsonschema.validators.extend(
    jsonschema.Draft7Validator,
    type_checker=jsonschema.Draft7Validator.TYPE_CHECKER.redefine(
        "integer",
        lambda _checker, value: isinstance(value, int) and not isinstance(value, bool),
    ),
)


def load_frozen_input(kind: str, raw: bytes) -> dict[str, Any]:
    """Read bounded UTF-8 JSON and reject duplicate keys before validation."""

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate frozen input key")
            result[key] = value
        return result

    if not isinstance(raw, bytes) or len(raw) > 8 * 1024**2:
        raise ContractError("Frozen input JSON exceeds byte boundary")
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("Invalid frozen input JSON") from exc
    validate_frozen_input(kind, document)
    return document


def _path(value: str, *, absolute: bool) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("//")
        or "\x00" in value
        or ".." in path.parts
        or path.is_absolute() != absolute
        or str(path) != value
        or len(value.encode("utf-8")) > 4096
    ):
        raise ContractError("Noncanonical frozen input path")
    return path


def _invocation(document: dict[str, Any]) -> None:
    _path(document["cwd"], absolute=True)
    _path(document["argv"][0], absolute=True)
    values = list(document["argv"])
    for key, value in document["environment"].items():
        if any(
            token in key.upper()
            for token in (
                "TOKEN",
                "SECRET",
                "PASSWORD",
                "CREDENTIAL",
                "AUTH",
                "PRIVATE_KEY",
            )
        ):
            raise ContractError("Sensitive environment unsupported")
        values.append(key + "=" + value)
    if any("\x00" in value or len(value.encode("utf-8")) > 4096 for value in values):
        raise ContractError("Invalid invocation byte strings")


def validate_frozen_input(kind: str, document: dict[str, Any]) -> None:
    """Validate one bounded private document without executing or reading inputs."""
    if kind not in {"request", "manifest", "report", "capture", "archive"}:
        raise ContractError("Unknown frozen input contract")
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas/frozen_input_private", kind + ".schema.json")
        .read_bytes()
    )
    try:
        _EXACT_INTEGER_VALIDATOR(schema).validate(document)
        if len(canonical_json_bytes(document)) > 8 * 1024**2:
            raise ValueError("Frozen input document exceeds byte limit")
        if kind == "request":
            _invocation(document["invocation"])
            _path(document["client"]["path"], absolute=True)
            mappings = document["path_map"]
            if not mappings:
                raise ValueError("Missing selected input namespace")
            roots: list[PurePosixPath] = []
            sources: set[str] = set()
            for mapping in mappings:
                _path(mapping["source_root"], absolute=True)
                root = _path(mapping["container_root"], absolute=True)
                if (
                    root == PurePosixPath("/")
                    or any(
                        root == other or root in other.parents or other in root.parents
                        for other in roots
                    )
                    or mapping["source_root"] in sources
                ):
                    raise ValueError("Ambiguous selected input roots")
                roots.append(root)
                sources.add(mapping["source_root"])
        elif kind in {"manifest", "capture", "archive"}:
            seen: set[str] = set()
            entries = document["entries"]
            if not entries or [row["path"] for row in entries] != sorted(
                row["path"] for row in entries
            ):
                raise ValueError("Manifest must be nonempty and sorted")
            kinds: dict[str, str] = {}
            for row in entries:
                path = _path(row["path"], absolute=True)
                if kind != "archive":
                    _path(row["source_root"], absolute=True)
                    _path(row["source_relative"], absolute=False)
                if row["path"] in seen:
                    raise ValueError("Duplicate namespace entry")
                if any(
                    kinds.get(str(parent)) in {"regular", "symlink"}
                    for parent in path.parents
                ):
                    raise ValueError("Entry descends through a nondirectory")
                if row["kind"] == "regular":
                    if row["content"] is None or row.get("target") is not None:
                        raise ValueError("Regular entry needs only content")
                elif row["kind"] == "directory":
                    if row["content"] is not None or row.get("target") is not None:
                        raise ValueError("Directory has no content or target")
                else:
                    if row["content"] is not None or row["target"] is None:
                        raise ValueError("Symlink needs only target")
                    _path(row["target"], absolute=False)
                seen.add(row["path"])
                kinds[row["path"]] = row["kind"]
        elif document["native_receipt"] is not None:
            _invocation(document["native_receipt"]["invocation"])
    except (
        jsonschema.ValidationError,
        ValueError,
        TypeError,
        RecursionError,
        UnicodeError,
    ) as exc:
        raise ContractError("Invalid frozen input " + kind) from exc


def validate_frozen_bundle(
    request: dict[str, Any],
    manifest: dict[str, Any],
    report: dict[str, Any] | None = None,
) -> None:
    """Check identities and source mappings without claiming observed execution."""
    validate_frozen_input("request", request)
    validate_frozen_input("manifest", manifest)
    request_sha = hashlib.sha256(canonical_json_bytes(request)).hexdigest()
    if manifest["request_sha256"] != request_sha:
        raise ContractError("Frozen manifest changes original request")
    roots = {
        row["source_root"]: PurePosixPath(row["container_root"])
        for row in request["path_map"]
    }
    entries = {row["path"]: row for row in manifest["entries"]}
    if len(entries) > request["limits"]["max_entries"]:
        raise ContractError("Frozen namespace exceeds selected entry budget")
    total = 0
    for row in entries.values():
        root = roots.get(row["source_root"])
        if root is None or str(root / row["source_relative"]) != row["path"]:
            raise ContractError("Frozen entry changes selected source mapping")
        if row["content"] is not None:
            total += row["content"]["size_bytes"]
        for parent in PurePosixPath(row["path"]).parents:
            if parent == root.parent:
                break
            if (
                str(parent) not in entries
                or entries[str(parent)]["kind"] != "directory"
            ):
                raise ContractError("Frozen namespace omits an ancestor directory")
        if row["kind"] == "symlink":
            target = str(PurePosixPath(row["path"]).parent / row["target"])
            if target not in entries:
                raise ContractError("Frozen symlink target is not retained")
    if total > request["limits"]["max_payload_bytes"]:
        raise ContractError("Frozen payload exceeds selected byte budget")
    native = entries.get(request["invocation"]["argv"][0])
    if (
        native is None
        or native["kind"] != "regular"
        or native["content"] != request["native"]
    ):
        raise ContractError("Frozen native executable is not the selected bytes")
    if report is not None:
        validate_frozen_input("report", report)
        if (
            report["request_sha256"] != request_sha
            or report["manifest_sha256"]
            != hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
        ):
            raise ContractError("Frozen report changes selected request or namespace")
        for receipt in report["client_receipts"]:
            if receipt["argv"][0] != request["client"]["path"]:
                raise ContractError("Container client receipt changes selected client")
        if (
            report["native_receipt"] is not None
            and report["native_receipt"]["invocation"] != request["invocation"]
        ):
            raise ContractError("Inside native receipt changes selected invocation")
        if report["frozen_filesystem_observed"] and (
            report["native_receipt"] is None or not report["client_receipts"]
        ):
            raise ContractError(
                "Filesystem observation needs actual receipt references"
            )
