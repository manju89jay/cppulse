"""Retain actual used builtin SDK bytes separately from project source identity."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from cppulse.errors import IntegrityError
from cppulse.identities import digest_json
from cppulse.run_store import _check_file, _json_bytes, _read
from cppulse.work_units import _check
from cppulse.contracts import validate

MAX_USED_SDK_BYTES = 64 * 1024 * 1024
MAX_SDK_FILE_BYTES = 8 * 1024 * 1024
MAX_SDK_PROOF_BYTES = 64 * 1024 * 1024


def _proof_array_addition(row: dict[str, Any], *, first: bool) -> int:
    """Bytes added to a root-level array by the store's existing JSON encoder."""
    raw = _json_bytes(row)
    # The root array's rows start at four spaces. The encoder escapes literal
    # newlines inside values, so these are precisely its structural lines.
    indented = len(raw) - 1 + 4 * raw.count(b"\n")
    return indented + (4 if first else 2)


def retain_used_sdk_inputs(stage: Any, execution: Any) -> dict[str, Any]:
    """Capture finite actual TU SDK buffers, preserving unknown/mismatch outcomes.

    The enclosing publisher still checks the entire original SDK inventory
    before and after publication. This capture does not qualify an execution or
    implement dependency closure. Consumers must check the retained linkage.
    """
    units = []
    inventories: dict[str, dict[str, str]] = {}
    document = {
        "version": "2.0.0",
        "id": "sdk-used-inputs",
        "resource_inventories": [],
        "source_digest": execution.source["digest"],
        "max_file_bytes": MAX_SDK_FILE_BYTES,
        "max_total_bytes": MAX_USED_SDK_BYTES,
        # Capture may grow even when a later unit cannot fit. Reserve only the
        # actual wire width of its existing maximum, avoiding late digit growth.
        "captured_bytes": MAX_USED_SDK_BYTES,
        "units": [],
    }
    proof_size = len(_json_bytes(document))
    captured: dict[str, str] = {}
    total = 0
    for request, result in execution.results:
        if result.get("outcome") not in {"complete", "partial"}:
            continue
        root = Path(request["work_root"])
        resource_record = request["inputs"]["resource_manifest"]
        if resource_record is None:
            continue
        resource_bytes = _read(
            root / resource_record["path"],
            max_bytes=request["limits"]["max_artifact_bytes"],
        )
        if hashlib.sha256(resource_bytes).hexdigest() != resource_record["sha256"]:
            raise IntegrityError("Original SDK inventory changed before byte capture")
        resources = json.loads(resource_bytes)
        _check("resource_inputs", resources)
        validate("source", resources["source"])
        resource_root = Path(resources["root"])
        if not resource_root.is_absolute() or str(resource_root) != str(
            resource_root.resolve()
        ):
            raise IntegrityError("SDK resource root must remain absolute and canonical")
        reports = [
            row for row in result["artifacts"] if row["path"] == "output/findings.json"
        ]
        if len(reports) != 1:
            continue
        report_record = reports[0]
        # The legacy proof embeds the entire report as a JSON string. Even its
        # unescaped bytes cannot fit when this lower bound exceeds the cap.
        # Check the original artifact fully before declining capture: a budget
        # limit must never hide corruption, replacement or a changed size.
        if report_record.get("size_bytes", 0) > MAX_SDK_PROOF_BYTES:
            _check_file(
                root / report_record["path"],
                report_record,
                max_bytes=request["limits"]["max_artifact_bytes"],
            )
            continue
        raw = _read(
            root / report_record["path"],
            max_bytes=request["limits"]["max_artifact_bytes"],
        )
        if hashlib.sha256(raw).hexdigest() != report_record["sha256"]:
            raise IntegrityError("Native report changed before SDK byte capture")
        try:
            report = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            continue
        if not isinstance(report, dict):
            continue
        sdk_root = Path(resources["root"])
        expected = {row["path"]: row for row in resources["source"]["files"]}
        targets: dict[str, list[Any]] = {}
        metrics: Any = report
        for key in ("metadata", "analysis", "native_metrics"):
            metrics = metrics.get(key) if isinstance(metrics, dict) else None
        if not isinstance(metrics, dict) or not isinstance(metrics.get("files"), list):
            continue
        for native in metrics["files"]:
            if not isinstance(native, dict) or not isinstance(
                native.get("includes"), list
            ):
                continue
            for edge in native["includes"]:
                if not isinstance(edge, dict):
                    continue
                target = edge.get("target")
                if not isinstance(target, str):
                    continue
                path = Path(target)
                if not path.is_absolute():
                    continue
                try:
                    relative = path.relative_to(sdk_root).as_posix()
                except ValueError:
                    continue
                targets.setdefault(relative, []).append(edge.get("content_identity"))
        entries = []
        for relative, identities in sorted(targets.items()):
            entry = {
                "path": relative,
                "target": str(sdk_root / relative),
                "status": "unavailable",
                "artifact_id": None,
                "sha256": None,
                "size_bytes": None,
                "reason": "",
            }
            fact = expected.get(relative)
            if fact is None or any(
                not isinstance(identity, dict)
                or identity.get("status") != "available"
                or identity.get("method") != "libclang-tu-buffer-sha256-v1"
                for identity in identities
            ):
                entry["reason"] = (
                    "Used SDK buffer lacks original inventory or actual TU identity."
                )
            elif any(
                identity.get(key) != fact[key]
                for identity in identities
                for key in ("sha256", "size_bytes")
            ):
                entry["status"] = "mismatched"
                entry["reason"] = (
                    "Actual SDK TU buffer differs from original SDK inventory."
                )
            elif fact["size_bytes"] > MAX_SDK_FILE_BYTES or (
                fact["sha256"] not in captured
                and total + fact["size_bytes"] > MAX_USED_SDK_BYTES
            ):
                entry["reason"] = "Finite used-SDK byte capture budget exceeded."
            else:
                try:
                    content = _read(sdk_root / relative, max_bytes=MAX_SDK_FILE_BYTES)
                    if (
                        len(content) != fact["size_bytes"]
                        or hashlib.sha256(content).hexdigest() != fact["sha256"]
                    ):
                        entry["status"] = "mismatched"
                        entry["reason"] = "SDK bytes changed after actual parsing."
                    else:
                        sha = fact["sha256"]
                        identifier = captured.get(sha)
                        if identifier is None:
                            identifier = "sdk-buffer-" + sha
                            stage._put(
                                identifier,
                                "execution/sdk-buffers/" + sha + ".bin",
                                content,
                                "application/octet-stream",
                                None,
                            )
                            captured[sha] = identifier
                            total += len(content)
                        entry.update(
                            status="available",
                            artifact_id=identifier,
                            sha256=sha,
                            size_bytes=len(content),
                        )
                except IntegrityError as exc:
                    entry["reason"] = str(exc)
            entries.append(entry)
        unit_proof = {
            "unit_id": request["unit_id"],
            "request_sha256": digest_json(request),
            "resource_manifest_sha256": resource_record["sha256"],
            "report_artifact_id": report_record["id"],
            "report_sha256": report_record["sha256"],
            "report_json": raw.decode("utf-8"),
            "root": str(sdk_root),
            "entries": entries,
        }
        resource_proof = {
            "sha256": resource_record["sha256"],
            "raw_json": resource_bytes.decode("utf-8"),
        }
        added = _proof_array_addition(unit_proof, first=not units)
        if resource_record["sha256"] not in inventories:
            added += _proof_array_addition(resource_proof, first=not inventories)
        if proof_size + added > MAX_SDK_PROOF_BYTES:
            continue
        proof_size += added
        inventories[resource_record["sha256"]] = resource_proof
        units.append(unit_proof)
    document.update(
        resource_inventories=[inventories[key] for key in sorted(inventories)],
        captured_bytes=total,
        units=sorted(units, key=lambda row: row["unit_id"]),
    )
    validate("used_sdk_inputs", document)
    stage.write_json(
        "execution/sdk-used-inputs.json",
        document,
        contract="used_sdk_inputs",
        artifact_id="sdk-used-inputs",
    )
    return document


