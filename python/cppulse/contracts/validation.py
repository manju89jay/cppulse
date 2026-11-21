"""Validate packaged draft-07 schemas without network schema retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import deque
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from fractions import Fraction
from importlib import resources
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping

import jsonschema
from referencing import Registry, Resource

from cppulse.errors import ContractError, UnsupportedVersion

_VERSION = "2.0.0"
_KINDS = {
    "source",
    "context",
    "artifact",
    "run_manifest",
    "recipe",
    "collection_plan",
    "execution_receipt",
    "evidence",
    "policy",
    "assessment",
    "baseline",
    "observations",
    "analysis_metrics",
    "maintenance_health",
    "analysis_inventory",
    "analysis_scope",
    "work_unit_analysis_binding",
    "used_sdk_inputs",
    "execution_facts",
    "resource_manifest",
    "coverage_facts",
    "external_analysis_facts",
    "transfer_bundle",
    "distribution_subject",
    "consumer_matrix",
    "consumer_usage",
    "consumer_comparison",
    "snapshot_view",
    "collection_request",
    "workflow_result",
    "check_result",
    "assessment_lineage",
    "finding_baseline",
    "finding_comparison",
    "finding_suppressions",
    "finding_baseline_request",
    "finding_check_request",
    "sanitizer_facts",
    "rule_registry",
    "risk_scores",
    "shared_history",
}
_PROTOTYPE_KINDS = {"findings", "git_metrics", "risk_scores", "roadmap"}
_ALIASES = {"risk_v2": "risk_scores"}
_EVALUATORS = {
    "finding_limit",
    "minimum_analysis_coverage",
    "test_outcomes",
    "required_contexts",
}


def _fail(message: str, path: str = "", code: str = "INVALID_CONTRACT") -> None:
    raise ContractError(message, path=path, code=code)


def _pointer(parts: Any) -> str:
    return "".join(
        "/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts
    )


def _schema_path(kind: str, version: str) -> tuple[str, str]:
    kind = _ALIASES.get(kind, kind)
    if kind == "native_install" and version == "1.0.0":
        return "install_v1", kind
    if version == _VERSION and kind in _KINDS:
        return "v2", kind
    if version == "1.0.0" and kind == "risk_scores":
        return "legacy", kind
    if version == "prototype_v1" and kind in _PROTOTYPE_KINDS:
        return "prototype_v1", kind
    raise UnsupportedVersion(f"Unsupported local contract {kind!r} version {version!r}")


@lru_cache(maxsize=None)
def _read_schema(kind: str, version: str) -> dict[str, Any]:
    group, name = _schema_path(kind, version)
    source = resources.files(__package__).joinpath(
        "schemas", group, f"{name}.schema.json"
    )
    schema = json.loads(source.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    return schema


def load_schema(kind: str, version: str | None = None) -> dict[str, Any]:
    """Load an independent copy of a packaged schema.

    Args:
        kind: Contract name, such as run_manifest or risk_scores.
        version: Exact supported version; prototype_v1 explicitly opts into
            the unreleased legacy-shaped native pipeline contracts.

    Raises:
        UnsupportedVersion: If no supported local schema exists.
    """
    kind = _ALIASES.get(kind, kind)
    selected = version or ("1.0.0" if kind == "native_install" else _VERSION)
    return deepcopy(_read_schema(kind, selected))


@lru_cache(maxsize=1)
def _registry() -> Registry:
    folder = resources.files(__package__).joinpath("schemas", "v2")
    entries = []
    for path in folder.iterdir():
        if path.name.endswith(".schema.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            jsonschema.Draft7Validator.check_schema(schema)
            entries.append((schema["$id"], Resource.from_contents(schema)))
    # No retrieval callback: unavailable references fail rather than go online.
    return Registry().with_resources(entries)


def _safe_path(value: str, pointer: str, *, allow_dot: bool = False) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
        or path.as_posix() != value
        or (value == "." and not allow_dot)
    ):
        _fail(
            f"Expected a canonical relative path, got {value!r}", pointer, "UNSAFE_PATH"
        )


def _collection_path(value: str, pointer: str, *, allow_dot: bool = False) -> None:
    """Validate a portable file identity without changing older path contracts."""
    _safe_path(value, pointer, allow_dot=allow_dot)
    reserved = {"con", "prn", "aux", "nul"} | {
        prefix + str(number) for prefix in ["com", "lpt"] for number in range(1, 10)
    }
    for part in PurePosixPath(value).parts:
        if (
            any(
                ord(character) < 32
                or 127 <= ord(character) <= 159
                or character in '<>:"|?*'
                for character in part
            )
            or part.endswith((".", " "))
            or part.split(".", 1)[0].casefold() in reserved
        ):
            _fail(
                f"Expected a portable canonical path, got {value!r}",
                pointer,
                "UNSAFE_PATH",
            )


def _collection_outputs(entries: list[tuple[str, str]], pointer: str) -> dict[str, str]:
    by_folded: dict[str, tuple[str, str]] = {}
    for path, owner in entries:
        folded = path.casefold()
        if folded in by_folded:
            _fail(
                f"Collection output has duplicate/case-aliased owners: {path!r}",
                pointer,
                "PATH_COLLISION",
            )
        by_folded[folded] = (path, owner)
    for folded in by_folded:
        if any(
            parent.as_posix() in by_folded for parent in PurePosixPath(folded).parents
        ):
            _fail(
                "Collection output file/directory identities overlap",
                pointer,
                "PATH_COLLISION",
            )
    return {path: owner for path, owner in by_folded.values()}


def _collection_plan(document: dict[str, Any]) -> None:
    recipe = document["recipe"]
    _semantic("recipe", recipe)
    steps = {step["id"]: step for step in recipe["steps"]}
    if set(recipe["contexts"]) != {step["context_id"] for step in steps.values()}:
        _fail(
            "Every selected recipe context needs at least one declared step",
            "/recipe/contexts",
            "UNRESOLVED_REFERENCE",
        )
    output_entries = []
    for index, step in enumerate(recipe["steps"]):
        prefix = f"/recipe/steps/{index}"
        _collection_path(step["cwd"], prefix + "/cwd", allow_dot=True)
        if any("\x00" in argument for argument in step["argv"]):
            _fail("Command arguments cannot contain NUL", prefix + "/argv")
        for key, value in step.get("environment", {}).items():
            if (
                not isinstance(key, str)
                or not key
                or "=" in key
                or "\x00" in key
                or "\x00" in value
            ):
                _fail("Invalid explicit environment entry", prefix + "/environment")
            if re.search(r"token|pass(?:word|wd)|secret|api[_-]?key", key, re.I):
                _fail(
                    "Sensitive environment names cannot be retained in a collection plan",
                    prefix + "/environment",
                    "SENSITIVE_ENVIRONMENT",
                )
        for name in ["inputs", "outputs"]:
            for position, path in enumerate(step[name]):
                _collection_path(path, f"{prefix}/{name}/{position}")
                if name == "outputs":
                    if any(
                        part.casefold() == ".git" for part in PurePosixPath(path).parts
                    ):
                        _fail(
                            "Collection output cannot overwrite Git metadata",
                            prefix + "/outputs",
                            "UNSAFE_PATH",
                        )
                    output_entries.append((path, step["id"]))
    outputs = _collection_outputs(output_entries, "/recipe/steps/outputs")
    folded_outputs = {path.casefold(): (path, owner) for path, owner in outputs.items()}
    ancestors_by_step = {}
    for index, step in enumerate(recipe["steps"]):
        ancestors = set()
        pending = list(step["depends_on"])
        while pending:
            dependency = pending.pop()
            if dependency not in ancestors:
                ancestors.add(dependency)
                pending.extend(steps[dependency]["depends_on"])
        ancestors_by_step[step["id"]] = ancestors
        for path in step["inputs"]:
            generated = folded_outputs.get(path.casefold())
            if generated is not None and (
                generated[0] != path or generated[1] not in ancestors
            ):
                _fail(
                    "Generated input must use its canonical path and an ancestor producer",
                    f"/recipe/steps/{index}/inputs",
                    "UNRESOLVED_REFERENCE",
                )
            if (
                generated is not None
                and steps[generated[1]]["context_id"] != step["context_id"]
            ):
                _fail(
                    "Generated artifact cannot be relabeled as a different build context",
                    f"/recipe/steps/{index}/inputs",
                    "SUBJECT_MISMATCH",
                )
        cwd = step["cwd"].casefold()
        if any(
            cwd == output or cwd.startswith(output + "/") for output in folded_outputs
        ):
            _fail(
                "A working directory cannot also be an output file",
                f"/recipe/steps/{index}/cwd",
                "PATH_COLLISION",
            )
    _unique(document["bindings"], "id", "/bindings")
    bound_kinds = set()
    for index, binding in enumerate(document["bindings"]):
        prefix = f"/bindings/{index}"
        step_id = binding["step_id"]
        if step_id not in steps:
            _fail(
                "Binding refers to an undeclared step",
                prefix + "/step_id",
                "UNRESOLVED_REFERENCE",
            )
        pair = (step_id, binding["kind"])
        if pair in bound_kinds:
            _fail("Step/kind binding is duplicated", prefix, "DUPLICATE_ID")
        bound_kinds.add(pair)
        for name in ["scope_files", "exercised_inputs"]:
            for position, path in enumerate(binding[name]):
                _collection_path(path, f"{prefix}/{name}/{position}")
        for name in ["report_path", "execution_log_path"]:
            if binding[name] is not None:
                _collection_path(binding[name], prefix + "/" + name)
        step = steps[step_id]
        declared = step["outputs"] if binding["kind"] == "build" else step["inputs"]
        if not set(binding["exercised_inputs"]) <= set(declared):
            _fail(
                "Binding artifacts are outside the step's declared inputs/outputs",
                prefix + "/exercised_inputs",
                "UNRESOLVED_REFERENCE",
            )
        if binding["kind"] == "tests":
            for name in ["report_path", "execution_log_path"]:
                if binding[name] not in step["outputs"]:
                    _fail(
                        "Test report and actual execution log must be declared step outputs",
                        prefix + "/" + name,
                        "UNRESOLVED_REFERENCE",
                    )
            if binding["report_path"] == binding["execution_log_path"]:
                _fail(
                    "JUnit report and actual execution log require distinct file identities",
                    prefix + "/execution_log_path",
                    "PATH_COLLISION",
                )
            proof_ids = [
                binding["inventory_step_id"],
                binding["producer_version_step_id"],
            ]
            if len(set(proof_ids)) != 2:
                _fail(
                    "Test inventory and producer-version steps must be distinct",
                    prefix,
                    "DUPLICATE_ID",
                )
            for proof_id in proof_ids:
                if proof_id not in steps or proof_id not in ancestors_by_step[step_id]:
                    _fail(
                        "Test proof step must be a declared ancestor",
                        prefix,
                        "UNRESOLVED_REFERENCE",
                    )
                if steps[proof_id]["context_id"] != step["context_id"]:
                    _fail(
                        "Test proof step must use the test's context",
                        prefix,
                        "SUBJECT_MISMATCH",
                    )
            if not set(binding["exercised_inputs"]) <= set(
                steps[binding["inventory_step_id"]]["inputs"]
            ):
                _fail(
                    "Test inventory must bind every selected exercised artifact",
                    prefix + "/inventory_step_id",
                    "UNRESOLVED_REFERENCE",
                )


def _collection_bundle(
    plans: list[dict[str, Any]],
    manifest: dict[str, Any],
    standalone_recipes: list[dict[str, Any]],
) -> None:
    _unique(plans, "id", "/collection_plan")
    _unique(
        [plan["recipe"] for plan in plans] + standalone_recipes,
        "id",
        "/collection_plan/recipe",
    )
    _unique(
        [binding for plan in plans for binding in plan["bindings"]],
        "id",
        "/collection_plan/bindings",
    )
    projection = (
        plans[0]
        if len(plans) == 1
        else {"collection_plans": sorted(plans, key=lambda entry: entry["id"])}
    )
    if manifest["config_digest"] != _digest(projection):
        _fail(
            "Manifest config digest differs from the effective collection plan(s)",
            "/run_manifest/config_digest",
            "IDENTITY_MISMATCH",
        )
    outputs = _collection_outputs(
        [
            (path, plan["id"] + ":" + step["id"])
            for plan in plans
            for step in plan["recipe"]["steps"]
            for path in step["outputs"]
        ],
        "/collection_plan/recipe/steps/outputs",
    )
    source_paths = {entry["path"] for entry in manifest["source"]["files"]}
    folded_sources = {path.casefold() for path in source_paths}
    context_ids = {context["id"] for context in manifest["contexts"]}
    for output in outputs:
        folded = output.casefold()
        if any(
            folded == source
            or folded.startswith(source + "/")
            or source.startswith(folded + "/")
            for source in folded_sources
        ):
            _fail(
                "Collection output overlaps the selected source inventory",
                "/collection_plan/recipe/steps/outputs",
                "PATH_COLLISION",
            )
    for index, plan in enumerate(plans):
        prefix = f"/collection_plan/{index}"
        recipe = plan["recipe"]
        if not set(recipe["contexts"]) <= context_ids:
            _fail(
                "Collection plan refers to undeclared manifest contexts",
                prefix + "/recipe/contexts",
                "UNRESOLVED_REFERENCE",
            )
        local_outputs = {path for step in recipe["steps"] for path in step["outputs"]}
        for step in recipe["steps"]:
            if not set(step["inputs"]) <= source_paths | local_outputs:
                _fail(
                    "Collection input is neither selected source nor an in-plan generated artifact",
                    prefix + "/recipe/steps/inputs",
                    "UNRESOLVED_REFERENCE",
                )
            cwd = step["cwd"].casefold()
            if any(
                cwd == path.casefold() or cwd.startswith(path.casefold() + "/")
                for path in outputs
            ):
                _fail(
                    "Collection output file overlaps another plan's working directory",
                    prefix + "/recipe/steps/cwd",
                    "PATH_COLLISION",
                )
        for binding in plan["bindings"]:
            if not set(binding["scope_files"]) <= source_paths:
                _fail(
                    "Collection evidence scope is outside selected source inventory",
                    prefix + "/bindings/scope_files",
                    "SUBJECT_MISMATCH",
                )


def _unique(
    records: list[dict[str, Any]], key: str, path: str
) -> dict[str, dict[str, Any]]:
    result = {}
    for index, record in enumerate(records):
        value = record[key]
        if value in result:
            _fail(f"Duplicate {key}: {value}", f"{path}/{index}/{key}", "DUPLICATE_ID")
        result[value] = record
    return result


def _graph(records: list[dict[str, Any]], path: str) -> None:
    by_id = _unique(records, "id", path)
    degree = {}
    reverse: dict[str, list[str]] = {key: [] for key in by_id}
    for key, record in by_id.items():
        deps = record.get("depends_on", [])
        for dependency in deps:
            if dependency not in by_id:
                _fail(
                    f"Unresolved dependency {dependency!r}",
                    path,
                    "UNRESOLVED_REFERENCE",
                )
            reverse[dependency].append(key)
        degree[key] = len(deps)
    ready = deque(key for key, value in degree.items() if value == 0)
    processed = 0
    while ready:
        key = ready.popleft()
        processed += 1
        for dependent in reverse[key]:
            degree[dependent] -= 1
            if degree[dependent] == 0:
                ready.append(dependent)
    if processed != len(by_id):
        _fail("Dependency cycle is not allowed", path, "DEPENDENCY_CYCLE")


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})",
        value,
    ):
        return False
    return (
        datetime.fromisoformat(
            value.replace("Z", "+00:00").replace("z", "+00:00")
        ).tzinfo
        is not None
    )


def _digest(value: Any) -> str:
    try:
        content = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail(f"Identity projection is not finite JSON: {exc}")
    return hashlib.sha256(content).hexdigest()


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))


def _times(
    document: Mapping[str, Any], start: str, finish: str, path: str = ""
) -> None:
    first = _datetime(document[start])
    last = _datetime(document[finish])
    if last < first:
        _fail(f"{finish} precedes {start}", path)


def _source(document: dict[str, Any], prefix: str = "") -> None:
    files = _unique(document["files"], "path", prefix + "/files")
    case_keys = set()
    for index, path in enumerate(files):
        _safe_path(path, f"{prefix}/files/{index}/path")
        folded = path.casefold()
        if not document.get("path_case_sensitive", True) and folded in case_keys:
            _fail(
                "Case-folded source path collision", prefix + "/files", "PATH_COLLISION"
            )
        case_keys.add(folded)
    projection = {
        "kind": document["kind"],
        "files": sorted(document["files"], key=lambda entry: entry["path"]),
        "inventory_complete": document["inventory_complete"],
    }
    if document["digest"] != _digest(projection):
        _fail(
            "Source digest disagrees with selected inventory",
            prefix + "/digest",
            "IDENTITY_MISMATCH",
        )


def _context(document: dict[str, Any], prefix: str = "") -> None:
    _unique(document["dependencies"], "id", prefix + "/dependencies")
    for index, dependency in enumerate(document["dependencies"]):
        available = dependency["availability"] == "available"
        if available != (dependency["sha256"] is not None):
            _fail(
                "Dependency availability and digest disagree",
                f"{prefix}/dependencies/{index}",
            )
    projection = {
        key: value
        for key, value in document.items()
        if key not in {"version", "id", "digest", "limitations"}
    }
    if document["digest"] != _digest(projection):
        _fail(
            "Context digest disagrees with compile settings",
            prefix + "/digest",
            "IDENTITY_MISMATCH",
        )


def _artifact(document: dict[str, Any], prefix: str = "") -> None:
    _safe_path(document["path"], prefix + "/path")
    reserved = {
        "run_manifest.json",
        "latest.json",
        "latest_attempt.json",
        "heads.json",
        "store-format.json",
        ".migration-v3",
        ".publication.lock",
        ".coordination.lock",
        ".recovery",
    }
    if any(
        part.casefold() in reserved for part in PurePosixPath(document["path"]).parts
    ):
        _fail("Reserved publication metadata cannot be an artifact", prefix + "/path")


def _policy(document: dict[str, Any]) -> None:
    _graph(document["controls"], "/controls")
    fields = {
        "finding_limit": {"rule_ids", "max_findings"},
        "minimum_analysis_coverage": {"minimum"},
        "test_outcomes": {"evidence_ids"},
        "required_contexts": {"contexts"},
        "metric_threshold": {"metric", "operator", "threshold"},
        "minimum_coverage": {"minimum", "evidence_ids"},
        "reviewed_evidence": {"evidence_ids"},
        "sanitizer_outcome": {"fact_ids", "sanitizer"},
    }
    if document.get("evaluator_profile") in {"1.1.0", "1.2.0"}:
        fields["minimum_coverage"] = {
            "minimum",
            "fact_ids",
            "measurement_kind",
            "method",
        }
    if document.get("evaluator_profile") == "1.2.0":
        from .policy_extensions import METRIC_PARAMETERS, REVIEW_PARAMETERS

        fields["metric_threshold"] = METRIC_PARAMETERS
        fields["reviewed_evidence"] = REVIEW_PARAMETERS
    for index, control in enumerate(document["controls"]):
        parameters = control["parameters"]
        expected = fields[control["kind"]]
        allowed = expected | (
            {"contexts"}
            if control["kind"]
            in _EVALUATORS
            | {"minimum_coverage", "sanitizer_outcome"}
            | (
                {"metric_threshold", "reviewed_evidence"}
                if document.get("evaluator_profile") == "1.2.0"
                else set()
            )
            else set()
        )
        if not expected <= set(parameters) or not set(parameters) <= allowed:
            _fail(
                f"{control['kind']} requires {sorted(expected)} with only optional contexts",
                f"/controls/{index}/parameters",
            )
        for name in ["evidence_ids", "contexts", "rule_ids", "fact_ids"]:
            if name in parameters and not parameters[name]:
                _fail(
                    f"{name} must not be empty for this evaluator",
                    f"/controls/{index}/parameters/{name}",
                )
        if document.get("evaluator_profile") == "1.2.0":
            from .policy_extensions import validate_profile_12_control

            validate_profile_12_control(control, f"/controls/{index}")
    for name in ["include", "exclude"]:
        for index, value in enumerate(document["scope"][name]):
            _safe_path(value, f"/scope/{name}/{index}", allow_dot=True)


def _glob_expression(pattern: str) -> re.Pattern[str]:
    _safe_path(pattern, "/scope", allow_dot=True)
    pieces = pattern.split("/")
    output = ""
    for index, piece in enumerate(pieces):
        if "**" in piece and piece != "**":
            _fail("Double-star glob must occupy a complete path component", "/scope")
        if piece == "**":
            output += "(?:[^/]+/)*" if index < len(pieces) - 1 else ".*"
        else:
            output += "".join(
                "[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char)
                for char in piece
            )
            if index < len(pieces) - 1:
                output += "/"
    return re.compile(r"\A" + output + r"\Z", re.DOTALL)


def validate_evaluation_policy(
    policy: dict[str, Any], *, profile_version: str | None = None
) -> None:
    """Validate the bounded S5 evaluator profile without evaluating predicates."""
    if not isinstance(policy, dict):
        _fail("Evaluation policy must be a JSON object", "/policy")
    selected = policy.get("evaluator_profile", "1.0.0")
    if not isinstance(selected, str):
        _fail("Evaluator profile must be a version string", "/evaluator_profile")
    if selected not in {"1.0.0", "1.1.0", "1.2.0"} or (
        profile_version is not None and profile_version != selected
    ):
        raise UnsupportedVersion(
            f"Unsupported or mismatched evaluator profile {profile_version or selected!r}"
        )
    validate("policy", policy)
    if not policy["contexts"]:
        _fail("Evaluation requires explicit nonempty job contexts", "/contexts")
    for index, control in enumerate(policy["controls"]):
        supported = _EVALUATORS | (
            {"minimum_coverage", "sanitizer_outcome"}
            if selected in {"1.1.0", "1.2.0"}
            else set()
        )
        if selected == "1.2.0":
            supported |= {"metric_threshold", "reviewed_evidence"}
        if control["kind"] not in supported:
            raise UnsupportedVersion(
                f"Evaluator profile {selected} does not support {control['kind']!r}",
                path=f"/controls/{index}/kind",
            )
        if not set(control["parameters"].get("contexts", [])) <= set(
            policy["contexts"]
        ):
            _fail(
                "Control contexts are outside the selected policy job contexts",
                f"/controls/{index}/parameters/contexts",
            )
        if control["kind"] == "minimum_coverage" and selected in {"1.1.0", "1.2.0"}:
            methods = {
                "line": {"lcov-da-v1", "cobertura-lines-v1"},
                "branch": {"lcov-brda-v1", "cobertura-condition-counts-v1"},
                "function": {"lcov-fnda-v1"},
            }
            if (
                control["parameters"]["method"]
                not in methods[control["parameters"]["measurement_kind"]]
            ):
                raise UnsupportedVersion(
                    "Unsupported coverage measurement method/kind",
                    path=f"/controls/{index}/parameters/method",
                )
    for patterns in policy["scope"].values():
        for pattern in patterns:
            _glob_expression(pattern)


def policy_scope_paths(policy: dict[str, Any], files: Iterable[str]) -> list[str]:
    """Return sorted selected POSIX identities with shared include/exclude globs."""
    validate("policy", policy)
    includes = [_glob_expression(pattern) for pattern in policy["scope"]["include"]]
    excludes = [_glob_expression(pattern) for pattern in policy["scope"]["exclude"]]
    selected = set()
    for path in files:
        _safe_path(path, "/source/files")
        if any(pattern.fullmatch(path) for pattern in includes) and not any(
            pattern.fullmatch(path) for pattern in excludes
        ):
            selected.add(path)
    return sorted(selected)


def policy_gate(
    policy: dict[str, Any],
    controls: Iterable[dict[str, Any]],
    *,
    source_scope_empty: bool,
    excepted_control_ids: Iterable[str] = (),
) -> str:
    """Compute exact raw gate arithmetic; approval validity is checked separately."""
    records = list(controls)
    declared = {control["id"]: control for control in policy["controls"]}
    excepted = set(excepted_control_ids)
    totals = dict.fromkeys(["passed", "failed", "unknown"], Fraction(0))
    for record in records:
        if record["status"] in totals:
            totals[record["status"]] += Fraction(str(record["weight"]))
        permitted = (
            record["id"] in excepted
            and declared.get(record["id"], {}).get("allow_deviation", False)
            and record["status"] == "failed"
            and not record.get("incomplete", False)
        )
        if record["required"] and record["status"] == "failed" and not permitted:
            return "failed"
    passed, failed, unknown = (totals[key] for key in ["passed", "failed", "unknown"])
    applicable = passed + failed + unknown
    if not applicable:
        return "insufficient_evidence"
    minimum = Fraction(str(policy["gates"]["minimum_readiness"]))
    if 100 * (passed + unknown) / applicable < minimum:
        return "failed"
    if (
        source_scope_empty
        or any(
            record["required"]
            and (record["status"] == "unknown" or record.get("incomplete", False))
            for record in records
        )
        or 100 * (passed + failed) / applicable
        < Fraction(str(policy["gates"]["minimum_completeness"]))
        or 100 * passed / applicable < minimum
    ):
        return "insufficient_evidence"
    return "passed"


def validate_deviation_request(document: dict[str, Any]) -> None:
    """Check approval structure/order; caller active flags never authorize use."""
    schema = deepcopy(load_schema("assessment")["properties"]["deviations"]["items"])
    schema["required"].remove("active")
    checker = jsonschema.FormatChecker()
    checker.checks("date-time", raises=(ValueError, TypeError))(_valid_datetime)
    error = next(
        jsonschema.Draft7Validator(
            schema, registry=_registry(), format_checker=checker
        ).iter_errors(document),
        None,
    )
    if error:
        _fail(error.message, _pointer(error.absolute_path))
    for field in ["reason", "owner", "reviewer"]:
        if not document[field].strip():
            _fail("Approval reason/owner/reviewer must not be blank", "/" + field)
    _times(document, "approved_at", "expires_at")


def _assessment(document: dict[str, Any]) -> None:
    evaluator = document.get("evaluator")
    if evaluator is not None and (
        evaluator["name"] != "cppulse.policy"
        or evaluator["version"] not in {"1.0.0", "1.1.0", "1.2.0"}
    ):
        raise UnsupportedVersion(
            "Unsupported assessment evaluator identity/version", path="/evaluator"
        )
    controls = _unique(document["controls"], "id", "/controls")
    _unique(document["deviations"], "id", "/deviations")
    totals = {status: Fraction(0) for status in ["passed", "failed", "unknown"]}
    active = set()
    for index, deviation in enumerate(document["deviations"]):
        control = controls.get(deviation["control_id"])
        if control is None:
            _fail(
                "Deviation refers to an unknown control",
                f"/deviations/{index}/control_id",
                "UNRESOLVED_REFERENCE",
            )
        _times(deviation, "approved_at", "expires_at", f"/deviations/{index}")
        if (
            deviation["active"]
            and deviation["source_digest"] != document["source_digest"]
        ):
            _fail(
                "Deviation source does not match assessment",
                f"/deviations/{index}/source_digest",
            )
        if deviation["active"]:
            if any(
                not deviation[field].strip()
                for field in ["reason", "owner", "reviewer"]
            ):
                _fail(
                    "Active deviation reason/owner/reviewer must not be blank",
                    f"/deviations/{index}",
                )
            if control["status"] != "failed":
                _fail(
                    "Active deviation must preserve a failed control",
                    f"/deviations/{index}",
                )
            if _datetime(deviation["approved_at"]) > _datetime(
                document["generated_at"]
            ):
                _fail(
                    "Active deviation approval is in the future",
                    f"/deviations/{index}/approved_at",
                )
            if _datetime(deviation["expires_at"]) <= _datetime(
                document["generated_at"]
            ):
                _fail(
                    "Active deviation is expired at assessment time",
                    f"/deviations/{index}/expires_at",
                )
            if deviation.get("gate") != "required_controls":
                raise UnsupportedVersion(
                    "Active deviation requires gate='required_controls'",
                    path=f"/deviations/{index}/gate",
                )
            if (
                not control.get("context_ids")
                or set(deviation["context_ids"]) != set(control["context_ids"])
                or control.get("incomplete", True)
                or deviation.get("inactive_reason")
            ):
                _fail(
                    "Active deviation requires a complete failed control and exact nonempty context scope",
                    f"/deviations/{index}",
                )
            active.add(control["id"])
    for control in controls.values():
        if control.get("incomplete", False) and control["status"] in {
            "passed",
            "not_applicable",
        }:
            _fail("Passed/not-applicable control cannot be incomplete", "/controls")
        if control["status"] == "unknown" and control.get("incomplete") is False:
            _fail("Unknown control must remain incomplete", "/controls")
        if control["status"] in totals:
            totals[control["status"]] += Fraction(str(control["weight"]))
        if document["gate"] == "passed" and control["required"]:
            if control["status"] == "unknown" or (
                control["status"] == "failed" and control["id"] not in active
            ):
                _fail("Passed gate masks a required failed/unknown control", "/gate")
    if not all(
        abs(Fraction(str(document["weights"][key])) - value)
        <= max(Fraction("1e-8"), abs(value) * Fraction("1e-9"))
        for key, value in totals.items()
    ):
        _fail("Assessment weights disagree with control outcomes", "/weights")
    passed, failed, unknown = (totals[key] for key in ["passed", "failed", "unknown"])
    all_weight = passed + failed + unknown
    observed = passed + failed
    expected = {
        "readiness": 100 * passed / all_weight if all_weight else None,
        "evidence_completeness": 100 * observed / all_weight if all_weight else None,
        "observed_satisfaction": 100 * passed / observed if observed else None,
        "maximum_possible_readiness": (
            100 * (passed + unknown) / all_weight if all_weight else None
        ),
    }
    for key, value in expected.items():
        actual = document["scores"][key]
        if (value is None) != (actual is None) or (
            value is not None and not math.isclose(float(value), actual, abs_tol=1e-7)
        ):
            _fail("Assessment score disagrees with unrounded weights", f"/scores/{key}")
    if not all_weight and document["gate"] != "insufficient_evidence":
        _fail("No applicable controls require an insufficient-evidence gate", "/gate")


def _execution_facts(document: dict[str, Any]) -> None:
    _semantic("execution_receipt", document["receipt"])
    if document["material_status"] == "available" and any(
        row["freshness"] == "unchanged" for row in document["output_facts"]
    ):
        _fail(
            "Available material cannot claim an unchanged cached output",
            "/material_status",
            "SUBJECT_MISMATCH",
        )
    for key in [
        "input_facts",
        "input_after_facts",
        "output_facts",
        "preexisting_output_facts",
    ]:
        _unique(document[key], "path", "/" + key)
        for index, fact in enumerate(document[key]):
            _collection_path(fact["path"], f"/{key}/{index}/path")
    for key in ["input_artifacts", "output_artifacts"]:
        _unique(document["binding"][key], "path", "/binding/" + key)
        for index, link in enumerate(document["binding"][key]):
            _collection_path(link["path"], f"/binding/{key}/{index}/path")
    if document["executable_fact"] is not None:
        path = document["executable_fact"]["path"]
        pure = PurePosixPath(path)
        if (
            not pure.is_absolute()
            or "\x00" in path
            or ".." in pure.parts
            or pure.as_posix() != path
        ):
            _fail(
                "Executable fact requires a canonical absolute POSIX host path",
                "/executable_fact/path",
                "UNSAFE_PATH",
            )
    total = document["stdout_bytes"] + document["stderr_bytes"]
    if document["captured_bytes"] > total or document["logs_truncated"] != (
        document["captured_bytes"] < total
    ):
        _fail("Log capture counts/truncation disagree", "/captured_bytes")
    if document["binding"]["status"] == "verified":
        before = {row["path"]: row for row in document["input_facts"]}
        after = {row["path"]: row for row in document["input_after_facts"]}
        if before != after or document["executable_fact"] is None:
            _fail(
                "Verified binding requires unchanged observed inputs and an executable fact",
                "/binding",
            )
        for fact_key, link_key in [
            ("input_facts", "input_artifacts"),
            ("output_facts", "output_artifacts"),
        ]:
            if {row["path"] for row in document[fact_key]} != {
                row["path"] for row in document["binding"][link_key]
            }:
                _fail(
                    "Verified binding must retain every observed material file",
                    "/binding/" + link_key,
                )
        if any(
            identifier is None
            for identifier in document["binding"]["log_artifacts"].values()
        ):
            _fail(
                "Verified binding must retain both observed log streams",
                "/binding/log_artifacts",
            )
    if (
        document["binding"]["status"] == "invalid"
        and not document["binding"]["limitations"]
    ):
        _fail("Invalid binding requires an explicit limitation", "/binding/limitations")


def _analysis_inventory(document: dict[str, Any]) -> None:
    _unique(document["items"], "file", "/items")
    for path in document["requested_files"]:
        _collection_path(path, "/requested_files")
    if set(document["requested_files"]) != {row["file"] for row in document["items"]}:
        _fail("Every requested file needs exactly one explicit inventory row", "/items")
    enabled = set(document["enabled_rules"])
    for index, row in enumerate(document["items"]):
        pointer = f"/items/{index}"
        _collection_path(row["file"], pointer + "/file")
        coherence = row.get("buffer_coherence")
        if coherence == "verified" and row["status"] not in {"analyzed", "partial"}:
            _fail(
                "Unobserved AST cannot claim verified TU buffers",
                pointer + "/buffer_coherence",
            )
        if not set(row["executed_rules"]) <= enabled:
            _fail(
                "Rule completion includes an actually disabled rule",
                pointer + "/executed_rules",
            )
        if row["status"] == "analyzed":
            if row["error_count"] != 0:
                _fail(
                    "Analyzed inventory row cannot hide parse errors",
                    pointer + "/error_count",
                )
        elif row["executed_rules"]:
            _fail(
                "Incomplete parse cannot claim completed rule consideration",
                pointer + "/executed_rules",
            )
        if row["status"] == "partial" and row["error_count"] == 0:
            _fail(
                "Partial native parse needs its observed error count",
                pointer + "/error_count",
            )
        attempted = row["status"] in {"analyzed", "partial", "failed"}
        if not attempted:
            if (
                row["parse_context_id"] is not None
                or row["context_source"] != "none"
                or row["context_match"] != "unverified"
                or row["error_count"]
                or row["finding_count"]
            ):
                _fail(
                    "Unattempted file cannot claim parse context/errors/findings",
                    pointer,
                )
        if row["status"] in {"analyzed", "partial"} and (
            row["parse_context_id"] is None or row["context_source"] == "none"
        ):
            _fail(
                "Observed AST requires an explicit parse context",
                pointer + "/parse_context_id",
            )
        if row["context_match"] == "matched" and (
            row["parse_context_id"] is None or row["context_source"] != "database"
        ):
            _fail(
                "Inferred/fallback/absent context cannot claim a matched requested job",
                pointer + "/context_match",
            )
        if row["status"] not in {"analyzed", "partial"} and row["finding_count"]:
            _fail(
                "No observed AST exists for these findings", pointer + "/finding_count"
            )


def _resource_manifest(document: dict[str, Any]) -> None:
    _collection_path(document["root"], "/root")
    by_path = _unique(document["files"], "path", "/files")
    for path in by_path:
        _collection_path(path, "/files")
        if not path.startswith(document["root"] + "/"):
            _fail(
                "Resource file lies outside its selected finite root",
                "/files",
                "UNSAFE_PATH",
            )
    if document["root"] + "/include/stddef.h" not in by_path:
        _fail(
            "Selected Clang resource inventory lacks include/stddef.h sentinel",
            "/files",
        )


def _analysis_bundle(
    flat: list[tuple[str, dict[str, Any]]],
    manifest: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> None:
    from .work_unit_analysis import validate_work_unit_analysis_bundle
    from .sdk_inputs import validate_sdk_bundle

    validate_sdk_bundle(flat, manifest)
    bounded_inventory_ids = validate_work_unit_analysis_bundle(flat, manifest, receipts)
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    sources = {row["path"]: row for row in manifest["source"]["files"]}
    contexts = {row["id"]: row for row in manifest["contexts"]}
    facts_by_receipt: dict[str, dict[str, Any]] = {}
    for kind, facts in flat:
        if kind != "execution_facts":
            continue
        receipt = facts["receipt"]
        identifier = receipt["id"]
        if identifier in facts_by_receipt:
            _fail(
                "Duplicate typed execution facts for receipt",
                "/execution_facts",
                "DUPLICATE_ID",
            )
        if receipts.get(identifier) != receipt:
            _fail(
                "Execution facts do not match the separately retained typed receipt",
                "/execution_facts/receipt",
                "SUBJECT_MISMATCH",
            )
        facts_by_receipt[identifier] = facts
        if (
            receipt["source_digest"] != manifest["source"]["digest"]
            or receipt["context_id"] not in contexts
        ):
            _fail(
                "Execution facts refer to another subject/context",
                "/execution_facts/receipt",
                "SUBJECT_MISMATCH",
            )
        for fact_key, map_key in [
            ("input_facts", "input_artifacts"),
            ("output_facts", "output_artifacts"),
        ]:
            known = {row["path"]: row for row in facts[fact_key]}
            for link in facts["binding"][map_key]:
                descriptor = artifacts.get(link["artifact_id"])
                observed = known.get(link["path"])
                if (
                    descriptor is None
                    or observed is None
                    or link["artifact_id"] not in receipt["artifact_ids"]
                ):
                    _fail(
                        "Execution material role does not resolve to its observed receipt/file",
                        "/execution_facts/binding",
                        "UNRESOLVED_REFERENCE",
                    )
                if any(
                    descriptor[key] != observed[key] for key in ["sha256", "size_bytes"]
                ):
                    _fail(
                        "Execution material descriptor differs from observed file bytes",
                        "/execution_facts/binding",
                        "IDENTITY_MISMATCH",
                    )
                source = (
                    sources.get(link["path"]) if fact_key == "input_facts" else None
                )
                if (
                    source is not None
                    and facts["binding"]["status"] == "verified"
                    and any(
                        observed[key] != source[key] for key in ["sha256", "size_bytes"]
                    )
                ):
                    _fail(
                        "Verified execution input differs from selected source",
                        "/execution_facts/input_facts",
                        "SUBJECT_MISMATCH",
                    )
        log_size = 0
        for stream, artifact_id in facts["binding"]["log_artifacts"].items():
            if artifact_id is None:
                continue
            descriptor = artifacts.get(artifact_id)
            if descriptor is None or artifact_id not in receipt["log_artifact_ids"]:
                _fail(
                    "Execution log role is not retained by its receipt",
                    "/execution_facts/binding/log_artifacts",
                    "UNRESOLVED_REFERENCE",
                )
            if descriptor["size_bytes"] > facts[stream + "_bytes"]:
                _fail(
                    "Retained log exceeds observed stream bytes",
                    "/execution_facts/binding/log_artifacts",
                )
            log_size += descriptor["size_bytes"]
        if (
            facts["binding"]["status"] == "verified"
            and log_size != facts["captured_bytes"]
        ):
            _fail(
                "Verified stored log bytes differ from observed captured bytes",
                "/execution_facts/captured_bytes",
            )
    for identifier, facts in facts_by_receipt.items():
        if facts["binding"]["status"] != "verified":
            continue
        ancestors = set()
        pending = list(receipts[identifier]["depends_on"])
        while pending:
            ancestor = pending.pop()
            if ancestor not in ancestors:
                ancestors.add(ancestor)
                pending.extend(receipts[ancestor]["depends_on"])
        for observed in facts["input_facts"]:
            if observed["path"] in sources:
                continue
            produced = [
                (facts_by_receipt[ancestor], row)
                for ancestor in ancestors
                if ancestor in facts_by_receipt
                for row in facts_by_receipt[ancestor]["output_facts"]
                if row["path"] == observed["path"]
            ]
            if len(produced) != 1 or any(
                produced[0][1][key] != observed[key] for key in ["sha256", "size_bytes"]
            ):
                _fail(
                    "Verified generated input lacks an unambiguous typed ancestor byte identity",
                    "/execution_facts/input_facts",
                    "SUBJECT_MISMATCH",
                )
            parent, output = produced[0]
            if (
                parent["binding"]["status"] != "verified"
                or parent["material_status"] != "available"
                or parent["receipt"]["status"] != "passed"
                or parent["receipt"]["context_id"] != facts["receipt"]["context_id"]
                or output["freshness"] not in {"created", "modified"}
                or _datetime(parent["receipt"]["finished_at"])
                > _datetime(facts["receipt"]["started_at"])
            ):
                _fail(
                    "Verified generated input requires a usable fresh same-context producer",
                    "/execution_facts/input_facts",
                    "SUBJECT_MISMATCH",
                )
    inventories = [doc for kind, doc in flat if kind == "analysis_inventory"]
    by_inventory = _unique(inventories, "id", "/analysis_inventory")
    observations: dict[str, list[dict[str, Any]]] = {}
    for kind, doc in flat:
        if kind == "observations" and "analysis_inventory_id" in doc:
            identifier = doc["analysis_inventory_id"]
            if identifier not in by_inventory:
                _fail(
                    "Observation refers to a missing analysis inventory",
                    "/observations/analysis_inventory_id",
                    "UNRESOLVED_REFERENCE",
                )
            observations.setdefault(identifier, []).extend(doc["items"])
    registry_docs = [doc for kind, doc in flat if kind == "rule_registry"]
    resource_docs = [doc for kind, doc in flat if kind == "resource_manifest"]
    for resource in resource_docs:
        for file in resource["files"]:
            if sources.get(file["path"]) != file:
                _fail(
                    "Selected resource bytes differ from source inventory",
                    "/resource_manifest/files",
                    "SUBJECT_MISMATCH",
                )
    for inventory in inventories:
        if inventory["id"] in bounded_inventory_ids:
            continue
        facts = facts_by_receipt.get(inventory["receipt_id"])
        if facts is None:
            _fail(
                "Analysis inventory requires typed execution facts, not legacy debug JSON",
                "/analysis_inventory/receipt_id",
                "UNRESOLVED_REFERENCE",
            )
        receipt = facts["receipt"]
        if (
            inventory["source_digest"] != manifest["source"]["digest"]
            or inventory["job_context_id"] != receipt["context_id"]
        ):
            _fail(
                "Analysis job subject/context differs from its observed receipt",
                "/analysis_inventory",
                "SUBJECT_MISMATCH",
            )
        if not set(inventory["requested_files"]) <= sources.keys():
            _fail(
                "Requested analysis file is outside selected source",
                "/analysis_inventory/requested_files",
                "UNRESOLVED_REFERENCE",
            )
        input_ids = {row["artifact_id"] for row in facts["binding"]["input_artifacts"]}
        output_ids = {
            row["artifact_id"] for row in facts["binding"]["output_artifacts"]
        }
        if inventory["report_artifact_id"] not in output_ids:
            _fail(
                "Native report is not an observed output artifact",
                "/analysis_inventory/report_artifact_id",
                "UNRESOLVED_REFERENCE",
            )
        role_ids = []
        for role in [
            "registry_artifact_id",
            "config_artifact_id",
            "compilation_database_artifact_id",
            "resource_manifest_artifact_id",
        ]:
            artifact_id = inventory.get(role)
            if artifact_id is not None:
                if artifact_id not in input_ids:
                    _fail(
                        "Native input role is not an observed input artifact",
                        "/analysis_inventory/" + role,
                        "UNRESOLVED_REFERENCE",
                    )
                role_ids.append(artifact_id)
        if len(role_ids) != len(set(role_ids)):
            _fail(
                "Distinct analysis input roles cannot alias one artifact",
                "/analysis_inventory",
                "DUPLICATE_ID",
            )
        registry_artifact = artifacts[inventory["registry_artifact_id"]]
        if inventory["registry_sha256"] != registry_artifact["sha256"]:
            _fail(
                "Registry raw SHA differs from its retained input bytes",
                "/analysis_inventory/registry_sha256",
                "IDENTITY_MISMATCH",
            )
        typed_registry = [
            artifact
            for artifact in artifacts.values()
            if artifact.get("contract", {}).get("kind") == "rule_registry"
            and all(
                artifact[key] == registry_artifact[key]
                for key in ["sha256", "size_bytes"]
            )
        ]
        if (
            not typed_registry
            or not registry_docs
            or any(doc != registry_docs[0] for doc in registry_docs)
        ):
            _fail(
                "Analysis requires an unambiguous byte-identical typed registry copy",
                "/analysis_inventory/registry_artifact_id",
                "UNRESOLVED_REFERENCE",
            )
        rules = {row["id"]: row for row in registry_docs[0]["rules"]}
        if (
            not set(inventory["requested_rules"] + inventory["enabled_rules"])
            <= rules.keys()
        ):
            _fail(
                "Analysis rule selection refers to an unknown registry ID",
                "/analysis_inventory/requested_rules",
                "UNRESOLVED_REFERENCE",
            )
        resource_id = inventory.get("resource_manifest_artifact_id")
        if resource_id is not None:
            descriptor = artifacts[resource_id]
            typed = [
                artifact
                for artifact in artifacts.values()
                if artifact.get("contract", {}).get("kind") == "resource_manifest"
                and all(
                    artifact[key] == descriptor[key] for key in ["sha256", "size_bytes"]
                )
            ]
            if (
                not typed
                or not resource_docs
                or any(doc != resource_docs[0] for doc in resource_docs)
            ):
                _fail(
                    "Resource manifest needs a byte-identical typed finite inventory",
                    "/analysis_inventory/resource_manifest_artifact_id",
                    "UNRESOLVED_REFERENCE",
                )
            retained_inputs = {row["path"]: row for row in facts["input_facts"]}
            prefix = resource_docs[0]["root"] + "/"
            listed = {row["path"] for row in resource_docs[0]["files"]}
            if listed != {path for path in retained_inputs if path.startswith(prefix)}:
                _fail(
                    "Resource selected prefix and native input inventory differ",
                    "/resource_manifest/files",
                    "SUBJECT_MISMATCH",
                )
        rows = {row["file"]: row for row in inventory["items"]}
        for row in rows.values():
            parse_context = (
                contexts.get(row["parse_context_id"])
                if row["parse_context_id"] is not None
                else None
            )
            if row["parse_context_id"] is not None and parse_context is None:
                _fail(
                    "Inventory observed parse context is missing",
                    "/analysis_inventory/items/parse_context_id",
                    "UNRESOLVED_REFERENCE",
                )
            if parse_context is not None and (
                parse_context["provenance"] != "observed"
                or parse_context["compiler"]["name"] != "libclang"
            ):
                _fail(
                    "Inventory parse context must retain observed libclang arguments",
                    "/analysis_inventory/items/parse_context_id",
                    "SUBJECT_MISMATCH",
                )
            if row["context_match"] == "matched" and (
                manifest.get("input_verification", "unverified") != "verified"
                or facts["binding"]["status"] != "verified"
                or facts["material_status"] != "available"
                or receipt["status"] != "passed"
                or inventory["compilation_database_artifact_id"] is None
                or resource_id is None
            ):
                _fail(
                    "Matched analysis context requires verified successful execution/source binding",
                    "/analysis_inventory/items/context_match",
                    "SUBJECT_MISMATCH",
                )
            if row["context_match"] == "matched":
                before = {item["path"]: item for item in facts["input_facts"]}
                after = {item["path"]: item for item in facts["input_after_facts"]}
                frozen_paths = {
                    item["path"] for item in facts["binding"]["input_artifacts"]
                }
                if (
                    row["file"] not in before
                    or row["file"] not in after
                    or row["file"] not in frozen_paths
                ):
                    _fail(
                        "Matched requested source must be observed before/after and frozen as native input",
                        "/analysis_inventory/items/context_match",
                        "SUBJECT_MISMATCH",
                    )
        counts = dict.fromkeys(rows, 0)
        for observation in observations.get(inventory["id"], []):
            row = rows.get(observation["file"])
            rule = rules.get(observation["rule_id"])
            if (
                row is None
                or row["status"] not in {"analyzed", "partial"}
                or observation["context_id"] != row["parse_context_id"]
                or observation["producer"] != inventory["producer"]
                or rule is None
                or observation["rule_id"] not in inventory["enabled_rules"]
                or observation["rule_version"] != rule["version"]
            ):
                _fail(
                    "Observation differs from inventory file/parse context/producer/enabled registry rule",
                    "/observations/items",
                    "SUBJECT_MISMATCH",
                )
            counts[observation["file"]] += 1
        if any(row["finding_count"] != counts[path] for path, row in rows.items()):
            _fail(
                "Linked observation counts differ from explicit native per-file finding counts",
                "/analysis_inventory/items/finding_count",
                "SUBJECT_MISMATCH",
            )


def _semantic(kind: str, document: dict[str, Any]) -> None:
    if kind == "shared_history":
        from .history_contract import semantic

        semantic(document)
    elif kind == "used_sdk_inputs":
        from .sdk_inputs import validate_used_sdk_inputs

        validate_used_sdk_inputs(document)
    elif kind in {"analysis_scope", "work_unit_analysis_binding"}:
        from .work_unit_analysis import semantic

        semantic(kind, document)
    elif kind in {
        "finding_baseline",
        "finding_comparison",
        "finding_suppressions",
        "finding_baseline_request",
        "finding_check_request",
    }:
        from .finding_workflows import semantic

        semantic(kind, document)
    elif kind in {
        "collection_request",
        "workflow_result",
        "check_result",
        "assessment_lineage",
    }:
        from .public_workflows import semantic

        semantic(kind, document)
    elif kind == "snapshot_view":
        from .presentation import semantic

        semantic(document)
    elif kind in {
        "coverage_facts",
        "external_analysis_facts",
        "transfer_bundle",
        "distribution_subject",
        "consumer_matrix",
        "consumer_usage",
        "consumer_comparison",
        "sanitizer_facts",
    }:
        from .verification import semantic

        semantic(kind, document)
    elif kind == "execution_facts":
        _execution_facts(document)
    elif kind == "analysis_inventory":
        _analysis_inventory(document)
    elif kind == "resource_manifest":
        _resource_manifest(document)
    elif kind == "native_install":
        _safe_path(document["analyzer"], "/analyzer")
        _safe_path(document["resource_dir"], "/resource_dir", allow_dot=True)
        for index, path in enumerate(document["library_dirs"]):
            _safe_path(path, f"/library_dirs/{index}", allow_dot=True)
        if document["analyzer"] in {
            document["resource_dir"],
            *document["library_dirs"],
        }:
            _fail(
                "Analyzer file cannot also be a resource/library directory",
                "/analyzer",
                "INSTALL_PATH_COLLISION",
            )
        _unique(document["host_requirements"], "name", "/host_requirements")
    elif kind == "source":
        _source(document)
    elif kind == "context":
        _context(document)
    elif kind == "artifact":
        _artifact(document)
    elif kind == "run_manifest":
        _source(document["source"], "/source")
        _unique(document["contexts"], "id", "/contexts")
        for index, context in enumerate(document["contexts"]):
            _context(context, f"/contexts/{index}")
        _graph(document["stages"], "/stages")
        _unique(document["artifacts"], "id", "/artifacts")
        _unique(document["artifacts"], "path", "/artifacts")
        for index, artifact in enumerate(document["artifacts"]):
            _artifact(artifact, f"/artifacts/{index}")
        _times(document, "started_at", "finished_at")
        if document["status"] == "completed" and any(
            stage["status"] in {"error", "timed_out", "cancelled", "not_attempted"}
            for stage in document["stages"]
        ):
            _fail(
                "Completed collection contains operationally incomplete stages",
                "/status",
            )
    elif kind == "recipe":
        _graph(document["steps"], "/steps")
        for index, step in enumerate(document["steps"]):
            if step["context_id"] not in document["contexts"]:
                _fail(
                    "Step context is not declared",
                    f"/steps/{index}/context_id",
                    "UNRESOLVED_REFERENCE",
                )
            _safe_path(step["cwd"], f"/steps/{index}/cwd", allow_dot=True)
            for name in ["inputs", "outputs"]:
                for position, path in enumerate(step[name]):
                    _safe_path(path, f"/steps/{index}/{name}/{position}")
    elif kind == "collection_plan":
        _collection_plan(document)
    elif kind == "execution_receipt":
        _times(document, "started_at", "finished_at")
        if document["status"] == "passed" and (
            document["exit_code"] != 0 or document["signal"] is not None
        ):
            _fail("Passed execution requires zero exit and no signal", "/status")
        if document["status"] == "failed" and document["exit_code"] in {None, 0}:
            _fail("Failed execution requires a nonzero exit code", "/exit_code")
        if (
            document["status"]
            in {"error", "timed_out", "cancelled", "skipped", "not_attempted"}
            and not document["reason"]
        ):
            _fail("Unavailable execution requires a reason", "/reason")
        if "tests" in document:
            counts = document["tests"]
            if counts["total"] != sum(
                counts[key] for key in ["passed", "failed", "skipped", "errors"]
            ):
                _fail("Test total disagrees with outcome counts", "/tests")
    elif kind == "evidence":
        _unique(document["records"], "id", "/records")
        for index, record in enumerate(document["records"]):
            imported_fields = {"import_adapter", "test_counts", "test_cases"}
            if imported_fields & record.keys():
                if (
                    not imported_fields <= record.keys()
                    or record["kind"] != "tests"
                    or record["origin"] != "import"
                    or record["receipt_id"] is not None
                ):
                    _fail(
                        "Imported test counts require a complete attributed import without an execution receipt",
                        f"/records/{index}",
                    )
                counts, cases = record["test_counts"], record["test_cases"]
                if record["usability"] != "usable":
                    if counts is not None or cases:
                        _fail(
                            "Unavailable test import cannot supply clean/partial counts",
                            f"/records/{index}",
                        )
                elif counts is None:
                    _fail("Usable test import needs actual counts", f"/records/{index}")
                if counts is not None:
                    observed = {
                        "total": len(cases),
                        "passed": 0,
                        "failed": 0,
                        "skipped": 0,
                        "errors": 0,
                    }
                    _unique(cases, "identity", f"/records/{index}/test_cases")
                    for case in cases:
                        observed[
                            "errors" if case["status"] == "error" else case["status"]
                        ] += 1
                    if counts != observed or record["scope"]["tests"] != [
                        c["identity"] for c in cases
                    ]:
                        _fail(
                            "Imported counts/case identities disagree with retained occurrences",
                            f"/records/{index}/test_counts",
                        )
                    outcome = (
                        "error"
                        if counts["errors"]
                        else (
                            "failed"
                            if counts["failed"]
                            else "passed" if counts["passed"] else "skipped"
                        )
                    )
                    if record["status"] != outcome:
                        _fail(
                            "Imported test status disagrees with case counts",
                            f"/records/{index}/status",
                        )
            for position, path in enumerate(record["scope"]["files"]):
                _safe_path(path, f"/records/{index}/scope/files/{position}")
            if (
                "measurement" in record
                and record["measurement"]["covered"] > record["measurement"]["total"]
            ):
                _fail("Covered count exceeds total", f"/records/{index}/measurement")
            if record["usability"] == "usable" and not record["artifact_ids"]:
                _fail(
                    "Usable evidence needs retained artifacts",
                    f"/records/{index}/artifact_ids",
                )
            if record["origin"] == "execution" and record["receipt_id"] is None:
                _fail(
                    "Execution evidence needs a receipt reference",
                    f"/records/{index}/receipt_id",
                )
            if record["origin"] == "attestation" and not all(
                key in record for key in ["reviewer", "expires_at"]
            ):
                _fail("Attestation needs reviewer and expiry", f"/records/{index}")
            if "review_details" in record:
                from .policy_extensions import validate_review_details

                validate_review_details(record, f"/records/{index}")
    elif kind == "policy":
        _policy(document)
    elif kind == "assessment":
        _assessment(document)
    elif kind == "baseline":
        _unique(document["findings"], "fingerprint", "/findings")
    elif kind == "observations":
        _unique(document["items"], "id", "/items")
        for index, observation in enumerate(document["items"]):
            _safe_path(observation["file"], f"/items/{index}/file")
    elif kind == "analysis_metrics":
        _unique(document["items"], "id", "/items")
        for index, metric in enumerate(document["items"]):
            _safe_path(metric["file"], f"/items/{index}/file")
            if (metric["availability"] == "available") != (metric["value"] is not None):
                _fail("Metric availability and value disagree", f"/items/{index}/value")
        from .maintenance import validate_metrics

        validate_metrics(document)
    elif kind == "maintenance_health":
        from .maintenance import validate_health

        validate_health(document)
    elif kind == "rule_registry":
        _unique(document["rules"], "id", "/rules")
        for index, rule in enumerate(document["rules"]):
            try:
                jsonschema.Draft7Validator.check_schema(rule["configuration_schema"])
            except jsonschema.SchemaError as exc:
                _fail(
                    f"Invalid rule configuration schema: {exc.message}",
                    f"/rules/{index}/configuration_schema",
                )
    elif kind == "risk_scores":
        risks = _unique(document["file_risks"], "file", "/file_risks")
        _unique(document["hotspots"], "file", "/hotspots")
        for index, path in enumerate(risks):
            _safe_path(path, f"/file_risks/{index}/file")
        for index, hotspot in enumerate(document["hotspots"]):
            _safe_path(hotspot["file"], f"/hotspots/{index}/file")
            if hotspot["file"] not in risks:
                _fail(
                    "Hotspot is outside risk file scope",
                    f"/hotspots/{index}/file",
                    "UNRESOLVED_REFERENCE",
                )
            if hotspot["score"] <= 0:
                _fail("Zero-score files are not hotspots", f"/hotspots/{index}/score")
        health = document["health_score"]
        if health["availability"] != "scored" and (
            health["overall"] is not None
            or any(value is not None for value in health["by_category"].values())
        ):
            _fail("Unavailable full-scope health must use null scores", "/health_score")
        if health["availability"] == "scored" and (
            health["overall"] is None or health["denominator"] == 0
        ):
            _fail(
                "Scored health needs a value and a nonzero denominator", "/health_score"
            )
        meta = document["metadata"]
        active = meta["active_features"]
        if active is None:
            if meta["feature_count"] is not None:
                _fail(
                    "Unavailable active features need a null feature count",
                    "/metadata/feature_count",
                )
        elif meta["feature_count"] != len(active):
            _fail(
                "Feature count disagrees with active features",
                "/metadata/feature_count",
            )
        if (
            meta["evaluation_status"] == "not_evaluated"
            and meta["f1_score"] is not None
        ):
            _fail("Unevaluated model must not carry an F1 score", "/metadata/f1_score")
        if meta["evaluation_status"] == "cross_validated" and meta["f1_score"] is None:
            _fail("Cross-validated model needs its measured F1", "/metadata/f1_score")
        if meta["method"] == "heuristic" and (
            meta["score_kind"] != "heuristic_rank"
            or meta["evaluation_status"] != "not_evaluated"
        ):
            _fail("Heuristic method cannot claim evaluated model ranking", "/metadata")
        if meta["method"] == "xgboost" and meta["score_kind"] != "model_rank":
            _fail("XGBoost output must identify model ranking", "/metadata/score_kind")


def _risk_availability(document: dict[str, Any]) -> None:
    """Validate additive rank-scope facts without fabricating missing scores.

    Earlier supported documents may omit this unreleased extension. Once a
    producer supplies it, ranked and unranked identities must be disjoint and
    the published scope counts must account for every supplied file exactly.
    """
    unranked = document.get("unranked_files", [])
    unavailable = _unique(unranked, "file", "/unranked_files")
    ranked = _unique(document["file_risks"], "file", "/file_risks")
    for index, path in enumerate(unavailable):
        _safe_path(path, f"/unranked_files/{index}/file")
        if path in ranked:
            _fail(
                "A file cannot be both ranked and explicitly unranked",
                f"/unranked_files/{index}/file",
            )
    scope = document["metadata"].get("ranking_scope")
    if scope is not None:
        expected = {
            "declared_files": len(ranked) + len(unavailable),
            "ranked_files": len(ranked),
            "unranked_files": len(unavailable),
        }
        for key, count in expected.items():
            if scope[key] != count:
                _fail(
                    "Ranking scope count disagrees with supplied file inventories",
                    f"/metadata/ranking_scope/{key}",
                )


def validate(
    kind: str, document: dict[str, Any], *, version: str | None = None
) -> None:
    """Validate structural and semantic invariants without executing producers.

    Args:
        kind: Supported contract kind.
        document: Parsed JSON object.
        version: Optional explicit contract channel/version. Prototype-v1
            input must opt in using version='prototype_v1'.

    Raises:
        ContractError: If a schema or semantic invariant is violated.
        UnsupportedVersion: If the requested version is unsupported.
    """
    kind = _ALIASES.get(kind, kind)
    if not isinstance(document, dict):
        _fail("Contract document must be an object")
    try:
        json.dumps(document, allow_nan=False)
    except (TypeError, ValueError) as exc:
        _fail(f"Document must contain finite JSON values: {exc}")
    default_version = "1.0.0" if kind == "native_install" else _VERSION
    selected = version or document.get("version", default_version)
    schema = load_schema(kind, selected)
    checker = jsonschema.FormatChecker()
    checker.checks("date-time", raises=(ValueError, TypeError))(_valid_datetime)
    validator = jsonschema.Draft7Validator(
        schema, registry=_registry(), format_checker=checker
    )
    error = next(validator.iter_errors(document), None)
    if error:
        _fail(error.message, _pointer(error.absolute_path))
    if selected == _VERSION or (kind == "native_install" and selected == "1.0.0"):
        _semantic(kind, document)
    if kind == "risk_scores" and selected in {_VERSION, "prototype_v1"}:
        _risk_availability(document)
        if "component_hotspots" in document:
            from .component_hotspots import validate_component_hotspots

            validate_component_hotspots(document)
    if kind == "findings" and selected == "prototype_v1":
        from .maintenance import validate_native_metrics

        validate_native_metrics(document)


def validate_bundle(
    documents: Mapping[str, dict[str, Any] | list[dict[str, Any]]],
) -> None:
    """Validate a closed bundle and its cross-document identities/references.

    A bundle requires one run_manifest; other kind values may be a document
    or a list of documents. Artifact byte integrity belongs to the run store.
    """
    if "run_manifest" not in documents or not isinstance(
        documents["run_manifest"], dict
    ):
        _fail("Bundle needs one run_manifest", "/run_manifest")
    flat: list[tuple[str, dict[str, Any]]] = []
    for kind, value in documents.items():
        for document in value if isinstance(value, list) else [value]:
            validate(kind, document)
            flat.append((_ALIASES.get(kind, kind), document))
    manifest = documents["run_manifest"]
    plans = [document for kind, document in flat if kind == "collection_plan"]
    if "collection_plan" in documents:
        if not plans:
            _fail("Collection plan list must not be empty", "/collection_plan")
        _collection_bundle(
            plans,
            manifest,
            [document for kind, document in flat if kind == "recipe"],
        )
    source_digest = manifest["source"]["digest"]
    contexts = {entry["id"] for entry in manifest["contexts"]}
    source_files = {entry["path"] for entry in manifest["source"]["files"]}
    artifacts = {entry["id"] for entry in manifest["artifacts"]}
    receipt_records = [entry for kind, entry in flat if kind == "execution_receipt"]
    receipt_map = _unique(receipt_records, "id", "/execution_receipt")
    _graph(receipt_records, "/execution_receipt")
    _analysis_bundle(flat, manifest, receipt_map)
    receipts = set(receipt_map)
    evidence_map = _unique(
        [
            record
            for kind, entry in flat
            if kind == "evidence"
            for record in entry["records"]
        ],
        "id",
        "/evidence/records",
    )
    evidence_ids = set(evidence_map)
    from .verification import validate_verification_bundle

    validate_verification_bundle(flat, manifest, receipt_map, evidence_map)
    for plan in plans:
        steps = {step["id"]: step for step in plan["recipe"]["steps"]}
        for binding in plan["bindings"]:
            record = evidence_map.get(binding["id"])
            if record is not None and (
                record["kind"] != binding["kind"]
                or record["context_id"] != steps[binding["step_id"]]["context_id"]
                or record["origin"] != "execution"
                or set(record["scope"]["files"]) != set(binding["scope_files"])
            ):
                _fail(
                    "Observed evidence disagrees with its selected collection binding",
                    "/collection_plan/bindings",
                    "SUBJECT_MISMATCH",
                )
    _unique(
        [
            record
            for kind, entry in flat
            if kind == "observations"
            for record in entry["items"]
        ],
        "id",
        "/observations/items",
    )
    for kind, document in flat:
        if "source_digest" in document and document["source_digest"] != source_digest:
            _fail(
                f"{kind} source differs from run manifest",
                f"/{kind}/source_digest",
                "SUBJECT_MISMATCH",
            )
        if "run_id" in document and document["run_id"] != manifest["run_id"]:
            _fail(
                f"{kind} run differs from manifest",
                f"/{kind}/run_id",
                "SUBJECT_MISMATCH",
            )
        if kind == "source" and document != manifest["source"]:
            _fail(
                "Source inventory differs from run manifest",
                "/source",
                "SUBJECT_MISMATCH",
            )
        if kind == "artifact":
            known_artifact = next(
                (
                    item
                    for item in manifest["artifacts"]
                    if item["id"] == document["id"]
                ),
                None,
            )
            if known_artifact != document:
                _fail(
                    "Artifact differs from run manifest",
                    "/artifact",
                    "SUBJECT_MISMATCH",
                )
        if kind == "baseline" and any(
            value not in contexts for value in document["context_ids"]
        ):
            _fail(
                "Baseline refers to undeclared context",
                "/baseline/context_ids",
                "UNRESOLVED_REFERENCE",
            )
        if kind == "context":
            known = next(
                (item for item in manifest["contexts"] if item["id"] == document["id"]),
                None,
            )
            if known != document:
                _fail(
                    "Context differs from manifest inventory",
                    "/context",
                    "SUBJECT_MISMATCH",
                )
        if kind in {"observations", "analysis_metrics", "risk_scores"}:
            entries = (
                document["file_risks"] + document.get("unranked_files", [])
                if kind == "risk_scores"
                else document["items"]
            )
            if any(entry["file"] not in source_files for entry in entries):
                _fail(
                    "Observation or metric file is outside selected source inventory",
                    f"/{kind}",
                    "UNRESOLVED_REFERENCE",
                )
        records = (
            document["records"]
            if kind == "evidence"
            else (
                document["items"]
                if kind in {"observations", "analysis_metrics"}
                else [document]
            )
        )
        for record in records:
            if "context_id" in record and record["context_id"] not in contexts:
                _fail(
                    "Reference to undeclared context",
                    f"/{kind}/context_id",
                    "UNRESOLVED_REFERENCE",
                )
            for key in ["artifact_ids", "log_artifact_ids"]:
                if any(value not in artifacts for value in record.get(key, [])):
                    _fail(
                        "Reference to missing artifact",
                        f"/{kind}/{key}",
                        "UNRESOLVED_REFERENCE",
                    )
            if (
                record.get("receipt_id") is not None
                and record["receipt_id"] not in receipts
            ):
                _fail(
                    "Reference to missing execution receipt",
                    f"/{kind}/receipt_id",
                    "UNRESOLVED_REFERENCE",
                )
            if kind == "evidence":
                if any(value not in source_files for value in record["scope"]["files"]):
                    _fail(
                        "Evidence scope is outside selected source inventory",
                        "/evidence/records/scope/files",
                        "SUBJECT_MISMATCH",
                    )
                if (
                    record["origin"] == "execution"
                    and record.get("receipt_id") in receipt_map
                ):
                    receipt = receipt_map[record["receipt_id"]]
                    if record["context_id"] != receipt["context_id"]:
                        _fail(
                            "Evidence context differs from its execution receipt",
                            "/evidence/records/context_id",
                            "SUBJECT_MISMATCH",
                        )
                    produced = set(receipt["artifact_ids"]) | set(
                        receipt["log_artifact_ids"]
                    )
                    if not set(record["artifact_ids"]) <= produced:
                        _fail(
                            "Evidence artifacts are not linked by the execution receipt",
                            "/evidence/records/artifact_ids",
                            "SUBJECT_MISMATCH",
                        )
                    if record["usability"] == "usable" and record["status"] == "passed":
                        if receipt["status"] != "passed":
                            _fail(
                                "Passed usable evidence contradicts failed/incomplete execution",
                                "/evidence/records/status",
                            )
                        if record["kind"] == "tests":
                            counts = receipt.get("tests")
                            if (
                                counts is None
                                or counts["total"] == 0
                                or counts["passed"] == 0
                                or counts["failed"]
                                or counts["errors"]
                            ):
                                _fail(
                                    "Passed usable test evidence lacks successful executed tests",
                                    "/evidence/records/status",
                                )
            if any(
                value not in evidence_ids for value in record.get("evidence_ids", [])
            ):
                _fail(
                    "Reference to missing evidence",
                    f"/{kind}/evidence_ids",
                    "UNRESOLVED_REFERENCE",
                )
        if kind == "recipe" and any(
            value not in contexts for value in document["contexts"]
        ):
            _fail(
                "Recipe refers to undeclared contexts",
                "/recipe/contexts",
                "UNRESOLVED_REFERENCE",
            )
        if kind == "execution_receipt" and any(
            value not in receipts for value in document["depends_on"]
        ):
            _fail(
                "Receipt dependency is missing",
                "/execution_receipt/depends_on",
                "UNRESOLVED_REFERENCE",
            )
        if kind == "assessment":
            for control in document["controls"]:
                if any(value not in evidence_ids for value in control["evidence_ids"]):
                    _fail(
                        "Assessment refers to missing evidence",
                        "/assessment/controls",
                        "UNRESOLVED_REFERENCE",
                    )
            policy = documents.get("policy")
            if (
                not isinstance(policy, dict)
                or document["policy"]["id"] != policy["id"]
                or document["policy"]["policy_version"] != policy["policy_version"]
                or document["policy"]["sha256"] != _digest(policy)
            ):
                _fail(
                    "Assessment policy does not match supplied policy",
                    "/assessment/policy",
                    "SUBJECT_MISMATCH",
                )
            if "evaluator" in document:
                validate_evaluation_policy(policy)
                if document["evaluator"]["version"] != policy.get(
                    "evaluator_profile", "1.0.0"
                ):
                    _fail(
                        "Assessment evaluator differs from declared policy profile",
                        "/assessment/evaluator",
                        "SUBJECT_MISMATCH",
                    )
                from .verification import validate_verification_assessment

                validate_verification_assessment(
                    flat, manifest, policy, document, evidence_map
                )
                from .policy_extensions import validate_profile_12_assessment

                validate_profile_12_assessment(flat, manifest, policy, document)
                generated = _datetime(document["generated_at"])
                if generated < _datetime(manifest["finished_at"]):
                    _fail(
                        "Assessment predates its completed run facts",
                        "/assessment/generated_at",
                        "SUBJECT_MISMATCH",
                    )
                used_receipts = {
                    evidence_map[identifier]["receipt_id"]
                    for result in document["controls"]
                    for identifier in result["evidence_ids"]
                    if evidence_map[identifier]["receipt_id"] is not None
                }
                used_receipts.update(
                    row["receipt_id"]
                    for family, row in flat
                    if family == "analysis_inventory"
                    and row["job_context_id"] in policy["contexts"]
                )
                if any(
                    generated < _datetime(receipt_map[identifier]["finished_at"])
                    for identifier in used_receipts
                ):
                    _fail(
                        "Assessment predates used execution facts",
                        "/assessment/generated_at",
                        "SUBJECT_MISMATCH",
                    )
            expected_controls = {item["id"]: item for item in policy["controls"]}
            results = {item["id"]: item for item in document["controls"]}
            if set(expected_controls) != set(results):
                _fail(
                    "Assessment does not cover exactly the supplied policy controls",
                    "/assessment/controls",
                    "SUBJECT_MISMATCH",
                )
            selected_scope = set(policy_scope_paths(policy, source_files))
            for control_id, expected in expected_controls.items():
                actual = results[control_id]
                if any(
                    actual[key] != expected[key]
                    for key in ["title", "weight", "required"]
                ):
                    _fail(
                        "Assessment control metadata differs from policy",
                        "/assessment/controls",
                        "SUBJECT_MISMATCH",
                    )
                selected_contexts = set(
                    expected["parameters"].get("contexts", policy["contexts"])
                )
                if (
                    "context_ids" in actual
                    and set(actual["context_ids"]) != selected_contexts
                ):
                    _fail(
                        "Assessment context scope differs from selected policy jobs",
                        "/assessment/controls/context_ids",
                        "SUBJECT_MISMATCH",
                    )
                applies = manifest["source"]["kind"] in expected.get(
                    "applicable_to", ["application", "library", "header-only"]
                )
                if (actual["status"] == "not_applicable") == applies:
                    _fail(
                        "Control applicability contradicts selected subject kind",
                        "/assessment/controls",
                        "SUBJECT_MISMATCH",
                    )
                required_evidence = set(expected["parameters"].get("evidence_ids", []))
                if (
                    "evaluator" in document
                    and actual["status"] == "passed"
                    and any(
                        identifier in evidence_map
                        and evidence_map[identifier].get("expires_at") is not None
                        and _datetime(evidence_map[identifier]["expires_at"])
                        <= _datetime(document["generated_at"])
                        for identifier in required_evidence
                    )
                ):
                    _fail(
                        "Expired required evidence cannot support a current positive control",
                        "/assessment/controls",
                        "SUBJECT_MISMATCH",
                    )
                blocked = any(
                    results[dependency]["status"] in {"failed", "unknown"}
                    or results[dependency].get("incomplete", False)
                    for dependency in expected["depends_on"]
                )
                missing = (
                    not selected_contexts <= contexts
                    or not required_evidence <= evidence_ids
                    or any(
                        results[dependency]["status"] == "unknown"
                        or results[dependency].get("incomplete", False)
                        for dependency in expected["depends_on"]
                    )
                )
                if applies and (
                    (missing and actual.get("incomplete") is False)
                    or ((missing or blocked) and actual["status"] == "passed")
                ):
                    _fail(
                        "Missing expected context/evidence/prerequisite must remain incomplete",
                        "/assessment/controls",
                        "SUBJECT_MISMATCH",
                    )
                if (
                    "evaluator" in document
                    and manifest.get("input_verification", "unverified") != "verified"
                    and actual["status"] not in {"unknown", "not_applicable"}
                ):
                    _fail(
                        "Current assessment cannot trust unverified source binding",
                        "/assessment/controls",
                        "SUBJECT_MISMATCH",
                    )
                if actual["status"] == "passed" and not required_evidence <= set(
                    actual["evidence_ids"]
                ):
                    _fail(
                        "Passed control omits its policy-required evidence references",
                        "/assessment/controls",
                        "UNRESOLVED_REFERENCE",
                    )
                if actual["status"] == "passed" and any(
                    evidence_map[key]["usability"] != "usable"
                    or evidence_map[key]["status"] != "passed"
                    for key in required_evidence
                ):
                    _fail(
                        "Passed evidence control contradicts its required evidence",
                        "/assessment/controls",
                        "SUBJECT_MISMATCH",
                    )
                if actual["status"] == "passed" and expected["kind"] in {
                    "test_outcomes",
                    "required_contexts",
                }:
                    candidate_records = [
                        record
                        for identifier, record in evidence_map.items()
                        if (
                            expected["kind"] == "required_contexts"
                            or identifier in required_evidence
                        )
                        and record["origin"] == "execution"
                        and record["usability"] == "usable"
                        and (
                            "evaluator" not in document
                            or record.get("expires_at") is None
                            or _datetime(record["expires_at"])
                            > _datetime(document["generated_at"])
                        )
                        and record["status"]
                        in (
                            {"passed"}
                            if expected["kind"] == "test_outcomes"
                            else {"passed", "failed"}
                        )
                        and record["kind"]
                        in (
                            {"tests"}
                            if expected["kind"] == "test_outcomes"
                            else {"build", "tests"}
                        )
                    ]
                    for selected_context in selected_contexts:
                        covered = {
                            path
                            for record in candidate_records
                            if record["context_id"] == selected_context
                            for path in record["scope"]["files"]
                        }
                        observed = any(
                            record["context_id"] == selected_context
                            for record in candidate_records
                        )
                        if expected["kind"] == "required_contexts":
                            analysis_covered = {
                                item["file"]
                                for family, inventory in flat
                                if family == "analysis_inventory"
                                and inventory["job_context_id"] == selected_context
                                for item in inventory["items"]
                                if item["context_match"] == "matched"
                                and (
                                    "native_input_binding" not in document
                                    or item.get("buffer_coherence") == "verified"
                                )
                                and item["parse_context_id"] is not None
                                and item["status"] in {"analyzed", "partial", "failed"}
                            }
                            covered.update(analysis_covered)
                            observed |= bool(analysis_covered)
                        if not selected_scope <= covered or not observed:
                            _fail(
                                "Passed context/test control lacks observed selected-scope coverage",
                                "/assessment/controls",
                                "SUBJECT_MISMATCH",
                            )
                if (
                    "evaluator" in document
                    and actual["status"] == "passed"
                    and expected["kind"]
                    in {"finding_limit", "minimum_analysis_coverage"}
                ):
                    inventories = [
                        row for family, row in flat if family == "analysis_inventory"
                    ]
                    covered_cells = 0
                    for selected_context in selected_contexts:
                        current = [
                            row
                            for row in inventories
                            if row["job_context_id"] == selected_context
                        ]
                        if not current:
                            _fail(
                                "Positive analysis control requires typed job inventory",
                                "/assessment/controls",
                                "UNRESOLVED_REFERENCE",
                            )
                        if expected["kind"] == "finding_limit":
                            needed_rules = set(expected["parameters"]["rule_ids"])
                            for path in selected_scope:
                                if not any(
                                    needed_rules <= set(inventory["requested_rules"])
                                    and any(
                                        item["file"] == path
                                        and item["status"] == "analyzed"
                                        and item["context_match"] == "matched"
                                        and (
                                            "native_input_binding" not in document
                                            or item.get("buffer_coherence")
                                            == "verified"
                                        )
                                        and needed_rules <= set(item["executed_rules"])
                                        for item in inventory["items"]
                                    )
                                    for inventory in current
                                ):
                                    _fail(
                                        "Within-limit finding result lacks complete file/rule consideration",
                                        "/assessment/controls",
                                        "SUBJECT_MISMATCH",
                                    )
                        else:
                            for path in selected_scope:
                                known = []
                                for inventory in current:
                                    execution = next(
                                        value
                                        for family, value in flat
                                        if family == "execution_facts"
                                        and value["receipt"]["id"]
                                        == inventory["receipt_id"]
                                    )
                                    if (
                                        execution["binding"]["status"] != "verified"
                                        or execution["material_status"] != "available"
                                        or execution["receipt"]["status"] != "passed"
                                        or inventory.get(
                                            "resource_manifest_artifact_id"
                                        )
                                        is None
                                        or inventory["compilation_database_artifact_id"]
                                        is None
                                        or path
                                        not in {
                                            link["path"]
                                            for link in execution["binding"][
                                                "input_artifacts"
                                            ]
                                        }
                                    ):
                                        continue
                                    known.extend(
                                        item
                                        for item in inventory["items"]
                                        if item["file"] == path
                                        and (
                                            "native_input_binding" not in document
                                            or item.get("buffer_coherence")
                                            == "verified"
                                        )
                                        and (
                                            item["status"] in {"skipped", "excluded"}
                                            or item["context_match"]
                                            in {"matched", "mismatched"}
                                        )
                                    )
                                if not known:
                                    _fail(
                                        "Positive parse coverage lacks known source/job cell facts",
                                        "/assessment/controls",
                                        "SUBJECT_MISMATCH",
                                    )
                                covered_cells += any(
                                    item["status"] == "analyzed"
                                    and item["error_count"] == 0
                                    and item["context_match"] == "matched"
                                    for item in known
                                )
                    if expected["kind"] == "minimum_analysis_coverage":
                        cells = len(selected_scope) * len(selected_contexts)
                        if not cells or Fraction(100 * covered_cells, cells) < Fraction(
                            str(expected["parameters"]["minimum"])
                        ):
                            _fail(
                                "Positive analysis parse coverage is below the selected threshold",
                                "/assessment/controls",
                                "SUBJECT_MISMATCH",
                            )
                if (
                    "evaluator" in document
                    and actual["status"] == "failed"
                    and expected["kind"] == "test_outcomes"
                ):
                    credible = [
                        evidence_map[identifier]
                        for identifier in required_evidence
                        if identifier in evidence_map
                        and evidence_map[identifier]["origin"] == "execution"
                        and evidence_map[identifier]["usability"] == "usable"
                        and evidence_map[identifier]["kind"] == "tests"
                        and evidence_map[identifier]["context_id"] in selected_contexts
                        and bool(
                            set(evidence_map[identifier]["scope"]["files"])
                            & selected_scope
                        )
                        and (
                            evidence_map[identifier].get("expires_at") is None
                            or _datetime(evidence_map[identifier]["expires_at"])
                            > _datetime(document["generated_at"])
                        )
                        and receipt_map.get(evidence_map[identifier]["receipt_id"], {})
                        .get("tests", {})
                        .get("failed", 0)
                        > 0
                    ]
                    if not credible:
                        _fail(
                            "Definitive test failure needs a current observed failed testcase",
                            "/assessment/controls",
                            "SUBJECT_MISMATCH",
                        )
            for deviation in document["deviations"]:
                if deviation["active"] and not expected_controls[
                    deviation["control_id"]
                ].get("allow_deviation", False):
                    _fail(
                        "Policy does not permit this required-controls deviation",
                        "/assessment/deviations",
                        "SUBJECT_MISMATCH",
                    )
                if (
                    deviation["active"]
                    and not set(deviation["context_ids"]) <= contexts
                ):
                    _fail(
                        "Active deviation context is outside selected manifest",
                        "/assessment/deviations/context_ids",
                        "SUBJECT_MISMATCH",
                    )
            expected_gate = policy_gate(
                policy,
                document["controls"],
                source_scope_empty=not selected_scope,
                excepted_control_ids=[
                    item["control_id"]
                    for item in document["deviations"]
                    if item["active"]
                ],
            )
            if document["gate"] != expected_gate:
                _fail(
                    "Assessment gate contradicts exact raw weights, scope or policy thresholds",
                    "/assessment/gate",
                    "SUBJECT_MISMATCH",
                )
    from .finding_workflows import validate_finding_bundle

    validate_finding_bundle(flat, manifest, receipt_map, evidence_map)
    from .public_workflows import validate_lineage_bundle

    validate_lineage_bundle(flat, manifest)
    from .maintenance import validate_maintenance_bundle

    validate_maintenance_bundle(flat, manifest)
