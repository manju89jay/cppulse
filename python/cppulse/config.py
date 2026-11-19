"""Resolve compatible project settings without executing project code."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field
from importlib import resources
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from cppulse.errors import ContractError

CONFIG_NAMES = (".cppulserc.yml", ".cppulserc.yaml", ".cppulserc.json")
DEFAULT_MAX_FILE_BYTES = 16 * 1024 * 1024


def default_history() -> dict[str, Any]:
    """Return optional finite history choices separately from native settings."""
    return {
        "enabled": True,
        "cache_dir": None,
        "max_commits": 100000,
        "max_record_bytes": 8388608,
        "max_cache_bytes": 268435456,
        "timeout_seconds": 60,
        "szz_max_fix_commits": 500,
        "behavior_config": None,
        "behavior_cutoff": None,
    }


def _history_settings(
    repo: Path, stored: dict[str, Any], explicit: dict[str, Any] | None
) -> dict[str, Any]:
    """Validate explicit history controls before optional tooling is imported."""
    schema = json.loads(
        resources.files("cppulse")
        .joinpath("data/project_config.schema.json")
        .read_bytes()
    )["definitions"]["history"]
    try:
        jsonschema.validate(stored, schema)
        jsonschema.validate(explicit or {}, schema)
        json.dumps([stored, explicit], allow_nan=False)
    except (ValueError, TypeError, jsonschema.ValidationError) as exc:
        raise ContractError(f"Invalid history configuration: {exc}") from exc
    result = {**default_history(), **stored, **(explicit or {})}
    for key in ("cache_dir", "behavior_config"):
        if result[key] is not None:
            base = Path.cwd() if explicit and key in explicit else repo
            result[key] = str((base / result[key]).resolve())
    if (result["behavior_config"] is None) != (result["behavior_cutoff"] is None):
        raise ContractError("Both behavior configuration and UTC cutoff are required")
    if result["behavior_cutoff"] is not None:
        from datetime import datetime, timedelta

        try:
            stamp = datetime.fromisoformat(
                result["behavior_cutoff"].replace("Z", "+00:00")
            )
            if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
                raise ValueError("expected aware UTC")
            path = Path(result["behavior_config"])
            with path.open("rb") as source:
                raw = source.read(65537)
            if len(raw) > 65536:
                raise ValueError("Behavior configuration exceeds 64 KiB")
            from cppulse.git_miner.behavior import BehaviorConfig

            BehaviorConfig.from_document(
                json.loads(raw, object_pairs_hook=_unique_pairs)
            )
        except (OSError, ValueError, TypeError) as exc:
            raise ContractError(f"Invalid behavior configuration: {exc}") from exc
    return result


def default_execution() -> dict[str, Any]:
    """Return finite worker defaults; legacy mode applies no worker isolation."""
    return {
        "mode": "legacy",
        "jobs": 1,
        "wall_seconds": 300,
        "cpu_seconds": 120,
        "address_space_bytes": 2 * 1024**3,
        "output_bytes": 64 * 1024**2,
        "work_directory": None,
        "resume": False,
    }


def _execution_settings(
    repo: Path,
    stored: dict[str, Any],
    explicit: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve data-only execution budgets separately from native detectors."""
    schema = json.loads(
        resources.files("cppulse")
        .joinpath("data/project_config.schema.json")
        .read_bytes()
    )["definitions"]["execution"]
    try:
        jsonschema.validate(stored, schema)
        jsonschema.validate(explicit or {}, schema)
        json.dumps([stored, explicit], allow_nan=False)
    except (ValueError, TypeError, jsonschema.ValidationError) as exc:
        raise ContractError(f"Invalid execution configuration: {exc}") from exc
    result = {
        **default_execution(),
        **({"mode": "bounded"} if stored or explicit else {}),
        **stored,
        **(explicit or {}),
    }
    directory = result["work_directory"]
    if directory is not None:
        selected = Path(directory)
        base = Path.cwd() if explicit and "work_directory" in explicit else repo
        result["work_directory"] = str((base / selected).resolve())
    if result["resume"] and result["work_directory"] is None:
        raise ContractError("Execution resume requires an explicit work_directory")
    legacy_options = (
        set(explicit)
        if explicit and explicit.get("mode") == "legacy"
        else set(stored) | set(explicit or {})
    )
    if result["mode"] == "legacy" and legacy_options - {"mode"}:
        raise ContractError("Worker execution options require bounded mode")
    return result