@dataclass
class UsedSDKProof:
    """One immutable-run proof index and bounded shared content cache."""

    snapshot: Any
    descriptors: dict[str, dict[str, Any]]
    document: dict[str, Any] | None
    units: dict[str, dict[str, Any]]
    buffers: dict[str, bytes] = field(default_factory=dict)
    cached_bytes: int = 0


def load_used_sdk_proof(snapshot: Any) -> UsedSDKProof:
    """Read and validate the finite SDK proof once for an entire normalization."""
    descriptors = {row["id"]: row for row in snapshot.manifest["artifacts"]}
    descriptor = descriptors.get("sdk-used-inputs")
    if descriptor is None or descriptor.get("contract") != {
        "kind": "used_sdk_inputs",
        "version": "2.0.0",
    }:
        return UsedSDKProof(snapshot, descriptors, None, {})
    if descriptor["size_bytes"] > MAX_SDK_PROOF_BYTES:
        raise IntegrityError("Retained SDK proof exceeds its finite byte budget")
    raw = snapshot.read_bytes("sdk-used-inputs")
    if (
        hashlib.sha256(raw).hexdigest() != descriptor["sha256"]
        or len(raw) != descriptor["size_bytes"]
    ):
        raise IntegrityError("Retained SDK proof bytes changed")
    document = json.loads(raw)
    validate("used_sdk_inputs", document)
    return UsedSDKProof(
        snapshot,
        descriptors,
        document,
        {row["unit_id"]: row for row in document["units"]},
    )


