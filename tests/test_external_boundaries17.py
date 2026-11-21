"""Small serialized GCC import boundaries; no compiler/provider executes."""

import hashlib
import json

import pytest

from cppulse.adapters.gcc_diagnostics import parse_gcc_json
from cppulse.errors import ContractError, IntegrityError
from cppulse.external import normalize_gcc_import, persist_gcc_import
from cppulse.run_store import RunSnapshot
from test_external_import import archive
from test_gcc_diagnostics import PRODUCER, diagnostic


def parse(raw, **selection):
    return parse_gcc_json(
        raw,
        source_root=selection.get("source_root", "/project"),
        scope_files=selection.get("scope_files", ["src/main.cpp"]),
        producer=selection.get("producer", PRODUCER),
    )


def test_hashed_namespace_cannot_alias_a_distinct_accepted_rule():
    unsafe = "-Wformat=odd value"
    reserved = "option-" + hashlib.sha256(unsafe.encode()).hexdigest()
    rows = [diagnostic(), diagnostic()]
    rows[0]["option"] = unsafe
    rows[1]["option"] = reserved
    result = parse(json.dumps(rows).encode())
    assert result.usability == "usable"
    assert [row.original_rule_id for row in result.diagnostics] == [unsafe, reserved]
    assert len({row.namespaced_rule_id for row in result.diagnostics}) == 2
    assert result.diagnostics[0].namespaced_rule_id == "gcc:" + reserved


@pytest.mark.parametrize("field", ["message", "option", "file", "ignored_key"])
def test_invalid_unicode_in_raw_payload_is_unavailable_not_exception(field):
    row = diagnostic()
    if field == "file":
        row["locations"][0]["caret"]["file"] = "/project/src/\ud800.cpp"
    elif field == "ignored_key":
        row["\ud800"] = 0
    else:
        row[field] = "\ud800"
    result = parse(json.dumps([row]).encode())
    assert result.usability in ("unsupported", "malformed")
    assert result.diagnostics == ()


def test_numeric_overflow_in_payload_never_becomes_usable_infinite_tree():
    raw = (
        json.dumps([diagnostic()])
        .encode()
        .replace(b'"children": []', b'"children": [], "metadata":1e9999')
    )
    result = parse(raw)
    assert result.usability in ("unsupported", "malformed") and result.diagnostics == ()


@pytest.mark.parametrize(
    "selection",
    [
        {"source_root": "/project/\ud800"},
        {"scope_files": ["src/\ud800.cpp"]},
        {"producer": {"name": "GNU-G++", "version": "\ud800"}},
    ],
)
def test_invalid_unicode_caller_metadata_is_typed(selection):
    with pytest.raises(ContractError):
        parse(b"[]", **selection)


def test_oversized_report_identity_does_not_require_body_materialization(
    tmp_path, monkeypatch
):
    import cppulse.adapters.gcc_diagnostics as adapter

    parent, _, selection = archive(tmp_path)
    raw_entry = next(
        row for row in parent.manifest["artifacts"] if row["id"] == "raw-report"
    )
    monkeypatch.setattr(adapter, "MAX_REPORT_BYTES", 8)
    original = RunSnapshot.read_bytes

    def forbidden(self, name):
        if self.run_id == parent.run_id and name == "raw-report":
            pytest.fail(
                "overbudget raw body materialized before adapter size rejection"
            )
        return original(self, name)

    monkeypatch.setattr(RunSnapshot, "read_bytes", forbidden)
    result = normalize_gcc_import(parent, **selection)
    assert result["usability"] == "unsupported" and result["observations"] == []
    assert result["report_artifact_id"] == raw_entry["id"]
    assert result["origin"] == "import" and result["scope_completeness"] == "unverified"


def test_changed_archive_during_parser_does_not_return_normalized_claim(
    tmp_path, monkeypatch
):
    import cppulse.external as external

    parent, _, selection = archive(tmp_path)
    original = external.parse_gcc_json
    entry = next(
        row for row in parent.manifest["artifacts"] if row["id"] == "raw-report"
    )

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        (parent.path / entry["path"]).write_bytes(b"[]")
        return result

    monkeypatch.setattr(external, "parse_gcc_json", changed)
    with pytest.raises(IntegrityError):
        normalize_gcc_import(parent, **selection)


def test_oversized_import_remains_partial_and_keeps_original_bytes(
    tmp_path, monkeypatch
):
    import cppulse.adapters.gcc_diagnostics as adapter

    parent, store, selection = archive(tmp_path)
    raw = parent.read_bytes("raw-report")
    monkeypatch.setattr(adapter, "MAX_REPORT_BYTES", 8)
    original = RunSnapshot.read_bytes

    def forbidden(self, name):
        if self.run_id == parent.run_id and name == "raw-report":
            pytest.fail("overbudget parent report body materialized")
        return original(self, name)

    monkeypatch.setattr(RunSnapshot, "read_bytes", forbidden)
    result = persist_gcc_import(parent, workspace=tmp_path, store=store, **selection)
    assert result.manifest["status"] == "partial"
    assert store.resolve_latest().run_id == parent.run_id
    assert store.resolve_latest_attempt().run_id == result.run_id
    assert result.read_bytes("raw-report") == raw
    facts = next(
        row
        for row in result.manifest["artifacts"]
        if row.get("contract", {}).get("kind") == "external_analysis_facts"
    )
    document = result.read_json(facts["id"])
    assert document["usability"] == "unsupported" and document["observations"] == []
    assert (
        document["origin"] == "import"
        and document["scope_completeness"] == "unverified"
    )


