"""Measured maintenance calculations, distinct from consumer assurance.

Scores are experimental calibration choices. They never establish safety,
standards compliance, test coverage or calibrated prediction accuracy.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from cppulse.contracts import validate
from cppulse.contracts.maintenance import (
    BASE_CATEGORIES,
    FUNCTION_UNITS,
    METRIC_VERSION,
)
from cppulse.errors import ContractError
from cppulse.identities import digest_json
from cppulse.run_store import RunSnapshot, RunStore


def _unique(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        if row[key] in result:
            raise ContractError(f"Duplicate measured {key}: {row[key]}")
        result[row[key]] = row
    return result


def compute_maintenance_health(
    *,
    source_digest: str,
    inventories: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    registry: dict[str, Any],
    required_context_ids: list[str],
    optional_context_ids: list[str] | None = None,
    allow_inferred_parse: bool = False,
    profile: str = "default",
    expected_scopes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute unrounded physical-KLOC scores only for complete declared scope.

    Inputs are normalized contracts; execution authenticity remains the enclosing
    immutable run store's responsibility. Missing measurements and contexts yield
    null scores, including when an optional context happens to be complete.
    """
    optional = sorted(optional_context_ids or [])
    required = sorted(required_context_ids)
    if (
        len(set(required)) != len(required)
        or len(set(optional)) != len(optional)
        or set(required) & set(optional)
    ):
        raise ContractError("Maintenance job contexts must be distinct")
    if profile not in {"default", "safety-critical"}:
        raise ContractError("Unsupported maintenance profile")
    rules = _unique(registry["rules"], "id")
    categories = dict(BASE_CATEGORIES)
    if profile == "safety-critical":
        categories["misra"] = (2.5, 10)
    selected_rules = sorted(
        rule for rule, row in rules.items() if row["category"] in categories
    )
    method = {
        "id": "analyzed-kloc-context-v4",
        "version": "4.0.0",
        "profile": profile,
        "loc_metric": "physical_loc",
        "metric_version": METRIC_VERSION,
        "allow_inferred_parse": allow_inferred_parse,
        "requires_buffer_coherence": True,
        "required_rule_ids": selected_rules,
        "required_rule_versions": {
            rule: rules[rule]["version"] for rule in selected_rules
        },
        "categories": [
            {"category": name, "weight": weight, "density_cap": cap}
            for name, (weight, cap) in sorted(categories.items())
        ],
    }
    method["configuration_digest"] = digest_json(method)
    inventory_map = _unique(inventories, "id")
    scopes = _unique(expected_scopes or [], "job_context_id")
    for scope in scopes.values():
        validate("analysis_scope", scope)
        if scope["source_digest"] != source_digest:
            raise ContractError("Declared analysis scope differs from selected source")
    for kind, documents in (
        ("analysis_inventory", inventories),
        ("analysis_metrics", metrics),
        ("observations", observations),
    ):
        for document in documents:
            if document["source_digest"] != source_digest:
                raise ContractError(
                    "Measured source digest differs from selected source"
                )
            validate(kind, document)
    for document in metrics + observations:
        linked = inventory_map.get(document.get("analysis_inventory_id"))
        if linked is None:
            raise ContractError("Measured document has no selected analysis inventory")
        if (
            document in metrics
            and document["job_context_id"] != linked["job_context_id"]
        ):
            raise ContractError("Measured job context differs from inventory")
    _unique([row for document in observations for row in document["items"]], "id")
    _unique(observations, "analysis_inventory_id")
    for document in observations:
        linked = inventory_map[document["analysis_inventory_id"]]
        by_file = {row["file"]: row for row in linked["items"]}
        for row in document["items"]:
            native = by_file.get(row["file"])
            if native is None or row["context_id"] != native["parse_context_id"]:
                raise ContractError(
                    "Observation file/parse context differs from inventory"
                )
            if (
                row["rule_id"] not in rules
                or row["rule_version"] != rules[row["rule_id"]]["version"]
            ):
                raise ContractError("Observation rule version differs from registry")
    contexts = []
    weight_sum = sum(Fraction(str(weight)) for weight, _ in categories.values())
    for context in sorted(set(required + optional)):
        selected = [row for row in inventories if row["job_context_id"] == context]
        if not selected:
            continue
        ids = {row["id"] for row in selected}
        files = _unique(
            [row for inventory in selected for row in inventory["items"]], "file"
        )
        applicable = {
            file: row for file, row in files.items() if row["status"] != "excluded"
        }
        chosen = sorted(
            [
                row
                for document in metrics
                if document["analysis_inventory_id"] in ids
                for row in document["items"]
                if row["metric_version"] == METRIC_VERSION
            ],
            key=lambda row: row["id"],
        )
        _unique(chosen, "id")
        cells = {(row["file"], row["symbol"], row["metric"]): row for row in chosen}
        if len(cells) != len(chosen):
            raise ContractError("Duplicate measured metric cell in selected context")
        for row in chosen:
            native = files.get(row["file"])
            if native is None or row["context_id"] != native["parse_context_id"]:
                raise ContractError("Metric file/parse context differs from inventory")
        limits = []
        scope = scopes.get(context)
        if scope is not None:
            expected = {row["primary_file"]: row for row in scope["units"]}
            if set(files) != set(expected):
                limits.append(
                    "Selected inventories do not cover declared analysis scope."
                )
            if (
                not scope["inventory_complete"]
                or scope["discovery_gaps"]
                or scope["input_verification"] != "verified"
                or any(
                    row["execution"] is None
                    or row["parse_status"] not in {"analyzed", "excluded"}
                    or row["outcome"] != "complete"
                    for row in scope["units"]
                )
            ):
                limits.append(
                    "Declared work-unit scope has incomplete execution or inputs."
                )
        if ids - {document["analysis_inventory_id"] for document in observations}:
            limits.append("Missing selected observation document.")
        raw = [
            row
            for document in observations
            if document["analysis_inventory_id"] in ids
            for row in document["items"]
        ]
        for file, native in files.items():
            if native["finding_count"] != sum(row["file"] == file for row in raw):
                raise ContractError("Observation counts differ from native inventory")
        counts = {
            category: sum(
                row["rule_id"] in selected_rules
                and rules[row["rule_id"]]["category"] == category
                for row in raw
            )
            for category in categories
        }
        totals = {}
        for name in ("physical_loc", "code_loc"):
            references = [cells.get((file, None, name)) for file in applicable]
            totals[name] = (
                sum(row["value"] for row in references)
                if references
                and all(
                    row is not None and row["availability"] == "available"
                    for row in references
                )
                else None
            )
            if totals[name] is None:
                limits.append(f"Missing complete {name} measurement.")
        if not totals["physical_loc"]:
            limits.append("No nonzero measured physical source scope.")
        for inventory in selected:
            if not set(selected_rules) <= set(inventory["requested_rules"]) & set(
                inventory["enabled_rules"]
            ):
                limits.append("Required detectors are disabled or not requested.")
        inferred = False
        for file, native in applicable.items():
            if (
                native["status"] != "analyzed"
                or native["error_count"]
                or not set(selected_rules) <= set(native["executed_rules"])
            ):
                limits.append("Native file/rule scope is incomplete.")
            if native.get("buffer_coherence") != "verified":
                limits.append(
                    "Actual native TU buffer input coherence is unknown or mismatched."
                )
            permitted_inferred = (
                native.get("buffer_coherence") == "verified"
                and native["context_source"] == "inferred"
                and allow_inferred_parse
                and native["context_match"] != "mismatched"
            )
            if permitted_inferred:
                inferred = True
            elif (
                native["context_source"] != "database"
                or native["context_match"] != "matched"
            ):
                limits.append(
                    "Parse context is not matched to the required configuration."
                )
            functions = cells.get((file, None, "function_count"))
            symbols = {
                row["symbol"]
                for row in chosen
                if row["file"] == file and row["symbol"] is not None
            }
            if (
                functions is None
                or functions["availability"] != "available"
                or len(symbols) != functions["value"]
                or any(
                    (file, symbol, name) not in cells
                    or cells[(file, symbol, name)]["availability"] != "available"
                    for symbol in symbols
                    for name in FUNCTION_UNITS
                )
            ):
                limits.append("Function measurement inventory is incomplete.")
        complete = not limits
        calculations = []
        weighted = Fraction(0)
        for category, (weight, cap) in sorted(categories.items()):
            density = (
                Fraction(counts[category] * 1000, totals["physical_loc"])
                if complete
                else None
            )
            penalty = (
                min(Fraction(1), density / Fraction(str(cap))) if complete else None
            )
            if complete:
                weighted += Fraction(str(weight)) * penalty
            calculations.append(
                {
                    "category": category,
                    "count": counts[category],
                    "density": float(density) if complete else None,
                    "penalty": float(penalty) if complete else None,
                    "score": float(100 * (1 - penalty)) if complete else None,
                }
            )
        if inferred:
            limits.append(
                "Inferred parse opt-in supports maintenance only; consumer assurance is not assessed."
            )
        contexts.append(
            {
                "job_context_id": context,
                "availability": "scored" if complete else "partial",
                "analysis_inventory_ids": sorted(ids),
                "metric_ids": [row["id"] for row in chosen],
                "declared_files": (
                    len(scope["units"]) if scope is not None else len(files)
                ),
                "analyzed_files": sum(
                    row["status"] == "analyzed" and not row["error_count"]
                    for row in applicable.values()
                ),
                "excluded_files": len(files) - len(applicable),
                **totals,
                "parse_context_counts": {
                    name: sum(
                        row["context_source"] == name for row in applicable.values()
                    )
                    + (
                        len(
                            {row["primary_file"] for row in scope["units"]} - set(files)
                        )
                        if name == "none" and scope is not None
                        else 0
                    )
                    for name in ("database", "inferred", "fallback", "none")
                },
                "finding_counts": counts,
                "category_calculations": calculations,
                "weighted_penalty": float(weighted) if complete else None,
                "weight_sum": float(weight_sum),
                "overall": (
                    float(100 * (1 - weighted / weight_sum)) if complete else None
                ),
                "limitations": sorted(set(limits)),
            }
        )
    by_context = {row["job_context_id"]: row for row in contexts}
    missing = sorted(
        context
        for context in required
        if context not in by_context or by_context[context]["availability"] != "scored"
    )
    worst = (
        min(
            (by_context[context] for context in required),
            key=lambda row: (row["overall"], row["job_context_id"]),
        )
        if required and not missing
        else None
    )
    aggregate = {
        "availability": "scored" if worst else ("partial" if contexts else "no_data"),
        "overall": worst["overall"] if worst else None,
        "by_category": (
            {row["category"]: row["score"] for row in worst["category_calculations"]}
            if worst
            else dict.fromkeys(sorted(categories))
        ),
        "worst_context_id": worst["job_context_id"] if worst else None,
        "incomplete_required_context_ids": missing,
        "limitations": (
            [] if worst else ["Required context evidence is incomplete or absent."]
        ),
    }
    result = {
        "version": "2.0.0",
        "source_digest": source_digest,
        "scorer": method,
        "consumer_assurance": "not_assessed",
        "required_context_ids": required,
        "optional_context_ids": optional,
        "contexts": contexts,
        "aggregate": aggregate,
        "limitations": [
            "Calibration constants are experimental and not empirically validated."
        ],
    }
    result["id"] = "health-" + digest_json(result)
    validate("maintenance_health", result)
    return result


