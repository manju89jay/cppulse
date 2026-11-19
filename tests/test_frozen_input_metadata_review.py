"""Producer-to-contract checks with actual nanosecond filesystem metadata."""
import os
from pathlib import Path
import pytest
from cppulse.contracts.frozen_input import load_frozen_input, validate_frozen_input
from cppulse.errors import ContractError
from cppulse.frozen_input import inventory_frozen_inputs
from cppulse.identities import canonical_json_bytes
from test_frozen_input_contract import request, manifest


def test_current_filesystem_metadata_is_representable(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    source = root / "a.cpp"
    source.write_text("int a;\n")
    selected = request()
    selected["path_map"][0]["source_root"] = str(root)
    observed = inventory_frozen_inputs(selected)
    document = manifest()
    document["entries"] = observed
    validate_frozen_input("manifest", document)
    assert load_frozen_input("manifest", canonical_json_bytes(document)) == document
    first = source.stat().st_mtime_ns
    os.utime(source, ns=(first, first + 1))
    assert source.stat().st_mtime_ns == first + 1
    changed = inventory_frozen_inputs(selected)
    a = next(row for row in observed if row["kind"] == "regular")
    b = next(row for row in changed if row["kind"] == "regular")
    assert a["content"] == b["content"]
    assert b["mtime_ns"] - a["mtime_ns"] == 1
    document["entries"] = changed
    assert load_frozen_input("manifest", canonical_json_bytes(document)) == document


def test_private_metadata_retains_exact_signed64_integer_boundary() -> None:
    document = manifest()
    document["entries"][0]["mtime_ns"] = 2**63 - 1
    encoded = canonical_json_bytes(document)
    assert b"9223372036854775807" in encoded
    assert load_frozen_input("manifest", encoded) == document


@pytest.mark.parametrize("timestamp", [-1, 2**63])
def test_private_metadata_rejects_out_of_range_timestamp(timestamp: int) -> None:
    document = manifest()
    document["entries"][0]["mtime_ns"] = timestamp
    with pytest.raises(ContractError):
        validate_frozen_input("manifest", document)


def test_actual_out_of_range_file_metadata_fails_producer(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    source = root / "a.cpp"
    source.write_text("int a;\n")
    os.utime(source, ns=(2**63, 2**63))
    assert source.stat().st_mtime_ns == 2**63
    selected = request()
    selected["path_map"][0]["source_root"] = str(root)
    with pytest.raises(ContractError):
        inventory_frozen_inputs(selected)
