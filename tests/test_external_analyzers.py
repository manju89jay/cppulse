"""Bounded external analyzer imports over authored serialized reports only."""

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path

import pytest

from cppulse.adapters.external_analyzers import (
    parse_clang_tidy_text,
    parse_cppcheck_xml,
)
from cppulse.errors import ContractError

ROOT = "/project"
SCOPE = ["src/main.cpp"]
CLANG = {"name": "clang-tidy", "version": "19.1.7"}
CPPCHECK = {"name": "Cppcheck", "version": "2.17.1"}
TEXT = (
    b"/project/src/main.cpp:1:28: warning: use nullptr [modernize-use-nullptr]\n"
    b"    1 | int *p = 0;\n      |          ^\n      |          nullptr\n"
    b"/project/src/main.cpp:1:38: warning: Dereference of null pointer [clang-analyzer-core.NullDereference]\n"
    b"    1 | return *p;\n      |        ^~\n"
    b"/outside/header.h:5:3: note: expanded from a macro\n"
    b"    5 | #define P p\n      |           ^\n"
)
XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n<results version="2"><cppcheck version="2.17.1"/><errors>'
    b'<error id="nullPointer" severity="error" msg="Null pointer dereference: p" verbose="Null pointer dereference: p" cwe="476" file0="/project/src/main.cpp">'
    b'<location file="/project/src/main.cpp" line="1" column="39" info="Null pointer dereference"/>'
    b'<location file="/outside/header.h" line="4" column="5" info="Caller"/><symbol>p</symbol></error></errors></results>\n'
)


def clang(data=TEXT, **kwargs):
    return parse_clang_tidy_text(
        data,
        source_root=ROOT,
        scope_files=SCOPE,
        producer=kwargs.get("producer", CLANG),
    )


def cpp(data=XML, **kwargs):
    return parse_cppcheck_xml(
        data,
        source_root=ROOT,
        scope_files=SCOPE,
        producer=kwargs.get("producer", CPPCHECK),
    )


def test_live_module_origin():
    import cppulse.adapters.external_analyzers as module

    assert (
        Path(module.__file__).resolve()
        == Path(__file__).resolve().parents[1]
        / "python/cppulse/adapters/external_analyzers.py"
    )


def test_clang_primaries_keep_rule_location_and_secondary_notes_do_not_multiply():
    report = clang()
    assert report.usability == "usable" and len(report.diagnostics) == 2
    row = report.diagnostics[0]
    assert (row.original_rule_id, row.namespaced_rule_id, row.rule_version) == (
        "modernize-use-nullptr",
        "clang-tidy:modernize-use-nullptr",
        "19.1.7",
    )
    assert (row.file, row.line, row.column, row.severity) == (
        "src/main.cpp",
        1,
        28,
        "warning",
    )
    assert (
        report.report_sha256 == hashlib.sha256(TEXT).hexdigest()
        and report.origin == "import"
    )
    with pytest.raises(FrozenInstanceError):
        row.line = 2


def test_cppcheck_primary_location_and_secondary_callstack_stay_separate():
    report = cpp()
    assert report.usability == "usable" and len(report.diagnostics) == 1
    row = report.diagnostics[0]
    assert (
        row.original_rule_id,
        row.namespaced_rule_id,
        row.file,
        row.line,
        row.column,
    ) == ("nullPointer", "cppcheck:nullPointer", "src/main.cpp", 1, 39)
    assert report.report_sha256 == hashlib.sha256(XML).hexdigest()


def test_clang_combined_raw_check_identity_is_one_occurrence():
    raw = b"/project/src/main.cpp:2:1: warning: Avoid magic value [check-A,check-B]\n"
    report = clang(raw + raw)
    assert report.usability == "usable" and len(report.diagnostics) == 2
    assert report.diagnostics[0].original_rule_id == "check-A,check-B"
    assert report.diagnostics[0].namespaced_rule_id.startswith("clang-tidy:option-")
    assert report.diagnostics[0].fingerprint == report.diagnostics[1].fingerprint


@pytest.mark.parametrize("parser", [clang, cpp])
def test_missing_empty_and_unknown_version_are_explicit(parser):
    assert parser(None).usability == "missing" and parser(None).report_sha256 is None
    assert (
        parser(b"").usability == "missing"
        and parser(b"").report_sha256 == hashlib.sha256(b"").hexdigest()
    )
    result = parser(producer={"name": "unknown", "version": "99"})
    assert result.usability == "unsupported" and not result.diagnostics
    assert parser(producer=None).usability == "unsupported"


