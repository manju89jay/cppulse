"""Check registry/source agreement and local-only incomplete scaffolds."""

from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from cppulse.contracts import validate
from cppulse.tooling import (
    check_generated,
    generated_files,
    load_rule_registry,
    scaffold,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def registry() -> dict[str, Any]:
    """Return a fresh schema-validated registry."""
    return load_rule_registry()


def test_registry_matches_native_registrations_and_categories(
    registry: dict[str, Any],
) -> None:
    native: dict[str, tuple[str, str]] = {}
    for header in (ROOT / "analyzer-core/src/rules").rglob("*.h"):
        source = header.read_text()
        rule_id = re.search(r'rule_id_impl\(\).*?return "([^"]+)";', source, re.S)
        category = re.search(r'category_impl\(\).*?return "([^"]+)";', source, re.S)
        class_name = re.search(r"class (\w+) : public RuleBase", source)
        assert rule_id and category and class_name
        native[rule_id[1]] = (category[1], class_name[1])
    engine = (ROOT / "analyzer-core/src/analyzer.cpp").read_text()
    registered = set(re.findall(r"add_rule\((\w+)\{\}\)", engine))
    registered.update(re.findall(r"(\w+Rule) r;\s*apply_thresholds", engine))
    assert registered == {item[1] for item in native.values()}
    assert len(registered) == 22
    rules = registry["rules"]
    assert {rule["id"]: rule["category"] for rule in rules} == {
        rule_id: metadata[0] for rule_id, metadata in native.items()
    }
    assert all(rule["maturity"] == "experimental" for rule in rules)
    assert all(rule["configuration_schema"]["title"] for rule in rules)
    assert all(
        rule["configuration_schema"]["properties"]["enabled"]["default"] is True
        for rule in rules
    )
    config = (ROOT / "analyzer-core/src/config.h").read_text()
    assert "bool enabled{true};" in config
    enabled_body = engine.split("bool is_rule_enabled", 1)[1].split(
        "/// @brief Apply threshold", 1
    )[0]
    assert "profile" not in enabled_body
    assert "return it->second.enabled;" in enabled_body


@pytest.mark.parametrize(
    ("rule_id", "filename", "warn_member", "error_member"),
    [
        ("CPP-CX-001", "cyclomatic_complexity", "warn_threshold_", "error_threshold_"),
        ("CPP-CX-002", "function_length", "warn_lines_", "error_lines_"),
        ("CPP-CX-003", "parameter_count", "warn_params_", "error_params_"),
    ],
)
def test_registry_threshold_defaults_match_native_values(
    registry: dict[str, Any],
    rule_id: str,
    filename: str,
    warn_member: str,
    error_member: str,
) -> None:
    source = (ROOT / f"analyzer-core/src/rules/complexity/{filename}.h").read_text()
    properties = next(
        rule["configuration_schema"]["properties"]
        for rule in registry["rules"]
        if rule["id"] == rule_id
    )
    for setting, member in (
        ("warning_threshold", warn_member),
        ("error_threshold", error_member),
    ):
        value = re.search(r"int " + re.escape(member) + r"\{(\d+)\}", source)
        assert value
        assert properties[setting]["default"] == int(value[1])


def test_registry_is_a_fresh_packaged_contract(registry: dict[str, Any]) -> None:
    validate("rule_registry", registry)
    registry["rules"][0]["maturity"] = "stable"
    assert load_rule_registry()["rules"][0]["maturity"] == "experimental"


def test_generated_config_validates_and_refuses_unknown_settings() -> None:
    rendered = generated_files()
    schema = json.loads(rendered["docs/generated/native-config.schema.json"])
    example = json.loads(rendered["docs/generated/native-config.example.json"])
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.validate(example, schema)
    assert example["profile"] == "default"
    assert example["exclude_paths"] == []
    assert len(example["rules"]) == 22
    assert example["rules"]["CPP-CX-003"] == {
        "enabled": True,
        "warning_threshold": 5,
        "error_threshold": 8,
    }
    example["rules"]["UNKNOWN-001"] = {"enabled": True}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(example, schema)
    example["rules"].pop("UNKNOWN-001")
    example["rules"]["CPP-MEM-001"]["unsupported"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(example, schema)


def test_checked_in_generated_files_are_current() -> None:
    assert check_generated(ROOT) == []


@pytest.mark.parametrize("rule_id", ["CPP-CX-001", "CPP-CX-002", "CPP-CX-003"])
@pytest.mark.parametrize("setting", ["warning_threshold", "error_threshold"])
def test_generated_threshold_config_respects_native_integer_range(
    rule_id: str, setting: str
) -> None:
    schema = json.loads(generated_files()["docs/generated/native-config.schema.json"])
    jsonschema.validate({"rules": {rule_id: {setting: 2147483647}}}, schema)
    for invalid in (-1, 2147483648):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"rules": {rule_id: {setting: invalid}}}, schema)


