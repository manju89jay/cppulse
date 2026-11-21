"""Normalize checked native analysis into explicit per-file observed facts.

No command, live project discovery or compiler-argument reconstruction occurs in
normalization. The publication wrapper separately checks current finite sources.
"""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib import resources
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import tempfile
from typing import Any

from cppulse.measurements import DuplicateCount

import jsonschema
import yaml

from cppulse import __version__
from cppulse.contracts import validate, validate_bundle
from cppulse.errors import (
    CompatibilityError,
    ContractError,
    InputChanged,
    IntegrityError,
)
from cppulse.identities import context_identity, digest_json, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.tooling import load_rule_registry

_VERSION = "1.0.0"
_PRODUCER = {"name": "cppulse.native-normalizer", "version": _VERSION}
_LIMITS = [
    "Rules remain experimental; normalized findings and zero counts are not certification or proof of safety.",
    "Binding covers the finite selected source/resource inventory; unlisted additions and the general host/runtime dependency closure are not observed.",
    "A matched context binds an explicit file command and native-reported libclang arguments; it does not establish GCC/libclang semantic equivalence.",
    "Content hashes identify bytes, not producer authenticity.",
]


@dataclass(frozen=True)
class NormalizedAnalysis:
    """Authoritative inventory/observations plus distinct measured parse contexts."""

    inventory: dict[str, Any]
    observations: dict[str, Any]
    derived_parse_contexts: list[dict[str, Any]]
    metrics: dict[str, Any] | None = None


def _physical_loc(content: bytes) -> int:
    """Count Clang physical lines: CRLF is paired, LFCR is not."""
    return len(re.findall(rb"\r\n|\r|\n", content)) + int(
        bool(content) and content[-1] not in (10, 13)
    )


def _id(label: str) -> str:
    return "analysis-" + hashlib.sha256(label.encode()).hexdigest()


def _json_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode()


def _json(content: bytes, label: str) -> dict[str, Any] | list[Any]:
    try:
        document = json.loads(content)
        json.dumps(document, allow_nan=False)
    except (ValueError, UnicodeError, TypeError) as error:
        raise ContractError(f"Invalid retained JSON {label}: {error}") from error
    if not isinstance(document, (dict, list)):
        raise ContractError(f"Retained JSON {label} must contain an object or array")
    return document


def _typed(snapshot: RunSnapshot) -> dict[str, list[dict[str, Any]]]:
    documents: dict[str, list[dict[str, Any]]] = {}
    for entry in snapshot.manifest["artifacts"]:
        reference = entry.get("contract", {})
        if reference.get("version") == "2.0.0":
            documents.setdefault(reference["kind"], []).append(
                snapshot.read_json(entry["id"])
            )
    return documents


def _entry(snapshot: RunSnapshot, identifier: str) -> dict[str, Any]:
    matches = [row for row in snapshot.manifest["artifacts"] if row["id"] == identifier]
    if len(matches) != 1:
        raise ContractError(
            f"Explicit artifact ID is absent or ambiguous: {identifier!r}"
        )
    return matches[0]


def _absolute(value: str, base: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ContractError("Expected a POSIX path in the observed native invocation")
    return posixpath.normpath(
        value if value.startswith("/") else posixpath.join(base, value)
    )


def _relative(value: str, root: str, *, base: str | None = None) -> str:
    selected = _absolute(value, root if base is None else base)
    prefix = root.rstrip("/") + "/"
    if not selected.startswith(prefix):
        raise ContractError(f"Native path is outside the selected workspace: {value!r}")
    relative = selected[len(prefix) :]
    if not relative or ".." in PurePosixPath(relative).parts:
        raise ContractError("Native file identity is not canonical")
    return relative


def _option(argv: list[str], name: str) -> str | None:
    values = []
    for index, argument in enumerate(argv[1:], 1):
        if argument == name:
            if index + 1 >= len(argv):
                raise ContractError(f"Native option {name} has no value")
            values.append(argv[index + 1])
        elif argument.startswith(name + "="):
            values.append(argument.split("=", 1)[1])
    if len(values) > 1:
        raise ContractError(f"Repeated native option {name} is unsupported")
    return values[0] if values else None


def _workspace(step: dict[str, Any], receipt: dict[str, Any]) -> str:
    observed = receipt["cwd"]
    if not observed.startswith("/") or posixpath.normpath(observed) != observed:
        raise CompatibilityError(
            "Observed receipt cwd is not a canonical absolute POSIX path"
        )
    parts = [] if step["cwd"] == "." else step["cwd"].split("/")
    current = PurePosixPath(observed)
    if parts and list(current.parts[-len(parts) :]) != parts:
        raise ContractError("Observed cwd disagrees with the selected recipe step")
    for _ in parts:
        current = current.parent
    return str(current)


def _settings(content: bytes, registry: dict[str, Any]) -> dict[str, Any]:
    try:
        text = content.decode("utf-8")
        settings = (
            json.loads(text) if text.lstrip().startswith("{") else yaml.safe_load(text)
        )
        schema = json.loads(
            resources.files("cppulse")
            .joinpath("data/project_config.schema.json")
            .read_bytes()
        )
        jsonschema.Draft7Validator(schema).validate(settings)
        known = {row["id"]: row for row in registry["rules"]}
        if not set(settings.get("rules", {})) <= known.keys():
            raise ValueError("Configuration contains unregistered rule IDs")
        for rule, value in settings.get("rules", {}).items():
            jsonschema.Draft7Validator(known[rule]["configuration_schema"]).validate(
                value
            )
        json.dumps(settings, allow_nan=False)
    except (
        ValueError,
        TypeError,
        UnicodeError,
        yaml.YAMLError,
        jsonschema.ValidationError,
    ) as error:
        raise ContractError(
            f"Invalid retained native configuration: {error}"
        ) from error
    return settings


def _bound_facts(
    snapshot: RunSnapshot, receipt_id: str
) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], str, dict[str, list[dict[str, Any]]]
]:
    snapshot.verify()
    documents = _typed(snapshot)
    matches = [
        row
        for row in documents.get("execution_facts", [])
        if row["receipt"]["id"] == receipt_id
    ]
    if len(matches) != 1:
        raise CompatibilityError(
            "Normalization requires one retained typed execution_facts contract; legacy debug JSON is not proof"
        )
    facts = matches[0]
    receipt = facts["receipt"]
    manifest = snapshot.manifest
    if manifest.get("input_verification") != "verified":
        raise CompatibilityError(
            "Native normalization requires source-verified collection facts"
        )
    if (
        receipt["status"] != "passed"
        or facts["material_status"] != "available"
        or facts["binding"]["status"] != "verified"
    ):
        raise CompatibilityError(
            "Native receipt/material/private-copy binding is not verified successful execution"
        )
    if facts["input_facts"] != facts["input_after_facts"]:
        raise IntegrityError("Native inputs changed during execution")
    context = next(
        row for row in manifest["contexts"] if row["id"] == receipt["context_id"]
    )
    if context["compiler"]["name"] != "cppulse-analyzer" or context["compiler"].get(
        "sha256"
    ) != (facts["executable_fact"] or {}).get("sha256"):
        raise CompatibilityError(
            "Observed executable does not match the declared cppulse-analyzer job hash"
        )
    if context["compiler"]["version"] != __version__:
        raise CompatibilityError(
            "Declared native tool version is outside this normalizer's supported distribution"
        )
    candidates = [
        (plan, step)
        for plan in documents.get("collection_plan", [])
        for step in plan["recipe"]["steps"]
        if step["id"] == receipt_id
        and step["context_id"] == receipt["context_id"]
        and step["argv"] == receipt["argv"]
    ]
    if len(candidates) != 1:
        raise CompatibilityError(
            "Native receipt needs one exact retained collection-plan step"
        )
    plan, step = candidates[0]
    return facts, plan, context, _workspace(step, receipt), documents


