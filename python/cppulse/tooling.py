"""Local development scaffolds and deterministic registry-derived native helpers.

Scaffolds are deliberately incomplete and never registered or executed here.
The packaged registry supplies native bindings, configuration and public metadata.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

from cppulse.contracts import validate

_NAME = re.compile(r"[a-z][a-z0-9_-]{0,62}\Z", re.ASCII)
_KINDS = {"rule", "adapter", "policy"}


def _json(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def load_rule_registry(*, include_native_bindings: bool = False) -> dict[str, Any]:
    """Read and validate an independent copy of the packaged native registry.

    Generator annotations are opt-in; existing public v2 consumers retain their
    metadata and configuration schemas without implementation details.
    """
    content = resources.files("cppulse").joinpath("data", "rule_registry.json")
    document = json.loads(content.read_text(encoding="utf-8"))
    validate("rule_registry", document)
    if not isinstance(include_native_bindings, bool):
        raise ValueError("include_native_bindings must be a boolean")
    if include_native_bindings:
        return document
    from cppulse.native_rule_generator import public_rule_registry

    return public_rule_registry(document)


def _rule_files(name: str) -> dict[str, str]:
    class_name = "".join(part.capitalize() for part in re.split("[-_]", name)) + "Rule"
    entry = {
        "id": f"DRAFT-{name}",
        "version": "0.0.0-draft",
        "maturity": "experimental",
        "category": "TODO-review-category",
        "required_capabilities": ["libclang_ast"],
        "supported_inputs": ["c++_translation_unit"],
        "configuration_schema": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": f"Draft: {name}",
            "type": "object",
            "additionalProperties": False,
            "properties": {"enabled": {"type": "boolean", "default": False}},
        },
        "documentation": "DRAFT ONLY: choose a native rule ID and document scope, limitations and reviewed fixtures before registration.",
    }
    validate("rule_registry", {"version": "2.0.0", "rules": [entry]})
    return {
        "registry-entry.json": _json({"version": "2.0.0", "rules": [entry]}),
        "rule.h": f"""// DRAFT ONLY: not registered in the native engine.
#pragma once
#include "rule_base.h"

namespace cppulse {{
class {class_name} : public RuleBase<{class_name}> {{
 public:
    void check_impl(CXCursor cursor, const std::string& file_path);
    std::string_view rule_id_impl() const noexcept {{ return "DRAFT-{name}"; }}
    std::string_view category_impl() const noexcept {{ return "TODO-review-category"; }}
}};
}}  // namespace cppulse
""",
        "rule.cpp": f"""// DRAFT ONLY: implement and review before adding to a build or registry.
#include "rule.h"
#include <stdexcept>

void cppulse::{class_name}::check_impl(CXCursor, const std::string&) {{
    throw std::logic_error("Draft detector has not been implemented");
}}
""",
        "cases/positive.cpp": "// TODO: add a minimal intentional trigger and expected location.\n",
        "cases/negative.cpp": "// TODO: add a clean counterexample that must not trigger.\n",
    }


def _adapter_files(name: str) -> dict[str, str]:
    return {
        "adapter.py": f'''"""Draft {name} adapter: not registered or executed by cppulse."""

from __future__ import annotations

from typing import Any


def normalize(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize a reviewed source format; implementation is required."""
    raise NotImplementedError("Draft adapter: implement identity, scope and failure semantics")
