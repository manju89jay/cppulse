"""Actual tiny retained layer controls; no container or cache qualification."""

from decimal import Decimal
import gzip
import hashlib
import os
import tarfile

import pytest

from cppulse.errors import ContractError, InputChanged
from cppulse import frozen_layer as module

from test_frozen_input_inventory import selected


retain_frozen_layer = module.retain_frozen_layer


def test_retained_archive_contains_same_hashed_bytes_and_exact_ns_metadata(tmp_path):
    root, req = selected(tmp_path)
    precise = 1800000000123456789
    os.utime(root / "a.cpp", ns=(precise, precise))
    destination = tmp_path / "layer.tar.gz"
    result = retain_frozen_layer(req, destination)
    raw = gzip.decompress(destination.read_bytes())
    assert result["raw_layer"] == {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }
    assert result["compressed_layer"] == {
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "size_bytes": destination.stat().st_size,
    }
    with tarfile.open(destination, "r:gz") as archive:
        assert archive.getnames() == ["input", "input/a.cpp", "input/empty"]
        member = archive.getmember("input/a.cpp")
        assert Decimal(member.pax_headers["mtime"]) * 10**9 == precise
        assert member.uid == member.gid == 1000
        assert archive.extractfile(member).read() == b"int a;\n"
    assert result["state"] == "retained_verified"
    assert result["cache_eligible"] is False
    assert result["closure"] == "unqualified"


def test_repeat_capture_is_deterministic_for_identical_selected_inputs(tmp_path):
    _, req = selected(tmp_path)
    one = retain_frozen_layer(req, tmp_path / "one.gz")
    two = retain_frozen_layer(req, tmp_path / "two.gz")
    assert one == two
    assert (tmp_path / "one.gz").read_bytes() == (tmp_path / "two.gz").read_bytes()


def test_output_cannot_create_a_new_selected_input(tmp_path):
    root, req = selected(tmp_path)
    with pytest.raises(ContractError):
        retain_frozen_layer(req, root / "layer.gz")
    assert not (root / "layer.gz").exists()


def test_existing_artifact_is_never_overwritten(tmp_path):
    _, req = selected(tmp_path)
    path = tmp_path / "layer.gz"
    path.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        retain_frozen_layer(req, path)
    assert path.read_bytes() == b"original"


@pytest.mark.parametrize(
    "mutation", ["same_size_file", "add", "delete", "create_delete", "root_replace"]
)
def test_actual_capture_races_fail_and_preserve_partial_output(
    tmp_path, monkeypatch, mutation
):
    root, req = selected(tmp_path)
    original = os.read
    reads = 0
    mutated = False

    def read(fd, count):
        nonlocal reads, mutated
        data = original(fd, count)
        if data:
            reads += 1
        # First nonempty read is initial inventory; second is actual tar stream.
        if data and reads == 2 and not mutated:
            mutated = True
            if mutation == "same_size_file":
                (root / "a.cpp").write_bytes(b"int b;\n")
            elif mutation == "add":
                (root / "new.h").write_bytes(b"new")
            elif mutation == "delete":
                (root / "empty").rmdir()
            elif mutation == "create_delete":
                (root / "new.h").write_bytes(b"new")
                (root / "new.h").unlink()
            else:
                root.rename(tmp_path / "old-source")
                root.mkdir()
                (root / "a.cpp").write_bytes(b"int a;\n")
        return data

    monkeypatch.setattr(os, "read", read)
    path = tmp_path / "partial-layer.gz"
    with pytest.raises((InputChanged, FileNotFoundError)):
        retain_frozen_layer(req, path)
    assert mutated
    assert not path.exists()
    assert path.with_name(path.name + ".partial").stat().st_size > 0


def test_capture_result_is_strict_contract_before_acceptance(tmp_path):
    from cppulse.contracts.frozen_input import validate_frozen_input

    _, req = selected(tmp_path)
    result = retain_frozen_layer(req, tmp_path / "layer.gz")
    validate_frozen_input("capture", result)
    result["cache_eligible"] = True
    with pytest.raises(ContractError):
        validate_frozen_input("capture", result)
