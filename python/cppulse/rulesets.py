"""Resolve finite local data packs without executing providers or project code."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from importlib import resources
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any

import jsonschema

from cppulse.errors import ContractError
from cppulse.identities import digest_json
from cppulse.tooling import load_rule_registry

MAX_PACK_BYTES = 65536
MAX_PACKS = 32
MAX_DEPTH = 8


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate ruleset key: {key}")
        result[key] = value
    return result


def validate_native(settings: dict[str, Any]) -> None:
    """Validate native options against the existing registry capabilities."""
    from cppulse.config import _validate_project_settings

    schema = json.loads(resources.files("cppulse").joinpath(
        "data/project_config.schema.json").read_bytes())
    _validate_project_settings(settings, schema)
    rules = {r["id"]: r for r in load_rule_registry()["rules"]}
    unknown = set(settings.get("rules", {})) - rules.keys()
    if unknown:
        raise ValueError("Unknown rule IDs: " + ", ".join(sorted(unknown)))
    for identifier, options in settings.get("rules", {}).items():
        try:
            _validate_project_settings(options, rules[identifier]["configuration_schema"])
        except jsonschema.ValidationError as error:
            raise ValueError(f"Unsupported configuration for {identifier}: {error.message}") from error


def merge_native(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge rule options individually; explicit scope arrays replace parents."""
    result = deepcopy(base)
    for key, value in incoming.items():
        if key == "rules":
            target = result.setdefault("rules", {})
            for identifier, options in value.items():
                target.setdefault(identifier, {}).update(deepcopy(options))
        else:
            result[key] = deepcopy(value)
    return result


def _leaves(value: dict[str, Any], prefix: str = "") -> list[str]:
    leaves: list[str] = []
    for key, item in value.items():
        name = prefix + key
        leaves.extend(_leaves(item, name + ".") if isinstance(item, dict) else [name])
    return leaves


@dataclass(frozen=True)
class ResolvedRuleset:
    """Detector settings and inspectable identities, separate from scoring/policy."""

    native: dict[str, Any]
    providers: dict[str, Any]
    identity: dict[str, Any]