''',
        "cases.json": _json(
            {
                "draft": True,
                "todo": [
                    "Add versioned positive and malformed source fixtures",
                    "Assert context/source/artifact links and test-count denominators",
                    "Retain failed and unavailable results without inventing a pass",
                ],
            }
        ),
    }


def _policy_files(name: str) -> dict[str, str]:
    document = {
        "version": "2.0.0",
        "id": f"draft-{name}",
        "policy_version": "0.0.0-draft",
        "standards": [],
        "scope": {"include": ["**"], "exclude": []},
        "contexts": ["TODO-reviewed-context"],
        "gates": {"minimum_readiness": 100, "minimum_completeness": 100},
        "controls": [
            {
                "id": "draft-tests",
                "title": "DRAFT: replace with reviewed test evidence requirement",
                "kind": "test_outcomes",
                "weight": 1,
                "required": True,
                "parameters": {"evidence_ids": ["TODO-reviewed-evidence"]},
                "depends_on": [],
            }
        ],
    }
    validate("policy", document)
    return {"policy.json": _json(document)}


def _real_directory(directory: Path) -> None:
    for candidate in (directory, *directory.parents):
        if candidate.is_symlink():
            raise ValueError(f"Scaffold destination must not use symlinks: {candidate}")
    if not directory.is_dir():
        raise NotADirectoryError(
            f"Scaffold destination must already exist: {directory}"
        )


def scaffold(kind: str, name: str, destination: str | Path) -> Path:
    """Create an explicitly incomplete local rule, adapter or policy draft.

    Args:
        kind: One of rule, adapter or policy.
        name: Lowercase ASCII slug (at most 63 characters).
        destination: Existing local directory; symlinks are refused.

    Returns:
        The newly created destination/name directory.

    Raises:
        ValueError: For unsupported kinds, unsafe names or symlink destinations.
        FileExistsError: If the output already exists, including a symlink.
        NotADirectoryError: If the destination is not an existing directory.
    """
    if kind not in _KINDS:
        raise ValueError(
            f"Unknown scaffold kind {kind!r}; choose rule, adapter or policy"
        )
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("Scaffold name must match [a-z][a-z0-9_-]{0,62}")
    directory = Path(destination).absolute()
    _real_directory(directory)
    builders = {"rule": _rule_files, "adapter": _adapter_files, "policy": _policy_files}
    files = builders[kind](name)
    files["README.md"] = (
        f"# Draft {kind}: {name}\n\n"
        "This is an incomplete scaffold. It is not a detector, registered adapter, "
        "approved policy, or executed check. Generation does not change any active "
        "registry, configuration, policy selection or pipeline.\n\n"
        "Review the intended behavior, source/context scope, unavailable and failed "
        "inputs, limitations, compatibility and positive/negative regression cases. "
        "Choose reviewed identifiers and versions before explicit integration. "
        "A policy's placeholder context and evidence IDs must be replaced and bound "
        "to real evidence; schema validity alone does not establish suitability.\n"
    )
    target = directory / name
    target.mkdir()  # Exclusive creation; do not touch an existing file or directory.
    created: list[Path] = []
    try:
        for relative, content in files.items():
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(output)
                stream.write(content)
    except OSError:
        for output in reversed(created):
            output.unlink()
        for child in sorted(target.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
        target.rmdir()
        raise
    return target


def generated_files() -> dict[str, str]:
    """Render deterministic source-controlled reference and native config files."""
    registry = load_rule_registry()
    from cppulse.native_rule_generator import native_rule_headers

    native_headers = native_rule_headers(
        load_rule_registry(include_native_bindings=True)
    )
    schemas = {rule["id"]: rule["configuration_schema"] for rule in registry["rules"]}
    defaults = {
        rule_id: {key: spec["default"] for key, spec in schema["properties"].items()}
        for rule_id, schema in schemas.items()
    }
    config_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "cppulse reviewed native analysis configuration",
        "description": "Generated from the packaged experimental rule registry. Profiles affect scoring; rule.enabled selects detectors.",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "profile": {"enum": ["default", "safety-critical"], "default": "default"},
            "exclude_paths": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
            "rules": {
                "type": "object",
                "additionalProperties": False,
                "properties": schemas,
            },
        },
    }
    lines = [
        "# Native rule reference\n",
        "Generated from `python/cppulse/data/rule_registry.json`. Regenerate with "
        "`python scripts/check_generated.py --write`; check with "
        "`python scripts/check_generated.py`.\n",
        f"All {len(registry['rules'])} checks are **experimental** and enabled by default. Availability "
        "depends on the selected successfully parsed C++ context and libclang AST. "
        "A registered check does not establish complete source coverage, correctness, "
        "MISRA compliance or certification. Zero findings can coexist with partial "
        "or unavailable analysis. `prototype-*` versions are implementation labels, not "
        "validated stable releases.\n",
        "The `default` scoring profile excludes MISRA findings from scores and "
        "ranking; it does not disable MISRA detectors. `safety-critical` includes "
        "those experimental signals in scoring. Use an explicit per-rule "
        "`enabled: false` to disable a detector.\n",
        "| ID | Version | Name | Category | Maturity | Default configuration |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for rule in registry["rules"]:
        rid = rule["id"]
        default = json.dumps(defaults[rid], sort_keys=True)
        lines.append(
            f"| {rid} | {rule['version']} | {schemas[rid]['title']} | {rule['category']} | "
            f"{rule['maturity']} | `{default}` |"
        )
    lines += ["", "## Detection scope", ""]
    for rule in registry["rules"]:
        lines.append(f"- **{rule['id']}:** {rule['documentation']}")
    lines += [
        "",
        "Complexity findings trigger when a value is strictly greater than the "
        "warning threshold; error severity requires strictly greater than the error "
        "threshold. The generated config is an explicit default example, not a "
        "project-specific recommendation. Thresholds use nonnegative integers up "
        "to 2147483647 (the supported native int range) in the reviewed config "
        "schema. Unknown rule IDs are refused by that schema.",
        "",
    ]
    return {
        **native_headers,
        "docs/generated/rules.md": "\n".join(lines),
        "docs/generated/native-config.schema.json": _json(config_schema),
        "docs/generated/native-config.example.json": _json(
            {"profile": "default", "exclude_paths": [], "rules": defaults}
        ),
        "docs/generated/development.md": _DEVELOPMENT,
    }


def check_generated(root: str | Path) -> list[str]:
    """Return missing or stale generated paths without modifying the checkout."""
    directory = Path(root)
    mismatches = []
    for relative, expected in generated_files().items():
        path = directory / relative
        try:
            current = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            current = None
        if current != expected:
            mismatches.append(relative)
    return mismatches


_DEVELOPMENT = """# Development and candidate review

Generated reference: edit `cppulse.tooling` or the packaged registry, then run
`python scripts/check_generated.py --write` and review the resulting diff.
`python scripts/check_generated.py` only checks; it exits nonzero for stale files.
The local tooling tests also compare the registry with native rule registrations,
categories and complexity defaults. Generated native helpers define registered
types, constructors, option capabilities and defaults. Detector implementations
remain explicit C++ source with reviewed positive and negative fixtures.

## Draft scaffolds

`cppulse.tooling.scaffold(kind, name, destination)` creates a new local directory
for a `rule`, `adapter` or `policy`. Names must be lowercase ASCII slugs. The
destination must already exist and contain no symlink path components. Existing
targets are refused. No code, registry, config or active policy is overwritten.
No command executes and no network call, Git operation or publication occurs.

Rules require a reviewed native ID, implementation, build/variant registration
and positive/negative tests. The rule stub throws until implemented; its draft
registry entry is not loaded. Adapters raise NotImplementedError until reviewed
normalization and failure behavior exist. Policy JSON is schema-valid draft data
with placeholder context/evidence IDs; it is not an approved or evaluated policy.

## Preview and stable candidates

These are review channels, not automatic release or update mechanisms. Current
checks remain experimental. A locally prepared preview candidate may contain an
experimental check only with its scope, fixtures and limitations disclosed. An
installed-artifact smoke run, contract/config compatibility checks, generated-file
checks, dependency inventory and reproducible checksums must accompany review.
This document does not claim those checks passed for a particular candidate.

Stable promotion requires independent review of positive and clean cases,
supported language/build contexts, parse failures and unsupported inputs;
measured false positives/negatives on disclosed representative inputs; versioned
behavior and default changes; compatibility/migration/rollback evidence; and
actual installed-artifact checks on every claimed platform. Agree acceptance
thresholds before evaluation and retain inconclusive results. MISRA-like signals
and experimental ranking do not become certification or calibrated probability
claims through promotion.

A new detector or scoring default must not silently change a pinned policy,
scorer or organization requirement. Promote through an explicit reviewed version
and migration; never rewrite immutable run evidence. Preparation is local and
publication requires a separate authorized action. No stable candidate is
declared by the existence of this registry or a generated scaffold.
"""