def _input_role(
    snapshot: RunSnapshot, facts: dict[str, Any], identifier: str
) -> tuple[str, dict[str, Any], bytes]:
    links = [
        row
        for row in facts["binding"]["input_artifacts"]
        if row["artifact_id"] == identifier
    ]
    if len(links) != 1:
        raise ContractError(
            f"Selected role {identifier!r} is not one observed native input"
        )
    descriptor = _entry(snapshot, identifier)
    return links[0]["path"], descriptor, snapshot.read_bytes(identifier)


def _database(
    content: bytes, workspace: str, process_cwd: str
) -> dict[str, list[dict[str, Any]]]:
    document = _json(content, "compilation database")
    if not isinstance(document, list):
        raise ContractError("Retained compilation database must be an array")
    selected: dict[str, list[dict[str, Any]]] = {}
    for item in document:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("directory"), str)
            or not item["directory"]
            or not isinstance(item.get("file"), str)
            or not item["file"]
        ):
            raise ContractError(
                "Compilation database entry requires directory and file strings"
            )
        arguments, command = item.get("arguments"), item.get("command")
        if arguments is not None:
            if (
                not isinstance(arguments, list)
                or not arguments
                or any(
                    not isinstance(value, str) or not value or "\x00" in value
                    for value in arguments
                )
            ):
                raise ContractError("Compilation database arguments are malformed")
        elif not isinstance(command, str) or not command.strip() or "\x00" in command:
            raise ContractError(
                "Compilation database has no actual file command declaration"
            )
        directory = _absolute(item["directory"], process_cwd)
        try:
            file = _relative(item["file"], workspace, base=directory)
        except ContractError:
            continue  # Entries outside this finite selected workspace stay raw.
        selected.setdefault(file, []).append(item)
    return selected


