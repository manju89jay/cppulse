"""One checked snapshot projection for JSON, HTML, PDF and HTTP consumers.

Only retained contract bytes are read. No live source discovery, tool execution,
policy evaluation or mutable latest resolution occurs here. The caller supplies
an already pinned snapshot; renderers copy its stored assessment values.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping
from urllib.parse import quote

from jinja2 import Environment, PackageLoader, StrictUndefined

from cppulse.contracts import validate
from cppulse.contracts.presentation import assessment_display, fact_summary
from cppulse.errors import ContractError, CppulseError, IntegrityError
from cppulse.run_store import RunSnapshot

_LEGACY = ("findings", "git_metrics", "risk_scores", "roadmap")
_LIMITS = [
    "Experimental local prototype. Stored assessments describe their recorded scope and time.",
    "Collection status records execution completion. The stored assessment supplies the policy gate.",
    "Legacy health and ranking are experimental descriptive outputs with no demonstrated prediction accuracy or safety assurance.",
]


def _select(
    artifacts: list[dict[str, Any]], kind: str, version: str, identifier: str | None
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in artifacts
        if row.get("contract") == {"kind": kind, "version": version}
    ]
    if identifier is not None:
        if not isinstance(identifier, str):
            raise ContractError("Artifact selection must use a retained artifact ID")
        candidates = [row for row in candidates if row["id"] == identifier]
        if len(candidates) != 1:
            raise ContractError(
                f"Selected artifact ID is absent or is not typed {kind}/{version}: {identifier!r}"
            )
    elif len(candidates) > 1:
        raise ContractError(
            f"Multiple {kind} artifacts are ambiguous; select an explicit artifact ID"
        )
    return candidates[0] if candidates else None


def _payload(
    snapshot: RunSnapshot, artifact: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    content = snapshot.read_bytes(artifact["id"])
    if (
        len(content) != artifact["size_bytes"]
        or hashlib.sha256(content).hexdigest() != artifact["sha256"]
    ):
        raise IntegrityError(
            "Selected presentation bytes differ from original artifact"
        )
    try:
        text = content.decode("utf-8")
        document = json.loads(text)
    except (UnicodeError, ValueError) as error:
        raise ContractError(
            "Selected presentation artifact is not supported UTF-8 JSON"
        ) from error
    if not isinstance(document, dict):
        raise ContractError("Selected presentation contract must contain an object")
    reference = artifact["contract"]
    validate(reference["kind"], document, version=reference["version"])
    return {
        "artifact_id": artifact["id"],
        "sha256": artifact["sha256"],
        "size_bytes": artifact["size_bytes"],
        "raw_json": text,
    }, document


def _gaps(
    view: dict[str, Any], documents: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []

    def add(
        kind: str, identifier: str | None, message: str, artifacts: list[str]
    ) -> None:
        gap = {
            "kind": kind,
            "id": identifier,
            "message": message,
            "artifact_ids": artifacts,
        }
        if gap not in gaps:
            gaps.append(gap)

    run = view["run"]
    if run["status"] != "completed":
        add(
            "run",
            run["id"],
            "Collection status: "
            + run["status"]
            + ". Recorded partial facts remain available.",
            [],
        )
    if run["input_verification"] != "verified":
        add(
            "run",
            run["id"],
            "Finite selected inputs were not verified at publication.",
            [],
        )
    if not run["inventory_complete"]:
        add(
            "run",
            run["id"],
            "The source inventory is explicitly finite; unlisted additions are not detected.",
            [],
        )
    selected = view["assessment"]
    if selected is None:
        add(
            "assessment",
            None,
            "No stored assessment selected. Policy gate and scores are unavailable.",
            [],
        )
    else:
        for control in selected["display"]["controls"]:
            if control["status"] in {"failed", "unknown"} or control.get(
                "incomplete", False
            ):
                add(
                    "control",
                    control["id"],
                    control["reason"],
                    [selected["artifact_id"]],
                )
    for fact in view["facts"]:
        raw = documents[fact["artifact_id"]]
        if fact["usability"] not in {None, "usable"}:
            message = (
                "; ".join(fact["limitations"])
                or "Stored " + fact["kind"] + " usability: " + fact["usability"] + "."
            )
            add("fact", fact["id"], message, [fact["artifact_id"]])
        elif fact["status"] in {
            "failed",
            "error",
            "timed_out",
            "cancelled",
            "skipped",
            "not_attempted",
        }:
            core = raw.get("receipt", raw)
            message = (
                core.get("reason")
                or "Recorded " + fact["kind"] + " status: " + fact["status"] + "."
            )
            add("fact", fact["id"], message, [fact["artifact_id"]])
        if fact["kind"] == "consumer_comparison":
            for case in raw["cases"]:
                if case["status"] != "compatible" or case["missing_local_checks"]:
                    message = case["reason"]
                    if case["missing_local_checks"]:
                        message += " Missing local checks: " + ", ".join(
                            case["missing_local_checks"]
                        )
                    add("fact", fact["id"], message, [fact["artifact_id"]])
    return gaps


def build_snapshot_view(
    snapshot: RunSnapshot,
    *,
    assessment_artifact_id: str | None = None,
    legacy_artifact_ids: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build one validated envelope from a pinned, completely checked snapshot.

    Args:
        snapshot: Historical or current immutable run selected by its caller.
        assessment_artifact_id: Exact typed artifact ID; absent selects the only
            stored assessment, leaves an unassessed run explicit, or rejects
            ambiguous selection. Generic archived history cannot be selected.
        legacy_artifact_ids: None selects unique typed prototype documents.
            An explicit mapping selects only its named slots; {} disables all.

    Returns:
        A standalone snapshot_view v2 with original manifest/artifact JSON,
        lossless assessment display strings, facts and explicit optional data.
    """
    snapshot.verify()
    manifest_bytes = snapshot.read_manifest_bytes()
    manifest = snapshot.manifest
    artifacts = manifest["artifacts"]
    if legacy_artifact_ids is not None and (
        not isinstance(legacy_artifact_ids, Mapping)
        or not set(legacy_artifact_ids) <= set(_LEGACY)
    ):
        raise ContractError("Legacy selectors must name registered prototype slots")
    selected = _select(artifacts, "assessment", "2.0.0", assessment_artifact_id)
    assessment = None
    if selected is not None:
        assessment, document = _payload(snapshot, selected)
        assessment["display"] = assessment_display(
            document, raw_json=assessment["raw_json"]
        )
    facts = []
    documents = {}
    for artifact in artifacts:
        reference = artifact.get("contract", {})
        if reference.get("version") != "2.0.0" or reference.get("kind") in {
            "assessment",
            "snapshot_view",
        }:
            continue
        wrapper, document = _payload(snapshot, artifact)
        kind = reference["kind"]
        facts.append({"kind": kind, **wrapper, **fact_summary(kind, document)})
        documents[artifact["id"]] = document
    legacy = {}
    for kind in _LEGACY:
        if legacy_artifact_ids is not None and kind not in legacy_artifact_ids:
            legacy[kind] = None
            continue
        identifier = None if legacy_artifact_ids is None else legacy_artifact_ids[kind]
        selected = _select(artifacts, kind, "prototype_v1", identifier)
        legacy[kind] = None
        if selected is not None:
            wrapper, document = _payload(snapshot, selected)
            legacy[kind] = {**wrapper, "document": document}
    view = {
        "version": "2.0.0",
        "run_manifest_json": manifest_bytes.decode("utf-8"),
        "run": {
            "id": manifest["run_id"],
            "manifest_sha256": snapshot.manifest_sha256,
            "status": manifest["status"],
            "input_verification": manifest.get("input_verification", "unverified"),
            "source_digest": manifest["source"]["digest"],
            "inventory_complete": manifest["source"]["inventory_complete"],
            "started_at": manifest["started_at"],
            "finished_at": manifest["finished_at"],
            "config_digest": manifest["config_digest"],
            "limitations": deepcopy(manifest["limitations"]),
        },
        "source": deepcopy(manifest["source"]),
        "stages": deepcopy(manifest["stages"]),
        "contexts": deepcopy(manifest["contexts"]),
        "assessment": assessment,
        "facts": facts,
        "artifacts": deepcopy(artifacts),
        "legacy": legacy,
        "configuration": None,
        "gaps": [],
        "limitations": list(
            dict.fromkeys(
                [*manifest["limitations"], *manifest["source"]["limitations"], *_LIMITS]
            )
        ),
    }
    configurations = []
    for artifact in artifacts:
        if artifact["id"] == "effective_config-json":
            if artifact["size_bytes"] > 8 * 1024**2:
                raise ContractError("Retained configuration exceeds presentation byte limit")
            raw = snapshot.read_bytes(artifact["id"])
            document = json.loads(raw)
            if not isinstance(document, dict):
                raise ContractError("Retained configuration must contain an object")
            configurations.append({"artifact_id": artifact["id"], "sha256": artifact["sha256"],
                                   "size_bytes": artifact["size_bytes"], "raw_json": raw.decode("utf-8"),
                                   "document": document})
        elif artifact.get("contract") == {"kind": "collection_request", "version": "2.0.0"}:
            wrapper, request = _payload(snapshot, artifact)
            if "resolved_ruleset" in request:
                configurations.append({**wrapper, "document": request})
    if len(configurations) > 1:
        raise ContractError("Selected snapshot contains ambiguous retained configuration")
    if configurations:
        view["configuration"] = configurations[0]
    from cppulse.external import external_relationships

    external = [
        documents[f["artifact_id"]]
        for f in facts
        if f["kind"] == "external_analysis_facts"
    ]
    native = [documents[f["artifact_id"]] for f in facts if f["kind"] == "observations"]
    if external:
        view["external_relationships"] = external_relationships(external, native)
        view["limitations"].append(
            "External repeated diagnostics and potential location overlaps are retained claims, not independent confirmation. Hashes bind report bytes, not producer authenticity; confidence is not increased."
        )
    view["gaps"] = _gaps(view, documents)
    validate("snapshot_view", view)
    return view