def resolve_ruleset(path: Path) -> ResolvedRuleset:
    """Resolve JSON packs in parent order, then the child, with finite local I/O.

    No module import, command, provider invocation or network request is taken
    from pack data. Paths in parents are relative to the declaring pack.
    """
    from cppulse import __version__
    from cppulse.config import _validate_project_settings

    schema = json.loads(resources.files("cppulse").joinpath(
        "data/ruleset.schema.json").read_bytes())
    registry = load_rule_registry()
    rule_ids = {r["id"] for r in registry["rules"]}
    native: dict[str, Any] = {}
    providers: dict[str, Any] = {}
    origins: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    preset_layers: list[tuple[str, str]] = []
    stack: list[Path] = []
    seen: set[Path] = set()
    names: dict[tuple[str, str], str] = {}

    def visit(selected: Path) -> None:
        nonlocal native
        if "://" in str(selected) or str(selected).startswith("http:"):
            raise ValueError("Ruleset inherits accepts local file paths only")
        selected = selected.resolve(strict=True)
        if selected in stack:
            raise ValueError("Ruleset inheritance cycle: " + " -> ".join(map(str, [*stack, selected])))
        if selected in seen:
            return
        if len(stack) >= MAX_DEPTH or len(seen) + len(stack) >= MAX_PACKS:
            raise ValueError("Ruleset inheritance exceeds pack/depth limits")
        descriptor = os.open(selected, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Ruleset pack must be an ordinary data file")
            raw = stream.read(MAX_PACK_BYTES + 1)
        if len(raw) > MAX_PACK_BYTES:
            raise ValueError("Ruleset pack exceeds 64 KiB")
        document = json.loads(raw, object_pairs_hook=_unique)
        _validate_project_settings(document, schema)
        json.dumps(document, allow_nan=False)
        digest = hashlib.sha256(raw).hexdigest()
        named = (document["name"], document["version"])
        if named in names and names[named] != digest:
            raise ValueError(f"Conflicting content for ruleset {named[0]}@{named[1]}")
        names[named] = digest
        stack.append(selected)
        for parent in document.get("inherits", []):
            if "://" in parent or "\0" in parent:
                raise ValueError("Ruleset inherits accepts local file paths only")
            visit(selected.parent / parent)
        stack.pop()
        supplied = deepcopy(document.get("native", {}))
        preset = document.get("preset")
        if preset:
            preset_layers.append((str(selected), preset))
        if "select" in supplied:
            chosen = set(supplied.pop("select"))
            if chosen - rule_ids:
                raise ValueError("Unknown selected native rule IDs: " + ", ".join(sorted(chosen - rule_ids)))
            native = merge_native(native, {"rules": {
                r: {"enabled": r in chosen} for r in sorted(rule_ids)}})
            for r in rule_ids:
                origins[f"native.rules.{r}.enabled"] = str(selected) + "#native.select"
        validate_native(supplied)
        native = merge_native(native, supplied)
        for key in _leaves(supplied, "native."):
            origins[key] = str(selected)
        for provider, value in document.get("providers", {}).items():
            for name in value["scope_files"]:
                p = PurePosixPath(name)
                if p.is_absolute() or p.as_posix() != name or ".." in p.parts or "\\" in name or ":" in name or "\0" in name:
                    raise ValueError("Provider scope_files requires literal relative POSIX files")
            # A provider declaration is an atomic versioned scope and check set.
            providers[provider] = deepcopy(value)
            for key in _leaves(value, "providers." + provider + "."):
                origins[key] = str(selected)
        records.append({"path": str(selected), "name": named[0],
                        "version": named[1], "format_version": document["format_version"],
                        "sha256": digest, "raw_json": raw.decode("utf-8")})
        seen.add(selected)

    try:
        visit(path)
    except (OSError, ValueError, TypeError, jsonschema.ValidationError, RecursionError) as error:
        raise ContractError(f"Invalid ruleset {path}: {error}") from error
    preset_native: dict[str, Any] = {}
    preset_origins: dict[str, str] = {}
    for filename, preset in preset_layers:
        preset_native = {"rules": {r: {"enabled": preset == "all-native"} for r in sorted(rule_ids)}}
        for identifier in rule_ids:
            preset_origins[f"native.rules.{identifier}.enabled"] = filename + "#preset=" + preset
    native = merge_native(preset_native, native)
    origins = {**preset_origins, **origins}
    identity = {
        "format_version": "1.0.0", "tool_version": __version__,
        "registry_format_version": registry["version"],
        "registry_sha256": digest_json(registry),
        "native_rule_versions": {r["id"]: r.get("rule_version", r.get("version")) for r in registry["rules"]},
        "native_defaults": {r["id"]: {k: v["default"] for k, v in r["configuration_schema"]["properties"].items()
                                        if "default" in v} for r in registry["rules"]},
        "packs": records, "origins": origins,
        "native": deepcopy(native), "providers": deepcopy(providers),
    }
    for identifier, options in identity["native_defaults"].items():
        for option in options:
            origins.setdefault(f"native.rules.{identifier}.{option}", "registry-default")
    identity["digest"] = digest_json(identity)
    return ResolvedRuleset(native, providers, identity)


def clang_tidy_arguments(provider: dict[str, Any]) -> list[str]:
    """Render the explicitly selected check/options data for an explicit recipe.

    This function never invokes a tool. Source files, compiler context and
    completion receipts still have to be declared by the collector request.
    """
    checks = provider["checks"]
    selected = sorted(k for k, v in checks.items() if v["enabled"])
    options: dict[str, str] = {}
    for identifier, check in sorted(checks.items()):
        for name, value in check.get("options", {}).items():
            options[identifier + "." + name] = (
                ";".join(value) if isinstance(value, list)
                else "true" if value is True else "false"
            )
    return ["--checks=" + ",".join(["-*", *selected]),
            "--config=" + json.dumps({"CheckOptions": options}, sort_keys=True, separators=(",", ":"))]


def bind_collection_ruleset(request: dict[str, Any], workspace: Path) -> dict[str, Any]:
    """Check an explicit recipe against its pack without rewriting any command.

    Every pack must be an explicitly selected source input. The collector's
    ordinary source verification, receipts and import semantics remain intact.
    """
    if "resolved_ruleset" in request:
        raise ContractError("resolved_ruleset is collector-generated; declare ruleset instead")
    if "ruleset" not in request:
        return request
    root = workspace.resolve(strict=True)
    path = (root / request["ruleset"]).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ContractError("Collection ruleset must be inside the declared workspace")
    resolved = resolve_ruleset(path)
    selected = set(request["source"]["files"])
    for row in resolved.identity["packs"]:
        source = Path(row["path"])
        if not source.is_relative_to(root) or source.relative_to(root).as_posix() not in selected:
            raise ContractError("Every inherited pack must be an explicitly declared source input")
    provider = resolved.providers.get("clang-tidy")
    if provider is None:
        raise ContractError("Collection ruleset needs an explicit supported provider declaration")
    imports = [n for n in request["normalizers"] if n["kind"] == "external_import"
               and n["adapter"] == "clang-tidy-text"]
    if not imports:
        raise ContractError("Collection ruleset requires a clang-tidy-text external_import role")
    steps = {s["id"]: s for s in request["plan"]["recipe"]["steps"]}
    expected_args = clang_tidy_arguments(provider)
    for item in imports:
        if item["producer"] != {"name": "clang-tidy", "version": provider["version"]}:
            raise ContractError("Declared producer/version does not match the ruleset")
        if set(item["scope_files"]) != set(provider["scope_files"]):
            raise ContractError("Declared provider scope does not match the ruleset")
        argv = steps[item["report"]["step_id"]]["argv"]
        front = argv[:argv.index("--")] if "--" in argv else argv
        if any(a.startswith("@") for a in front):
            raise ContractError("Provider response files are outside this explicit finite settings contract")
        for flag in ("--checks", "--config"):
            supplied = [a for a in front if a == flag or a.startswith(flag + "=")]
            expected = next(a for a in expected_args if a.startswith(flag + "="))
            if supplied != [expected]:
                raise ContractError("Explicit recipe must contain exactly the resolved " + flag + " argument")
        if any(a.startswith(("--config-file", "-config", "-checks", "--load", "-load", "--checks-file")) for a in front):
            raise ContractError("Recipe has a competing provider configuration/plugin argument")
    result = deepcopy(request)
    result["resolved_ruleset"] = resolved.identity
    result["resolved_ruleset"]["provider_arguments"] = {"clang-tidy": expected_args}
    # This is retained declarative configuration, not a producer authentication.
    result["resolved_ruleset"]["digest"] = digest_json({
        k: v for k, v in result["resolved_ruleset"].items() if k != "digest"})
    return result