def measured_hotspot_calculation(
    *, change_frequency: int, complexity: int, finding_count: int, physical_loc: int
) -> dict[str, float]:
    """Calculate the shared versioned CC × activity × findings/KLOC formula.

    Counts must be nonnegative bounded integral values; a callable CC and a
    positive physical denominator are prerequisites, never inferred defaults.
    """
    values = [change_frequency, complexity, finding_count, physical_loc]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (isinstance(value, float) and value != value)
        or value < 0
        or value > 2**63 - 1
        or int(value) != value
        for value in values
    ):
        raise ContractError(
            "Measured hotspot counts must be bounded nonnegative integers"
        )
    if not complexity or not physical_loc:
        raise ContractError(
            "Measured hotspot needs callable complexity and physical LOC"
        )
    density = Fraction(int(finding_count) * 1000, int(physical_loc))
    return {
        "debt_density": float(density),
        "hotspot_score": float(int(change_frequency) * int(complexity) * density),
    }


def measured_hotspots(
    *,
    metrics: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    registry: dict[str, Any],
    git_metrics: dict[str, Any],
    job_context_id: str,
) -> dict[str, Any]:
    """Combine measured CC, history frequency and selected finding density."""
    rules = _unique(registry["rules"], "id")
    selected = [
        document for document in metrics if document["job_context_id"] == job_context_id
    ]
    inventory_ids = {document["analysis_inventory_id"] for document in selected}
    sources = {document["source_digest"] for document in selected}
    if len(sources) > 1:
        raise ContractError("Hotspot metrics refer to conflicting sources")
    for document in observations:
        if (
            document.get("analysis_inventory_id") in inventory_ids
            and document["source_digest"] not in sources
        ):
            raise ContractError("Hotspot observations refer to a different source")
    rows = [row for document in selected for row in document["items"]]
    findings = [
        row
        for document in observations
        if document.get("analysis_inventory_id") in inventory_ids
        for row in document["items"]
    ]
    _unique(findings, "id")
    items, unavailable = [], []
    for history in sorted(
        git_metrics.get("file_metrics", []), key=lambda row: row["file"]
    ):
        file = history["file"]
        cells = [
            row
            for row in rows
            if row["file"] == file and row["metric_version"] == METRIC_VERSION
        ]
        physical = [
            row
            for row in cells
            if row["metric"] == "physical_loc" and row["symbol"] is None
        ]
        function_count = [
            row
            for row in cells
            if row["metric"] == "function_count" and row["symbol"] is None
        ]
        cc = [row for row in cells if row["metric"] == "cyclomatic_complexity"]
        if (
            len(physical) != 1
            or physical[0]["availability"] != "available"
            or not physical[0]["value"]
            or len(function_count) != 1
            or function_count[0]["availability"] != "available"
            or len(cc) != function_count[0]["value"]
            or not cc
            or any(row["availability"] != "available" for row in cc)
        ):
            unavailable.append(
                {
                    "file": file,
                    "limitations": [
                        "Complete measured complexity and physical LOC are required."
                    ],
                }
            )
            continue
        observed = [
            row for row in findings if row["file"] == file and row["rule_id"] in rules
        ]
        for row in observed:
            if row["rule_version"] != rules[row["rule_id"]]["version"]:
                raise ContractError("Hotspot rule version differs from registry")
        complexity = max(row["value"] for row in cc)
        calculation = measured_hotspot_calculation(
            change_frequency=history["change_frequency"],
            complexity=complexity,
            finding_count=len(observed),
            physical_loc=physical[0]["value"],
        )
        items.append(
            {
                "file": file,
                "hotspot_score": calculation["hotspot_score"],
                "change_frequency": history["change_frequency"],
                "complexity_score": complexity,
                "debt_density": calculation["debt_density"],
                "finding_count": len(observed),
                "metric_ids": sorted(row["id"] for row in cells),
                "observation_ids": sorted(row["id"] for row in observed),
            }
        )
    return {
        "job_context_id": job_context_id,
        "items": sorted(items, key=lambda row: (-row["hotspot_score"], row["file"])),
        "unavailable_files": unavailable,
        "limitations": ["Hotspot priority is heuristic, not calibrated defect risk."],
    }