def render_snapshot_json(view: dict[str, Any]) -> str:
    """Serialize the checked envelope without rebuilding policy outputs."""
    validate("snapshot_view", view)
    return (
        json.dumps(view, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n"
    )


def _artifact_url(view: dict[str, Any], identifier: str) -> str:
    return (
        "/api/v1/runs/"
        + quote(view["run"]["id"], safe="")
        + "/artifacts/"
        + quote(identifier, safe="")
        + "?manifest_sha256="
        + view["run"]["manifest_sha256"]
    )


def _short_id(identifier: str) -> str:
    return identifier if len(identifier) <= 32 else identifier[:18] + "..."


def _render_details(view: dict[str, Any]) -> dict[str, Any]:
    """Copy typed details into readable rows; never aggregate a policy result."""
    records = [
        (fact, json.loads(fact["raw_json"], parse_int=str, parse_float=str))
        for fact in view["facts"]
    ]
    inventories = {
        raw["id"]: raw for fact, raw in records if fact["kind"] == "analysis_inventory"
    }
    labels: dict[str, str] = {}
    evidence_refs: dict[str, list[str]] = {}
    fact_refs: dict[str, list[str]] = {}
    native_rows = []
    external_rows = []
    test_imports = []
    analysis = []
    coverage = []
    sanitizers = []
    comparisons = []
    measured_health = []
    measured_metrics = []
    evidence_records = []
    evidence_record_count = 0
    for fact, raw in records:
        identifier = fact["artifact_id"]
        kind = fact["kind"]
        if fact["id"] is not None:
            fact_refs.setdefault(fact["id"], []).append(identifier)
        if kind == "execution_facts":
            step = raw["receipt"]["id"]
            labels[identifier] = step + " material facts"
            for role in ["input_artifacts", "output_artifacts"]:
                for material in raw["binding"][role]:
                    labels[material["artifact_id"]] = material["path"]
            for stream, artifact_id in raw["binding"]["log_artifacts"].items():
                if artifact_id is not None:
                    labels[artifact_id] = step + " " + stream
        elif kind == "execution_receipt":
            labels[identifier] = raw["id"] + " receipt"
        elif kind == "evidence":
            for record in raw["records"]:
                evidence_record_count += 1
                if len(evidence_records) < 50:
                    evidence_records.append(
                        {"record": record, "artifact_id": identifier}
                    )
                evidence_refs.setdefault(record["id"], []).append(identifier)
                if "import_adapter" in record:
                    test_imports.append(record)
            labels[identifier] = "Recorded evidence"
        elif kind == "observations":
            inventory = inventories.get(raw.get("analysis_inventory_id"), {})
            job = inventory.get("job_context_id")
            labels[identifier] = "Typed observations" + (": " + job if job else "")
            for item in raw["items"]:
                native_rows.append(
                    {
                        "observation": item,
                        "job_context_id": job,
                        "artifact_id": identifier,
                    }
                )
        elif kind == "external_analysis_facts":
            labels[identifier] = raw["producer_namespace"] + " external observations"
            for item in raw["observations"]:
                external_rows.append(
                    {
                        "observation": item,
                        "namespace": raw["producer_namespace"],
                        "context_id": raw["context_id"],
                        "origin": raw["origin"],
                        "artifact_id": identifier,
                    }
                )
        elif kind == "analysis_inventory":
            labels[identifier] = "Analysis inventory: " + raw["job_context_id"]
            analysis.append({"fact": raw, "artifact_id": identifier})
        elif kind == "maintenance_health":
            labels[identifier] = "Measured maintenance health: " + raw["scorer"]["id"]
            measured_health.append({"fact": raw, "artifact_id": identifier})
        elif kind == "analysis_metrics":
            labels[identifier] = "Measured metrics: " + raw["job_context_id"]
            measured_metrics.append({"fact": raw, "artifact_id": identifier})
        elif kind == "coverage_facts":
            labels[identifier] = "Coverage: " + raw["context_id"]
            coverage.append({"fact": raw, "artifact_id": identifier})
        elif kind == "sanitizer_facts":
            labels[identifier] = raw["sanitizer"] + ": " + raw["context_id"]
            sanitizers.append({"fact": raw, "artifact_id": identifier})
        elif kind == "consumer_comparison":
            labels[identifier] = "Consumer comparison: " + _short_id(raw["id"])
            comparisons.append(raw)
        else:
            subject = raw.get("job_context_id", raw.get("context_id", raw.get("id")))
            labels[identifier] = kind + (": " + _short_id(subject) if subject else "")
    for artifact in view["artifacts"]:
        if artifact["id"] not in labels:
            path = artifact["path"]
            if path.startswith("artifacts/") and path.endswith(".blob"):
                path = artifact.get("contract", {}).get("kind", "Retained material")
            labels[artifact["id"]] = path

    def label(identifier: str) -> str:
        text = labels.get(identifier, "Retained artifact")
        return text + " [" + _short_id(identifier) + "]"

    def references(identifiers: list[str], role: str) -> list[dict[str, Any]]:
        index = evidence_refs if role == "evidence" else fact_refs
        result = []
        for identifier in identifiers:
            selected = index.get(identifier, [])
            if len(selected) == 1:
                result.append({"label": label(selected[0]), "artifact_id": selected[0]})
            else:
                # IDs from different fact namespaces are not guessed or merged.
                result.append({"label": _short_id(identifier), "artifact_id": None})
        return result

    return {
        "artifact_label": label,
        "references": references,
        "native_rows": native_rows,
        "external_rows": external_rows,
        "test_imports": test_imports,
        "evidence_records": evidence_records,
        "evidence_record_count": evidence_record_count,
        "analysis": analysis,
        "coverage": coverage,
        "sanitizers": sanitizers,
        "comparisons": comparisons,
        "measured_health": measured_health,
        "measured_metrics": measured_metrics,
    }


def render_snapshot_html(view: dict[str, Any]) -> str:
    """Render self-contained styled HTML; no plotting, HTTP or PDF extra is used."""
    validate("snapshot_view", view)
    environment = Environment(
        loader=PackageLoader("cppulse.report_engine", "templates"),
        autoescape=True,
        undefined=StrictUndefined,
    )
    environment.globals["artifact_url"] = lambda identifier: _artifact_url(
        view, identifier
    )
    details = _render_details(view)
    environment.globals.update(
        artifact_label=details["artifact_label"],
        references=details["references"],
        short_id=_short_id,
    )
    return environment.get_template("snapshot.html").render(
        view=view,
        **{
            key: value
            for key, value in details.items()
            if key not in {"artifact_label", "references"}
        },
        legacy={
            kind: None if slot is None else slot["document"]
            for kind, slot in view["legacy"].items()
        },
    )


def render_snapshot_pdf(view: dict[str, Any], *, base_url: str | None = None) -> bytes:
    """Render the same checked HTML with the optional local WeasyPrint backend.

    An explicit API origin resolves pinned raw-download link annotations. No
    server origin is invented for offline exports; artifact identities remain
    visible there. External document resource fetching is always disabled.
    """
    html = render_snapshot_html(view)
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as error:
        raise CppulseError(
            "PDF support is unavailable. Install cppulse[pdf] and the WeasyPrint system libraries; HTML and JSON remain available.",
            code="OPTIONAL_DEPENDENCY_MISSING",
        ) from error

    def reject_external(url: str, *args: Any, **kwargs: Any) -> Any:
        raise ValueError("Snapshot PDF has no external resource dependencies")

    return HTML(string=html, base_url=base_url, url_fetcher=reject_external).write_pdf()
