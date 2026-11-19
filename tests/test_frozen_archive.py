"""Shared byte codec does not invent source provenance for assembled layers."""
from copy import deepcopy
import pytest
from cppulse.contracts.frozen_input import validate_frozen_input
from cppulse.errors import ContractError
from cppulse.frozen_layer import retain_frozen_layer, verify_archive
from test_frozen_input_inventory import selected


def archive_document(capture):
    fields = (
        "version",
        "cache_eligible",
        "closure",
        "raw_layer",
        "compressed_layer",
        "compression",
        "ownership",
    )
    doc = {key: deepcopy(capture[key]) for key in fields}
    doc["entries"] = [
        {
            key: deepcopy(row[key])
            for key in ("path", "kind", "mode", "mtime_ns", "content")
        }
        for row in capture["entries"]
    ]
    return doc


def test_real_retained_bytes_verify_without_invented_source_paths(tmp_path):
    _, request = selected(tmp_path)
    path = tmp_path / "layer.gz"
    capture = retain_frozen_layer(request, path)
    doc = archive_document(capture)
    validate_frozen_input("archive", doc)
    verify_archive(doc, path)
    assert all("source_root" not in row for row in doc["entries"])


@pytest.mark.parametrize(
    "mutation", ["path", "bytes", "timestamp", "duplicate", "ownership", "extra"]
)
def test_assembled_expected_archive_cannot_hide_mismatches(tmp_path, mutation):
    _, request = selected(tmp_path)
    path = tmp_path / "layer.gz"
    doc = archive_document(retain_frozen_layer(request, path))
    if mutation == "path":
        doc["entries"][1]["path"] = "/input/wrong.cpp"
    elif mutation == "bytes":
        doc["entries"][1]["content"]["sha256"] = "e" * 64
    elif mutation == "timestamp":
        doc["entries"][1]["mtime_ns"] += 1
    elif mutation == "duplicate":
        doc["entries"].append(deepcopy(doc["entries"][-1]))
    elif mutation == "ownership":
        doc["ownership"]["uid"] = 0
    else:
        doc["entries"][0]["source_root"] = "/invented"
    with pytest.raises(ContractError):
        verify_archive(doc, path)