def _unique_pairs(pairs: list[tuple[Any, Any]]) -> dict[Any, Any]:
    """Construct one data mapping without silently replacing a selected value."""
    result: dict[Any, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate project configuration key: {key}")
        result[key] = value
    return result


class _UniqueKeyLoader(yaml.SafeLoader):
    """Keep safe YAML construction while rejecting root and nested duplicates."""

    def construct_mapping(
        self, node: yaml.nodes.MappingNode, deep: bool = False
    ) -> dict[Any, Any]:
        """Construct safe mappings while retaining duplicate-key diagnostics."""
        self.flatten_mapping(node)
        return _unique_pairs(
            [
                (
                    self.construct_object(key, deep=deep),
                    self.construct_object(value, deep=deep),
                )
                for key, value in node.value
            ]
        )


@dataclass(frozen=True)
class EffectiveConfig:
    """Invocation paths, native settings and the separate explicit execution plan."""

    repo: Path
    output: Path
    config_path: Path | None
    compilation_database: Path | None
    settings: dict[str, Any]
    profile_source: str
    execution: dict[str, Any] = dataclass_field(default_factory=default_execution)

    history: dict[str, Any] = dataclass_field(default_factory=default_history)

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-compatible effective configuration and provenance."""
        result = asdict(self)
        for field in ("repo", "output", "config_path", "compilation_database"):
            result[field] = str(result[field]) if result[field] is not None else None
        return result


def _validate_project_settings(value: Any, schema: dict[str, Any]) -> None:
    """Validate data with the native loader's strict integer token policy.

    JSON Schema treats 9.0 as an integer, but the native JSON/YAML loader
    rejects floating tokens. Reject them here before publishing configuration
    that the next consumer cannot load; never coerce user supplied values.
    """
    base = jsonschema.validators.validator_for(schema)
    strict_integer = base.TYPE_CHECKER.redefine(
        "integer", lambda checker, item: isinstance(item, int) and not isinstance(item, bool)
    )
    validator = jsonschema.validators.extend(base, type_checker=strict_integer)
    validator(schema).validate(value)


def read_settings(path: Path) -> dict[str, Any]:
    """Read safe JSON/YAML data and reject unsupported settings/types."""
    text = path.read_text(encoding="utf-8")
    try:
        settings = (
            json.loads(text, object_pairs_hook=_unique_pairs)
            if path.suffix == ".json"
            else yaml.load(text, Loader=_UniqueKeyLoader)
        )
        schema = json.loads(
            resources.files("cppulse")
            .joinpath("data/project_config.schema.json")
            .read_bytes()
        )
        _validate_project_settings(settings, schema)
        json.dumps(settings, allow_nan=False)
        from cppulse.tooling import load_rule_registry

        rule_schemas = {
            rule["id"]: rule["configuration_schema"]
            for rule in load_rule_registry()["rules"]
        }
        unknown = set(settings.get("rules", {})) - rule_schemas.keys()
        if unknown:
            raise ValueError(f"Unknown rule IDs: {', '.join(sorted(unknown))}")
        for rule_id, options in settings.get("rules", {}).items():
            try:
                _validate_project_settings(options, rule_schemas[rule_id])
            except jsonschema.ValidationError as exc:
                raise ValueError(
                    f"Unsupported configuration for {rule_id}: {exc.message}"
                ) from exc
    except (ValueError, TypeError, yaml.YAMLError, jsonschema.ValidationError) as exc:
        raise ContractError(f"Invalid project configuration {path}: {exc}") from exc
    return settings


def effective_config(
    repo: Path,
    output: Path,
    *,
    config: Path | None = None,
    profile: str | None = None,
    compilation_database: Path | None = None,
    execution: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
) -> EffectiveConfig:
    """Apply explicit options, repository settings, then documented defaults."""
    repo = repo.resolve(strict=True)
    if not repo.is_dir():
        raise ContractError(f"Repository must be a directory: {repo}")
    if config is not None:
        selected = config.resolve(strict=True)
    else:
        candidates = [repo / name for name in CONFIG_NAMES if (repo / name).is_file()]
        if len(candidates) > 1:
            names = ", ".join(path.name for path in candidates)
            raise ContractError(
                f"Ambiguous project configuration in {repo}: {names}. "
                "Select one explicitly with --config."
            )
        selected = candidates[0] if candidates else None
    settings = read_settings(selected) if selected else {}
    execution_options = _execution_settings(
        repo, settings.pop("execution", {}), execution
    )
    history_options = _history_settings(repo, settings.pop("history", {}), history)
    origin = (
        "command"
        if profile is not None
        else "config" if "profile" in settings else "default"
    )
    selected_profile = profile or settings.get("profile", "default")
    if selected_profile not in {"default", "safety-critical"}:
        raise ContractError(f"Unsupported profile: {selected_profile}")
    settings = {
        "profile": selected_profile,
        "exclude_paths": [],
        "rules": {},
        "max_file_bytes": DEFAULT_MAX_FILE_BYTES,
        **settings,
    }
    settings["profile"] = selected_profile
    database = (
        compilation_database.resolve(strict=True) if compilation_database else None
    )
    return EffectiveConfig(
        repo,
        output.resolve(),
        selected,
        database,
        settings,
        origin,
        execution_options,
        history_options,
    )


def initialize(repo: Path) -> Path:
    """Create an editable JSON config; never overwrite an existing config."""
    repo = repo.resolve(strict=True)
    if any((repo / name).exists() for name in CONFIG_NAMES):
        raise ContractError(
            "A project configuration already exists; inspect it with cppulse config"
        )
    path = repo / ".cppulserc.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "profile": "default",
                "exclude_paths": ["build/**", "vendor/**"],
                "rules": {},
            },
            stream,
            indent=2,
        )
        stream.write("\n")
    return path