def test_parent_archive_drift_at_publication_cannot_advance_derived_heads(
    tmp_path, monkeypatch
):
    from cppulse.run_store import StagedRun

    parent, store, selection = archive(tmp_path)
    original = StagedRun.publish
    raw = next(row for row in parent.manifest["artifacts"] if row["id"] == "raw-report")
    before = (store.root / "heads.json").read_bytes()

    def changed(self, *args, **kwargs):
        if self.run_id != parent.run_id:
            (parent.path / raw["path"]).write_bytes(b"[]")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(StagedRun, "publish", changed)
    with pytest.raises(IntegrityError):
        persist_gcc_import(parent, workspace=tmp_path, store=store, **selection)
    assert (store.root / "heads.json").read_bytes() == before
    assert list((store.root / ".staging").glob("*/external/*.json"))


def test_normalized_occurrences_keep_distinct_original_rule_namespaces(tmp_path):
    unsafe = "-Wformat=odd value"
    reserved = "option-" + hashlib.sha256(unsafe.encode()).hexdigest()
    records = [diagnostic(), diagnostic(), diagnostic()]
    for record, rule in zip(records, [unsafe, reserved, unsafe]):
        record["option"] = rule
    parent, _, selection = archive(tmp_path, json.dumps(records).encode())
    result = normalize_gcc_import(parent, **selection)
    observations = result["observations"]
    assert [row["original_rule_id"] for row in observations] == [
        unsafe,
        reserved,
        unsafe,
    ]
    assert len({row["id"] for row in observations}) == 3
    assert (
        observations[0]["namespaced_rule_id"] == observations[2]["namespaced_rule_id"]
    )
    assert (
        observations[0]["namespaced_rule_id"] != observations[1]["namespaced_rule_id"]
    )
    assert observations[0]["fingerprint"] == observations[2]["fingerprint"]
    assert result["producer_namespace"] == "gcc" and result["origin"] == "import"
    assert any("not deduplicated" in text for text in result["limitations"])


@pytest.mark.parametrize(
    "message", ["λ😀", "combining e\u0301", "literal\\u0061", "nul\x00message"]
)
def test_valid_unicode_messages_and_exact_large_integer_coordinates_survive(message):
    row = diagnostic()
    row["message"] = message
    row["locations"][0]["caret"]["line"] = 2**100
    result = parse(json.dumps([row], ensure_ascii=False).encode())
    assert result.usability == "usable"
    assert result.diagnostics[0].message == message
    assert result.diagnostics[0].line == 2**100
    assert result.diagnostics[0].column == 7


def test_finite_ignored_numbers_and_normal_rule_spellings_remain_supported():
    row = diagnostic()
    row["metadata"] = 1e200
    result = parse(json.dumps([row]).encode())
    assert result.usability == "usable"
    assert result.diagnostics[0].namespaced_rule_id == "gcc:-Wunused-variable"
    assert result.diagnostics[0].original_rule_id == "-Wunused-variable"


def test_empty_missing_and_unknown_producer_never_gain_completeness(tmp_path):
    parent, _, selection = archive(tmp_path, b"[]")
    for producer in [None, {"name": "GNU-G++", "version": "99.0.0"}]:
        result = normalize_gcc_import(parent, **{**selection, "producer": producer})
        assert result["usability"] == "unsupported" and result["observations"] == []
        assert result["scope_completeness"] == "unverified"
        assert result["origin"] == "import"


@pytest.mark.parametrize("artifact_id", ["reports/gcc.json", "absent"])
def test_report_selection_requires_exact_declared_artifact_identity(
    tmp_path, artifact_id
):
    parent, _, selection = archive(tmp_path)
    with pytest.raises((ContractError, IntegrityError)):
        normalize_gcc_import(parent, **{**selection, "report_artifact_id": artifact_id})


def test_valid_unicode_root_and_distinct_file_spellings_stay_exact():
    files = ["src/é.cpp", "src/e\u0301.cpp"]
    rows = [diagnostic(), diagnostic()]
    for row, file in zip(rows, files):
        row["locations"][0]["caret"]["file"] = "/prøject/" + file
    result = parse(
        json.dumps(rows, ensure_ascii=True).encode(),
        source_root="/prøject",
        scope_files=files,
    )
    assert result.usability == "usable"
    assert [row.file for row in result.diagnostics] == files
    assert len({row.fingerprint for row in result.diagnostics}) == 2


def test_valid_escaped_surrogate_pair_is_not_rejected_as_lone_surrogate():
    row = diagnostic()
    row["message"] = "paired😀"
    result = parse(json.dumps([row], ensure_ascii=True).encode())
    assert result.usability == "usable" and result.diagnostics[0].message == "paired😀"
