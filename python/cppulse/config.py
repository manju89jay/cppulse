"""Resolve compatible project settings without executing project code."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from cppulse.errors import ContractError

CONFIG_NAMES = (".cppulserc.yml", ".cppulserc.yaml", ".cppulserc.json")
DEFAULT_MAX_FILE_BYTES = 16 * 1024 * 1024


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
    """Invocation-relative paths and the exact settings sent to the analyzer."""

    repo: Path
    output: Path
    config_path: Path | None
    compilation_database: Path | None
    settings: dict[str, Any]
    profile_source: str

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-compatible effective configuration and provenance."""
        result = asdict(self)
        for field in ("repo", "output", "config_path", "compilation_database"):
            result[field] = str(result[field]) if result[field] is not None else None
        return result


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
        jsonschema.validate(settings, schema)
        json.dumps(settings, allow_nan=False)
        from cppulse.tooling import load_rule_registry

        known_rules = {rule["id"] for rule in load_rule_registry()["rules"]}
        unknown = set(settings.get("rules", {})) - known_rules
        if unknown:
            raise ValueError(f"Unknown rule IDs: {', '.join(sorted(unknown))}")
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
    return EffectiveConfig(repo, output.resolve(), selected, database, settings, origin)


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
