"""Read-only, pinned MCP stdio access to retained cppulse results.

No tool executes project code or evaluates policy. Default tools are read-only;
explicit operator query-cache configuration adds a selected-artifact index tool
which writes only that separate cache. JSON-RPC is newline-framed MCP stdio.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from importlib import resources
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, BinaryIO

import jsonschema

from cppulse import __version__
from cppulse.errors import CppulseError, ContractError
from cppulse.contracts.frozen_input import _EXACT_INTEGER_VALIDATOR
from cppulse.presentation import build_snapshot_view
from cppulse.result_index import (
    build_result_index,
    make_index_request,
    read_source_manifest_metadata,
)
from cppulse.run_store import RunStore

PROTOCOL_VERSION = "2024-11-05"
MAX_REQUEST_BYTES = 65536
MAX_RESPONSE_BYTES = 524288
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
_PIN = {
    "run_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "manifest_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "assessment_artifact_id": {"type": "string", "minLength": 1, "maxLength": 256},
}
_PAGE = {
    "offset": {"type": "integer", "minimum": 0},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def tool_definitions(*, indexed: bool = False) -> list[dict[str, Any]]:
    """Return strict public schemas for the finite read-only tool set."""
    result = []
    descriptions = {
        "run_status": "Stored historical run status, source/context identities and limitations.",
        "health": "Stored health and exact assessment display; no recalculation or freshness claim.",
        "findings": "A bounded page of retained prototype findings, preserving every occurrence.",
        "hotspots": "A bounded page of stored experimental hotspots, without new ranking.",
        "policy_gaps": "A bounded page of shared presentation gaps, including required unknowns.",
        "artifact": "Read a bounded UTF-8 byte chunk by retained artifact ID and original hash.",
    }
    for name, description in descriptions.items():
        properties = dict(_PIN)
        required = ["run_id", "manifest_sha256"]
        if name in {"findings", "hotspots", "policy_gaps"}:
            properties.update(_PAGE)
        if name == "artifact":
            properties.update(
                {
                    "artifact_id": {"type": "string", "minLength": 1, "maxLength": 256},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 32768},
                }
            )
            required.append("artifact_id")
        result.append(
            {
                "name": name,
                "description": description,
                "inputSchema": _schema(properties, required),
            }
        )
    if indexed:
        result.append(
            {
                "name": "indexed_findings",
                "description": "A manifest-pinned prototype findings page; may build/reuse the operator-configured separate query cache. Selected artifact only, no native/source verification.",
                "inputSchema": _schema(
                    {
                        "run_id": {
                            "type": "string",
                            "pattern": r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
                            "maxLength": 64,
                        },
                        "manifest_sha256": {
                            "type": "string",
                            "pattern": r"^[a-f0-9]{64}$",
                            "maxLength": 64,
                        },
                        "artifact_id": {
                            "type": "string",
                            "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
                            "maxLength": 128,
                        },
                        "page": {"type": "integer", "minimum": 1, "maximum": 2**63 - 1},
                        "per_page": {"type": "integer", "minimum": 1, "maximum": 100},
                        **{
                            k: {"type": "string", "maxLength": 4096}
                            for k in ("category", "file", "text")
                        },
                    },
                    ["run_id", "manifest_sha256"],
                ),
            }
        )
    result.append(
        {
            "name": "documentation",
            "description": "Packaged rule metadata or a selected retained policy document; no network fetch.",
            "inputSchema": _schema(
                {
                    **_PIN,
                    "kind": {"enum": ["rule", "policy"]},
                    "id": {"type": "string", "minLength": 1, "maxLength": 256},
                },
                ["kind", "id"],
            ),
        }
    )
    return result


def _page(rows: list[Any], arguments: dict[str, Any]) -> dict[str, Any]:
    offset, limit = arguments.get("offset", 0), arguments.get("limit", 50)
    end = min(offset + limit, len(rows))
    return {
        "items": rows[offset:end],
        "total": len(rows),
        "next_offset": end if end < len(rows) else None,
    }


def _validated_query_limits(limits: Any) -> dict[str, Any]:
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas/result_index_private/request.schema.json")
        .read_bytes()
    )
    try:
        _EXACT_INTEGER_VALIDATOR(schema["properties"]["limits"]).validate(limits)
    except jsonschema.ValidationError as error:
        raise ContractError("Query limits violate the private index profile") from error
    return deepcopy(limits)


def _query_limits(raw: str) -> dict[str, Any]:
    """Parse an explicit small closed operator profile without cache actions."""

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("Duplicate query limit")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("Nonfinite query limit: " + value)

    try:
        if len(raw.encode("utf-8")) > 4096:
            raise ValueError("Query limits exceed4096bytes")
        document = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContractError("Invalid query limits JSON") from error
    return _validated_query_limits(document)


class Reader:
    """Serve one authorized existing store without creating writer state."""

    def __init__(
        self,
        root: Path,
        *,
        query_cache_root: Path | None = None,
        query_limits: dict[str, Any] | None = None,
    ) -> None:
        self.store = RunStore.open_existing(root)
        self._query_cache_root = (
            None
            if query_cache_root is None
            else Path(os.path.abspath(query_cache_root))
        )
        if (
            self._query_cache_root is not None
            and self._query_cache_root.is_relative_to(self.store.root)
        ):
            raise ContractError("MCP query cache must be outside the original store")
        if query_limits is not None and self._query_cache_root is None:
            raise ContractError("Query limits require an explicit query cache")
        self._query_limits = (
            None if query_limits is None else _validated_query_limits(query_limits)
        )

    def tools(self) -> list[dict[str, Any]]:
        """Advertise cache-writing functionality only after explicit opt-in."""
        return tool_definitions(indexed=self._query_cache_root is not None)

    def _indexed_findings(self, arguments: dict[str, Any]) -> dict[str, Any]:
        for key, pattern in (
            ("run_id", r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"),
            ("manifest_sha256", r"[a-f0-9]{64}"),
            ("artifact_id", r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"),
        ):
            if re.fullmatch(pattern, arguments.get(key, "findings")) is None:
                raise ContractError("Invalid canonical index identity")
        for key in ("category", "file", "text"):
            if key not in arguments:
                continue
            try:
                if (
                    "\x00" in arguments[key]
                    or len(arguments[key].encode("utf-8")) > 4096
                ):
                    raise ValueError("Filter byte budget exceeded")
            except (ValueError, UnicodeError) as error:
                raise ContractError("Invalid bounded index filter") from error
        page, per_page = arguments.get("page", 1), arguments.get("per_page", 50)
        if (page - 1) * per_page > 2**63 - 1:
            raise ContractError("Query offset exceeds finite index range")
        run_id, digest = arguments["run_id"], arguments["manifest_sha256"]
        manifest = read_source_manifest_metadata(self.store, run_id, digest)
        if manifest["status"] != "completed":
            raise ContractError("Cannot query an incomplete original attempt")
        request = make_index_request(
            self.store,
            run_id,
            digest,
            arguments.get("artifact_id", "findings"),
            limits=self._query_limits,
        )
        index = build_result_index(self.store, self._query_cache_root, request)
        result = index.page(
            page=page,
            per_page=per_page,
            category=arguments.get("category"),
            file=arguments.get("file"),
            text=arguments.get("text"),
            max_page_bytes=MAX_RESPONSE_BYTES // 4,
        )
        return {
            **result,
            "run_id": run_id,
            "manifest_sha256": digest,
            "selection": "historical-pinned",
            "current_source_verified": False,
        }

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate a tool request and return stored values under exact run pins."""
        definitions = {item["name"]: item for item in self.tools()}
        if name not in definitions:
            raise ContractError("Unknown or unavailable read-only tool")
        try:
            if name == "indexed_findings":
                _EXACT_INTEGER_VALIDATOR(definitions[name]["inputSchema"]).validate(
                    arguments
                )
            else:
                jsonschema.validate(arguments, definitions[name]["inputSchema"])
        except jsonschema.ValidationError as error:
            raise ContractError(
                "Tool arguments violate the advertised input schema"
            ) from error
        if name == "indexed_findings":
            return self._indexed_findings(arguments)
        if name == "documentation" and arguments["kind"] == "rule":
            from cppulse.tooling import load_rule_registry

            registry = load_rule_registry()
            matches = [r for r in registry["rules"] if r["id"] == arguments["id"]]
            if len(matches) != 1:
                raise ContractError("Unknown packaged rule ID")
            return {"document": matches[0], "origin": "packaged-rule-registry"}
        if not {"run_id", "manifest_sha256"} <= arguments.keys():
            raise ContractError(
                "Retained policy reads require both run and manifest pins"
            )
        snapshot = self.store.open_run(
            arguments["run_id"],
            manifest_sha256=arguments["manifest_sha256"],
            max_snapshot_bytes=MAX_SNAPSHOT_BYTES,
        )
        entries = snapshot.manifest["artifacts"]
        pin = {
            "run_id": snapshot.run_id,
            "manifest_sha256": snapshot.manifest_sha256,
            "selection": "historical-pinned",
            "current_source_verified": False,
        }
        if name in {"artifact", "documentation"}:
            identifier = arguments.get("artifact_id", arguments.get("id"))
            matches = [row for row in entries if row["id"] == identifier]
            if len(matches) != 1:
                raise ContractError("Unknown retained artifact ID")
            entry = matches[0]
            if name == "documentation":
                if entry.get("contract", {}).get("kind") != "policy":
                    raise ContractError("Selected artifact is not a retained policy")
                return {
                    **pin,
                    "document": snapshot.read_json(identifier),
                    "artifact_id": identifier,
                    "sha256": entry["sha256"],
                }
            raw = snapshot.read_bytes(identifier)
            offset, limit = arguments.get("offset", 0), arguments.get("limit", 16384)
            if offset > len(raw):
                raise ContractError("Artifact offset exceeds its byte length")
            chunk = raw[offset : offset + limit]
            try:
                content = chunk.decode("utf-8")
            except UnicodeError as error:
                raise ContractError(
                    "Chunk is not UTF-8; select boundaries between codepoints"
                ) from error
            return {
                **pin,
                "artifact_id": identifier,
                "sha256": entry["sha256"],
                "size_bytes": len(raw),
                "offset": offset,
                "text": content,
                "next_offset": (
                    offset + len(chunk) if offset + len(chunk) < len(raw) else None
                ),
            }
        view = build_snapshot_view(
            snapshot, assessment_artifact_id=arguments.get("assessment_artifact_id")
        )
        if name == "run_status":
            return {
                **pin,
                "run": view["run"],
                "configuration": view.get("configuration"),
                "contexts": view["contexts"],
                "stages": view["stages"],
                "limitations": view["limitations"],
            }
        if name == "health":
            risk = view["legacy"]["risk_scores"]
            return {
                **pin,
                "health": None if risk is None else risk["document"]["health_score"],
                "assessment": (
                    None
                    if view["assessment"] is None
                    else view["assessment"]["display"]
                ),
                "measured_health": [
                    {
                        "artifact_id": fact["artifact_id"],
                        "sha256": fact["sha256"],
                        "document": json.loads(fact["raw_json"]),
                    }
                    for fact in view["facts"]
                    if fact["kind"] == "maintenance_health"
                ],
                "limitations": view["limitations"],
            }
        if name == "policy_gaps":
            return {**pin, **_page(view["gaps"], arguments)}
        if name == "findings":
            observations = [
                fact for fact in view["facts"] if fact["kind"] == "observations"
            ]
            if observations:
                rows = [
                    row
                    for fact in observations
                    for row in json.loads(fact["raw_json"])["items"]
                ]
                return {
                    **pin,
                    **_page(rows, arguments),
                    "availability": "stored-observations",
                    "artifact_ids": [fact["artifact_id"] for fact in observations],
                    "limitations": view["limitations"],
                }
        slot = view["legacy"]["findings" if name == "findings" else "risk_scores"]
        rows = [] if slot is None else slot["document"][name]
        hotspot_metadata = {} if slot is None else slot["document"].get("metadata", {})
        return {
            **pin,
            **_page(rows, arguments),
            **(
                {
                    "method": hotspot_metadata.get(
                        "hotspot_method", "legacy-severity-proxy"
                    ),
                    "scope": hotspot_metadata.get("hotspot_scope"),
                }
                if name == "hotspots" and slot is not None
                else {}
            ),
            "availability": "unavailable" if slot is None else "stored-prototype",
            "limitations": view["limitations"],
        }