def measured_roadmap(
    *,
    observations: list[dict[str, Any]],
    registry: dict[str, Any],
    hotspots: dict[str, Any],
) -> dict[str, Any]:
    """Retain exact observation and metric links behind effort estimates."""
    rules = _unique(registry["rules"], "id")
    links = {row["file"]: row for row in hotspots["items"]}
    items = []
    for document in observations:
        for row in document["items"]:
            rule = rules[row["rule_id"]]
            hotspot = links.get(row["file"], {})
            items.append(
                {
                    "file": row["file"],
                    "rule_id": row["rule_id"],
                    "category": rule["category"],
                    "action": row["message"],
                    "estimated_hours": 1.0,
                    "effort_basis": "heuristic_estimate",
                    "observation_ids": [row["id"]],
                    "metric_ids": hotspot.get("metric_ids", []),
                    "priority_score": hotspot.get("hotspot_score", 0),
                }
            )
    items.sort(
        key=lambda row: (
            -row["priority_score"],
            row["file"],
            row["rule_id"],
            row["observation_ids"],
        )
    )
    return {
        "items": [dict(row, priority=index + 1) for index, row in enumerate(items)],
        "limitations": [
            "Effort estimates are heuristic and have not been empirically validated."
        ],
    }


def compare_maintenance_snapshots(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    """Compare only compatible scorer methods, declared contexts and file scope."""

    def scope(snapshot: dict[str, Any]) -> list[tuple[Any, ...]]:
        return sorted(
            (
                inventory["job_context_id"],
                row["file"],
                row["status"],
                row["parse_context_id"],
                row["context_source"],
                row["context_match"],
            )
            for inventory in snapshot["inventories"]
            for row in inventory["items"]
        )

    limits = []
    left, right = before["health"], after["health"]
    if left["scorer"] != right["scorer"]:
        limits.append("Maintenance method changed.")
    if (
        left["required_context_ids"] != right["required_context_ids"]
        or left["optional_context_ids"] != right["optional_context_ids"]
    ):
        limits.append("Declared job contexts changed.")
    if scope(before) != scope(after):
        limits.append("Selected source scope changed.")
    if left["aggregate"]["overall"] is None or right["aggregate"]["overall"] is None:
        limits.append("Complete health measurement is unavailable.")

    def cells(snapshot: dict[str, Any]) -> dict[tuple[Any, ...], dict[str, Any]]:
        return {
            (
                document["job_context_id"],
                row["file"],
                row["symbol"],
                row["metric"],
                row["metric_version"],
            ): row
            for document in snapshot["metrics"]
            for row in document["items"]
        }

    first, second = cells(before), cells(after)
    metrics = []
    for key in sorted(first.keys() | second.keys(), key=str):
        a, b = first.get(key), second.get(key)
        available = (
            not limits
            and a is not None
            and b is not None
            and a["availability"] == b["availability"] == "available"
        )
        metrics.append(
            {
                "job_context_id": key[0],
                "file": key[1],
                "symbol": key[2],
                "metric": key[3],
                "metric_version": key[4],
                "before": a["value"] if a else None,
                "after": b["value"] if b else None,
                "delta": b["value"] - a["value"] if available else None,
                "availability": "available" if available else "unavailable",
                "metric_ids": [row["id"] for row in (a, b) if row is not None],
            }
        )
    return {
        "comparable": not limits,
        "overall_delta": (
            right["aggregate"]["overall"] - left["aggregate"]["overall"]
            if not limits
            else None
        ),
        "metrics": metrics,
        "limitations": limits,
    }


def persist_maintenance_health(
    snapshot: RunSnapshot,
    *,
    workspace: Path,
    store: RunStore | Path,
    required_context_ids: list[str],
    optional_context_ids: list[str] | None = None,
    allow_inferred_parse: bool = False,
    profile: str = "default",
) -> RunSnapshot:
    """Publish an explicit scoped calculation from checked immutable inputs.

    No producer is executed and no historical score is rewritten. Selected
    sources and retained materials must still match the parent run before and
    during derived publication.
    """
    from cppulse.workflows import (
        _derive,
        _mutable_parent,
        ensure_current_materials,
        read_documents,
    )

    snapshot.verify()
    _mutable_parent(snapshot)
    documents = read_documents(snapshot)
    inventories = documents.get("analysis_inventory", [])
    selected = set(required_context_ids) | set(optional_context_ids or [])
    inventories = [row for row in inventories if row["job_context_id"] in selected]
    inventory_ids = {row["id"] for row in inventories}
    registry_ids = {row["registry_artifact_id"] for row in inventories}
    if not registry_ids:
        raise ContractError(
            "Maintenance calculation requires a retained native rule registry"
        )
    registries = [
        snapshot.read_json(identifier, contract="rule_registry")
        for identifier in sorted(registry_ids)
    ]
    if len({digest_json(registry) for registry in registries}) != 1:
        raise ContractError(
            "Selected native jobs use conflicting rule registry versions"
        )
    result = compute_maintenance_health(
        source_digest=snapshot.manifest["source"]["digest"],
        inventories=inventories,
        metrics=[
            row
            for row in documents.get("analysis_metrics", [])
            if row["analysis_inventory_id"] in inventory_ids
        ],
        observations=[
            row
            for row in documents.get("observations", [])
            if row.get("analysis_inventory_id") in inventory_ids
        ],
        registry=registries[0],
        required_context_ids=required_context_ids,
        optional_context_ids=optional_context_ids,
        allow_inferred_parse=allow_inferred_parse,
        profile=profile,
        expected_scopes=[
            row
            for row in documents.get("analysis_scope", [])
            if row["job_context_id"] in selected
        ],
    )
    if result in documents.get("maintenance_health", []):
        # A deterministic calculation may already be retained by the pipeline.
        # Reusing it must retain the same freshness/parent restrictions as a new
        # publication, without introducing a second fact with the same identity.
        ensure_current_materials(snapshot, workspace)
        return snapshot
    return _derive(
        snapshot,
        workspace=workspace,
        store=store,
        operation="maintenance-health",
        documents=[("maintenance_health", result)],
        reason="Explicit measured maintenance calculation; consumer assurance is not assessed.",
    )