def read_used_sdk_buffers(
    snapshot: Any,
    *,
    unit_id: str,
    request: dict[str, Any],
    result: dict[str, Any],
    resource_manifest_bytes: bytes | None,
    report: dict[str, Any] | None,
    proof: UsedSDKProof | None = None,
) -> dict[str, bytes]:
    """Read byte-checked actual SDK inputs without consulting live compiler paths."""
    selected = proof if proof is not None else load_used_sdk_proof(snapshot)
    if selected.snapshot is not snapshot:
        raise IntegrityError("SDK proof cache belongs to a different immutable run")
    document, descriptors = selected.document, selected.descriptors
    if document is None:
        return {}
    if document["source_digest"] != request["source_digest"]:
        raise IntegrityError("Retained SDK proof identifies another selected source")
    unit = selected.units.get(unit_id)
    if unit is None:
        return {}
    reports = [
        row for row in result["artifacts"] if row["path"] == "output/findings.json"
    ]
    if (
        unit["request_sha256"] != digest_json(request)
        or resource_manifest_bytes is None
        or hashlib.sha256(resource_manifest_bytes).hexdigest()
        != unit["resource_manifest_sha256"]
        or len(reports) != 1
        or unit["report_artifact_id"] != reports[0]["id"]
        or unit["report_sha256"] != reports[0]["sha256"]
        or json.loads(unit["report_json"]) != report
    ):
        raise IntegrityError(
            "SDK proof differs from original retained work-unit inputs"
        )
    buffers = {}
    for entry in unit["entries"]:
        if entry["status"] != "available":
            continue
        record = descriptors.get(entry["artifact_id"])
        if (
            record is None
            or any(record[key] != entry[key] for key in ("sha256", "size_bytes"))
            or record["size_bytes"] > MAX_SDK_FILE_BYTES
        ):
            raise IntegrityError("SDK buffer artifact differs from checked TU identity")
        content = selected.buffers.get(entry["artifact_id"])
        if content is None:
            if selected.cached_bytes + record["size_bytes"] > MAX_USED_SDK_BYTES:
                raise IntegrityError("Selected SDK bytes exceed finite read budget")
            content = snapshot.read_bytes(entry["artifact_id"])
            if (
                hashlib.sha256(content).hexdigest() != entry["sha256"]
                or len(content) != entry["size_bytes"]
            ):
                raise IntegrityError(
                    "SDK buffer content differs from checked TU identity"
                )
            selected.buffers[entry["artifact_id"]] = content
            selected.cached_bytes += len(content)
        buffers[entry["target"]] = content
    return buffers