def test_generated_check_detects_drift_without_writing(tmp_path: Path) -> None:
    expected = generated_files()
    assert check_generated(tmp_path) == list(expected)
    assert list(tmp_path.iterdir()) == []
    for relative, content in expected.items():
        output = tmp_path / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)
    assert check_generated(tmp_path) == []
    changed = tmp_path / "docs/generated/rules.md"
    changed.write_text("stale\n")
    assert check_generated(tmp_path) == ["docs/generated/rules.md"]
    assert changed.read_text() == "stale\n"
    changed.write_bytes(b"\xff")
    assert check_generated(tmp_path) == ["docs/generated/rules.md"]


def test_generated_script_check_and_explicit_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = runpy.run_path(str(ROOT / "scripts/check_generated.py"))
    main = script["main"]
    monkeypatch.setitem(main.__globals__, "ROOT", tmp_path)
    assert main([]) == 1
    assert "Stale generated files" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
    assert main(["--write"]) == 0
    assert "are current" in capsys.readouterr().out
    assert main([]) == 0


def test_generated_script_refuses_symlink_writes_before_changing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = runpy.run_path(str(ROOT / "scripts/check_generated.py"))
    main = script["main"]
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "docs").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "rules.md"
    marker.write_text("preserve")
    (checkout / "docs/generated").symlink_to(outside, target_is_directory=True)
    monkeypatch.setitem(main.__globals__, "ROOT", checkout)
    assert main(["--write"]) == 1
    assert marker.read_text() == "preserve"
    assert list(outside.iterdir()) == [marker]


@pytest.mark.parametrize("kind", ["rule", "adapter", "policy"])
def test_scaffolds_are_labeled_drafts_and_do_not_register_or_execute(
    tmp_path: Path, kind: str
) -> None:
    before = load_rule_registry()
    output = scaffold(kind, "example-check", tmp_path)
    assert output == tmp_path / "example-check"
    readme = (output / "README.md").read_text()
    assert "incomplete scaffold" in readme
    assert "not a detector" in readme
    assert load_rule_registry() == before
    if kind == "rule":
        entry = json.loads((output / "registry-entry.json").read_text())
        validate("rule_registry", entry)
        assert entry["rules"][0]["id"].startswith("DRAFT-")
        assert "throw std::logic_error" in (output / "rule.cpp").read_text()
        assert (output / "cases/positive.cpp").read_text().startswith("// TODO")
        assert (output / "cases/negative.cpp").read_text().startswith("// TODO")
    elif kind == "adapter":
        adapter = runpy.run_path(str(output / "adapter.py"))
        with pytest.raises(NotImplementedError, match="Draft adapter"):
            adapter["normalize"]({})
    else:
        policy = json.loads((output / "policy.json").read_text())
        validate("policy", policy)
        assert policy["policy_version"] == "0.0.0-draft"
        assert policy["contexts"] == ["TODO-reviewed-context"]


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../escape",
        "/absolute",
        "a/b",
        "a\\b",
        "Upper",
        "café",
        "a b",
        "x" * 64,
        "a\n",
    ],
)
def test_scaffold_refuses_unsafe_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="Scaffold name"):
        scaffold("rule", name, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_scaffold_refuses_unknown_kind_and_missing_destination(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown scaffold kind"):
        scaffold("unknown", "example", tmp_path)
    with pytest.raises(NotADirectoryError):
        scaffold("rule", "example", tmp_path / "missing")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("existing", ["file", "directory", "symlink", "broken-symlink"])
def test_scaffold_refuses_every_existing_target(tmp_path: Path, existing: str) -> None:
    target = tmp_path / "example"
    if existing == "file":
        target.write_text("preserve")
    elif existing == "directory":
        target.mkdir()
        (target / "keep.txt").write_text("preserve")
    else:
        target.symlink_to(
            tmp_path / ("missing" if existing == "broken-symlink" else "keep")
        )
    with pytest.raises(FileExistsError):
        scaffold("adapter", "example", tmp_path)
    if existing == "file":
        assert target.read_text() == "preserve"
    elif existing == "directory":
        assert (target / "keep.txt").read_text() == "preserve"
    else:
        assert target.is_symlink()


def test_scaffold_refuses_symlink_destination_or_ancestor(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "nested").mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    for destination in (link, link / "nested"):
        with pytest.raises(ValueError, match="must not use symlinks"):
            scaffold("policy", "example", destination)
    assert not (real / "example").exists()
    assert not (real / "nested/example").exists()


def test_partial_scaffold_write_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.open

    def fail_on_second_file(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path.name == "cases.json":
            raise OSError("synthetic disk failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_on_second_file)
    with pytest.raises(OSError, match="synthetic disk failure"):
        scaffold("adapter", "example", tmp_path)
    assert list(tmp_path.iterdir()) == []
