"""Generate native bindings from private annotations in the rule registry."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

NATIVE_ANNOTATION = "x-cppulse-native"


def public_rule_registry(document: dict[str, Any]) -> dict[str, Any]:
    """Retain the public v2 metadata without generator implementation details."""
    result = deepcopy(document)
    for rule in result["rules"]:
        rule["configuration_schema"].pop(NATIVE_ANNOTATION, None)
    return result


def _native_rows(document: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows = []
    for rule in document["rules"]:
        schema = rule["configuration_schema"]
        binding = schema.get(NATIVE_ANNOTATION)
        if not isinstance(binding, dict) or set(binding) != {"class", "header", "order"}:
            raise ValueError(f"Native registration binding required for {rule['id']}")
        if (not isinstance(binding["class"], str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", binding["class"]) is None
                or not isinstance(binding["header"], str)
                or len(binding["header"]) > 512
                or re.fullmatch(r"rules/(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*\.h", binding["header"]) is None
                or type(binding["order"]) is not int):
            raise ValueError(f"Invalid native registration binding for {rule['id']}")
        allowed_schema = {"$schema", "$comment", "title", "description", "type",
                          "additionalProperties", "properties", NATIVE_ANNOTATION}
        if (set(schema) - allowed_schema or schema.get("type") != "object"
                or schema.get("additionalProperties") is not False):
            raise ValueError(f"Unsupported native configuration schema for {rule['id']}")
        props = schema.get("properties")
        if not isinstance(props, dict) or set(props) not in (
            {"enabled"}, {"enabled", "warning_threshold", "error_threshold"}
        ):
            raise ValueError(f"Unsupported native option capabilities for {rule['id']}")
        for name, spec in props.items():
            allowed = {"type", "default", "description", "title", "$comment"}
            if name != "enabled":
                allowed |= {"minimum", "maximum"}
            if not isinstance(spec, dict) or set(spec) - allowed:
                raise ValueError(f"Unsupported native option schema for {rule['id']}.{name}")
            value = spec.get("default")
            if name == "enabled":
                valid = spec.get("type") == "boolean" and type(value) is bool
            else:
                valid = (spec.get("type") == "integer" and type(value) is int
                         and 0 <= value <= 2147483647
                         and spec.get("minimum") == 0 and spec.get("maximum") == 2147483647)
            if not valid:
                raise ValueError(f"Unsupported native option default/range for {rule['id']}.{name}")
        rows.append((rule, binding))
    if not rows:
        raise ValueError("Native registration requires at least one rule")
    for field in ["id", "class", "order"]:
        values = [rule["id"] if field == "id" else binding[field] for rule, binding in rows]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate native registration {field}")
    if sorted(binding["order"] for _, binding in rows) != list(range(len(rows))):
        raise ValueError("Native registration order must be contiguous from zero")
    return sorted(rows, key=lambda entry: entry[1]["order"])


def native_rule_headers(document: dict[str, Any]) -> dict[str, str]:
    """Emit real native types, option capabilities/defaults and constructors."""
    rows = _native_rows(document)
    notice = "// Generated from cppulse/data/rule_registry.json; use scripts/check_generated.py.\n"
    types = [notice, "#pragma once\n#include <variant>\n"]
    types += [f'#include "{header}"\n' for header in sorted({binding["header"] for _, binding in rows})]
    types += ["\nnamespace cppulse {\nusing AnyRule = std::variant<\n",
              ",\n".join("    " + binding["class"] for _, binding in rows),
              ">;\n}  // namespace cppulse\n"]
    registration = [notice, '#pragma once\n#include "generated_rule_types.h"\n',
                    "#include <cstddef>\n#include <set>\n#include <stdexcept>\n",
                    "#include <string>\n#include <string_view>\n#include <utility>\n\nnamespace cppulse {\n",
                    f"inline constexpr std::size_t generated_native_rule_count = {len(rows)};\n\n",
                    "inline std::set<std::string> generated_native_rule_options(std::string_view id) {\n"]
    for rule, _ in rows:
        keys = ", ".join(json.dumps(key) for key in sorted(rule["configuration_schema"]["properties"]))
        registration.append(f"    if (id == {json.dumps(rule['id'])}) return {{{keys}}};\n")
    registration += ['    throw std::invalid_argument("Unknown registry rule ID: " + std::string{id});\n}\n\n',
                     "inline bool generated_native_rule_default_enabled(std::string_view id) {\n"]
    for rule, _ in rows:
        enabled = str(rule["configuration_schema"]["properties"]["enabled"]["default"]).lower()
        registration.append(f"    if (id == {json.dumps(rule['id'])}) return {enabled};\n")
    registration += ['    throw std::invalid_argument("Unknown registry rule ID: " + std::string{id});\n}\n\n',
                     "template <typename AddRule, typename ApplyConfig>\n",
                     "inline void register_generated_native_rules(AddRule&& add_rule, ApplyConfig&& apply_config) {\n"]
    for rule, binding in rows:
        props = rule["configuration_schema"]["properties"]
        registration.append(f"    {{\n        {binding['class']} rule;\n")
        if "warning_threshold" in props:
            registration += [f"        rule.set_warn_threshold({props['warning_threshold']['default']});\n",
                             f"        rule.set_error_threshold({props['error_threshold']['default']});\n",
                             "        apply_config(rule);\n"]
        enabled = str(props["enabled"]["default"]).lower()
        registration.append(f"        add_rule(std::move(rule), {enabled});\n    }}\n")
    registration += ["}\n}  // namespace cppulse\n"]
    return {"analyzer-core/src/generated_rule_types.h": "".join(types),
            "analyzer-core/src/generated_rule_registration.h": "".join(registration)}