@pytest.mark.parametrize(
    "data",
    [
        b"unknown output\n",
        b"1 warning generated.\n",
        TEXT[:-1],
        TEXT + b"future unrecognized trailer\n",
        TEXT.replace(b"/project/src/main.cpp", b"/foreign/main.cpp", 1),
    ],
)
def test_unknown_truncated_and_out_of_scope_text_never_becomes_clean(data):
    report = clang(data)
    assert report.usability in ("unsupported", "malformed") and not report.diagnostics


@pytest.mark.parametrize(
    "data",
    [
        XML[:-10],
        XML.replace(b'version="2.17.1"', b'version="99"'),
        XML.replace(b'/project/src/main.cpp" line=', b'/foreign/main.cpp" line=', 1),
        b'<!DOCTYPE results [<!ENTITY leak SYSTEM "file:///etc/passwd">]><results version="2"/>',
    ],
)
def test_unknown_truncated_out_of_scope_or_entity_xml_is_unavailable(data):
    report = cpp(data)
    assert report.usability in ("unsupported", "malformed") and not report.diagnostics


@pytest.mark.parametrize(
    "text",
    [b"Suppressed 1 warnings (1 with check filters).\n", b"0 warnings generated.\n"],
)
def test_summary_only_text_is_not_a_located_report_or_clean_scan(text):
    report = clang(text)
    assert report.usability == "unsupported" and not report.diagnostics


@pytest.mark.parametrize(
    "change",
    [
        lambda xml: xml.replace(b'encoding="UTF-8"', b'encoding="UTF-16"'),
        lambda xml: xml.replace(b'version="1.0"', b'version="1.1"'),
        lambda xml: xml.replace(
            b"<results", b'<?unknown execution="complete"?><results', 1
        ),
    ],
)
def test_unreviewed_xml_encoding_version_or_processing_instruction_is_unavailable(
    change,
):
    report = cpp(change(XML))
    assert report.usability in ("unsupported", "malformed") and not report.diagnostics


def test_cppcheck_explicit_empty_xml_is_not_complete_clean_analysis():
    raw = b'<results version="2"><cppcheck version="2.17.1"/><errors/></results>'
    result = cpp(raw)
    assert result.usability == "usable" and result.diagnostics == ()
    assert result.origin == "import" and any(
        "clean scan" in item for item in result.limitations
    )


def test_repeated_cppcheck_occurrences_and_xml_entities_are_preserved():
    start = XML.index(b"<error ")
    end = XML.index(b"</error>") + len(b"</error>")
    raw = XML[:end] + XML[start:end] + XML[end:]
    result = cpp(raw)
    assert result.usability == "usable" and len(result.diagnostics) == 2
    assert result.diagnostics[0].fingerprint == result.diagnostics[1].fingerprint
    escaped = cpp(
        XML.replace(
            b'msg="Null pointer dereference: p"', b'msg="x &amp; &quot;y&quot;"'
        )
    )
    assert escaped.diagnostics[0].message == 'x & "y"'


@pytest.mark.parametrize(
    "parser,raw,prefix", [(clang, TEXT, "clang-tidy"), (cpp, XML, "cppcheck")]
)
def test_reserved_hash_slots_cannot_alias_distinct_original_ids(parser, raw, prefix):
    unsafe = "odd check/id"
    reserved = "option-" + hashlib.sha256(unsafe.encode()).hexdigest()
    if prefix == "clang-tidy":
        body = (
            f"/project/src/main.cpp:1:1: warning: Same message [{unsafe}]\n/project/src/main.cpp:1:1: warning: Same message [{reserved}]\n"
        ).encode()
    else:
        body = f'<results version="2"><cppcheck version="2.17.1"/><errors><error id="{unsafe}" severity="warning" msg="Same message"><location file="src/main.cpp" line="1"/></error><error id="{reserved}" severity="warning" msg="Same message"><location file="src/main.cpp" line="1"/></error></errors></results>'.encode()
    result = parser(body)
    assert (
        result.usability == "usable"
        and len({row.namespaced_rule_id for row in result.diagnostics}) == 2
    )
    assert [row.original_rule_id for row in result.diagnostics] == [unsafe, reserved]
    assert result.diagnostics[0].namespaced_rule_id == prefix + ":" + reserved


