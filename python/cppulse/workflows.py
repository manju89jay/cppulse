"""Installed local workflows over explicit recipes and immutable checked facts.

Commands are launched only by ``collect_request`` through the accepted collector.
Other operations interpret retained facts and verify finite current material;
they do not discover or run additional project commands.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Sequence

from cppulse import __version__
from cppulse.collection import collect
from cppulse.consumer import RetainedBlob
from cppulse.contracts import validate
from cppulse.errors import (
    CompatibilityError,
    ContractError,
    CppulseError,
    InputChanged,
    IntegrityError,
)
from cppulse.execution import CancellationToken
from cppulse.identities import snapshot_inputs, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore

_FACTS = {
    "native_analysis": {"analysis_inventory", "observations", "analysis_metrics"},
    "coverage": {"coverage_facts"},
    "sanitizer": {"sanitizer_facts"},
    "gcc_import": {"external_analysis_facts"},
    "external_import": {"external_analysis_facts"},
    "test_import": {"evidence"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode()


def _id(value: str) -> str:
    return "workflow-" + hashlib.sha256(value.encode()).hexdigest()


def run_reference(snapshot: RunSnapshot) -> dict[str, Any]:
    """Return one frozen manifest/source pin, without resolving latest again."""
    return {
        "run_id": snapshot.run_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "status": snapshot.manifest["status"],
        "source_digest": snapshot.manifest["source"]["digest"],
    }


def read_documents(snapshot: RunSnapshot) -> dict[str, Any]:
    """Read only checked declared v2 contracts from a fixed local snapshot."""
    snapshot.verify()
    result: dict[str, Any] = {"run_manifest": snapshot.manifest}
    for artifact in snapshot.manifest["artifacts"]:
        contract = artifact.get("contract", {})
        if contract.get("version") != "2.0.0":
            continue
        document = snapshot.read_json(artifact["id"])
        if contract["kind"] == "policy":
            if "policy" in result:
                raise ContractError("Selected snapshot contains ambiguous policies")
            result["policy"] = document
        else:
            result.setdefault(contract["kind"], []).append(document)
    return result


def _limits(snapshot: RunSnapshot) -> tuple[int, int]:
    plans = read_documents(snapshot).get("collection_plan", [])
    versions = snapshot.manifest["versions"]
    metadata_default = int(
        versions.get("workflow_max_metadata_bytes", 16 * 1024 * 1024)
    )
    artifact_default = int(
        versions.get("workflow_max_artifact_bytes", 64 * 1024 * 1024)
    )
    if (
        not 1 <= metadata_default <= 64 * 1024 * 1024
        or not 1 <= artifact_default <= 256 * 1024 * 1024
    ):
        raise ContractError("Recorded workflow limits are outside supported bounds")
    return (
        min(
            (int(plan["limits"]["max_metadata_bytes"]) for plan in plans),
            default=metadata_default,
        ),
        min(
            (int(plan["limits"]["max_artifact_bytes"]) for plan in plans),
            default=artifact_default,
        ),
    )


def ensure_current_materials(snapshot: RunSnapshot, workspace: Path) -> None:
    """Reject changed selected source and every finite observed generated output.

    A replacement binary/package cannot inherit the snapshot's old tests. This
    checks content identity, not a whole directory or host dependency closure.
    """
    snapshot.verify()
    changed = verify_inputs(workspace, snapshot.manifest["source"])
    if changed:
        raise InputChanged(
            "Selected source no longer matches retained facts: " + "; ".join(changed),
            code="STALE_SOURCE",
        )
    expected: dict[str, tuple[str, int]] = {}
    for fact in read_documents(snapshot).get("execution_facts", []):
        for row in fact["output_facts"]:
            identity = (row["sha256"], row["size_bytes"])
            if row["path"] in expected and expected[row["path"]] != identity:
                raise InputChanged(
                    "Retained output identities conflict",
                    code="STALE_OUTPUT",
                    path=row["path"],
                )
            expected[row["path"]] = identity
    for path, identity in expected.items():
        try:
            current = snapshot_inputs(workspace, [path])["files"][0]
        except CppulseError as error:
            raise InputChanged(
                "Observed generated output is missing or unsafe: " + str(error),
                code="STALE_OUTPUT",
                path=path,
            ) from error
        if (current["sha256"], current["size_bytes"]) != identity:
            raise InputChanged(
                "Generated output differs from the executed material",
                code="STALE_OUTPUT",
                path=path,
            )


def _mutable_parent(snapshot: RunSnapshot) -> None:
    if snapshot.manifest.get("input_verification") != "verified":
        raise CompatibilityError(
            "Historical source verification is unavailable; today's files cannot establish past execution",
            code="UNVERIFIED_SOURCE",
        )
    if read_documents(snapshot).get("assessment"):
        raise ContractError(
            "Adding facts to an assessed parent is ambiguous; select the original unassessed facts base",
            code="ASSESSED_PARENT",
        )


def _derive(
    snapshot: RunSnapshot,
    *,
    workspace: Path,
    store: RunStore | Path,
    operation: str,
    documents: Sequence[tuple[str, dict[str, Any]]] = (),
    blobs: Sequence[RetainedBlob] = (),
    partial: bool = False,
    reason: str,
) -> RunSnapshot:
    """Persist metadata transforms with exact parent bytes and final freshness."""
    snapshot.verify()
    _mutable_parent(snapshot)
    ensure_current_materials(snapshot, workspace)
    metadata_cap, artifact_cap = _limits(snapshot)
    for kind, document in documents:
        validate(kind, document)
        if len(_bytes(document)) > metadata_cap:
            raise IntegrityError("Derived control document exceeds max_metadata_bytes")
    for blob in blobs:
        cap = metadata_cap if blob.media_type == "application/json" else artifact_cap
        if len(blob.content) > cap:
            raise IntegrityError(
                "Derived retained bytes exceed their metadata/artifact bound"
            )
    known = {entry["id"]: entry for entry in snapshot.manifest["artifacts"]}
    additions = []
    for blob in blobs:
        descriptor = blob.descriptor()
        if blob.id in known:
            if known[blob.id] != descriptor:
                raise ContractError(
                    "Retained blob conflicts with existing byte identity"
                )
        else:
            known[blob.id] = descriptor
            additions.append(blob)
    parent_bytes = snapshot.read_manifest_bytes()
    if (
        len(parent_bytes) > metadata_cap
        or hashlib.sha256(parent_bytes).hexdigest() != snapshot.manifest_sha256
    ):
        raise IntegrityError(
            "Pinned parent manifest serialization or metadata bound differs"
        )
    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with runtime.begin() as stage:
        for artifact in snapshot.manifest["artifacts"]:
            copied = stage.copy_artifact(
                artifact["id"],
                snapshot.path / artifact["path"],
                artifact["path"],
                artifact["media_type"],
                contract=artifact.get("contract"),
            )
            if copied != artifact:
                raise IntegrityError("Derived workflow changed a parent descriptor")
        with tempfile.TemporaryDirectory(prefix="cppulse-workflow-") as temporary:
            temporary = Path(temporary)
            for index, blob in enumerate(additions):
                path = temporary / str(index)
                path.write_bytes(blob.content)
                stage.copy_artifact(blob.id, path, blob.path, blob.media_type)
            parent_id = _id(operation + ":parent:" + snapshot.manifest_sha256)
            path = temporary / "parent.json"
            path.write_bytes(parent_bytes)
            stage.copy_artifact(
                parent_id,
                path,
                "workflows/provenance/" + parent_id + ".json",
                "application/json",
            )
        for kind, document in documents:
            identifier = _id(
                operation
                + ":"
                + kind
                + ":"
                + hashlib.sha256(_bytes(document)).hexdigest()
            )
            stage.write_json(
                "workflows/" + kind + "/" + identifier + ".json",
                document,
                contract=kind,
                artifact_id=identifier,
            )
        manifest = snapshot.manifest
        manifest.update(
            run_id=stage.run_id, artifacts=stage.artifacts, finished_at=_now()
        )
        if partial and manifest["status"] == "completed":
            manifest["status"] = "partial"
        manifest["versions"]["cppulse.workflows"] = __version__
        manifest["stages"].append(
            {
                "id": _id(operation + ":" + stage.run_id),
                "status": "error" if partial else "passed",
                "depends_on": [],
                "reason": reason,
            }
        )
        if len(_bytes(manifest)) > metadata_cap:
            raise IntegrityError("Derived workflow manifest exceeds max_metadata_bytes")
        return stage.publish(
            manifest, source_check=lambda: ensure_current_materials(snapshot, workspace)
        )


def workflow_result(
    operation: str,
    store: RunStore | Path,
    *,
    status: str,
    reason: str,
    raw: RunSnapshot | None = None,
    final: RunSnapshot | None = None,
    error: CppulseError | None = None,
) -> dict[str, Any]:
    """Create a typed result; operation success is distinct from policy success."""
    result = {
        "version": "2.0.0",
        "operation": operation,
        "store": str(
            (store.root if isinstance(store, RunStore) else Path(store)).absolute()
        ),
        "status": status,
        "exit_code": {
            "completed": 0,
            "partial": 3,
            "failed": 1,
            "insufficient_evidence": 3,
            "invalid": 2,
            "cancelled": 130,
        }[status],
        "reason": reason,
        "raw_run": run_reference(raw) if raw else None,
        "final_run": run_reference(final) if final else None,
        "facts_base_run": None,
        "upstream_run": None,
        "assessment_artifact_id": None,
        "comparison_artifact_id": None,
        "baseline_artifact_id": None,
        "policy_gate": None,
        "normalizers": [],
        "error": error.as_dict() if error else None,
    }
    # Operation-specific pins are completed by its caller before validation.
    return result


def _role(snapshot: RunSnapshot, selector: dict[str, Any]) -> str:
    facts = [
        row
        for row in read_documents(snapshot).get("execution_facts", [])
        if row["receipt"]["id"] == selector["step_id"]
    ]
    if len(facts) != 1:
        raise CompatibilityError(
            "Selected receipt has no unique typed execution facts", code="MISSING_ROLE"
        )
    binding = facts[0]["binding"]
    if selector["role"] in {"stdout", "stderr"}:
        selected = binding["log_artifacts"][selector["role"]]
        if selected is None:
            raise CompatibilityError(
                "Selected captured stream is unavailable", code="MISSING_ROLE"
            )
        return selected
    rows = [
        row["artifact_id"]
        for row in binding[selector["role"] + "_artifacts"]
        if row["path"] == selector["path"]
    ]
    if len(rows) != 1:
        raise CompatibilityError(
            "Selected observed path role is unavailable",
            code="MISSING_ROLE",
            path=selector["path"],
        )
    return rows[0]


def _normalize(
    snapshot: RunSnapshot, item: dict[str, Any], workspace: Path, store: RunStore | Path
) -> RunSnapshot:
    kind = item["kind"]
    if kind == "native_analysis":
        from cppulse.analysis import persist_native_analysis

        return persist_native_analysis(
            snapshot,
            workspace=workspace,
            store=store,
            receipt_id=item["step_id"],
            report_artifact_id=_role(snapshot, item["report"]),
            registry_artifact_id=_role(snapshot, item["registry"]),
            config_artifact_id=_role(snapshot, item["config"]),
            compilation_database_artifact_id=(
                _role(snapshot, item["compilation_database"])
                if item["compilation_database"]
                else None
            ),
            resource_manifest_artifact_id=(
                _role(snapshot, item["resource_manifest"])
                if item["resource_manifest"]
                else None
            ),
            requested_files=item["requested_files"],
            requested_rules=item["requested_rules"],
        )
    if kind == "coverage":
        from cppulse.coverage import persist_coverage

        return persist_coverage(
            snapshot,
            workspace=workspace,
            store=store,
            receipt_id=item["step_id"],
            report_artifact_id=_role(snapshot, item["report"]),
            adapter=item["adapter"],
            producer_version_receipt_id=item["producer_version_step_id"],
            gcov_version_receipt_id=item["gcov_version_step_id"],
            compiler_version_receipt_id=item["compiler_version_step_id"],
            configuration_artifact_id=_role(snapshot, item["configuration"]),
            gcov_artifact_id=_role(snapshot, item["gcov"]),
            proof_receipt_ids=item["proof_step_ids"],
            test_evidence_ids=item["test_binding_ids"],
            instrumentation=[
                {
                    "object_artifact_id": _role(snapshot, row["object"]),
                    "mapping_artifact_id": _role(snapshot, row["mapping"]),
                    "source_files": row["source_files"],
                }
                for row in item["instrumentation"]
            ],
            profiles=[
                {
                    "artifact_id": _role(snapshot, row["profile"]),
                    "binary_artifact_id": _role(snapshot, row["binary"]),
                    "test_receipt_id": row["test_step_id"],
                }
                for row in item["profiles"]
            ],
        )
    if kind == "sanitizer":
        from cppulse.sanitizers import (
            ObjectSelection,
            SanitizerSelection,
            persist_gcc_sanitizer,
        )

        selection = SanitizerSelection(
            item["id"],
            item["sanitizer"],
            tuple(item["requested_files"]),
            item["compiler_version_step_id"],
            item["nm_version_step_id"],
            item["readelf_version_step_id"],
            tuple(
                ObjectSelection(
                    row["compile_step_id"], row["nm_step_id"], row["elf_step_id"]
                )
                for row in item["objects"]
            ),
            item["link_step_id"],
            item["runtime_inspection_step_id"],
            item["test_binding_id"],
        )
        return persist_gcc_sanitizer(
            snapshot, workspace=workspace, store=store, selection=selection
        )
    if kind == "test_import":
        from cppulse.test_import import persist_test_import

        return persist_test_import(
            snapshot,
            workspace=workspace,
            store=store,
            adapter=item["adapter"],
            report_artifact_id=_role(snapshot, item["report"]),
            context_id=item["context_id"],
            scope_files=item["scope_files"],
            producer=item["producer"],
        )
    if kind == "external_import":
        from cppulse.external import persist_external_import

        return persist_external_import(
            snapshot,
            workspace=workspace,
            store=store if isinstance(store, RunStore) else RunStore(store),
            adapter=item["adapter"],
            report_artifact_id=_role(snapshot, item["report"]),
            context_id=item["context_id"],
            source_root=item["source_root"],
            scope_files=item["scope_files"],
            producer=item["producer"],
        )
    from cppulse.external import persist_gcc_import

    runtime = store if isinstance(store, RunStore) else RunStore(store)
    return persist_gcc_import(
        snapshot,
        workspace=workspace,
        store=runtime,
        report_artifact_id=_role(snapshot, item["report"]),
        context_id=item["context_id"],
        source_root=item["source_root"],
        scope_files=item["scope_files"],
        producer=item["producer"],
    )


def _record(
    parent: RunSnapshot, child: RunSnapshot, item: dict[str, Any]
) -> dict[str, Any]:
    previous = {entry["id"] for entry in parent.manifest["artifacts"]}
    facts = []
    values = []
    for entry in child.manifest["artifacts"]:
        kind = entry.get("contract", {}).get("kind")
        if entry["id"] not in previous and kind in _FACTS[item["kind"]]:
            value = child.read_json(entry["id"])
            facts.append(
                {"kind": kind, "artifact_id": entry["id"], "id": value.get("id")}
            )
            values.append(value)
    usabilities = [value["usability"] for value in values if "usability" in value]
    usabilities.extend(
        record["usability"]
        for value in values
        for record in value.get("records", [])
        if "usability" in record
    )
    usability = next(
        (value for value in usabilities if value != "usable"),
        "usable" if usabilities else None,
    )
    return {
        "id": item["id"],
        "kind": item["kind"],
        "status": "completed",
        "outcome": next((row["outcome"] for row in values if "outcome" in row), None),
        "usability": usability,
        "fact_artifacts": facts,
        "run": run_reference(child),
        "reason": "Accepted normalizer retained typed facts; this is not a policy gate.",
    }


def collect_request(
    request: dict[str, Any],
    *,
    workspace: Path,
    store: RunStore | Path,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    """Validate the complete finite request, execute it, then normalize known roles.

    Args:
        request: Typed source selection, contexts, plan and bounded built-ins.
        workspace: Existing caller-selected root; no discovery occurs.
        store: Local output store, created only after validation.
        cancel: Optional cooperative cancellation token.

    Returns:
        A workflow_result preserving raw/final pins and independent outcomes.
    """
    request = deepcopy(request)
    validate("collection_request", request)
    if "ruleset" in request or "resolved_ruleset" in request:
        from cppulse.rulesets import bind_collection_ruleset

        request = bind_collection_ruleset(request, Path(workspace))
        validate("collection_request", request)
    if len(_bytes(request)) > int(request["plan"]["limits"]["max_metadata_bytes"]):
        raise ContractError("Public collection request exceeds max_metadata_bytes")
    workspace = Path(workspace).resolve(strict=True)
    source = snapshot_inputs(
        workspace,
        request["source"]["files"],
        kind=request["source"]["kind"],
        inventory_complete=request["source"]["inventory_complete"],
    )
    if "resolved_ruleset" in request:
        observed = {row["path"]: row["sha256"] for row in source["files"]}
        for pack in request["resolved_ruleset"]["packs"]:
            name = Path(pack["path"]).relative_to(workspace).as_posix()
            if observed.get(name) != pack["sha256"]:
                raise InputChanged(
                    "Ruleset changed while establishing collection inputs: " + name
                )
    source["limitations"] = list(
        dict.fromkeys([*source["limitations"], *request["source"]["limitations"]])
    )
    token = cancel or CancellationToken()
    raw = collect(
        request["plan"],
        workspace=workspace,
        source=source,
        contexts=request["contexts"],
        store=store,
        cancel=token,
    )
    current = raw
    error: CppulseError | None = None
    records = []
    if (
        raw.manifest.get("input_verification") == "verified"
        and not token.is_cancelled()
    ):
        try:
            current = _derive(
                raw,
                workspace=workspace,
                store=store,
                operation="collection-request",
                documents=[("collection_request", request)],
                reason="Explicit public request retained; no additional commands executed.",
            )
        except (InputChanged, IntegrityError) as problem:
            error = problem
            current = _unavailable_attempt(
                raw, problem, store=store, operation="collect"
            )
    elif raw.manifest.get("input_verification") != "verified":
        error = CompatibilityError(
            "Capture source is unverified; no derived transforms attempted",
            code="UNVERIFIED_SOURCE",
        )
    for item in request["normalizers"]:
        empty = {
            "id": item["id"],
            "kind": item["kind"],
            "status": "not_attempted",
            "outcome": None,
            "usability": None,
            "fact_artifacts": [],
            "run": None,
            "reason": "Collection cancelled or source binding unavailable; no transform attempted.",
        }
        if (
            token.is_cancelled()
            or raw.manifest.get("input_verification") != "verified"
            or isinstance(error, (InputChanged, IntegrityError))
        ):
            records.append(empty)
            continue
        try:
            _mutable_parent(current)
            ensure_current_materials(current, workspace)
            child = _normalize(current, item, workspace, store)
            previous = current
            current = child
            ensure_current_materials(child, workspace)
            records.append(_record(previous, child, item))
        except (CompatibilityError, ContractError) as problem:
            error = problem
            records.append({**empty, "status": "unavailable", "reason": str(problem)})
            blob_id = _id(
                "normalization-error:" + item["id"] + ":" + current.manifest_sha256
            )
            diagnostic = RetainedBlob(
                blob_id,
                "workflows/errors/" + blob_id + ".json",
                _bytes(problem.as_dict()),
            )
            try:
                current = _derive(
                    current,
                    workspace=workspace,
                    store=store,
                    operation="normalizer-unavailable",
                    blobs=[diagnostic],
                    partial=True,
                    reason="Requested normalizer unavailable: "
                    + item["id"]
                    + "; "
                    + str(problem),
                )
            except (InputChanged, IntegrityError) as publication_problem:
                error = publication_problem
                current = _unavailable_attempt(
                    current, publication_problem, store=store, operation="collect"
                )
                break
        except (InputChanged, IntegrityError) as problem:
            error = problem
            records.append({**empty, "status": "unavailable", "reason": str(problem)})
            current = _unavailable_attempt(
                current, problem, store=store, operation="collect"
            )
            break
    attempted = {row["id"] for row in records}
    for item in request["normalizers"]:
        if item["id"] not in attempted:
            records.append(
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "status": "not_attempted",
                    "outcome": None,
                    "usability": None,
                    "fact_artifacts": [],
                    "run": None,
                    "reason": "Current material changed; no subsequent transform attempted.",
                }
            )
    status = (
        "cancelled"
        if token.is_cancelled() or raw.manifest["status"] == "cancelled"
        else (
            "partial"
            if error
            or current.manifest["status"] != "completed"
            or any(row["status"] != "completed" for row in records)
            else "completed"
        )
    )
    if status == "cancelled" and error is not None:
        error = CppulseError(
            "Cancellation requested; retained capture issue: " + str(error),
            code="CANCELLED",
        )
    if status == "cancelled" and current.manifest["status"] != "cancelled":
        error = error or CppulseError(
            "Cancellation requested after capture; transforms were stopped",
            code="CANCELLED",
        )
        current = _unavailable_attempt(
            current, error, store=store, operation="collect", status="cancelled"
        )
    result = workflow_result(
        "collect",
        store,
        status=status,
        reason="Explicit capture "
        + status
        + "; producer/test outcomes are retained separately from policy acceptance.",
        raw=raw,
        final=current,
        error=error,
    )
    result["normalizers"] = records
    validate("workflow_result", result)
    return result


_ASSESSMENT_METADATA = {"policy", "assessment", "assessment_lineage"}


def _same_facts(base: dict[str, Any], candidate: dict[str, Any]) -> None:
    for key in ["source", "contexts", "config_digest", "status", "input_verification"]:
        if candidate.get(key) != base.get(key):
            raise ContractError(
                "Assessment lineage changes original " + key, code="INVALID_LINEAGE"
            )
    original = {entry["id"]: entry for entry in base["artifacts"]}
    current = {entry["id"]: entry for entry in candidate["artifacts"]}
    if any(current.get(identifier) != entry for identifier, entry in original.items()):
        raise ContractError(
            "Assessment lineage changed or removed original fact bytes/descriptors",
            code="INVALID_LINEAGE",
        )
    if any(
        entry.get("contract", {}).get("kind") not in _ASSESSMENT_METADATA
        for identifier, entry in current.items()
        if identifier not in original and "contract" in entry
    ):
        raise ContractError(
            "Assessment lineage contains new producer facts", code="INVALID_LINEAGE"
        )


def _manifest_blob(
    snapshot: RunSnapshot, identifier: str, reference: dict[str, Any]
) -> dict[str, Any]:
    content = snapshot.read_bytes(identifier)
    if hashlib.sha256(content).hexdigest() != reference["manifest_sha256"]:
        raise IntegrityError("Archived ancestor manifest differs from its lineage pin")
    try:
        manifest = json.loads(content)
    except (ValueError, UnicodeError) as error:
        raise ContractError(
            "Archived ancestor manifest is malformed", code="INVALID_LINEAGE"
        ) from error
    validate("run_manifest", manifest)
    if (
        manifest["run_id"] != reference["run_id"]
        or manifest["source"]["digest"] != reference["source_digest"]
        or manifest["status"] != reference["status"]
    ):
        raise ContractError(
            "Archived ancestor manifest identity differs from its pin",
            code="INVALID_LINEAGE",
        )
    return manifest


def _assessment_base(snapshot: RunSnapshot) -> RunSnapshot:
    snapshot.verify()
    if snapshot.manifest.get("input_verification") != "verified":
        raise CompatibilityError(
            "Unverified historical execution cannot be upgraded by today's source check",
            code="UNVERIFIED_SOURCE",
        )
    documents = read_documents(snapshot)
    assessments = documents.get("assessment", [])
    lineage = documents.get("assessment_lineage", [])
    if not assessments:
        if lineage or "policy" in documents:
            raise ContractError(
                "Facts base has unsupported standalone assessment metadata",
                code="INVALID_LINEAGE",
            )
        return snapshot
    if len(assessments) != 1 or len(lineage) != 1 or "policy" not in documents:
        raise ContractError(
            "Reassessment requires the bounded typed assessment lineage protocol",
            code="INVALID_LINEAGE",
        )
    selected = lineage[0]
    reference = selected["facts_base_run"]
    reader = RunStore.open_existing(snapshot.path.parents[1])
    base = reader.open_run(
        reference["run_id"], manifest_sha256=reference["manifest_sha256"]
    )
    if run_reference(base) != reference:
        raise ContractError(
            "Reopened facts base differs from its original identity",
            code="INVALID_LINEAGE",
        )
    base_documents = read_documents(base)
    if any(base_documents.get(kind) for kind in _ASSESSMENT_METADATA):
        raise ContractError(
            "Recorded facts base is already assessed", code="INVALID_LINEAGE"
        )
    if (
        _manifest_blob(snapshot, selected["base_manifest_artifact_id"], reference)
        != base.manifest
    ):
        raise ContractError(
            "Archived base differs from the reopened original", code="INVALID_LINEAGE"
        )
    previous = _manifest_blob(
        snapshot,
        selected["parent_manifest_artifact_id"],
        selected["selected_parent_run"],
    )
    _same_facts(base.manifest, previous)
    _same_facts(base.manifest, snapshot.manifest)
    active = {
        entry["id"]
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") in _ASSESSMENT_METADATA
    }
    allowed = {
        *active,
        *selected["history_artifact_ids"],
        selected["base_manifest_artifact_id"],
        selected["parent_manifest_artifact_id"],
    }
    original = {entry["id"] for entry in base.manifest["artifacts"]}
    if {entry["id"] for entry in snapshot.manifest["artifacts"]} != original | allowed:
        raise ContractError(
            "Assessment lineage has undeclared extra material", code="INVALID_LINEAGE"
        )
    if selected["created_at"] != assessments[0]["generated_at"]:
        raise ContractError(
            "Active assessment clock differs from its lineage", code="INVALID_LINEAGE"
        )
    return base


def _assess_current(
    snapshot: RunSnapshot,
    policy: dict[str, Any],
    *,
    workspace: Path,
    store: RunStore | Path,
) -> dict[str, Any]:
    """Assess or reassess original checked facts at current UTC, without commands.

    Old active decisions become byte-identical generic history in a new run.
    Original producer facts remain unchanged; source and every finite generated
    output are checked before evaluation and immediately before publication.
    """
    from uuid import uuid4
    from cppulse.contracts import validate_evaluation_policy
    from cppulse.policy import evaluate_policy

    policy = deepcopy(policy)
    validate_evaluation_policy(policy)
    target = (store.root if isinstance(store, RunStore) else Path(store)).absolute()
    if target != snapshot.path.parents[1]:
        raise ContractError(
            "Assessment/reassessment requires the same local store as its original facts base",
            code="INVALID_LINEAGE",
        )
    base = _assessment_base(snapshot)
    ensure_current_materials(base, workspace)
    generated_at = _now()
    run_id = uuid4().hex
    prospective = base.manifest
    prospective["run_id"] = run_id
    bundle = read_documents(base)
    bundle["run_manifest"] = prospective
    # All policy/contract errors are resolved before opening a writer stage.
    assessment = evaluate_policy(policy, bundle, generated_at=generated_at)
    metadata_cap, _ = _limits(base)
    if any(len(_bytes(document)) > metadata_cap for document in [policy, assessment]):
        raise IntegrityError("Assessment/policy exceeds max_metadata_bytes")
    policy_id, assessment_id, lineage_id = (
        _id(label + ":" + run_id)
        for label in ["policy", "assessment", "assessment-lineage"]
    )
    base_blob_id = _id("facts-base-manifest:" + base.manifest_sha256)
    parent_blob_id = _id("assessed-parent-manifest:" + snapshot.manifest_sha256)
    original = {entry["id"] for entry in base.manifest["artifacts"]}
    history = sorted(
        {entry["id"] for entry in snapshot.manifest["artifacts"]}
        - original
        - {base_blob_id, parent_blob_id}
    )
    lineage = {
        "version": "2.0.0",
        "id": lineage_id,
        "source_digest": base.manifest["source"]["digest"],
        "facts_base_run": run_reference(base),
        "selected_parent_run": run_reference(snapshot),
        "base_manifest_artifact_id": base_blob_id,
        "parent_manifest_artifact_id": parent_blob_id,
        "policy_artifact_id": policy_id,
        "assessment_artifact_id": assessment_id,
        "history_artifact_ids": history,
        "created_at": generated_at,
    }
    validate("assessment_lineage", lineage)
    if len(_bytes(lineage)) > metadata_cap:
        raise IntegrityError("Assessment lineage exceeds max_metadata_bytes")
    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with runtime.begin(run_id) as stage:
        for artifact in snapshot.manifest["artifacts"]:
            active_contract = (
                artifact.get("contract") if artifact["id"] in original else None
            )
            copied = stage.copy_artifact(
                artifact["id"],
                snapshot.path / artifact["path"],
                artifact["path"],
                artifact["media_type"],
                contract=active_contract,
            )
            expected = deepcopy(artifact)
            if active_contract is None:
                expected.pop("contract", None)
            if copied != expected:
                raise IntegrityError(
                    "Assessment history copy changed original bytes or identities"
                )
        copied_ids = {entry["id"] for entry in stage.artifacts}
        with tempfile.TemporaryDirectory(prefix="cppulse-assessment-") as temporary:
            for identifier, parent in [
                (base_blob_id, base),
                (parent_blob_id, snapshot),
            ]:
                content = parent.read_manifest_bytes()
                if len(content) > metadata_cap:
                    raise IntegrityError("Ancestor manifest exceeds max_metadata_bytes")
                if identifier not in copied_ids:
                    path = Path(temporary) / identifier
                    path.write_bytes(content)
                    stage.copy_artifact(
                        identifier,
                        path,
                        "workflows/assessment-history/" + identifier + ".json",
                        "application/json",
                    )
                    copied_ids.add(identifier)
        for kind, identifier, document in [
            ("policy", policy_id, policy),
            ("assessment", assessment_id, assessment),
            ("assessment_lineage", lineage_id, lineage),
        ]:
            stage.write_json(
                "workflows/" + kind + "/" + identifier + ".json",
                document,
                contract=kind,
                artifact_id=identifier,
            )
        manifest = snapshot.manifest
        manifest.update(run_id=run_id, artifacts=stage.artifacts)
        # The run window describes retained producer execution. Assessment has
        # its own actual clock, rather than pretending that producers reran.
        manifest["started_at"] = base.manifest["started_at"]
        manifest["finished_at"] = base.manifest["finished_at"]
        manifest["versions"].update(
            {
                "cppulse.workflows": __version__,
                "cppulse.policy": assessment["evaluator"]["version"],
            }
        )
        manifest["limitations"] = list(
            dict.fromkeys(
                [
                    *manifest["limitations"],
                    "Assessment-only derivation retains the producer execution window and exact historical decisions; the sole active assessment uses its own recorded UTC time. No project commands were rerun.",
                ]
            )
        )
        manifest["stages"].append(
            {
                "id": _id("assess:" + run_id),
                "status": "passed",
                "depends_on": [],
                "reason": "Pure policy evaluation completed; gate="
                + assessment["gate"]
                + ". This stage does not change producer outcomes.",
            }
        )
        if len(_bytes(manifest)) > metadata_cap:
            raise IntegrityError("Assessment manifest exceeds max_metadata_bytes")
        child = stage.publish(
            manifest, source_check=lambda: ensure_current_materials(base, workspace)
        )
    gate = assessment["gate"]
    result = workflow_result(
        "assess",
        store,
        status="completed" if gate == "passed" else gate,
        reason="Current-time policy evaluation: "
        + gate
        + "; original producer facts were not rerun.",
        raw=snapshot,
        final=child,
    )
    result.update(
        facts_base_run=run_reference(base),
        assessment_artifact_id=assessment_id,
        policy_gate=gate,
    )
    validate("workflow_result", result)
    return result


def check_policy(
    snapshot: RunSnapshot,
    policy: dict[str, Any],
    *,
    workspace: Path,
    store: RunStore | Path,
) -> dict[str, Any]:
    """Run a current policy check over retained facts; collect no new evidence."""
    from cppulse.identities import digest_json

    result = assess_run(snapshot, policy, workspace=workspace, store=store)
    checked = {
        "version": "2.0.0",
        "mode": "policy",
        "store": result["store"],
        "status": "passed" if result["status"] == "completed" else result["status"],
        "exit_code": result["exit_code"],
        "reason": result["reason"],
        "run": result["final_run"],
        "facts_base_run": result["facts_base_run"],
        "assessment_artifact_id": result["assessment_artifact_id"],
        "comparison_artifact_id": None,
        "policy_sha256": digest_json(policy),
        "baseline_sha256": None,
        "error": result["error"],
    }
    validate("check_result", checked)
    return checked


def _unavailable_attempt(
    snapshot: RunSnapshot,
    problem: CppulseError,
    *,
    store: RunStore | Path,
    operation: str,
    status: str = "partial",
) -> RunSnapshot:
    """Advance latest-attempt with an honest gap and an exact historical link.

    No prior positive contract is activated under an unverified current source.
    The compact parent-manifest link keeps tight metadata quotas usable; all
    original facts/decisions remain unchanged in the selected historical run.
    """
    snapshot.verify()
    metadata_cap, artifact_cap = _limits(snapshot)
    parent_bytes = snapshot.read_manifest_bytes()
    if len(parent_bytes) > metadata_cap:
        raise IntegrityError(
            "Unavailable-attempt parent manifest exceeds its retained metadata cap"
        )
    reason = (problem.code + ": " + str(problem))[:1500]
    parent_id = _id("unavailable-parent:" + snapshot.manifest_sha256)
    diagnostic_id = _id(
        "unavailable:" + operation + ":" + snapshot.manifest_sha256 + ":" + reason
    )
    bounded_error = problem.as_dict()
    bounded_error["message"] = bounded_error["message"][:1500]
    diagnostic = {
        "operation": operation,
        "status": "unavailable",
        "selected_parent_run": run_reference(snapshot),
        "parent_manifest_artifact_id": parent_id,
        "error": bounded_error,
        "reason": "No current positive proof or policy decision is asserted. Historical facts remain in the pinned selected parent.",
    }
    content = _bytes(diagnostic)
    if len(content) > metadata_cap:
        raise IntegrityError(
            "Unavailable-attempt diagnostic exceeds max_metadata_bytes"
        )
    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with runtime.begin() as stage:
        with tempfile.TemporaryDirectory(prefix="cppulse-unavailable-") as temporary:
            for identifier, data in [
                (parent_id, parent_bytes),
                (diagnostic_id, content),
            ]:
                path = Path(temporary) / identifier
                path.write_bytes(data)
                stage.copy_artifact(
                    identifier,
                    path,
                    "workflows/unavailable/" + identifier + ".json",
                    "application/json",
                )
        stamp = _now()
        source = snapshot.manifest["source"]
        source["limitations"] = list(
            dict.fromkeys(
                [
                    *source["limitations"],
                    "Historical selected source identity retained only for comparison; this attempt does not verify the current source or generated material.",
                ]
            )
        )
        manifest = {
            "version": "2.0.0",
            "run_id": stage.run_id,
            "status": status,
            "source": source,
            "contexts": [],
            "stages": [
                {
                    "id": diagnostic_id,
                    "status": "error",
                    "depends_on": [],
                    "reason": reason,
                }
            ],
            "artifacts": stage.artifacts,
            "started_at": stamp,
            "finished_at": stamp,
            "config_digest": snapshot.manifest["config_digest"],
            "versions": {
                "cppulse.workflows": __version__,
                "workflow_max_metadata_bytes": str(metadata_cap),
                "workflow_max_artifact_bytes": str(artifact_cap),
            },
            "limitations": [
                "Current workflow attempt is unavailable: " + reason,
                "No active assessment or producer verification was copied. Exact selected-parent manifest and run/hash pin link to unchanged historical facts.",
            ],
        }
        if len(_bytes(manifest)) > metadata_cap:
            raise IntegrityError(
                "Compact unavailable-attempt manifest exceeds max_metadata_bytes"
            )
        return stage.publish(manifest)


def assess_run(
    snapshot: RunSnapshot,
    policy: dict[str, Any],
    *,
    workspace: Path,
    store: RunStore | Path,
) -> dict[str, Any]:
    """Assess retained current material or persist an explicit unavailable attempt.

    Current source/output mismatches return exit3 with a new partial, unverified
    latest-attempt. Historical completed decisions remain at their original pins.
    """
    try:
        return _assess_current(snapshot, policy, workspace=workspace, store=store)
    except (InputChanged, CompatibilityError) as problem:
        if (
            isinstance(problem, CompatibilityError)
            and problem.code != "UNVERIFIED_SOURCE"
        ):
            raise
        base_ref = None
        if snapshot.manifest.get("input_verification") == "verified":
            base_ref = run_reference(_assessment_base(snapshot))
        attempt = _unavailable_attempt(
            snapshot, problem, store=store, operation="assess"
        )
        result = workflow_result(
            "assess",
            store,
            status="insufficient_evidence",
            reason="Current assessment unavailable; historical gate is not reused. "
            + str(problem),
            raw=snapshot,
            final=attempt,
            error=problem,
        )
        result["facts_base_run"] = base_ref
        validate("workflow_result", result)
        return result


def _retained_reference(reference: dict[str, Any], directory: Path) -> Any:
    from cppulse.transfer import open_bundle

    if reference["source"] == "local_run":
        location = Path(reference["store"])
        location = location if location.is_absolute() else directory / location
        return RunStore.open_existing(location).open_run(
            reference["run_id"], manifest_sha256=reference["manifest_sha256"]
        )
    location = Path(reference["bundle"])
    location = location if location.is_absolute() else directory / location
    result = open_bundle(location).open_run(reference["root_id"])
    if result.manifest_sha256 != reference["manifest_sha256"]:
        raise IntegrityError("Transferred root differs from the explicit manifest pin")
    return result


def _json_control(content: bytes) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise ContractError("Control JSON contains duplicate keys")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ContractError("Control JSON contains nonfinite values")

    try:
        document = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContractError("Invalid control JSON: " + str(error)) from error
    if not isinstance(document, dict):
        raise ContractError("Control JSON must contain an object")
    return document


def _read_control_bytes(path: Path, cap: int) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("Selected control must be a regular file")
        content = stream.read(cap + 1)
        after = os.fstat(stream.fileno())
    if len(content) > cap:
        raise IntegrityError("Selected control exceeds the effective metadata cap")
    if (
        before.st_dev,
        before.st_ino,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_size,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_size,
    ):
        raise ContractError("Selected control changed while reading")
    return content


def create_baseline(
    snapshot: RunSnapshot,
    request: dict[str, Any],
    *,
    workspace: Path,
    store: RunStore | Path,
) -> dict[str, Any]:
    """Persist an explicit reviewed finding baseline; do not run an analyzer."""
    from cppulse.findings import create_finding_baseline

    request = deepcopy(request)
    validate("finding_baseline_request", request)
    try:
        ensure_current_materials(snapshot, workspace)
        _mutable_parent(snapshot)
        if any(
            row["id"] == request["baseline_id"]
            for row in read_documents(snapshot).get("finding_baseline", [])
        ):
            raise ContractError(
                "Baseline ID is already retained; choose a new ID and explicit reason"
            )
        produced = create_finding_baseline(
            snapshot,
            baseline_id=request["baseline_id"],
            scope_files=request["scope_files"],
            context_ids=request["context_ids"],
            rule_ids=request["rule_ids"],
            reason=request["reason"],
            created_at=_now(),
        )
        child = _derive(
            snapshot,
            workspace=workspace,
            store=store,
            operation="finding-baseline",
            documents=[("finding_baseline", produced.document)],
            blobs=produced.artifacts,
            reason="Explicit finding baseline retained; no observations suppressed and no policy acceptance asserted.",
        )
        artifact = next(
            row
            for row in child.manifest["artifacts"]
            if row.get("contract", {}).get("kind") == "finding_baseline"
            and child.read_json(row["id"])["id"] == produced.document["id"]
        )
        result = workflow_result(
            "baseline",
            store,
            status="completed",
            reason="Baseline record created; inspect selected cells and limitations. Creation is not a passing check.",
            raw=snapshot,
            final=child,
        )
        result["baseline_artifact_id"] = artifact["id"]
    except (InputChanged, CompatibilityError) as problem:
        if (
            isinstance(problem, CompatibilityError)
            and problem.code != "UNVERIFIED_SOURCE"
        ):
            raise
        child = _unavailable_attempt(
            snapshot, problem, store=store, operation="baseline"
        )
        result = workflow_result(
            "baseline",
            store,
            status="insufficient_evidence",
            reason="Current baseline unavailable: " + str(problem),
            raw=snapshot,
            final=child,
            error=problem,
        )
    validate("workflow_result", result)
    return result


def check_findings(
    snapshot: RunSnapshot,
    request: dict[str, Any],
    *,
    workspace: Path,
    store: RunStore | Path,
    request_root: Path | None = None,
) -> dict[str, Any]:
    """Compare exact checked finding scopes; never imply an evidence-policy pass."""
    from cppulse.findings import compare_findings

    request = deepcopy(request)
    validate("finding_check_request", request)
    directory = request_root or Path.cwd()
    try:
        ensure_current_materials(snapshot, workspace)
        _mutable_parent(snapshot)
        baseline = _retained_reference(request["baseline"], directory)
        records = []
        raw = None
        if "suppressions" in request:
            selected = request["suppressions"]
            if selected["source"] == "file":
                location = Path(selected["path"])
                raw = _read_control_bytes(
                    location if location.is_absolute() else directory / location,
                    _limits(snapshot)[0],
                )
            else:
                owner = _retained_reference(selected, directory)
                raw = owner.read_bytes(selected["artifact_id"])
                if len(raw) > _limits(snapshot)[0]:
                    raise IntegrityError(
                        "Suppression artifact exceeds the effective metadata cap"
                    )
            document = _json_control(raw)
            validate("finding_suppressions", document)
            records = document["records"]
        produced = compare_findings(
            snapshot,
            baseline,
            baseline_artifact_id=request["baseline"]["artifact_id"],
            scope_files=request["scope_files"],
            context_ids=request["context_ids"],
            rule_ids=request["rule_ids"],
            generated_at=_now(),
            rename_map=request.get("rename_map"),
            suppressions=records,
            suppression_bytes=raw,
            max_new=request["max_new"],
        )
        child = _derive(
            snapshot,
            workspace=workspace,
            store=store,
            operation="finding-check",
            documents=[("finding_comparison", produced.document)],
            blobs=produced.artifacts,
            reason="Finding regression comparison retained; this is separate from evidence-policy acceptance.",
        )
        artifact = next(
            row
            for row in child.manifest["artifacts"]
            if row.get("contract", {}).get("kind") == "finding_comparison"
            and child.read_json(row["id"])["id"] == produced.document["id"]
        )
        gate = produced.document["gate"]
        result = {
            "version": "2.0.0",
            "mode": "findings",
            "store": str(
                (store.root if isinstance(store, RunStore) else Path(store)).absolute()
            ),
            "status": gate,
            "exit_code": {"passed": 0, "failed": 1, "insufficient_evidence": 3}[gate],
            "reason": "Finding regression gate="
            + gate
            + "; no evidence-policy acceptance was evaluated.",
            "run": run_reference(child),
            "facts_base_run": None,
            "assessment_artifact_id": None,
            "comparison_artifact_id": artifact["id"],
            "policy_sha256": None,
            "baseline_sha256": produced.document["baseline_sha256"],
            "error": None,
        }
    except (InputChanged, CompatibilityError) as problem:
        if (
            isinstance(problem, CompatibilityError)
            and problem.code != "UNVERIFIED_SOURCE"
        ):
            raise
        child = _unavailable_attempt(
            snapshot, problem, store=store, operation="finding-check"
        )
        result = {
            "version": "2.0.0",
            "mode": "findings",
            "store": str(
                (store.root if isinstance(store, RunStore) else Path(store)).absolute()
            ),
            "status": "insufficient_evidence",
            "exit_code": 3,
            "reason": "Current finding check unavailable: " + str(problem),
            "run": run_reference(child),
            "facts_base_run": None,
            "assessment_artifact_id": None,
            "comparison_artifact_id": None,
            "policy_sha256": None,
            "baseline_sha256": None,
            "error": problem.as_dict(),
        }
    validate("check_result", result)
    return result


def compare_runs(
    snapshot: RunSnapshot,
    *,
    upstream_bundle: Path,
    upstream_root_id: str,
    upstream_manifest_sha256: str,
    upstream_subject_id: str,
    local_subject_id: str,
    upstream_matrix_id: str,
    local_matrix_id: str,
    workspace: Path,
    store: RunStore | Path,
) -> dict[str, Any]:
    """Retain scoped consumer correspondence without promoting imported claims.

    The imported descriptor and explicit manifest pin are checked before any
    derived writer opens. A completed operation is not a local test or policy
    pass; the consumer comparison retains its own compatibility and gap states.
    """
    from cppulse.consumer import compare_consumers
    from cppulse.transfer import open_bundle

    upstream = open_bundle(upstream_bundle).open_run(upstream_root_id)
    if upstream.manifest_sha256 != upstream_manifest_sha256:
        raise IntegrityError("Selected upstream manifest pin does not match bundle")
    try:
        ensure_current_materials(snapshot, workspace)
        _mutable_parent(snapshot)
        produced = compare_consumers(
            upstream,
            snapshot,
            upstream_subject_id=upstream_subject_id,
            local_subject_id=local_subject_id,
            upstream_matrix_id=upstream_matrix_id,
            local_matrix_id=local_matrix_id,
            generated_at=_now(),
        )
        child = _derive(
            snapshot,
            workspace=workspace,
            store=store,
            operation="consumer-comparison",
            documents=[("consumer_comparison", produced.document)],
            blobs=produced.artifacts,
            reason="Scoped consumer correspondence retained; foreign claims remain imported and local test gaps remain explicit.",
        )
        artifact = next(
            row
            for row in child.manifest["artifacts"]
            if row.get("contract", {}).get("kind") == "consumer_comparison"
            and child.read_json(row["id"])["id"] == produced.document["id"]
        )
        result = workflow_result(
            "compare",
            store,
            status="completed",
            reason="Consumer comparison created; inspect compatibility and missing local checks separately from operation completion.",
            raw=snapshot,
            final=child,
        )
        result["comparison_artifact_id"] = artifact["id"]
    except (InputChanged, CompatibilityError) as problem:
        if (
            isinstance(problem, CompatibilityError)
            and problem.code != "UNVERIFIED_SOURCE"
        ):
            raise
        child = _unavailable_attempt(
            snapshot, problem, store=store, operation="compare"
        )
        result = workflow_result(
            "compare",
            store,
            status="insufficient_evidence",
            reason="Current local consumer material unavailable: " + str(problem),
            raw=snapshot,
            final=child,
            error=problem,
        )
    result["upstream_run"] = run_reference(upstream)
    validate("workflow_result", result)
    return result
