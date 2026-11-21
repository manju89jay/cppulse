"""Reject producer-noncanonical regular names without weakening directory support."""

import gzip
import hashlib
import io
import tarfile
import pytest
from cppulse.errors import ContractError
from cppulse import frozen_layer as module
from test_frozen_input_inventory import selected


def test_regular_pax_path_trailing_slash_is_outside_producer_profile(tmp_path):
    _, request = selected(tmp_path)
    path = tmp_path / "layer.gz"
    capture = module.retain_frozen_layer(request, path)
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:", format=tarfile.PAX_FORMAT) as archive:
        for row in capture["entries"]:
            member = tarfile.TarInfo(row["path"].lstrip("/"))
            member.uid = member.gid = 1000
            member.mode = row["mode"]
            member.mtime = row["mtime_ns"] // 10**9
            member.pax_headers = {"mtime": module._format_ns(row["mtime_ns"])}
            if row["kind"] == "directory":
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
            else:
                data = b"int a;\n"
                member.size = len(data)
                member.pax_headers["path"] = member.name + "////"
                archive.addfile(member, io.BytesIO(data))
    raw = stream.getvalue()
    compressed = gzip.compress(raw, mtime=0)
    path.write_bytes(compressed)
    capture["raw_layer"] = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }
    capture["compressed_layer"] = {
        "sha256": hashlib.sha256(compressed).hexdigest(),
        "size_bytes": len(compressed),
    }
    with pytest.raises(ContractError):
        module.verify_frozen_layer(capture, path, request=request)


def test_actual_long_directory_pax_path_still_verifies(tmp_path):
    source, request = selected(tmp_path)
    directory = source / ("a" * 120)
    directory.mkdir()
    (directory / "b.cpp").write_bytes(b"int b;\n")
    path = tmp_path / "layer.gz"
    capture = module.retain_frozen_layer(request, path)
    module.verify_frozen_layer(capture, path, request=request)