@pytest.mark.parametrize(
    "raw",
    [
        TEXT.replace(b"warning:", b"error:", 1),
        TEXT.replace(b"warning:", b"fatal error:", 1),
        TEXT.replace(b"\n", b"\r\n"),
    ],
)
def test_clang_error_and_crlf_profiles_keep_locations_and_byte_identity(raw):
    result = clang(raw)
    assert result.usability == "usable"
    assert result.diagnostics[0].severity in ("error", "warning")
    assert result.report_sha256 == hashlib.sha256(
        raw
    ).hexdigest() and result.size_bytes == len(raw)


@pytest.mark.parametrize(
    "raw",
    [
        TEXT.replace(b"/outside/header.h:5:3:", b"/outside/header.h:0:3:"),
        TEXT.replace(b"/outside/header.h:5:3:", b"/outside/header.h:5:x:"),
        XML.replace(b'line="4"', b'line="0"'),
        XML.replace(b'line="4"', b'line="nan"'),
        XML.replace(b'info="Caller"', b'info="Caller" unexpected="fact"'),
    ],
)
def test_malformed_secondary_details_refuse_entire_report(raw):
    result = cpp(raw) if raw.startswith(b"<?xml") else clang(raw)
    assert result.usability in ("unsupported", "malformed") and not result.diagnostics


@pytest.mark.parametrize(
    "replace_from,replace_to",
    [
        (b"<errors>", b'<errors hidden="5">'),
        (b'severity="error"', b'severity="future-kind"'),
        (b"<symbol>p</symbol>", b"<unknown>p</unknown>"),
        (b"<symbol>p</symbol>", b"<symbol><nested>p</nested></symbol>"),
        (b'id="nullPointer"', b'id="nullPointer" id="other"'),
        (b'line="1"', b'line="999999999999999999999999999999"'),
        (b'<results version="2">', b'<results version="3">'),
    ],
)
def test_unknown_xml_shapes_and_duplicate_metadata_never_claim_usable(
    replace_from, replace_to
):
    result = cpp(XML.replace(replace_from, replace_to, 1))
    assert result.usability in ("unsupported", "malformed") and not result.diagnostics


@pytest.mark.parametrize("parser", [clang, cpp])
@pytest.mark.parametrize("data", [b"\xff", b"\xed\xa0\x80", b"\x00bad"])
def test_invalid_unicode_and_nul_bytes_keep_raw_identity(parser, data):
    result = parser(data)
    assert result.usability == "malformed" and not result.diagnostics
    assert result.report_sha256 == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "function,producer",
    [(parse_clang_tidy_text, CLANG), (parse_cppcheck_xml, CPPCHECK)],
)
@pytest.mark.parametrize(
    "selection",
    [
        {"source_root": "relative"},
        {"source_root": "/bad\ud800"},
        {"scope_files": ["../bad.cpp"]},
        {"scope_files": ["src/main.cpp", "src/main.cpp"]},
        {"producer": {"name": "bad", "version": "\ud800"}},
    ],
)
def test_invalid_caller_metadata_is_contract_error(function, producer, selection):
    kwargs = {
        "source_root": ROOT,
        "scope_files": SCOPE,
        "producer": producer,
        **selection,
    }
    with pytest.raises(ContractError):
        function(b"[]", **kwargs)


@pytest.mark.parametrize(
    "limit,parser,raw",
    [
        ("MAX_REPORT_BYTES", clang, TEXT),
        ("MAX_DIAGNOSTICS", clang, TEXT),
        ("MAX_TEXT_LINES", clang, TEXT),
        ("MAX_LINE_BYTES", clang, TEXT),
        ("MAX_REPORT_BYTES", cpp, XML),
        ("MAX_NODES", cpp, XML),
        ("MAX_DEPTH", cpp, XML),
    ],
)
def test_parser_limits_fail_unavailable_without_partial_observations(
    monkeypatch, limit, parser, raw
):
    import cppulse.adapters.external_analyzers as module

    monkeypatch.setattr(module, limit, 1)
    result = parser(raw)
    assert result.usability == "unsupported" and result.diagnostics == ()
    assert result.report_sha256 == hashlib.sha256(raw).hexdigest()


def test_cppcheck_missing_column_stays_unknown_and_inconclusive_is_disclosed():
    raw = XML.replace(b' column="39"', b"", 1).replace(
        b'severity="error"', b'severity="error" inconclusive="true"', 1
    )
    result = cpp(raw)
    assert result.usability == "usable" and result.diagnostics[0].column is None
    assert any("Inconclusive" in item for item in result.limitations)
