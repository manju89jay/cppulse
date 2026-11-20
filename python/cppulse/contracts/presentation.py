"""Validate exact stored presentation projections without evaluating a policy.

The envelope carries original UTF-8 JSON strings so a manifest pin and artifact
byte descriptors can be checked without guessing serialization. These checks
preserve local content identities; they do not authenticate a producer.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from cppulse.errors import ContractError

MAX_RAW_JSON_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 128


def _fail(message: str, path: str) -> None:
    raise ContractError(message, path=path)


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            _fail("Embedded JSON contains a duplicate object key", "/raw_json")
        result[key] = value
    return result


def _constant(value: str) -> None:
    _fail("Embedded JSON contains a nonfinite number", "/raw_json")


def _raw(value: str, path: str) -> tuple[dict[str, Any], bytes]:
    try:
        data = value.encode("utf-8")
    except UnicodeError as error:
        raise ContractError("Embedded JSON is not valid UTF-8", path=path) from error
    if len(data) > MAX_RAW_JSON_BYTES:
        _fail("Embedded JSON exceeds the 64 MiB presentation bound", path)
    # Bound parser nesting before json.loads; braces inside strings are literals.
    depth = 0
    quoted = escaped = False
    for character in value:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                _fail("Embedded JSON exceeds the presentation nesting bound", path)
        elif character in "]}":
            depth -= 1
    try:
        document = json.loads(value, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError) as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError(
            "Embedded JSON is malformed or unsupported", path=path
        ) from error
    if not isinstance(document, dict):
        _fail("Embedded contract JSON must contain an object", path)
    return document, data


def _equal(actual: Any, expected: Any, path: str) -> None:
    if actual != expected:
        _fail("Presentation summary differs from exact stored values", path)


def _unique(
    rows: list[dict[str, Any]], key: str, path: str
) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        identifier = row[key]
        if identifier in result:
            _fail("Presentation contains a duplicate stored identity", path)
        result[identifier] = row
    return result


def _contexts(value: Any) -> list[str]:
    found: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key in {
                    "context_id",
                    "job_context_id",
                    "parse_context_id",
                } and isinstance(child, str):
                    found.add(child)
                elif key in {"context_ids", "contexts"} and isinstance(child, list):
                    found.update(item for item in child if isinstance(item, str))
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return sorted(found)


def assessment_display(
    document: dict[str, Any], *, raw_json: str | None = None
) -> dict[str, Any]:
    """Copy stored values and display original numeric tokens when available.

    The optional exact stored JSON keeps decimal tokens beyond binary-float
    precision. Without raw bytes this utility stringifies caller values only;
    semantic envelope validation always supplies the retained original string.
    """
    numbers = document
    if raw_json is not None:
        parsed, _ = _raw(raw_json, "/assessment/raw_json")
        _equal(parsed, document, "/assessment/raw_json")
        numbers = json.loads(
            raw_json,
            parse_int=str,
            parse_float=str,
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    result = deepcopy(document)
    for section in ["weights", "scores"]:
        result[section] = {
            key: None if value is None else str(value)
            for key, value in numbers[section].items()
        }
    for index, control in enumerate(result["controls"]):
        control["weight"] = str(numbers["controls"][index]["weight"])
    return result


def fact_summary(kind: str, document: dict[str, Any]) -> dict[str, Any]:
    """Copy named stored fact fields without inferring an aggregate outcome.

    Execution-facts ID, producer and process status come from its embedded
    receipt. A sanitizer's explicit outcome remains distinct from usability.
    """
    core = document["receipt"] if kind == "execution_facts" else document
    return {
        "id": core.get("id"),
        "context_ids": _contexts(document),
        "origin": document.get("origin"),
        "producer": core.get("producer"),
        "status": document.get("status", document.get("outcome", core.get("status"))),
        "usability": document.get("usability"),
        "limitations": deepcopy(document.get("limitations", [])),
    }


def semantic(document: dict[str, Any]) -> None:
    """Check byte pins and literal stored summaries; perform no gate evaluation."""
    from .validation import validate

    manifest, manifest_bytes = _raw(document["run_manifest_json"], "/run_manifest_json")
    validate("run_manifest", manifest)
    run = document["run"]
    _equal(
        run["manifest_sha256"],
        hashlib.sha256(manifest_bytes).hexdigest(),
        "/run/manifest_sha256",
    )
    expected_run = {
        "id": manifest["run_id"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "status": manifest["status"],
        "input_verification": manifest.get("input_verification", "unverified"),
        "source_digest": manifest["source"]["digest"],
        "inventory_complete": manifest["source"]["inventory_complete"],
        "started_at": manifest["started_at"],
        "finished_at": manifest["finished_at"],
        "config_digest": manifest["config_digest"],
        "limitations": manifest["limitations"],
    }
    _equal(run, expected_run, "/run")
    for field in ["source", "stages", "contexts", "artifacts"]:
        _equal(document[field], manifest[field], "/" + field)
    artifacts = _unique(document["artifacts"], "id", "/artifacts")
    known_contexts = {row["id"] for row in manifest["contexts"]}
    if not set(manifest["limitations"]) <= set(document["limitations"]):
        _fail("Presentation omits stored run limitations", "/limitations")

    def payload(
        wrapper: dict[str, Any], kind: str | None, path: str, version: str = "2.0.0"
    ) -> dict[str, Any]:
        identifier = wrapper["artifact_id"]
        artifact = artifacts.get(identifier)
        if artifact is None:
            _fail(
                "Selected presentation artifact is outside this snapshot",
                path + "/artifact_id",
            )
        for field in ["sha256", "size_bytes"]:
            _equal(wrapper[field], artifact[field], path + "/" + field)
        _equal(
            artifact.get("contract"),
            {"kind": kind, "version": version} if kind is not None else None,
            path + "/artifact_id",
        )
        raw, content = _raw(wrapper["raw_json"], path + "/raw_json")
        _equal(len(content), artifact["size_bytes"], path + "/size_bytes")
        _equal(
            hashlib.sha256(content).hexdigest(), artifact["sha256"], path + "/sha256"
        )
        if kind is not None:
            validate(kind, raw, version=version)
        if "source_digest" in raw:
            _equal(
                raw["source_digest"],
                manifest["source"]["digest"],
                path + "/source_digest",
            )
        # Requested policy targets may be absent, yielding an explicit stored
        # unknown/incomplete control. Only actual observation/job proof binds
        # every context reference to the collected inventory.
        observed_kinds = {
            "execution_receipt",
            "execution_facts",
            "analysis_inventory",
            "observations",
            "analysis_metrics",
            "evidence",
            "baseline",
            "coverage_facts",
            "sanitizer_facts",
            "external_analysis_facts",
            "consumer_usage",
            "consumer_matrix",
            "collection_plan",
            "recipe",
        }
        contexts = (
            _contexts(raw)
            if kind in observed_kinds
            else ([raw["context_id"]] if isinstance(raw.get("context_id"), str) else [])
        )
        if not set(contexts) <= known_contexts:
            _fail(
                "Stored presentation document names an unknown snapshot context",
                path + "/context_ids",
            )
        return raw

    assessment = document["assessment"]
    if assessment is not None:
        raw = payload(assessment, "assessment", "/assessment")
        _equal(raw["run_id"], manifest["run_id"], "/assessment/run_id")
        for control in raw["controls"]:
            missing = set(control.get("context_ids", [])) - known_contexts
            if (
                missing
                and control["status"] not in {"unknown", "not_applicable"}
                and not control.get("incomplete", False)
            ):
                _fail(
                    "Complete control claims an uncollected job context",
                    "/assessment/controls/context_ids",
                )
        _equal(
            assessment["display"],
            assessment_display(raw, raw_json=assessment["raw_json"]),
            "/assessment/display",
        )
    else:
        if not any(row["kind"] == "assessment" for row in document["gaps"]):
            _fail("Unassessed presentation needs an explicit assessment gap", "/gaps")

    _unique(document["facts"], "artifact_id", "/facts")
    for index, fact in enumerate(document["facts"]):
        path = f"/facts/{index}"
        kind = fact["kind"]
        if kind == "snapshot_view":
            _fail("Nested snapshot views are unsupported", path + "/kind")
        raw = payload(fact, kind, path)
        if kind == "execution_facts":
            _equal(
                raw["receipt"]["source_digest"],
                manifest["source"]["digest"],
                path + "/receipt/source_digest",
            )
        expected = fact_summary(kind, raw)
        for field, value in expected.items():
            _equal(fact[field], value, path + "/" + field)
        if kind == "source":
            _equal(raw, manifest["source"], path + "/raw_json")
        elif kind == "context":
            selected = next(
                (row for row in manifest["contexts"] if row["id"] == raw["id"]), None
            )
            _equal(raw, selected, path + "/raw_json")

    if "external_relationships" in document:
        from cppulse.external import external_relationships

        external = [
            json.loads(f["raw_json"])
            for f in document["facts"]
            if f["kind"] == "external_analysis_facts"
        ]
        native = [
            json.loads(f["raw_json"])
            for f in document["facts"]
            if f["kind"] == "observations"
        ]
        _equal(
            document["external_relationships"],
            external_relationships(external, native),
            "/external_relationships",
        )
    configuration = document.get("configuration")
    if configuration is not None:
        descriptor = artifacts[configuration["artifact_id"]]
        kind = descriptor.get("contract", {}).get("kind")
        if kind not in {None, "collection_request"} or (kind is None and descriptor["id"] != "effective_config-json"):
            _fail("Configuration must select its original retained artifact", "/configuration")
        raw = payload(configuration, kind, "/configuration")
        _equal(configuration["document"], raw, "/configuration/document")
        if kind == "collection_request" and "resolved_ruleset" not in raw:
            _fail("Selected request has no resolved ruleset", "/configuration")
    for kind, wrapper in document["legacy"].items():
        if wrapper is not None:
            raw = payload(wrapper, kind, "/legacy/" + kind, "prototype_v1")
            _equal(wrapper["document"], raw, "/legacy/" + kind + "/document")
    for gap in document["gaps"]:
        if not set(gap["artifact_ids"]) <= artifacts.keys():
            _fail("Gap refers to artifacts outside this snapshot", "/gaps/artifact_ids")
