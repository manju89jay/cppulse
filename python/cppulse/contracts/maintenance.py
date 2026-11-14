"""Pure semantic checks for measured maintenance facts and stored calculations.

Validation does not launch a producer, establish authenticity or manufacture
measurements. Source/receipt/artifact integrity is checked by the enclosing run
store and the existing native execution lineage.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from cppulse.errors import ContractError

METRIC_VERSION = "cppulse-metrics-1"
DUPLICATION_VERSION = "cppulse-exact-duplicates-30-v1"
FILE_UNITS = {
    "physical_loc": "lines",
    "code_loc": "lines",
    "function_count": "functions",
    "duplicate_tokens": "tokens",
    "duplicate_lines": "lines",
}
FUNCTION_UNITS = {
    "function_length": "lines",
    "cyclomatic_complexity": "count",
    "nesting_depth": "levels",
    "parameter_count": "parameters",
}
BASE_CATEGORIES = {
    "memory_safety": (3, 5),
    "complexity": (1.5, 10),
    "modernization": (1, 50),
}
TOLERANCE = Fraction(1, 1_000_000_000)


def _fail(message: str, path: str) -> None:
    raise ContractError(message, path=path)


def _unique(
    rows: list[dict[str, Any]], key: str, path: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row[key] in result:
            _fail(f"Duplicate {key} in maintenance facts", path)
        result[row[key]] = row
    return result


def _same(
    actual: int | float | None, expected: Fraction | int | float, path: str
) -> None:
    if (
        actual is None
        or abs(Fraction(str(actual)) - Fraction(str(expected))) > TOLERANCE
    ):
        _fail(
            "Stored maintenance calculation differs from its raw counts or method", path
        )


def _location(location: dict[str, int], path: str) -> None:
    if (location["end_line"], location["end_column"]) < (
        location["line"],
        location["column"],
    ):
        _fail("Source location ends before its beginning", path)


def validate_metrics(document: dict[str, Any]) -> None:
    """Validate the named measured profile while preserving older generic metrics."""
    known = [
        row
        for row in document["items"]
        if row["metric_version"] in {METRIC_VERSION, DUPLICATION_VERSION}
    ]
    if not known:
        return
    if not document.get("analysis_inventory_id") or not document.get("job_context_id"):
        _fail(
            "Measured metrics require native inventory and declared job context links",
            "/analysis_metrics",
        )
    cells: set[tuple[Any, ...]] = set()
    values: dict[tuple[str, str], dict[str, Any]] = {}
    for index, row in enumerate(known):
        path = f"/analysis_metrics/items/{index}"
        name = row["metric"]
        units = FILE_UNITS | FUNCTION_UNITS
        if name not in units or row["units"] != units[name]:
            _fail("Named metric or units do not match the measured profile", path)
        if row["metric_version"] == DUPLICATION_VERSION and name not in {
            "duplicate_tokens", "duplicate_lines"
        }:
            _fail("Duplication method cannot claim an unrelated metric", path)
        key = (row["file"], row["context_id"], row["symbol"], name, row["metric_version"])
        if key in cells:
            _fail("Duplicate measured metric cell", path)
        cells.add(key)
        if row["availability"] == "available":
            value = row["value"]
            if value < 0 or int(value) != value:
                _fail("Measured counts must be nonnegative integers", path + "/value")
            if name in {"function_length", "cyclomatic_complexity"} and value < 1:
                _fail(
                    "Measured function length/complexity needs a positive count",
                    path + "/value",
                )
            if name in {"duplicate_tokens", "duplicate_lines"} and row["metric_version"] == METRIC_VERSION:
                _fail(
                    "Initial metric profile has no qualified duplication producer",
                    path + "/metric",
                )
        elif not row["limitations"]:
            _fail(
                "Unavailable measurement needs an explicit limitation",
                path + "/limitations",
            )
        if name in FUNCTION_UNITS:
            if row["symbol"] is None or "location" not in row:
                _fail("Function metric needs symbol identity and source location", path)
        elif row["symbol"] is not None:
            _fail(
                "File-level metric must not claim a function symbol", path + "/symbol"
            )
        if "location" in row:
            _location(row["location"], path + "/location")
        if row["symbol"] is None and row["availability"] == "available":
            values.setdefault((row["file"], row["context_id"]), {})[name] = row["value"]
    for value in values.values():
        if value.get("code_loc", 0) > value.get("physical_loc", float("inf")):
            _fail("Code LOC exceeds measured physical LOC", "/analysis_metrics/items")


def validate_native_metrics(findings: dict[str, Any]) -> None:
    """Check an optional raw payload against its ordinary native parse inventory."""
    analysis = findings.get("metadata", {}).get("analysis", {})
    raw = analysis.get("native_metrics")
    if raw is None:
        return
    coverage = _unique(analysis["files"], "path", "/metadata/analysis/files")
    files = _unique(raw["files"], "path", "/metadata/analysis/native_metrics/files")
    if files.keys() != coverage.keys():
        _fail(
            "Native metrics and parse inventory cover different files",
            "/metadata/analysis/native_metrics/files",
        )
    for path, row in files.items():
        pointer = "/metadata/analysis/native_metrics/files/" + path
        if any(row[key] != coverage[path][key] for key in ["status", "error_count"]):
            _fail("Native metric status differs from its parse inventory", pointer)
        if row["measurement_complete"]:
            if row["status"] != "analyzed" or row["error_count"]:
                _fail("Complete metrics require an error-free analyzed file", pointer)
            if row["function_count"] != len(row["functions"]):
                _fail(
                    "Function count differs from measured definition inventory", pointer
                )
        elif row["function_count"] is not None:
            _fail(
                "Incomplete function inventory cannot claim a complete function count",
                pointer,
            )
        if row["status"] not in {"analyzed", "partial"} and any(
            row[key] is not None
            for key in ["physical_loc", "code_loc", "function_count"]
        ):
            _fail(
                "Unobserved native input cannot claim zero-valued measurements", pointer
            )
        if (
            row["code_loc"] is not None
            and row["physical_loc"] is not None
            and row["code_loc"] > row["physical_loc"]
        ):
            _fail("Native code LOC exceeds physical LOC", pointer)
        for function in row["functions"]:
            numbers = [function[key] for key in FUNCTION_UNITS]
            coordinates = {
                key: function[key]
                for key in ["line", "column", "end_line", "end_column"]
            }
            if function["availability"] == "measured":
                if any(value is None for value in numbers + list(coordinates.values())):
                    _fail(
                        "Measured function cells and locations must be available",
                        pointer,
                    )
                if (
                    function["function_length"] < 1
                    or function["cyclomatic_complexity"] < 1
                ):
                    _fail(
                        "Measured function length/complexity must be positive", pointer
                    )
                _location(coordinates, pointer)
                if (
                    function["function_length"]
                    != function["end_line"] - function["line"] + 1
                ):
                    _fail(
                        "Function length differs from its declared inclusive source extent",
                        pointer,
                    )
            elif not function["limitations"]:
                _fail(
                    "Partial function measurement requires an explicit limitation",
                    pointer,
                )
            if function["availability"] == "unavailable" and any(
                value is not None for value in numbers
            ):
                _fail("Unavailable function cannot claim numeric measurements", pointer)
        stream = row["token_stream"]
        if stream["record_limit"] != raw["max_token_records"]:
            _fail(
                "Native token limit differs from the declared configured budget",
                pointer,
            )
        if (
            stream["retained_tokens"] != len(stream["records"])
            or len(stream["records"]) > stream["record_limit"]
        ):
            _fail(
                "Retained token records disagree with their count or configured limit",
                pointer,
            )
        if stream["complete"]:
            if stream["availability"] != "measured" or stream["total_tokens"] != len(
                stream["records"]
            ):
                _fail("Complete token stream must retain every observed token", pointer)
        elif stream["availability"] == "measured" or not stream["limitations"]:
            _fail(
                "Incomplete token stream needs explicit partial/unavailable status and reasons",
                pointer,
            )
        if stream["total_tokens"] is not None and stream["total_tokens"] < len(
            stream["records"]
        ):
            _fail("Retained token count exceeds observed total", pointer)
        for token in stream["records"]:
            _location(token, pointer)
        for edge in row["includes"]:
            if edge["target_kind"] == "project":
                target = PurePosixPath(edge["target"])
                if (
                    target.is_absolute()
                    or ".." in target.parts
                    or "\\" in edge["target"]
                    or target.as_posix() != edge["target"]
                ):
                    _fail(
                        "Project include target is not a canonical relative identity",
                        pointer,
                    )


def validate_health(document: dict[str, Any]) -> None:
    """Independently check stored density equations and required-context selection."""
    config = document["scorer"]
    projection = {
        key: value for key, value in config.items() if key != "configuration_digest"
    }
    digest = hashlib.sha256(
        json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    if config["configuration_digest"] != digest:
        _fail(
            "Maintenance scorer configuration digest differs from its method",
            "/scorer/configuration_digest",
        )
    categories = _unique(config["categories"], "category", "/scorer/categories")
    required_rules = set(config["required_rule_ids"])
    if not required_rules or required_rules != set(config["required_rule_versions"]):
        _fail(
            "Required rule identities and versions must account for the selected method",
            "/scorer/required_rule_ids",
        )
    if config["profile"] != "custom":
        expected = dict(BASE_CATEGORIES)
        if config["profile"] == "safety-critical":
            expected["misra"] = (2.5, 10)
        if set(categories) != set(expected) or any(
            (row["weight"], row["density_cap"]) != expected[name]
            for name, row in categories.items()
        ):
            _fail(
                "Named maintenance profile differs from its published weights/caps",
                "/scorer/categories",
            )
        expected_rules = {
            f"CPP-{family}-{number:03d}"
            for family, count in [("MEM", 3), ("CX", 3), ("MOD", 9)]
            for number in range(1, count + 1)
        }
        if config["profile"] == "safety-critical":
            expected_rules.update(f"MISRA-{number:03d}" for number in range(1, 8))
        if required_rules != expected_rules:
            _fail(
                "Named profile must retain every required native detector",
                "/scorer/required_rule_ids",
            )
    required = set(document["required_context_ids"])
    optional = set(document["optional_context_ids"])
    if required & optional:
        _fail(
            "Required and optional maintenance contexts overlap",
            "/required_context_ids",
        )
    contexts = _unique(document["contexts"], "job_context_id", "/contexts")
    if set(contexts) - (required | optional):
        _fail("Maintenance result contains an undeclared job context", "/contexts")
    weight_sum = sum(Fraction(str(row["weight"])) for row in categories.values())
    for identifier, context in contexts.items():
        pointer = "/contexts/" + identifier
        if (
            context["analyzed_files"] + context["excluded_files"]
            > context["declared_files"]
        ):
            _fail("Analyzed/excluded counts exceed declared source scope", pointer)
        if (
            sum(context["parse_context_counts"].values())
            != context["declared_files"] - context["excluded_files"]
        ):
            _fail("Parse-context counts do not account for applicable files", pointer)
        if (
            context["code_loc"] is not None
            and context["physical_loc"] is not None
            and context["code_loc"] > context["physical_loc"]
        ):
            _fail("Code LOC exceeds physical LOC", pointer)
        calculations = _unique(context["category_calculations"], "category", pointer)
        if set(calculations) != set(categories) or set(
            context["finding_counts"]
        ) != set(categories):
            _fail("Context calculation categories differ from the scorer", pointer)
        _same(context["weight_sum"], weight_sum, pointer + "/weight_sum")
        complete = context["availability"] == "scored"
        if not complete:
            derived = [context["overall"], context["weighted_penalty"]]
            derived.extend(
                value[key]
                for value in calculations.values()
                for key in ["density", "penalty", "score"]
            )
            if (
                any(value is not None for value in derived)
                or not context["limitations"]
            ):
                _fail(
                    "Incomplete context must retain null scores and an explicit limitation",
                    pointer,
                )
            continue
        counts = context["parse_context_counts"]
        if (
            not context["physical_loc"]
            or context["analyzed_files"] == 0
            or context["analyzed_files"] + context["excluded_files"]
            != context["declared_files"]
        ):
            _fail(
                "Scored context requires complete nonzero measured source scope",
                pointer,
            )
        if (
            counts["none"]
            or counts["fallback"]
            or (counts["inferred"] and not config["allow_inferred_parse"])
        ):
            _fail(
                "Scored context does not meet declared parse-quality prerequisites",
                pointer,
            )
        if counts["inferred"] and not context["limitations"]:
            _fail("Inferred maintenance opt-in requires a retained limitation", pointer)
        if not context["analysis_inventory_ids"] or not context["metric_ids"]:
            _fail("Scored context requires native inventory and metric links", pointer)
        weighted = Fraction(0)
        for category, calculation in calculations.items():
            count = context["finding_counts"][category]
            if count is None or count != calculation["count"]:
                _fail("Finding count differs from raw category calculation", pointer)
            density = Fraction(count * 1000, context["physical_loc"])
            penalty = min(
                Fraction(1),
                density / Fraction(str(categories[category]["density_cap"])),
            )
            _same(calculation["density"], density, pointer + "/density")
            _same(calculation["penalty"], penalty, pointer + "/penalty")
            _same(calculation["score"], 100 * (1 - penalty), pointer + "/score")
            weighted += Fraction(str(categories[category]["weight"])) * penalty
        _same(context["weighted_penalty"], weighted, pointer + "/weighted_penalty")
        _same(
            context["overall"], 100 * (1 - weighted / weight_sum), pointer + "/overall"
        )
    aggregate = document["aggregate"]
    incomplete = sorted(
        identifier
        for identifier in required
        if identifier not in contexts
        or contexts[identifier]["availability"] != "scored"
    )
    if aggregate["incomplete_required_context_ids"] != incomplete:
        _fail(
            "Aggregate required-context gaps differ from stored context availability",
            "/aggregate",
        )
    if set(aggregate["by_category"]) != set(categories):
        _fail("Aggregate categories differ from scorer", "/aggregate/by_category")
    if not required or incomplete:
        if (
            aggregate["availability"] == "scored"
            or aggregate["overall"] is not None
            or aggregate["worst_context_id"] is not None
            or any(value is not None for value in aggregate["by_category"].values())
        ):
            _fail(
                "Missing required scope cannot receive a full aggregate health score",
                "/aggregate",
            )
        if not aggregate["limitations"]:
            _fail(
                "Unavailable aggregate requires explicit limitations",
                "/aggregate/limitations",
            )
    else:
        worst = min(
            (contexts[identifier] for identifier in required),
            key=lambda row: (row["overall"], row["job_context_id"]),
        )
        if (
            aggregate["availability"] != "scored"
            or aggregate["worst_context_id"] != worst["job_context_id"]
        ):
            _fail(
                "Aggregate must identify the worst fully evaluated required job context",
                "/aggregate",
            )
        _same(aggregate["overall"], worst["overall"], "/aggregate/overall")
        for calculation in worst["category_calculations"]:
            _same(
                aggregate["by_category"][calculation["category"]],
                calculation["score"],
                "/aggregate/by_category",
            )


def validate_maintenance_bundle(
    flat: list[tuple[str, dict[str, Any]]], manifest: dict[str, Any]
) -> None:
    """Bind metrics/health references to existing native lineage and one source."""
    inventories = {doc["id"]: doc for kind, doc in flat if kind == "analysis_inventory"}
    source_files = {row["path"]: row for row in manifest["source"]["files"]}
    execution = {
        doc["receipt"]["id"]: doc for kind, doc in flat if kind == "execution_facts"
    }
    metrics: dict[str, dict[str, Any]] = {}
    for kind, document in flat:
        if kind != "analysis_metrics" or "analysis_inventory_id" not in document:
            continue
        inventory = inventories.get(document["analysis_inventory_id"])
        if (
            inventory is None
            or document.get("job_context_id") != inventory["job_context_id"]
        ):
            _fail(
                "Measured metric job does not resolve to its native inventory",
                "/analysis_metrics",
            )
        rows = {row["file"]: row for row in inventory["items"]}
        for metric in document["items"]:
            if metric["id"] in metrics:
                _fail(
                    "Duplicate metric identity across documents",
                    "/analysis_metrics/items",
                )
            metrics[metric["id"]] = {
                **metric,
                "job_context_id": inventory["job_context_id"],
                "analysis_inventory_id": inventory["id"],
            }
            row = rows.get(metric["file"])
            if row is None or row["parse_context_id"] != metric["context_id"]:
                _fail(
                    "Metric file/parse context differs from observed native inventory",
                    "/analysis_metrics/items",
                )
            if metric["availability"] == "available" and (
                row["status"] != "analyzed" or row["error_count"]
            ):
                _fail(
                    "Partial native parsing cannot establish a complete available metric",
                    "/analysis_metrics/items",
                )
            if metric["availability"] == "available":
                facts = execution.get(inventory["receipt_id"])
                if (
                    facts is None
                    or manifest.get("input_verification") != "verified"
                    or facts["binding"]["status"] != "verified"
                    or facts["material_status"] != "available"
                    or facts["receipt"]["status"] != "passed"
                ):
                    _fail(
                        "Available measured metrics require verified native execution/source binding",
                        "/analysis_metrics/items",
                    )
                before = {row["path"]: row for row in facts["input_facts"]}
                after = {row["path"]: row for row in facts["input_after_facts"]}
                frozen = {row["path"] for row in facts["binding"]["input_artifacts"]}
                file = metric["file"]
                if (
                    file not in before
                    or file not in after
                    or file not in frozen
                    or any(
                        before[file][key] != source_files[file][key]
                        or after[file][key] != source_files[file][key]
                        for key in ["sha256", "size_bytes"]
                    )
                ):
                    _fail(
                        "Measured metric input is not a frozen unchanged selected source",
                        "/analysis_metrics/items",
                    )
            if (
                metric["metric"] == "physical_loc"
                and metric["value"] is not None
                and metric["value"] > source_files[metric["file"]]["size_bytes"]
            ):
                _fail(
                    "Physical LOC exceeds the selected source byte bound",
                    "/analysis_metrics/items",
                )
    healths = _unique(
        [doc for kind, doc in flat if kind == "maintenance_health"],
        "id",
        "/maintenance_health",
    )
    registries = [doc for kind, doc in flat if kind == "rule_registry"]
    rules = {row["id"]: row for registry in registries for row in registry["rules"]}
    observations = [doc for kind, doc in flat if kind == "observations"]
    for health in healths.values():
        for context in health["contexts"]:
            for identifier in context["analysis_inventory_ids"]:
                if (
                    identifier not in inventories
                    or inventories[identifier]["job_context_id"]
                    != context["job_context_id"]
                ):
                    _fail(
                        "Health inventory is outside its declared job context",
                        "/maintenance_health/contexts",
                    )
            for identifier in context["metric_ids"]:
                if (
                    identifier not in metrics
                    or metrics[identifier]["job_context_id"]
                    != context["job_context_id"]
                    or metrics[identifier]["analysis_inventory_id"]
                    not in context["analysis_inventory_ids"]
                ):
                    _fail(
                        "Health metric reference is outside its selected native inventory/job",
                        "/maintenance_health/contexts",
                    )
                if (
                    context["availability"] == "scored"
                    and metrics[identifier]["availability"] != "available"
                ):
                    _fail(
                        "Scored health depends on an unavailable metric",
                        "/maintenance_health/contexts",
                    )
            selected = [
                inventories[identifier]
                for identifier in context["analysis_inventory_ids"]
            ]
            if not selected:
                continue
            rows = [row for inventory in selected for row in inventory["items"]]
            by_file = _unique(rows, "file", "/maintenance_health/contexts")
            applicable = {
                file: row
                for file, row in by_file.items()
                if row["status"] != "excluded"
            }
            expected_counts = {
                "declared_files": len(by_file),
                "excluded_files": len(by_file) - len(applicable),
                "analyzed_files": sum(
                    row["status"] == "analyzed" and row["error_count"] == 0
                    for row in applicable.values()
                ),
            }
            if any(context[key] != value for key, value in expected_counts.items()):
                _fail(
                    "Health source counts differ from native file inventory",
                    "/maintenance_health/contexts",
                )
            parse_counts = {
                name: sum(row["context_source"] == name for row in applicable.values())
                for name in ["database", "inferred", "fallback", "none"]
            }
            if context["parse_context_counts"] != parse_counts:
                _fail(
                    "Health parse-quality counts differ from native inventory",
                    "/maintenance_health/contexts",
                )
            chosen = [metrics[identifier] for identifier in context["metric_ids"]]
            cells = {(row["file"], row["symbol"], row["metric"]): row for row in chosen}
            if len(cells) != len(chosen):
                _fail(
                    "Health metric selection repeats a measurement cell",
                    "/maintenance_health/contexts",
                )
            for name in ["physical_loc", "code_loc"]:
                references = [cells.get((file, None, name)) for file in applicable]
                expected = (
                    sum(row["value"] for row in references)
                    if all(
                        row is not None and row["availability"] == "available"
                        for row in references
                    )
                    else None
                )
                if context[name] != expected:
                    _fail(
                        "Health LOC does not reproduce its selected measured facts",
                        "/maintenance_health/contexts/" + name,
                    )
            requested_rules = set(health["scorer"]["required_rule_ids"])
            raw_counts = dict.fromkeys(context["finding_counts"], 0)
            for document in observations:
                if (
                    document.get("analysis_inventory_id")
                    not in context["analysis_inventory_ids"]
                ):
                    continue
                for observation in document["items"]:
                    if observation["rule_id"] in requested_rules:
                        category = rules[observation["rule_id"]]["category"]
                        if category in raw_counts:
                            raw_counts[category] += 1
            for category, count in context["finding_counts"].items():
                if count is not None and count != raw_counts[category]:
                    _fail(
                        "Health finding counts differ from linked native observations",
                        "/maintenance_health/contexts/finding_counts",
                    )
            if context["availability"] != "scored":
                continue
            for inventory in selected:
                if not requested_rules <= set(
                    inventory["requested_rules"]
                ) or not requested_rules <= set(inventory["enabled_rules"]):
                    _fail(
                        "Required health detector was disabled or not requested",
                        "/maintenance_health/contexts",
                    )
            for rule in requested_rules:
                if (
                    rule not in rules
                    or rules[rule]["version"]
                    != health["scorer"]["required_rule_versions"][rule]
                ):
                    _fail(
                        "Health detector version differs from the observed registry",
                        "/maintenance_health/scorer/required_rule_versions",
                    )
            if not set(context["finding_counts"]) <= {
                rules[rule]["category"] for rule in requested_rules
            }:
                _fail(
                    "Health category has no required executed detector",
                    "/maintenance_health/scorer/categories",
                )
            for file, row in applicable.items():
                if (
                    row["status"] != "analyzed"
                    or row["error_count"]
                    or not requested_rules <= set(row["executed_rules"])
                    or row["context_match"] == "mismatched"
                ):
                    _fail(
                        "Scored health requires complete executed detector/context scope",
                        "/maintenance_health/contexts",
                    )
                if row["context_match"] != "matched" and not (
                    row["context_source"] == "inferred"
                    and health["scorer"]["allow_inferred_parse"]
                ):
                    _fail(
                        "Scored health has no matched or explicitly permitted inferred context",
                        "/maintenance_health/contexts",
                    )
                functions = cells.get((file, None, "function_count"))
                if functions is None or functions["availability"] != "available":
                    _fail(
                        "Scored health requires an explicit complete function inventory",
                        "/maintenance_health/contexts",
                    )
                symbols = {
                    metric["symbol"]
                    for metric in chosen
                    if metric["file"] == file and metric["symbol"] is not None
                }
                if len(symbols) != functions["value"] or any(
                    (file, symbol, name) not in cells
                    or cells[(file, symbol, name)]["availability"] != "available"
                    for symbol in symbols
                    for name in FUNCTION_UNITS
                ):
                    _fail(
                        "Scored health is missing required function measurement cells",
                        "/maintenance_health/contexts",
                    )
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    for kind, risk in flat:
        if kind != "risk_scores" or "maintenance_health_artifact_id" not in risk:
            continue
        identifier = risk["maintenance_health_artifact_id"]
        artifact = artifacts.get(identifier)
        if (
            identifier not in healths
            or artifact is None
            or artifact.get("contract")
            != {"kind": "maintenance_health", "version": "2.0.0"}
        ):
            _fail(
                "Risk maintenance-health reference is absent or has the wrong contract",
                "/risk_scores/maintenance_health_artifact_id",
            )
        health = healths[identifier]
        projection = health["aggregate"]
        if (
            risk["health_score"]["overall"] != projection["overall"]
            or risk["health_score"]["by_category"] != projection["by_category"]
            or risk["health_score"]["availability"] != projection["availability"]
            or risk["health_score"]["scorer_version"] != health["scorer"]["id"]
        ):
            _fail(
                "Risk health projection differs from the authoritative maintenance result",
                "/risk_scores/health_score",
            )
