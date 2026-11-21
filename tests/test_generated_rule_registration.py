"""Registry producer controls and a real compiled native registration consumer."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from cppulse.native_rule_generator import NATIVE_ANNOTATION, native_rule_headers
from cppulse.tooling import generated_files, load_rule_registry

ROOT = Path(__file__).resolve().parents[1]


def test_generator_metadata_preserves_existing_public_v2_contract(
    tmp_path: Path,
) -> None:
    old = ROOT / "work/installed-sdk-wire93/installed"
    assert (
        old.is_dir()
    ), "Retained candidate93 is required for this compatibility control"
    original = json.loads((old / "cppulse/data/rule_registry.json").read_bytes())
    assert load_rule_registry() == original
    raw = load_rule_registry(include_native_bindings=True)
    assert all(NATIVE_ANNOTATION in row["configuration_schema"] for row in raw["rules"])
    assert all(
        NATIVE_ANNOTATION not in row["configuration_schema"]
        for row in load_rule_registry()["rules"]
    )
    path = tmp_path / "registry-with-private-annotations.json"
    path.write_text(json.dumps(raw))
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(old) + ":" + str(ROOT / "work/closure-fr3/dependencies"),
    }
    command = [
        str(ROOT / "work/cloud-resume/installed-query20/core-venv/bin/python"),
        "-c",
        "import json,sys;from cppulse.contracts import validate;validate('rule_registry',json.load(open(sys.argv[1])))",
        str(path),
    ]
    subprocess.run(
        command, cwd="/tmp", env=environment, capture_output=True, check=True
    )


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate_id",
        "duplicate_class",
        "duplicate_order",
        "order_gap",
        "bool_order",
        "unsafe_class",
        "unsafe_header",
        "extra_binding",
        "unsupported_option",
        "unsupported_constraint",
        "invalid_default",
    ],
)
def test_invalid_registration_metadata_refuses_generation(change: str) -> None:
    registry = load_rule_registry(include_native_bindings=True)
    first, second = registry["rules"][:2]
    binding = first["configuration_schema"][NATIVE_ANNOTATION]
    if change == "missing":
        del first["configuration_schema"][NATIVE_ANNOTATION]
    elif change == "duplicate_id":
        second["id"] = first["id"]
    elif change == "duplicate_class":
        second["configuration_schema"][NATIVE_ANNOTATION]["class"] = binding["class"]
    elif change == "duplicate_order":
        second["configuration_schema"][NATIVE_ANNOTATION]["order"] = binding["order"]
    elif change == "order_gap":
        binding["order"] = 999
    elif change == "bool_order":
        binding["order"] = True
    elif change == "unsafe_class":
        binding["class"] = "Rule{}; injected()"
    elif change == "unsafe_header":
        binding["header"] = "../outside.h"
    elif change == "extra_binding":
        binding["execute"] = "anything"
    elif change == "unsupported_option":
        first["configuration_schema"]["properties"]["ignored"] = {
            "type": "integer",
            "default": 1,
        }
    elif change == "unsupported_constraint":
        first["configuration_schema"]["required"] = ["enabled"]
    else:
        first["configuration_schema"]["properties"]["enabled"]["default"] = 1
    with pytest.raises(ValueError):
        native_rule_headers(registry)


def test_compiled_registration_consumes_real_rule_types_and_metadata(
    tmp_path: Path,
) -> None:
    compiler = shutil.which("c++")
    assert (
        compiler is not None
    ), "A C++ compiler is required for the native producer gate"
    clang_include = ROOT / "work/native-deps/usr/lib/llvm-19/include"
    assert (clang_include / "clang-c/Index.h").is_file()
    registry = load_rule_registry(include_native_bindings=True)
    original = deepcopy(registry)
    files = generated_files()
    for name in ["generated_rule_types.h", "generated_rule_registration.h"]:
        (tmp_path / name).write_text(files["analyzer-core/src/" + name])
    source = tmp_path / "registration.cpp"
    source.write_text(
        """#include "generated_rule_registration.h"
#include <iostream>
int main() {
  cppulse::register_generated_native_rules(
    [](auto rule, bool enabled) {
      std::cout << "rule " << rule.rule_id() << " " << enabled << "\\n";
    },
    [](auto& rule) { std::cout << "configured " << rule.rule_id() << "\\n"; });
  for (const auto& id : {"CPP-MEM-001", "CPP-CX-001"}) {
    for (const auto& key : cppulse::generated_native_rule_options(id))
      std::cout << "option " << id << " " << key << "\\n";
  }
  try { cppulse::generated_native_rule_options("unknown"); return 2; }
  catch (const std::invalid_argument&) {}
}
"""
    )
    binary = tmp_path / "registration"
    command = [
        compiler,
        "-std=c++20",
        "-Os",
        "-g0",
        "-pipe",
        "-I",
        str(tmp_path),
        "-I",
        str(ROOT / "analyzer-core/src"),
        "-isystem",
        str(clang_include),
        str(source),
        "-o",
        str(binary),
    ]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (tmp_path / "compile.stdout").write_text(compiled.stdout)
    (tmp_path / "compile.stderr").write_text(compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
    (tmp_path / "run.stdout").write_text(result.stdout)
    (tmp_path / "run.stderr").write_text(result.stderr)
    assert result.returncode == 0, result.stderr
    rows = [line.split() for line in result.stdout.splitlines()]
    actual = [(row[1], row[2] == "1") for row in rows if row[0] == "rule"]
    expected = [
        (rule["id"], rule["configuration_schema"]["properties"]["enabled"]["default"])
        for rule in sorted(
            registry["rules"],
            key=lambda row: row["configuration_schema"][NATIVE_ANNOTATION]["order"],
        )
    ]
    assert actual == expected and len(actual) == 22
    configured = {row[1] for row in rows if row[0] == "configured"}
    assert configured == {
        rule["id"]
        for rule in registry["rules"]
        if "warning_threshold" in rule["configuration_schema"]["properties"]
    }
    for rule_id in ["CPP-MEM-001", "CPP-CX-001"]:
        keys = {row[2] for row in rows if row[0] == "option" and row[1] == rule_id}
        rule = next(rule for rule in registry["rules"] if rule["id"] == rule_id)
        assert keys == set(rule["configuration_schema"]["properties"])
    assert registry == original, "Generation mutated its authoritative input"
