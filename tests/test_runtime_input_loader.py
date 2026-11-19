"""Untrusted runtime declarations fail closed before filesystem consumption."""
import pytest
from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes
from cppulse.runtime_input import load_runtime_manifest
from test_runtime_input_contract import document


def test_canonical_exact_integer_runtime_round_trip():
    value = document()
    assert load_runtime_manifest(canonical_json_bytes(value)) == value


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"{",
        b"{} garbage",
        b"[]",
        b"null",
        b"NaN",
        b"Infinity",
        b"-Infinity",
    ],
)
def test_malformed_or_nonobject_runtime_json_is_typed(raw):
    with pytest.raises(ContractError):
        load_runtime_manifest(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_root",
        "duplicate_nested",
        "float",
        "huge_integer",
        "nonfinite",
        "surrogate",
    ],
)
def test_strict_json_rejects_ambiguous_or_unbounded_values(mutation):
    raw = canonical_json_bytes(document())
    if mutation == "duplicate_root":
        raw = b'{"version":"0.1.0",' + raw[1:]
    elif mutation == "duplicate_nested":
        raw = raw.replace(b'"mode":365', b'"mode":365,"mode":365', 1)
    elif mutation == "float":
        raw = raw.replace(b"1800000000123456789", b"0.0", 1)
    elif mutation == "huge_integer":
        raw = raw.replace(b"1800000000123456789", b"1" * 5000, 1)
    elif mutation == "nonfinite":
        raw = raw.replace(b"1800000000123456789", b"NaN", 1)
    else:
        raw = raw.replace(b"linux-vdso.so.1", b"\\ud800", 1)
    with pytest.raises(ContractError):
        load_runtime_manifest(raw)


def test_raw_byte_limit_precedes_decoding():
    with pytest.raises(ContractError):
        load_runtime_manifest(b" " * (8 * 1024**2 + 1))


def test_depth_and_member_limits_precede_object_materialization():
    with pytest.raises(ContractError):
        load_runtime_manifest(b"[" * 65 + b"0" + b"]" * 65)
    with pytest.raises(ContractError):
        load_runtime_manifest(b"[" + b"0," * 20001 + b"0]")


def test_brackets_and_escaped_quotes_in_strings_are_not_nesting():
    value = document()
    value["files"][0]["source_path"] = "/host/" + ("[}" * 80) + 'quoted"name'
    assert load_runtime_manifest(canonical_json_bytes(value)) == value
