"""Actual final output races cannot publish different unverified bytes."""

import gzip
import os

import pytest

from cppulse.errors import ContractError, InputChanged
from test_frozen_input_inventory import selected

from cppulse import frozen_layer as module


def test_source_path_replaced_at_final_link_never_publishes_wrong_bytes(
    tmp_path, monkeypatch
):
    _, req = selected(tmp_path)
    output = tmp_path / "layer.gz"
    partial = tmp_path / "layer.gz.partial"
    retained = tmp_path / "retained-original.gz"
    original = os.link

    def link(source, target, **kwargs):
        if target == output.name:
            partial.rename(retained)
            partial.write_bytes(b"foreign replacement")
        return original(source, target, **kwargs)

    monkeypatch.setattr(os, "link", link)
    try:
        module.retain_frozen_layer(req, output)
    except InputChanged:
        pass
    if output.exists():
        assert output.read_bytes() == retained.read_bytes()
        assert gzip.decompress(output.read_bytes())
    assert partial.read_bytes() == b"foreign replacement"


def test_output_directory_replaced_during_capture_leaves_only_partial(
    tmp_path, monkeypatch
):
    _, req = selected(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir(mode=0o700)
    old_dir = tmp_path / "old-output"
    original = os.read
    reads = 0

    def read(fd, count):
        nonlocal reads
        result = original(fd, count)
        if result:
            reads += 1
        if result and reads == 2:
            output_dir.rename(old_dir)
            output_dir.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(os, "read", read)
    with pytest.raises(InputChanged, match="directory was replaced"):
        module.retain_frozen_layer(req, output_dir / "layer.gz")
    assert not (output_dir / "layer.gz").exists()
    assert (old_dir / "layer.gz.partial").exists()


def test_foreign_existing_partial_is_preserved(tmp_path):
    _, req = selected(tmp_path)
    partial = tmp_path / "layer.gz.partial"
    partial.write_bytes(b"prior evidence")
    with pytest.raises(FileExistsError):
        module.retain_frozen_layer(req, tmp_path / "layer.gz")
    assert partial.read_bytes() == b"prior evidence"


def test_nonprivate_destination_directory_is_unsupported(tmp_path):
    _, req = selected(tmp_path)
    directory = tmp_path / "shared"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    with pytest.raises(ContractError, match="owned and private"):
        module.retain_frozen_layer(req, directory / "layer.gz")
