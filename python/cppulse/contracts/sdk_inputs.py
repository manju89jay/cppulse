"""Bind actual SDK buffers to retained original SDK inventory and native bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes


def sdk_targets(
    report: dict[str, Any], root: str
) -> dict[str, list[dict[str, Any] | None]]:
    """Select actual include edges strictly within an absolute canonical SDK root."""
    result: dict[str, list[dict[str, Any] | None]] = {}
    metrics: Any = report
    for key in ("metadata", "analysis", "native_metrics"):
        metrics = metrics.get(key) if isinstance(metrics, dict) else None
    if not isinstance(metrics, dict):
        return result
    for row in metrics.get("files", []):
        if not isinstance(row, dict):
            continue
        includes = row.get("includes", [])
        if not isinstance(includes, list):
            continue
        for edge in includes:
            if not isinstance(edge, dict) or not isinstance(edge.get("target"), str):
                continue
            target = PurePosixPath(edge["target"])
            try:
                relative = target.relative_to(root).as_posix()
            except ValueError:
                continue
            if not relative or ".." in PurePosixPath(relative).parts:
                raise ContractError("SDK include target is not canonical")
            result.setdefault(relative, []).append(edge.get("content_identity"))
    return result


def validate_used_sdk_inputs(document: dict[str, Any]) -> None:
    """Check exact original byte linkage without reading the live filesystem."""
    from cppulse.contracts import validate
    from cppulse.work_units import _check

    if len(canonical_json_bytes(document)) > 64 * 1024**2:
        raise ContractError("Used SDK proof exceeds its finite byte budget")
    resources = {}
    for record in document["resource_inventories"]:
        raw = record["raw_json"].encode("utf-8")
        if (
            hashlib.sha256(raw).hexdigest() != record["sha256"]
            or record["sha256"] in resources
        ):
            raise ContractError("Original SDK inventory bytes are changed or duplicate")
        value = json.loads(raw)
        _check("resource_inputs", value)
        validate("source", value["source"])
        root = PurePosixPath(value["root"])
        if not root.is_absolute() or ".." in root.parts or str(root) != value["root"]:
            raise ContractError("Retained SDK root is not canonical")
        resources[record["sha256"]] = value
    identifiers = [unit["unit_id"] for unit in document["units"]]
    if identifiers != sorted(set(identifiers)):
        raise ContractError("SDK unit ownership must be sorted and unique")
    for unit in document["units"]:
        raw = unit["report_json"].encode("utf-8")
        if hashlib.sha256(raw).hexdigest() != unit["report_sha256"]:
            raise ContractError("Used SDK proof changes original native report bytes")
        resource = resources.get(unit["resource_manifest_sha256"])
        if resource is None or resource["root"] != unit["root"]:
            raise ContractError(
                "Used SDK proof lacks its exact original resource inventory"
            )
        targets = sdk_targets(json.loads(raw), unit["root"])
        entries = {row["path"]: row for row in unit["entries"]}
        if len(entries) != len(unit["entries"]) or set(entries) != set(targets):
            raise ContractError(
                "Used SDK proof omits or duplicates actual SDK include edges"
            )
        files = {row["path"]: row for row in resource["source"]["files"]}
        for path, row in entries.items():
            if row["target"] != unit["root"].rstrip("/") + "/" + path:
                raise ContractError("Used SDK target escapes its original root")
            if row["status"] != "available":
                if not row["reason"] or any(
                    row[key] is not None
                    for key in ("artifact_id", "sha256", "size_bytes")
                ):
                    raise ContractError(
                        "Unknown SDK input must not invent retained bytes"
                    )
                continue
            fact = files.get(path)
            if (
                fact is None
                or row["artifact_id"] != "sdk-buffer-" + row["sha256"]
                or any(fact[key] != row[key] for key in ("sha256", "size_bytes"))
                or any(
                    not isinstance(identity, dict)
                    or identity.get("status") != "available"
                    or identity.get("method") != "libclang-tu-buffer-sha256-v1"
                    or any(
                        identity.get(key) != row[key]
                        for key in ("sha256", "size_bytes")
                    )
                    for identity in targets[path]
                )
            ):
                raise ContractError(
                    "SDK bytes differ from actual TU/original SDK inventory"
                )


def validate_sdk_bundle(
    flat: list[tuple[str, dict[str, Any]]], manifest: dict[str, Any]
) -> None:
    """Check retained descriptors and original work-unit links for SDK proofs."""
    from cppulse.contracts import validate
    from cppulse.identities import digest_json

    documents = [doc for kind, doc in flat if kind == "used_sdk_inputs"]
    if len(documents) > 1:
        raise ContractError("Ambiguous used SDK input proof")
    if not documents:
        if any(
            kind == "work_unit_analysis_binding"
            and doc.get("sdk_used_inputs_artifact_id") is not None
            for kind, doc in flat
        ):
            raise ContractError(
                "SDK-linked work unit lacks its typed retained SDK proof"
            )
        return
    document = documents[0]
    if document["source_digest"] != manifest["source"]["digest"]:
        raise ContractError("SDK proof identifies another selected source")
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    buffers = [row for row in artifacts.values() if row["id"].startswith("sdk-buffer-")]
    if (
        sum(row["size_bytes"] for row in buffers) != document["captured_bytes"]
        or document["captured_bytes"] > 64 * 1024**2
        or any(row["size_bytes"] > 8 * 1024**2 for row in buffers)
    ):
        raise ContractError(
            "Retained SDK byte accounting exceeds or differs from its finite budget"
        )
    units = {row["unit_id"]: row for row in document["units"]}
    for unit in units.values():
        report = artifacts.get(unit["report_artifact_id"])
        if report is None or report["sha256"] != unit["report_sha256"]:
            raise ContractError("SDK proof lacks original report bytes")
        if not any(
            row["sha256"] == unit["resource_manifest_sha256"]
            for row in artifacts.values()
        ):
            raise ContractError("SDK proof lacks original resource inventory artifact")
        for entry in unit["entries"]:
            if entry["status"] != "available":
                continue
            artifact = artifacts.get(entry["artifact_id"])
            if (
                artifact is None
                or any(artifact[key] != entry[key] for key in ("sha256", "size_bytes"))
                or artifact["media_type"] != "application/octet-stream"
            ):
                raise ContractError(
                    "SDK buffer descriptor differs from actual retained proof"
                )
    inventories = {doc["id"]: doc for kind, doc in flat if kind == "analysis_inventory"}
    for kind, binding in flat:
        if kind != "work_unit_analysis_binding":
            continue
        unit = units.get(binding["unit_id"])
        inventory = inventories.get(binding["analysis_inventory_id"])
        if inventory is None:
            raise ContractError("SDK-linked work unit lacks its analysis inventory")
        qualified = any(
            row.get("buffer_coherence") == "verified" for row in inventory["items"]
        )
        if (
            unit is not None
            and unit["entries"]
            and qualified
            and binding.get("sdk_used_inputs_artifact_id") is None
        ):
            raise ContractError("Qualified SDK parse omits its retained SDK proof role")
        if binding.get("sdk_used_inputs_artifact_id") is None:
            continue
        descriptor = artifacts.get(binding["sdk_used_inputs_artifact_id"])
        request = binding["request"]
        if (
            descriptor is None
            or descriptor.get("contract", {}).get("kind") != "used_sdk_inputs"
            or unit is None
            or unit["request_sha256"] != digest_json(request)
        ):
            raise ContractError(
                "Bounded SDK qualification lacks original request/proof linkage"
            )
        resource = request["inputs"]["resource_manifest"]
        if (
            resource is None
            or resource["sha256"] != unit["resource_manifest_sha256"]
            or inventory["report_artifact_id"] != unit["report_artifact_id"]
        ):
            raise ContractError(
                "Bounded SDK proof changes original resource/report role"
            )
        validate("findings", json.loads(unit["report_json"]), version="prototype_v1")
        if qualified and any(
            entry["status"] != "available" for entry in unit["entries"]
        ):
            raise ContractError(
                "Qualified SDK parse has an unavailable actual SDK buffer"
            )
