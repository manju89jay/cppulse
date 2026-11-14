"""Pure contracts for versioned finding identities and explicit regression gates.

Source-line hashing and checked raw-byte reads belong to the producer. These
guards validate metadata, closed current references and conservation without
inspecting project files or upgrading historical facts to current assurance.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from fractions import Fraction
import hashlib
import json
import re
from typing import Any

from cppulse.errors import ContractError

ANCHOR_VERSION = "native-line-anchor-1"
PRODUCER = {"name": "cppulse.findings", "version": "1.0.0"}


def _fail(message: str, path: str = "") -> None:
    raise ContractError(message, path=path)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def scope_identity(scope: Mapping[str, Any]) -> str:
    """Hash selected canonical paths, jobs and rules, without source contents."""
    return _digest(
        {key: sorted(scope[key]) for key in ("files", "context_ids", "rule_ids")}
    )


def anchor_fingerprint(item: Mapping[str, Any]) -> str | None:
    """Identify a line anchor while retaining context as separate matching data."""
    if item["anchor_sha256"] is None:
        return None
    projection = {
        "fingerprint_version": ANCHOR_VERSION,
        **{
            key: item[key]
            for key in (
                "file",
                "producer",
                "rule_id",
                "rule_version",
                "severity",
                "message",
                "anchor_sha256",
            )
        },
        "column": None if item["column"] is None else _count(item["column"]),
    }
    return _digest(projection)


def _count(value: int | float) -> int:
    number = Fraction(str(value))
    if number.denominator != 1 or number < 0:
        _fail("Finding counts must be nonnegative integers")
    return number.numerator


def _time(value: str, path: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(
            "Invalid finding-workflow UTC timestamp", path=path
        ) from error
    if result.utcoffset() != timedelta(0):
        _fail("Finding workflow timestamps require explicit UTC", path)
    return result


def _scope(scope: dict[str, Any]) -> None:
    from .validation import _safe_path

    for path in scope["files"]:
        _safe_path(path, "/scope/files")
    for key in ("files", "context_ids", "rule_ids"):
        if len(scope[key]) != len(set(scope[key])):
            _fail("Duplicate finding scope identity", "/scope/" + key)
    if scope["sha256"] != scope_identity(scope):
        _fail(
            "Finding scope digest disagrees with selected paths/jobs/rules",
            "/scope/sha256",
        )


def _renames(rows: list[dict[str, str]]) -> None:
    from .validation import _safe_path, _unique

    for row in rows:
        _safe_path(row["from"], "/rename_map/from")
        _safe_path(row["to"], "/rename_map/to")
    _unique(rows, "from", "/rename_map")
    _unique(rows, "to", "/rename_map")


def _request(document: dict[str, Any]) -> None:
    from .validation import _safe_path

    for path in document["scope_files"]:
        _safe_path(path, "/scope_files")
    if "reason" in document and not document["reason"].strip():
        _fail("Baseline creation needs a nonblank reason", "/reason")
    _renames(document.get("rename_map", []))
    for reference in [document.get("baseline"), document.get("suppressions")]:
        if reference is None:
            continue
        for key in ("store", "bundle", "path"):
            if key in reference and (
                "\x00" in reference[key]
                or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", reference[key])
            ):
                _fail(
                    "Finding references are explicit local filesystem paths", "/" + key
                )
        for key in ("run_id", "root_id"):
            if key in reference and not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", reference[key]
            ):
                _fail(
                    "Finding references need canonical run/root identifiers", "/" + key
                )


def _suppression_records(records: list[dict[str, Any]]) -> None:
    from .validation import _safe_path, _unique

    _unique(records, "id", "/records")
    windows: dict[tuple[Any, ...], list[tuple[datetime, datetime]]] = {}
    for row in records:
        _safe_path(row["file"], "/records/file")
        if not row["reason"].strip() or not row["owner"].strip():
            _fail("Suppression rationale and owner cannot be blank", "/records")
        first, last = (
            _time(row[key], "/records/" + key) for key in ("approved_at", "expires_at")
        )
        if last <= first:
            _fail("Suppression expiry must follow approval", "/records/expires_at")
        key = tuple(
            row[name]
            for name in (
                "baseline_sha256",
                "fingerprint_version",
                "fingerprint",
                "file",
                "context_id",
                "parse_context_digest",
                "rule_id",
                "rule_version",
            )
        )
        if any(
            max(first, start) < min(last, finish)
            for start, finish in windows.get(key, [])
        ):
            _fail(
                "Overlapping suppressions cannot stack the same exact scope", "/records"
            )
        windows.setdefault(key, []).append((first, last))


def _baseline(document: dict[str, Any]) -> None:
    from .validation import _safe_path

    _scope(document["scope"])
    _time(document["created_at"], "/created_at")
    if not document["reason"].strip():
        _fail("Baseline reason cannot be blank", "/reason")
    scope = document["scope"]
    expected = {
        (path, context) for path in scope["files"] for context in scope["context_ids"]
    }
    cells = {(row["file"], row["context_id"]): row for row in document["cells"]}
    if set(cells) != expected or len(cells) != len(document["cells"]):
        _fail("Baseline needs exactly one cell for every selected file/job", "/cells")
    for row in cells.values():
        _safe_path(row["file"], "/cells/file")
        if row["status"] == "complete" and (
            any(
                row[key] is None
                for key in (
                    "parse_context_digest",
                    "inventory_id",
                    "source_artifact_id",
                    "source_sha256",
                    "registry_sha256",
                    "config_sha256",
                    "native_executable_sha256",
                )
            )
            or not set(scope["rule_ids"]) <= set(row["executed_rules"])
        ):
            _fail(
                "Complete baseline cell lacks source/context/config/tool/rule consideration",
                "/cells",
            )
    identifiers: set[str] = set()
    groups = set()
    for row in document["findings"]:
        _safe_path(row["file"], "/findings/file")
        cell = cells.get((row["file"], row["context_id"]))
        if (
            cell is None
            or row["rule_id"] not in scope["rule_ids"]
            or row["parse_context_digest"] != cell["parse_context_digest"]
        ):
            _fail(
                "Baseline finding is outside its selected cell/rule context",
                "/findings",
            )
        if _count(row["count"]) != len(row["observation_ids"]) or identifiers & set(
            row["observation_ids"]
        ):
            _fail("Baseline multiplicity/observation identities disagree", "/findings")
        identifiers.update(row["observation_ids"])
        if row["anchor_status"] == "unavailable":
            if row["anchor_sha256"] is not None or row["fingerprint"] is not None:
                _fail("Unavailable anchors cannot invent stable hashes", "/findings")
        elif row["anchor_sha256"] is None or row["fingerprint"] != anchor_fingerprint(
            row
        ):
            _fail(
                "Anchor fingerprint disagrees with its explicit version/components",
                "/findings/fingerprint",
            )
        key = (
            row["file"],
            row["context_id"],
            row["rule_id"],
            row["fingerprint"],
            row["message"],
            row["column"],
        )
        if key in groups:
            _fail(
                "Repeated finding identities must retain one explicit multiset count",
                "/findings",
            )
        groups.add(key)
    if identifiers and not document["observations_artifact_ids"]:
        _fail(
            "Baseline observations need their original retained documents",
            "/observations_artifact_ids",
        )


def _comparison(document: dict[str, Any]) -> None:
    from .validation import _safe_path

    _scope(document["scope"])
    _renames(document["rename_map"])
    generated = _time(document["generated_at"], "/generated_at")
    current_ids: set[str] = set()
    baseline_ids: set[str] = set()
    seen = set()
    totals = {key: 0 for key in document["counts"]}
    for row in document["groups"]:
        _safe_path(row["file"], "/groups/file")
        if (
            row["file"] not in document["scope"]["files"]
            or row["context_id"] not in document["scope"]["context_ids"]
            or row["rule_id"] not in document["scope"]["rule_ids"]
        ):
            _fail(
                "Comparison group is outside selected source/job/rule scope", "/groups"
            )
        if current_ids & set(row["current_observation_ids"]) or baseline_ids & set(
            row["baseline_observation_ids"]
        ):
            _fail("Comparison cannot collapse or repeat finding occurrences", "/groups")
        current_ids.update(row["current_observation_ids"])
        baseline_ids.update(row["baseline_observation_ids"])
        key = (
            row["file"],
            row["context_id"],
            row["rule_id"],
            row["fingerprint"],
            row["baseline_fingerprint"],
        )
        if key in seen:
            _fail("Duplicate comparison finding group", "/groups")
        seen.add(key)
        new, same, resolved, unknown_c, unknown_b, suppressed = (
            _count(row[key])
            for key in (
                "new_count",
                "unchanged_count",
                "resolved_count",
                "unknown_current_count",
                "unknown_baseline_count",
                "suppressed_count",
            )
        )
        if (
            len(row["current_observation_ids"]) != new + same + unknown_c
            or len(row["baseline_observation_ids"]) != resolved + same + unknown_b
            or suppressed > new
        ):
            _fail("Comparison group violates multiset conservation", "/groups")
        if ((new or same) and row["fingerprint"] is None) or (
            (resolved or same) and row["baseline_fingerprint"] is None
        ):
            _fail(
                "Known comparison states require actual versioned fingerprints",
                "/groups",
            )
        renamed = any(
            mapping["to"] == row["file"] and mapping["from"] != mapping["to"]
            for mapping in document["rename_map"]
        )
        if same and not renamed and row["fingerprint"] != row["baseline_fingerprint"]:
            _fail(
                "Unchanged findings need equal fingerprints without an applicable non-identity rename",
                "/groups",
            )
        for name, count in [
            ("new", new),
            ("unchanged", same),
            ("resolved", resolved),
            ("unknown_current", unknown_c),
            ("unknown_baseline", unknown_b),
            ("suppressed_new", suppressed),
        ]:
            totals[name] += count
    totals["current"], totals["baseline"] = len(current_ids), len(baseline_ids)
    totals["unsuppressed_new"] = totals["new"] - totals["suppressed_new"]
    if any(_count(document["counts"][key]) != value for key, value in totals.items()):
        _fail("Comparison totals disagree with occurrence groups", "/counts")
    if (
        totals["unknown_current"]
        or totals["unknown_baseline"]
        or not document["comparable"]
    ) and not document["incomplete"]:
        _fail("Unknown/unsupported comparisons must remain incomplete", "/incomplete")
    if (document["suppressions_artifact_id"] is None) != (
        document["suppressions_sha256"] is None
    ):
        _fail(
            "Suppression raw role and digest must be supplied together",
            "/suppressions_artifact_id",
        )
    _suppression_records(document["suppressions"])
    applied = 0
    for row in document["suppressions"]:
        count = _count(row["applied_count"])
        matching = [
            group
            for group in document["groups"]
            if all(
                group[key] == row[key]
                for key in ("file", "context_id", "rule_id", "fingerprint")
            )
        ]
        if row["active"]:
            if (
                not count
                or count > _count(row["max_count"])
                or row["inactive_reason"] is not None
                or document["suppressions_artifact_id"] is None
                or row["baseline_sha256"] != document["baseline_sha256"]
                or not _time(row["approved_at"], "/suppressions/approved_at")
                <= generated
                < _time(row["expires_at"], "/suppressions/expires_at")
                or count > sum(_count(group["suppressed_count"]) for group in matching)
            ):
                _fail(
                    "Active suppression lacks exact current eligible count/time/baseline scope",
                    "/suppressions",
                )
        elif (
            count
            or row["inactive_reason"] is None
            or not row["inactive_reason"].strip()
        ):
            _fail(
                "Inactive suppressions retain a reason and apply no counts",
                "/suppressions",
            )
        applied += count
    if applied != totals["suppressed_new"]:
        _fail(
            "Suppression applications disagree with raw/effective finding counts",
            "/suppressions",
        )
    expected = (
        "failed"
        if totals["unsuppressed_new"] > _count(document["max_new"])
        else (
            "insufficient_evidence"
            if document["incomplete"]
            or not document["comparable"]
            or not document["scope"]["files"]
            else "passed"
        )
    )
    if document["gate"] != expected:
        _fail(
            "Finding gate disagrees with raw counts, completeness and explicit threshold",
            "/gate",
        )


def semantic(kind: str, document: dict[str, Any]) -> None:
    """Validate first-slice finding semantics after structural validation."""
    if kind in {"finding_baseline_request", "finding_check_request"}:
        _request(document)
    elif kind == "finding_suppressions":
        _suppression_records(document["records"])
    else:
        if document["producer"] != PRODUCER:
            _fail("Unsupported finding workflow producer", "/producer")
        if kind == "finding_baseline":
            _baseline(document)
        elif kind == "finding_comparison":
            _comparison(document)


def validate_finding_bundle(
    flat: list[tuple[str, dict[str, Any]]],
    manifest: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> None:
    """Bind finding contracts to retained raw roles and current typed analysis."""
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    inventories = {row["id"]: row for kind, row in flat if kind == "analysis_inventory"}
    facts = {
        row["receipt"]["id"]: row for kind, row in flat if kind == "execution_facts"
    }
    contexts = {row["id"]: row for row in manifest["contexts"]}
    observations = {
        item["id"]: (item, inventories.get(document.get("analysis_inventory_id")))
        for kind, document in flat
        if kind == "observations"
        for item in document["items"]
    }

    def raw(identifier: str, sha: str) -> None:
        item = artifacts.get(identifier)
        if item is None or item["sha256"] != sha or "contract" in item:
            _fail(
                "Finding workflow needs exact generic original raw role bytes",
                "/artifacts",
            )

    def scoped_observations(scope: dict[str, Any]) -> set[str]:
        return {
            identifier
            for identifier, (row, inventory) in observations.items()
            if inventory is not None
            and row["file"] in scope["files"]
            and row["rule_id"] in scope["rule_ids"]
            and inventory["job_context_id"] in scope["context_ids"]
        }

    def complete(path: str, job: str, rules: list[str]) -> bool:
        candidates = [
            inventory
            for inventory in inventories.values()
            if inventory["job_context_id"] == job
            and path in inventory["requested_files"]
        ]
        if len(candidates) != 1 or manifest.get("input_verification") != "verified":
            return False
        inventory = candidates[0]
        row = next(item for item in inventory["items"] if item["file"] == path)
        execution = facts.get(inventory["receipt_id"])
        return bool(
            execution is not None
            and execution["binding"]["status"] == "verified"
            and execution["material_status"] == "available"
            and execution["receipt"]["status"] == "passed"
            and row["status"] == "analyzed"
            and row["error_count"] == 0
            and row["context_match"] == "matched"
            and set(rules)
            <= set(inventory["requested_rules"]) & set(row["executed_rules"])
            and inventory.get("compilation_database_artifact_id") is not None
            and inventory.get("resource_manifest_artifact_id") is not None
        )

    def credible(inventory: dict[str, Any], path: str) -> bool:
        row = next(item for item in inventory["items"] if item["file"] == path)
        execution = facts.get(inventory["receipt_id"])
        return bool(
            manifest.get("input_verification") == "verified"
            and execution is not None
            and execution["binding"]["status"] == "verified"
            and execution["material_status"] == "available"
            and execution["receipt"]["status"] == "passed"
            and row["status"] in {"analyzed", "partial"}
            and row["context_match"] == "matched"
            and inventory.get("compilation_database_artifact_id") is not None
            and inventory.get("resource_manifest_artifact_id") is not None
        )

    for kind, document in flat:
        if kind not in {"finding_baseline", "finding_comparison"}:
            continue
        if document["source_digest"] != manifest["source"]["digest"]:
            _fail(
                "Finding workflow owning source differs from current run",
                "/source_digest",
            )
        if kind == "finding_baseline":
            generated = _time(document["created_at"], "/created_at")
            raw(
                document["original_manifest_artifact_id"],
                document["original_manifest_sha256"],
            )
            for identifier in document["observations_artifact_ids"]:
                if (
                    artifacts.get(identifier, {}).get("contract", {}).get("kind")
                    != "observations"
                ):
                    _fail(
                        "Baseline original observation role is absent",
                        "/observations_artifact_ids",
                    )
            for cell in document["cells"]:
                inventory = inventories.get(cell["inventory_id"])
                if cell["status"] == "complete" and not complete(
                    cell["file"], cell["context_id"], document["scope"]["rule_ids"]
                ):
                    _fail(
                        "Complete finding baseline lacks current matched rule consideration",
                        "/cells",
                    )
                if inventory is None:
                    if cell["inventory_id"] is not None:
                        _fail(
                            "Baseline refers to absent analysis inventory",
                            "/cells/inventory_id",
                        )
                    continue
                row = next(
                    (
                        item
                        for item in inventory["items"]
                        if item["file"] == cell["file"]
                    ),
                    None,
                )
                parse = contexts.get(row["parse_context_id"]) if row else None
                execution = facts.get(inventory["receipt_id"])
                if generated < datetime.fromisoformat(
                    receipts[inventory["receipt_id"]]["finished_at"].replace(
                        "Z", "+00:00"
                    )
                ):
                    _fail(
                        "Baseline creation predates used native analysis facts",
                        "/created_at",
                    )
                if (
                    row is None
                    or inventory["job_context_id"] != cell["context_id"]
                    or cell["parse_context_digest"]
                    != (parse["digest"] if parse else None)
                    or set(cell["executed_rules"]) != set(row["executed_rules"])
                ):
                    _fail(
                        "Baseline cell differs from actual observed inventory/context",
                        "/cells",
                    )
                for key, actual in [
                    ("registry_sha256", inventory["registry_sha256"]),
                    (
                        "config_sha256",
                        artifacts[inventory["config_artifact_id"]]["sha256"],
                    ),
                    (
                        "native_executable_sha256",
                        (
                            execution["executable_fact"]["sha256"]
                            if execution and execution["executable_fact"]
                            else None
                        ),
                    ),
                ]:
                    if cell[key] != actual:
                        _fail(
                            "Baseline cell configuration/registry/tool identity differs",
                            "/cells/" + key,
                        )
                if cell["source_artifact_id"] is not None:
                    source = next(
                        (
                            entry
                            for entry in manifest["source"]["files"]
                            if entry["path"] == cell["file"]
                        ),
                        None,
                    )
                    artifact = artifacts.get(cell["source_artifact_id"])
                    if (
                        source is None
                        or artifact is None
                        or cell["source_sha256"] != source["sha256"]
                        or artifact["sha256"] != source["sha256"]
                        or artifact["size_bytes"] != source["size_bytes"]
                    ):
                        _fail(
                            "Baseline source anchor role differs from selected source bytes",
                            "/cells/source_artifact_id",
                        )
            selected_ids = {
                identifier
                for row in document["findings"]
                for identifier in row["observation_ids"]
            }
            if selected_ids != scoped_observations(document["scope"]):
                _fail(
                    "Baseline must preserve all selected native observation occurrences",
                    "/findings",
                )
            for group in document["findings"]:
                for identifier in group["observation_ids"]:
                    row, inventory = observations[identifier]
                    if (
                        any(
                            group[key] != row[key]
                            for key in (
                                "file",
                                "producer",
                                "rule_id",
                                "rule_version",
                                "severity",
                                "message",
                            )
                        )
                        or group["column"] != row.get("column")
                        or inventory["job_context_id"] != group["context_id"]
                    ):
                        _fail(
                            "Baseline anchor metadata differs from original observation",
                            "/findings",
                        )
        else:
            generated = _time(document["generated_at"], "/generated_at")
            for artifact_key, hash_key in [
                ("current_manifest_artifact_id", "current_manifest_sha256"),
                ("baseline_manifest_artifact_id", "baseline_manifest_sha256"),
                ("baseline_artifact_id", "baseline_sha256"),
            ]:
                raw(document[artifact_key], document[hash_key])
            if document["suppressions_artifact_id"] is not None:
                raw(
                    document["suppressions_artifact_id"],
                    document["suppressions_sha256"],
                )
            selected_ids = {
                identifier
                for row in document["groups"]
                for identifier in row["current_observation_ids"]
            }
            if selected_ids != scoped_observations(document["scope"]):
                _fail(
                    "Finding comparison cannot hide selected current occurrences",
                    "/groups",
                )
            for group in document["groups"]:
                for identifier in group["current_observation_ids"]:
                    row, inventory = observations[identifier]
                    if (
                        row["file"] != group["file"]
                        or row["rule_id"] != group["rule_id"]
                        or inventory["job_context_id"] != group["context_id"]
                    ):
                        _fail(
                            "Comparison occurrence differs from current file/job/rule scope",
                            "/groups",
                        )
                    if generated < datetime.fromisoformat(
                        receipts[inventory["receipt_id"]]["finished_at"].replace(
                            "Z", "+00:00"
                        )
                    ):
                        _fail(
                            "Finding comparison predates used native analysis facts",
                            "/generated_at",
                        )
                    if (
                        group["new_count"] or group["unchanged_count"]
                    ) and not credible(inventory, row["file"]):
                        _fail(
                            "Known current finding states require source-bound matched native observations",
                            "/groups",
                        )
                if group["resolved_count"] and not complete(
                    group["file"], group["context_id"], [group["rule_id"]]
                ):
                    _fail(
                        "Absent old observations need complete current rule consideration",
                        "/groups/resolved_count",
                    )
            if document["gate"] == "passed" and any(
                not complete(path, job, document["scope"]["rule_ids"])
                for path in document["scope"]["files"]
                for job in document["scope"]["context_ids"]
            ):
                _fail(
                    "Positive finding comparison needs complete current selected rule coverage",
                    "/gate",
                )
            for request in document["suppressions"]:
                if not request["active"]:
                    continue
                eligible = [
                    observations[identifier]
                    for group in document["groups"]
                    if all(
                        group[key] == request[key]
                        for key in ("file", "context_id", "rule_id", "fingerprint")
                    )
                    for identifier in group["current_observation_ids"]
                ]
                if not eligible or any(
                    row["rule_version"] != request["rule_version"]
                    or contexts[row["context_id"]]["digest"]
                    != request["parse_context_digest"]
                    or inventory["job_context_id"] != request["context_id"]
                    for row, inventory in eligible
                ):
                    _fail(
                        "Active finding suppression differs from exact observed context/rule scope",
                        "/suppressions",
                    )