def _resource(
    snapshot: RunSnapshot,
    facts: dict[str, Any],
    identifier: str | None,
    sources: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if identifier is None:
        return None, None
    _, descriptor, data = _input_role(snapshot, facts, identifier)
    document = _json(data, "resource manifest")
    validate("resource_manifest", document)
    listed = {row["path"]: row for row in document["files"]}
    prefix = document["root"] + "/"
    inputs = {row["path"]: row for row in facts["input_facts"]}
    source_prefix = {path for path in sources if path.startswith(prefix)}
    input_prefix = {path for path in inputs if path.startswith(prefix)}
    if set(listed) != source_prefix or set(listed) != input_prefix:
        raise ContractError(
            "Selected resource manifest, source prefix and native input prefix disagree"
        )
    for path, expected in listed.items():
        if expected != sources[path] or any(
            expected[key] != inputs[path][key] for key in ("sha256", "size_bytes")
        ):
            raise IntegrityError(
                "Selected resource bytes disagree with retained source/input facts"
            )
    return document, descriptor


def _role_copies(
    snapshot: RunSnapshot, registry_id: str, resource_id: str | None
) -> list[tuple[str, str, bytes, str]]:
    copies = []
    for identifier, kind in [
        (registry_id, "rule_registry"),
        (resource_id, "resource_manifest"),
    ]:
        if identifier is None:
            continue
        descriptor = _entry(snapshot, identifier)
        existing = [
            entry
            for entry in snapshot.manifest["artifacts"]
            if entry.get("contract", {}).get("kind") == kind
            and (entry["sha256"], entry["size_bytes"])
            == (descriptor["sha256"], descriptor["size_bytes"])
        ]
        if not existing:
            artifact_id = _id("typed-role:" + kind + ":" + descriptor["sha256"])
            copies.append(
                (
                    artifact_id,
                    "analysis/roles/" + artifact_id + ".json",
                    snapshot.read_bytes(identifier),
                    kind,
                )
            )
    return copies


def _merged_contexts(
    original: list[dict[str, Any]], added: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result = deepcopy(original)
    by_id = {row["id"]: row for row in result}
    for context in added:
        if context["id"] in by_id:
            if by_id[context["id"]] != context:
                raise ContractError(
                    "Observed parse-context ID collides with another definition"
                )
        else:
            result.append(deepcopy(context))
            by_id[context["id"]] = context
    return result


def _validate_result(
    snapshot: RunSnapshot,
    result: NormalizedAnalysis,
    documents: dict[str, list[dict[str, Any]]],
    registry: dict[str, Any],
    resource: dict[str, Any] | None,
) -> None:
    inventory = result.inventory
    if any(
        row["receipt_id"] == inventory["receipt_id"]
        for row in documents.get("analysis_inventory", [])
    ):
        raise ContractError(
            "This receipt already has an analysis inventory; select its original collection snapshot"
        )
    manifest = snapshot.manifest
    manifest["contexts"] = _merged_contexts(
        manifest["contexts"], result.derived_parse_contexts
    )
    for artifact_id, path, content, kind in _role_copies(
        snapshot,
        inventory["registry_artifact_id"],
        inventory.get("resource_manifest_artifact_id"),
    ):
        manifest["artifacts"].append(
            {
                "id": artifact_id,
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
                "media_type": "application/json",
                "contract": {"kind": kind, "version": "2.0.0"},
            }
        )
        documents.setdefault(kind, []).append(
            registry if kind == "rule_registry" else resource
        )
    documents.setdefault("analysis_inventory", []).append(inventory)
    documents.setdefault("observations", []).append(result.observations)
    if result.metrics is not None:
        documents.setdefault("analysis_metrics", []).append(result.metrics)
    validate_bundle({"run_manifest": manifest, **documents})


def _include_binding(
    native: dict[str, Any] | None,
    *,
    arguments: list[str],
    workspace: str,
    repo: str,
    sources: dict[str, Any],
    input_facts: dict[str, Any],
    input_links: dict[str, str],
    read_content: Any,
    external_buffers: dict[str, bytes] | None = None,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Compare actual TU include bytes with the finite frozen native inputs."""
    if native is None:
        return (
            "unverified",
            ["Legacy native report lacks an observed TU include-buffer inventory."],
            [
                {
                    "id": "unobserved-native-include-buffers",
                    "sha256": None,
                    "availability": "unavailable",
                }
            ],
        )
    paths = {_relative(native["path"], workspace, base=repo)}
    edges = native["includes"]
    dependencies = [
        {
            "id": "native-tu-includes-" + digest_json(native["path"]),
            "sha256": digest_json(edges),
            "availability": "available",
        }
    ]
    opaque = any(
        argument.startswith(
            (
                "@",
                "-include",
                "-imacros",
                "-fmodule",
                "-ivfsoverlay",
                "-ast-merge",
                "-fpch",
                "-Wp,",
            )
        )
        for argument in arguments
    )
    missing_tu = native["status"] not in {"analyzed", "partial"}
    status = "unverified" if opaque or missing_tu else "matched"
    limitations = (
        [
            "Precompiled, forced-include, module or overlay input closure is not qualified by the TU inclusion visitor."
        ]
        if opaque
        else []
    )
    if missing_tu:
        limitations.append(
            "No analyzed translation unit establishes parsed-buffer coherence."
        )
    checked_external = []
    for edge in edges:
        identity = edge.get("content_identity")
        if identity is None or identity["status"] != "available":
            if status != "mismatched":
                status = "unverified"
            limitations.append(
                "An actual TU include buffer identity is unavailable or legacy path-only."
            )
            continue
        external = (external_buffers or {}).get(edge["target"])
        if external is not None:
            if identity["sha256"] != hashlib.sha256(external).hexdigest() or identity[
                "size_bytes"
            ] != len(external):
                status = "mismatched"
                limitations.append(
                    "Retained external SDK bytes differ from actual TU buffers."
                )
            else:
                checked_external.append(external)
            continue
        try:
            path = _relative(edge["target"], workspace, base=repo)
        except ContractError:
            path = None
        expected = sources.get(path)
        fact = input_facts.get(path)
        if expected is not None and fact is not None and path in input_links:
            paths.add(path)
        if expected is None or fact is None or path not in input_links:
            if status != "mismatched":
                status = "unverified"
            limitations.append(
                "An observed TU include buffer is outside the finite retained native input inventory."
            )
        elif any(
            identity[key] != expected[key] or fact[key] != expected[key]
            for key in ("sha256", "size_bytes")
        ):
            status = "mismatched"
            limitations.append(
                "An actual TU include buffer differs from its frozen retained native input."
            )
    if status != "mismatched":
        pattern = re.compile(
            rb"\b(?:embed|__has_include(?:_next)?|__has_embed|__DATE__|__TIME__|__TIMESTAMP__|_Pragma|__pragma)\b|##|%:%:|\?\?[=/]"
        )

        def unsupported(data: bytes) -> bool:
            logical = (
                data.replace(b"\\\r\n", b"").replace(b"\\\n", b"").replace(b"\\\r", b"")
            )
            return pattern.search(logical) is not None

        macro_arguments = [
            argument
            for index, argument in enumerate(arguments)
            if argument.startswith(("-D", "-U"))
            or (index and arguments[index - 1] in {"-D", "-U"})
        ]
        if (
            unsupported(" ".join(macro_arguments).encode("utf-8"))
            or any(unsupported(read_content(path)) for path in sorted(paths))
            or any(unsupported(content) for content in checked_external)
        ):
            status = "unverified"
            limitations.append(
                "Filesystem/time preprocessing queries or opaque macro construction require additional input-closure evidence."
            )
    return status, list(dict.fromkeys(limitations)), dependencies


def normalize_native_analysis(
    snapshot: RunSnapshot,
    *,
    receipt_id: str,
    report_artifact_id: str,
    registry_artifact_id: str,
    config_artifact_id: str,
    compilation_database_artifact_id: str | None = None,
    resource_manifest_artifact_id: str | None = None,
    requested_files: list[str],
    requested_rules: list[str],
) -> NormalizedAnalysis:
    """Normalize only checked, fresh, typed native-job facts without running tools."""
    with tempfile.TemporaryDirectory(prefix="cppulse-native-report-") as directory:
        with ExitStack() as resources:
            return _normalize_native_analysis(
                snapshot,
                receipt_id=receipt_id,
                report_artifact_id=report_artifact_id,
                registry_artifact_id=registry_artifact_id,
                config_artifact_id=config_artifact_id,
                compilation_database_artifact_id=compilation_database_artifact_id,
                resource_manifest_artifact_id=resource_manifest_artifact_id,
                requested_files=requested_files,
                requested_rules=requested_rules,
                resources=resources,
                directory=Path(directory),
            )


def _normalize_native_analysis(
    snapshot: RunSnapshot,
    *,
    receipt_id: str,
    report_artifact_id: str,
    registry_artifact_id: str,
    config_artifact_id: str,
    compilation_database_artifact_id: str | None,
    resource_manifest_artifact_id: str | None,
    requested_files: list[str],
    requested_rules: list[str],
    resources: ExitStack,
    directory: Path,
) -> NormalizedAnalysis:
    facts, plan, job, workspace, documents = _bound_facts(snapshot, receipt_id)
    receipt = facts["receipt"]
    sources = {row["path"]: row for row in snapshot.manifest["source"]["files"]}
    if (
        not requested_files
        or len(set(requested_files)) != len(requested_files)
        or not set(requested_files) <= sources.keys()
    ):
        raise ContractError(
            "Requested analysis files must be unique selected source identities"
        )
    roles = [
        registry_artifact_id,
        config_artifact_id,
        compilation_database_artifact_id,
        resource_manifest_artifact_id,
    ]
    selected = [role for role in roles if role is not None]
    if len(selected) != len(set(selected)):
        raise ContractError("Distinct native input roles cannot alias one artifact")
    registry_path, registry_descriptor, registry_bytes = _input_role(
        snapshot, facts, registry_artifact_id
    )
    registry = _json(registry_bytes, "rule registry")
    validate("rule_registry", registry)
    rules = {row["id"]: row for row in registry["rules"]}
    supported_rules = {row["id"]: row for row in load_rule_registry()["rules"]}
    if rules != supported_rules:
        raise CompatibilityError(
            "Retained registry versions/metadata do not match the packaged current native registry"
        )
    if (
        not requested_rules
        or len(set(requested_rules)) != len(requested_rules)
        or not set(requested_rules) <= rules.keys()
    ):
        raise ContractError("Requested rule IDs must be unique known registry entries")
    config_path, config_descriptor, config_bytes = _input_role(
        snapshot, facts, config_artifact_id
    )
    settings = _settings(config_bytes, registry)
    output_links = [
        row
        for row in facts["binding"]["output_artifacts"]
        if row["artifact_id"] == report_artifact_id
    ]
    if len(output_links) != 1:
        raise ContractError("Native report is not an observed output artifact")
    output_directory = _absolute(
        _option(receipt["argv"], "--output") or "output", receipt["cwd"]
    )
    expected_report = _relative(
        posixpath.join(output_directory, "findings.json"), workspace
    )
    if output_links[0]["path"] != expected_report:
        raise ContractError(
            "Selected native report output does not match the observed --output/findings.json location"
        )
    output_fact = next(
        row for row in facts["output_facts"] if row["path"] == output_links[0]["path"]
    )
    report_descriptor = _entry(snapshot, report_artifact_id)
    if output_fact["freshness"] not in {"created", "modified"} or any(
        output_fact[key] != report_descriptor[key] for key in ("sha256", "size_bytes")
    ):
        raise IntegrityError(
            "Native report is stale or differs from its observed output bytes"
        )
    from cppulse.contracts.json_projection import ProjectionLimits
    from cppulse.contracts.json_stream import JsonStreamLimits
    from cppulse.native_report_reader import open_native_report
    from cppulse.streamed_native_metrics import validate_streamed_native_metrics

    # Exact retained bytes, closed JSON schema and maintenance semantics must all
    # pass before the original source/context/rule normalization below. Keeping
    # the contexts open avoids ever materializing all native metric payloads.
    stream = resources.enter_context(snapshot.open_binary(report_artifact_id))
    reader = resources.enter_context(
        open_native_report(
            stream,
            expected_sha256=report_descriptor["sha256"],
            expected_size=report_descriptor["size_bytes"],
            directory=directory,
            source_guard=snapshot._check_manifest,
            projection_limits=ProjectionLimits(
                json_limits=JsonStreamLimits(
                    max_bytes=min(plan["limits"]["max_artifact_bytes"], 1024**3),
                    max_item_bytes=16 * 1024**2,
                    max_array_items=10_000_000,
                )
            ),
        )
    )
    report = reader.document
    native_header = report["metadata"].get("analysis", {}).get("native_metrics")
    validate_streamed_native_metrics(
        reader.iter_analysis_files(),
        reader.iter_metric_files(),
        metrics_header=(
            {key: value for key, value in native_header.items() if key != "files"}
            if native_header is not None
            else None
        ),
        directory=directory,
    )
    analysis = report["metadata"].get("analysis")
    if not isinstance(analysis, dict) or "parser" not in analysis:
        raise CompatibilityError(
            "Native report has no observed parser/parse-context trace"
        )
    parser = analysis["parser"]
    enabled = analysis["enabled_rules"]
    if not set(enabled) <= rules.keys():
        raise ContractError("Native report enables unknown registry rules")
    expected_enabled = {
        identifier
        for identifier, rule in rules.items()
        if settings.get("rules", {})
        .get(identifier, {})
        .get(
            "enabled",
            rule["configuration_schema"]
            .get("properties", {})
            .get("enabled", {})
            .get("default", True),
        )
    }
    if set(enabled) != expected_enabled:
        raise ContractError(
            "Native enabled-rule report disagrees with retained configuration/registry"
        )
    repo_option = _option(receipt["argv"], "--repo")
    if repo_option is None:
        raise CompatibilityError(
            "Native normalization requires explicit repository analysis mode"
        )
    repo = _absolute(repo_option, receipt["cwd"])
    if _absolute(report["metadata"]["repo_path"], receipt["cwd"]) != repo:
        raise ContractError(
            "Native report repository differs from the observed invocation"
        )
    if repo != workspace and not repo.startswith(workspace.rstrip("/") + "/"):
        raise ContractError(
            "Native repository lies outside the selected collection workspace"
        )
    config_selected = _option(receipt["argv"], "--config")
    config_matches = (
        config_selected is not None
        and _relative(config_selected, workspace, base=receipt["cwd"]) == config_path
    )
    db_entries: dict[str, list[dict[str, Any]]] = {}
    db_descriptor = None
    db_matches = False
    if compilation_database_artifact_id is not None:
        db_path, db_descriptor, db_bytes = _input_role(
            snapshot, facts, compilation_database_artifact_id
        )
        db_entries = _database(db_bytes, workspace, receipt["cwd"])
        selected_db = _option(receipt["argv"], "--compilation-database")
        if selected_db is not None:
            selected_absolute = _absolute(selected_db, receipt["cwd"])
            if PurePosixPath(selected_absolute).name != "compile_commands.json":
                selected_absolute = posixpath.join(
                    selected_absolute, "compile_commands.json"
                )
            db_matches = _relative(selected_absolute, workspace) == db_path
    resource, resource_descriptor = _resource(
        snapshot, facts, resource_manifest_artifact_id, sources
    )
    input_links = {
        row["path"]: row["artifact_id"] for row in facts["binding"]["input_artifacts"]
    }
    input_facts = {row["path"]: row for row in facts["input_facts"]}
    source_bytes: dict[str, bytes] = {}

    def content(path: str) -> bytes:
        if path not in source_bytes:
            expected = sources[path]
            artifact_id = input_links.get(path)
            if artifact_id is None:
                candidates = [
                    entry["id"]
                    for entry in snapshot.manifest["artifacts"]
                    if all(
                        entry[key] == expected[key] for key in ("sha256", "size_bytes")
                    )
                ]
                if not candidates:
                    raise IntegrityError("Native source content is not retained")
                artifact_id = candidates[0]
            source_bytes[path] = snapshot.read_bytes(artifact_id)
            if (
                hashlib.sha256(source_bytes[path]).hexdigest(),
                len(source_bytes[path]),
            ) != (expected["sha256"], expected["size_bytes"]):
                raise IntegrityError(
                    "Retained source bytes do not match the selected source identity"
                )
        return source_bytes[path]

    from cppulse.native_metric_index import MetricRowIndex

    native_files = MetricRowIndex(
        analysis.get("native_metrics", {}).get("files", []),
        lambda path: _relative(path, workspace, base=repo),
    )
    coverage: dict[str, dict[str, Any]] = {}
    for row in analysis["files"]:
        path = _relative(row["path"], workspace, base=repo)
        if path in coverage:
            raise ContractError(
                "Native file inventory contains duplicate canonical identities"
            )
        if path not in sources and row["status"] != "excluded":
            raise ContractError(
                "Native report contains an active file outside selected source inventory"
            )
        coverage[path] = row
    ast_files = [
        path
        for path, row in coverage.items()
        if row["status"] in {"analyzed", "partial"}
    ]
    loc = sum(_physical_loc(content(path)) for path in ast_files)
    if (
        report["metadata"]["file_count"] != len(ast_files)
        or report["metadata"]["total_loc"] != loc
    ):
        raise ContractError(
            "Native source file/LOC totals disagree with retained analyzed bytes"
        )
    category_counts = dict.fromkeys(
        ["memory_safety", "modernization", "complexity", "misra"], 0
    )
    severity_counts = dict.fromkeys(["error", "warning", "info"], 0)
    findings: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, finding in enumerate(report["findings"]):
        path = _relative(finding["file"], workspace, base=repo)
        row = coverage.get(path)
        rule = rules.get(finding["rule_id"])
        if (
            row is None
            or row["status"] not in {"analyzed", "partial"}
            or path not in sources
            or rule is None
            or finding["rule_id"] not in enabled
            or rule["category"] != finding["category"]
        ):
            raise ContractError(
                "Native finding disagrees with source traversal/enabled registry rules"
            )
        lines = _physical_loc(content(path))
        if finding["line"] > lines or not finding["message"].strip():
            raise ContractError(
                "Native finding location/message is inconsistent with retained source"
            )
        category_counts[finding["category"]] += 1
        severity_counts[finding["severity"]] += 1
        findings.setdefault(path, []).append((index, finding))
    if report["summary"] != {
        "total_findings": len(report["findings"]),
        "by_category": category_counts,
        "by_severity": severity_counts,
    }:
        raise ContractError(
            "Native finding summary totals disagree with actual findings"
        )
    dependencies = [
        {
            "id": registry_artifact_id,
            "sha256": registry_descriptor["sha256"],
            "availability": "available",
        },
        {
            "id": config_artifact_id,
            "sha256": config_descriptor["sha256"],
            "availability": "available",
        },
    ]
    if db_descriptor is not None:
        dependencies.append(
            {
                "id": compilation_database_artifact_id,
                "sha256": db_descriptor["sha256"],
                "availability": "available",
            }
        )
    if resource_descriptor is not None:
        dependencies.append(
            {
                "id": resource_manifest_artifact_id,
                "sha256": resource_descriptor["sha256"],
                "availability": "available",
            }
        )
    else:
        dependencies.append(
            {
                "id": "unbound-clang-resources",
                "sha256": None,
                "availability": "unavailable",
            }
        )
    contexts: dict[str, dict[str, Any]] = {}
    rows, observations = [], []
    inventory_id = _id(
        "inventory:"
        + job["id"]
        + ":"
        + receipt_id
        + ":"
        + report_descriptor["sha256"]
        + ":"
        + digest_json([requested_files, requested_rules])
    )
    for path in requested_files:
        observed = coverage.get(path)
        if observed is None:
            rows.append(
                {
                    "file": path,
                    "parse_context_id": None,
                    "status": "missing",
                    "error_count": 0,
                    "context_source": "none",
                    "context_match": "unverified",
                    "executed_rules": [],
                    "finding_count": 0,
                    "limitations": [
                        "Requested file is absent from the native traversal inventory."
                    ],
                }
            )
            continue
        status = observed["status"]
        if status not in {"analyzed", "partial", "failed"}:
            rows.append(
                {
                    "file": path,
                    "parse_context_id": None,
                    "status": status,
                    "error_count": 0,
                    "context_source": "none",
                    "context_match": "unverified",
                    "executed_rules": [],
                    "finding_count": 0,
                    "limitations": [
                        "No observed parse attempt completed for this requested file."
                    ],
                }
            )
            continue
        arguments, cwd = (
            observed.get("parse_arguments"),
            observed.get("working_directory"),
        )
        if arguments is None or cwd is None:
            if status == "failed":
                rows.append(
                    {
                        "file": path,
                        "parse_context_id": None,
                        "status": "failed",
                        "error_count": int(observed["error_count"]),
                        "context_source": "none",
                        "context_match": "unverified",
                        "executed_rules": [],
                        "finding_count": 0,
                        "limitations": [
                            "Native failure preceded an observed parse attempt."
                        ],
                    }
                )
                continue
            raise CompatibilityError(
                "Analyzed native report lacks exact observed parse arguments/cwd"
            )
        if any("\x00" in argument for argument in arguments):
            raise ContractError("Observed parse arguments contain NUL")
        observed_cwd = _absolute(cwd, receipt["cwd"])
        buffer_match, buffer_limits, buffer_dependencies = _include_binding(
            native_files.get(path),
            arguments=arguments,
            workspace=workspace,
            repo=repo,
            sources=sources,
            input_facts=input_facts,
            input_links=input_links,
            read_content=content,
        )
        context = context_identity(
            {
                "compiler": deepcopy(parser),
                "argv": deepcopy(arguments),
                "working_directory": cwd,
                "language_standard": None,
                "target": None,
                "provenance": "observed",
                "dependencies": deepcopy(dependencies) + buffer_dependencies,
                "limitations": _LIMITS,
            }
        )
        contexts[context["id"]] = context
        match, limitations = buffer_match, buffer_limits
        source_fact = input_facts.get(path)
        if (
            source_fact is None
            or path not in input_links
            or any(
                source_fact[key] != sources[path][key]
                for key in ("sha256", "size_bytes")
            )
        ):
            if match != "mismatched":
                match = "unverified"
            limitations.append(
                "Requested source was not a bound unchanged native input."
            )
        if observed_cwd != receipt["cwd"]:
            match = "mismatched"
            limitations.append(
                "Reported native process cwd differs from observed execution cwd."
            )
        if not config_matches:
            match = "mismatched"
            limitations.append(
                "Retained configuration was not explicitly selected by the native invocation."
            )
        if observed["compile_context"] != "database":
            if match != "mismatched":
                match = "unverified"
            limitations.append(
                "Inferred/fallback context is not an exact requested database command."
            )
        elif not db_matches:
            if match != "mismatched":
                match = "unverified"
            limitations.append(
                "An explicit retained compilation database was not selected."
            )
        elif len(db_entries.get(path, [])) != 1:
            if match != "mismatched":
                match = "unverified"
            limitations.append(
                "Requested file has no single unambiguous retained database command."
            )
        resource_flags = [
            argument.split("=", 1)[1]
            for argument in arguments
            if argument.startswith("-resource-dir=")
        ]
        for index, argument in enumerate(arguments[:-1]):
            if argument == "-resource-dir":
                resource_flags.append(arguments[index + 1])
        if (
            resource is None
            or len(resource_flags) != 1
            or _absolute(resource_flags[0], cwd)
            != _absolute(resource["root"], workspace)
        ):
            if match != "mismatched":
                match = "unverified"
            limitations.append(
                "Selected finite parser resources are external, unbound or ambiguous."
            )
        row = {
            "file": path,
            "parse_context_id": context["id"],
            "status": status,
            "error_count": int(observed["error_count"]),
            "context_source": observed["compile_context"],
            "context_match": match,
            "buffer_coherence": (
                "verified" if buffer_match == "matched" else buffer_match
            ),
            "executed_rules": (
                list(enabled)
                if status == "analyzed" and observed["error_count"] == 0
                else []
            ),
            "finding_count": len(findings.get(path, [])),
            "limitations": limitations,
        }
        rows.append(row)
        for index, finding in findings.get(path, []):
            rule = rules[finding["rule_id"]]
            fingerprint = digest_json(
                {
                    "version": "native-1",
                    "file": path,
                    "context": context["digest"],
                    "rule_id": rule["id"],
                    "rule_version": rule["version"],
                    "line": int(finding["line"]),
                    "column": int(finding.get("column", 1)),
                    "severity": finding["severity"],
                    "message": finding["message"],
                }
            )
            observations.append(
                {
                    "id": _id(
                        "observation:"
                        + job["id"]
                        + ":"
                        + receipt_id
                        + ":"
                        + report_descriptor["sha256"]
                        + ":"
                        + str(index)
                    ),
                    "producer": deepcopy(_PRODUCER),
                    "rule_id": rule["id"],
                    "rule_version": rule["version"],
                    "file": path,
                    "context_id": context["id"],
                    "line": int(finding["line"]),
                    "column": int(finding.get("column", 1)),
                    "severity": finding["severity"],
                    "message": finding["message"],
                    "fingerprint": fingerprint,
                    "fingerprint_version": "native-1",
                    "evidence_ids": [],
                }
            )
    inventory = {
        "version": "2.0.0",
        "id": inventory_id,
        "source_digest": snapshot.manifest["source"]["digest"],
        "producer": deepcopy(_PRODUCER),
        "receipt_id": receipt_id,
        "job_context_id": job["id"],
        "report_artifact_id": report_artifact_id,
        "registry_artifact_id": registry_artifact_id,
        "config_artifact_id": config_artifact_id,
        "compilation_database_artifact_id": compilation_database_artifact_id,
        "registry_sha256": registry_descriptor["sha256"],
        "requested_files": deepcopy(requested_files),
        "requested_rules": deepcopy(requested_rules),
        "enabled_rules": deepcopy(enabled),
        "items": rows,
        "limitations": list(_LIMITS),
    }
    if resource_manifest_artifact_id is not None:
        inventory["resource_manifest_artifact_id"] = resource_manifest_artifact_id
    result = NormalizedAnalysis(
        inventory,
        {
            "version": "2.0.0",
            "source_digest": inventory["source_digest"],
            "analysis_inventory_id": inventory_id,
            "items": observations,
        },
        list(contexts.values()),
    )
    raw_metrics = analysis.get("native_metrics")
    if raw_metrics is not None:
        metrics = _normalize_metrics(raw_metrics, inventory, workspace, repo, content)
        result = NormalizedAnalysis(
            result.inventory,
            result.observations,
            result.derived_parse_contexts,
            metrics,
        )
    _validate_result(snapshot, result, documents, registry, resource)
    return result


def _normalize_metrics(
    raw: dict[str, Any],
    inventory: dict[str, Any],
    workspace: str,
    repo: str,
    content: Any,
    *,
    duplication_counts: dict[str, DuplicateCount] | None = None,
) -> dict[str, Any]:
    from cppulse.contracts.maintenance import (
        FILE_UNITS,
        FUNCTION_UNITS,
        METRIC_VERSION,
        DUPLICATION_VERSION,
    )
    from cppulse.indexed_duplication import indexed_duplicate_token_counts
    from cppulse.native_metric_index import MetricRowIndex

    rows = {row["file"]: row for row in inventory["items"]}
    selected = MetricRowIndex(
        raw["files"], lambda path: _relative(path, workspace, base=repo)
    )
    selected_files = [file for file, row in rows.items() if row["status"] != "excluded"]

    def streams():
        for file in selected_files:
            native = selected.get(file)
            yield (
                file,
                (
                    native["token_stream"]
                    if native is not None
                    else {"availability": "unavailable", "complete": False}
                ),
            )
            native = None

    if duplication_counts is None:
        # Rows are already checked and replayable. The index independently
        # checks this declaration against all consumed original frames at EOF.
        scope_complete = True
        for file in selected_files:
            native = selected.get(file)
            if (
                native is None
                or not native["token_stream"]["complete"]
                or native["token_stream"]["availability"] != "measured"
            ):
                scope_complete = False
            native = None
        with tempfile.TemporaryDirectory(
            prefix="cppulse-metric-duplicates-"
        ) as directory:
            duplicates = indexed_duplicate_token_counts(
                streams(), directory=Path(directory), scope_complete=scope_complete
            )
    else:
        # A multi-process producer computes duplication over its entire declared
        # scope once. Recomputing within one unit would invent clean zeroes for
        # cross-unit duplicates or for an unstarted peer.
        if not set(selected_files) <= duplication_counts.keys():
            raise ContractError("Global duplication counts omit selected files")
        for count in duplication_counts.values():
            if not isinstance(count, DuplicateCount) or (
                (count.tokens is None) != (count.lines is None)
            ):
                raise ContractError("Invalid global duplication count")
            if any(
                value is not None
                and (type(value) is not int or value < 0)  # noqa: E721 -- exact count
                for value in (count.tokens, count.lines)
            ):
                raise ContractError("Invalid global duplication count")
        duplicates = duplication_counts
    items = []
    for file, observed in sorted(rows.items()):
        native = selected.get(file)
        if native is None or observed["parse_context_id"] is None:
            continue
        digest = native.get("source_content_sha256")
        if (
            observed["status"] in {"analyzed", "partial"}
            and digest != hashlib.sha256(content(file)).hexdigest()
        ):
            raise ContractError(
                "Native metric buffer content digest differs from retained input"
            )
        if observed["status"] in {"analyzed", "partial"}:
            physical = _physical_loc(content(file))
            if native["physical_loc"] != physical:
                raise ContractError(
                    "Native physical LOC differs from retained buffer content"
                )
            if native["token_stream"]["complete"]:
                code_lines: set[int] = set()
                for token in native["token_stream"]["records"]:
                    last = token["end_line"] - int(
                        token["end_column"] == 1 and token["end_line"] > token["line"]
                    )
                    code_lines.update(range(token["line"], min(last, physical) + 1))
                if native["code_loc"] != len(code_lines):
                    raise ContractError(
                        "Native code LOC differs from retained complete token extent union"
                    )
        complete = (
            native["measurement_complete"]
            and observed["status"] == "analyzed"
            and not observed["error_count"]
        )

        def cell(
            name: str,
            value: Any,
            units: str,
            symbol: str | None = None,
            location: dict[str, int] | None = None,
            version: str = METRIC_VERSION,
            available: bool = complete,
            reasons: list[str] | None = None,
        ) -> None:
            row = {
                "id": _id(
                    "metric:"
                    + inventory["id"]
                    + ":"
                    + digest_json(
                        [file, observed["parse_context_id"], symbol, name, version]
                    )
                ),
                "file": file,
                "symbol": symbol,
                "context_id": observed["parse_context_id"],
                "metric": name,
                "metric_version": version,
                "value": value if available else None,
                "units": units,
                "availability": "available" if available else "unavailable",
                "limitations": (
                    []
                    if available
                    else (reasons or ["Native measurement is incomplete."])
                ),
            }
            if location is not None:
                row["location"] = location
            items.append(row)

        for name in ("physical_loc", "code_loc", "function_count"):
            cell(
                name,
                native[name],
                FILE_UNITS[name],
                available=complete and native[name] is not None,
            )
        for function in native["functions"]:
            location = {
                key: function[key]
                for key in ("line", "column", "end_line", "end_column")
            }
            if any(value is None for value in location.values()):
                continue
            for name, units in FUNCTION_UNITS.items():
                cell(
                    name,
                    function[name],
                    units,
                    function["symbol"],
                    location,
                    available=complete and function["availability"] == "measured",
                    reasons=function["limitations"],
                )
        count = duplicates.get(file)
        if count is not None:
            for name, value in (
                ("duplicate_tokens", count.tokens),
                ("duplicate_lines", count.lines),
            ):
                cell(
                    name,
                    value,
                    FILE_UNITS[name],
                    version=DUPLICATION_VERSION,
                    available=complete and value is not None,
                    reasons=list(count.limitations),
                )
    result = {
        "version": "2.0.0",
        "source_digest": inventory["source_digest"],
        "analysis_inventory_id": inventory["id"],
        "job_context_id": inventory["job_context_id"],
        "items": items,
    }
    validate("analysis_metrics", result)
    return result


def persist_native_analysis(
    snapshot: RunSnapshot, *, workspace: Path, store: RunStore | Path, **selection: Any
) -> RunSnapshot:
    """Publish a new local derived run, preserving parent bytes and source checks."""
    result = normalize_native_analysis(snapshot, **selection)
    manifest = snapshot.manifest
    errors = verify_inputs(workspace, manifest["source"])
    if errors:
        raise InputChanged(
            "Selected sources changed before derived publication: " + "; ".join(errors)
        )

    def source_check() -> None:
        changed = verify_inputs(workspace, manifest["source"])
        if changed:
            raise InputChanged(
                "Selected sources changed during derived publication: "
                + "; ".join(changed)
            )

    plans = _typed(snapshot)["collection_plan"]
    metadata_cap = min(int(plan["limits"]["max_metadata_bytes"]) for plan in plans)

    def checked_metadata(document: dict[str, Any]) -> None:
        if len(_json_bytes(document)) > metadata_cap:
            raise IntegrityError("Derived control JSON exceeds max_metadata_bytes")

    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with tempfile.TemporaryDirectory(prefix="cppulse-analysis-") as temporary:
        temporary = Path(temporary)
        with runtime.begin() as stage:
            for entry in manifest["artifacts"]:
                descriptor = stage.copy_artifact(
                    entry["id"],
                    snapshot.path / entry["path"],
                    entry["path"],
                    entry["media_type"],
                    contract=entry.get("contract"),
                )
                if any(
                    descriptor[key] != entry[key] for key in ("sha256", "size_bytes")
                ):
                    raise IntegrityError(
                        "Parent artifact changed during derived copying"
                    )
            parent_path = snapshot.path / "run_manifest.json"
            descriptor = os.open(
                parent_path,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
            )
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise IntegrityError("Parent manifest is not a regular file")
                parent_bytes = stream.read(metadata_cap + 1)
            if (
                len(parent_bytes) > metadata_cap
                or hashlib.sha256(parent_bytes).hexdigest() != snapshot.manifest_sha256
            ):
                raise IntegrityError(
                    "Parent manifest bytes changed or exceed metadata cap"
                )
            parent_copy = temporary / "parent.json"
            parent_copy.write_bytes(parent_bytes)
            provenance_id = _id("parent:" + snapshot.manifest_sha256)
            stage.copy_artifact(
                provenance_id,
                parent_copy,
                "analysis/provenance/" + provenance_id + ".json",
                "application/json",
            )
            for artifact_id, path, data, kind in _role_copies(
                snapshot,
                selection["registry_artifact_id"],
                selection.get("resource_manifest_artifact_id"),
            ):
                if len(data) > metadata_cap:
                    raise IntegrityError("Typed role JSON exceeds max_metadata_bytes")
                local = temporary / (artifact_id + ".json")
                local.write_bytes(data)
                stage.copy_artifact(
                    artifact_id, local, path, "application/json", contract=kind
                )
            outputs = [
                ("analysis_inventory", result.inventory),
                ("observations", result.observations),
            ]
            if result.metrics is not None:
                outputs.append(("analysis_metrics", result.metrics))
            for kind, document in outputs:
                checked_metadata(document)
                artifact_id = _id(kind + ":" + result.inventory["id"])
                stage.write_json(
                    "analysis/" + kind + "/" + artifact_id + ".json",
                    document,
                    contract=kind,
                    artifact_id=artifact_id,
                )
            derived = deepcopy(manifest)
            derived["run_id"] = stage.run_id
            derived["contexts"] = _merged_contexts(
                manifest["contexts"], result.derived_parse_contexts
            )
            complete = all(
                row["status"] == "analyzed"
                and row["context_match"] == "matched"
                and set(result.inventory["requested_rules"])
                <= set(row["executed_rules"])
                for row in result.inventory["items"]
            )
            if derived["status"] == "completed" and not complete:
                derived["status"] = "partial"
            derived["stages"].append(
                {
                    "id": _id("normalize:" + result.inventory["id"]),
                    "status": "passed",
                    "depends_on": [],
                    "reason": "Checked native facts normalized; this is not a policy pass.",
                }
            )
            derived["artifacts"] = stage.artifacts
            derived["finished_at"] = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            derived["versions"] = {
                **derived["versions"],
                "native-normalizer": _VERSION,
                "parent-manifest-sha256": snapshot.manifest_sha256,
            }
            derived["limitations"] = list(
                dict.fromkeys([*derived["limitations"], *_LIMITS])
            )
            derived["input_verification"] = "verified"
            checked_metadata(derived)
            return stage.publish(derived, source_check=source_check)