def _error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": message},
    }


def serve(reader: Reader, source: BinaryIO, target: BinaryIO) -> None:
    """Serve bounded newline-delimited MCP messages until the client closes."""
    initialized = False
    while line := source.readline(MAX_REQUEST_BYTES + 1):
        if len(line) > MAX_REQUEST_BYTES:
            while line and not line.endswith(b"\n"):
                line = source.readline(MAX_REQUEST_BYTES + 1)
            reply = _error(None, -32600, "Request exceeds 65536 bytes")
        else:
            try:
                request = json.loads(line)
            except (ValueError, UnicodeError, RecursionError):
                reply = _error(None, -32700, "Invalid JSON")
            else:
                if (
                    not isinstance(request, dict)
                    or request.get("jsonrpc") != "2.0"
                    or not isinstance(request.get("method"), str)
                    or not set(request) <= {"jsonrpc", "id", "method", "params"}
                    or (
                        "id" in request
                        and (
                            isinstance(request["id"], bool)
                            or not isinstance(request["id"], (str, int))
                        )
                    )
                ):
                    reply = _error(None, -32600, "Invalid JSON-RPC request")
                elif "id" not in request:
                    continue
                else:
                    identifier, method = request["id"], request["method"]
                    params = request.get("params", {})
                    reply = {"jsonrpc": "2.0", "id": identifier, "result": {}}
                    if method == "initialize":
                        if (
                            initialized
                            or not isinstance(params, dict)
                            or params.get("protocolVersion") != PROTOCOL_VERSION
                        ):
                            reply = _error(
                                identifier,
                                -32602,
                                "Unsupported protocol or repeated initialization",
                            )
                        else:
                            initialized = True
                            reply["result"] = {
                                "protocolVersion": PROTOCOL_VERSION,
                                "capabilities": {"tools": {"listChanged": False}},
                                "serverInfo": {
                                    "name": "cppulse-readonly",
                                    "version": __version__,
                                },
                            }
                    elif not initialized:
                        reply = _error(
                            identifier, -32002, "Initialize the MCP session first"
                        )
                    elif method == "ping":
                        pass
                    elif method == "tools/list":
                        reply["result"] = {"tools": reader.tools()}
                    elif method == "tools/call":
                        try:
                            if (
                                not isinstance(params, dict)
                                or set(params) != {"name", "arguments"}
                                or not isinstance(params["name"], str)
                            ):
                                raise ContractError(
                                    "tools/call requires name and arguments"
                                )
                            result = reader.call(params["name"], params["arguments"])
                            reply["result"] = {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps(
                                            result, ensure_ascii=False, allow_nan=False
                                        ),
                                    }
                                ]
                            }
                        except (CppulseError, OSError, ValueError) as error:
                            reply["result"] = {
                                "isError": True,
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps(
                                            {
                                                "code": getattr(
                                                    error, "code", "READ_ERROR"
                                                ),
                                                "message": str(error),
                                            }
                                        ),
                                    }
                                ],
                            }
                    else:
                        reply = _error(identifier, -32601, "Method not found")
        encoded = json.dumps(reply, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_RESPONSE_BYTES:
            encoded = json.dumps(
                _error(
                    reply["id"],
                    -32001,
                    "Response exceeds finite preview limit; select a smaller page/chunk",
                )
            ).encode()
        target.write(encoded + b"\n")
        target.flush()


def main() -> int:
    """Start an explicit local read-only stdio server for an existing store."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument(
        "--query-cache",
        type=Path,
        help="Explicit separate cache enabling indexed_findings; never original-store writes",
    )
    parser.add_argument(
        "--query-limits",
        help="Complete private index limits JSON, at most4096UTF-8bytes",
    )
    arguments = parser.parse_args()
    try:
        serve(
            Reader(
                arguments.store,
                query_cache_root=arguments.query_cache,
                query_limits=(
                    None
                    if arguments.query_limits is None
                    else _query_limits(arguments.query_limits)
                ),
            ),
            sys.stdin.buffer,
            sys.stdout.buffer,
        )
    except (CppulseError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
