"""Distinct declared roots must not collapse into one actual tar namespace."""

import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import pytest
from cppulse.contracts.frozen_input import validate_frozen_input
from cppulse.errors import ContractError
from cppulse.frozen_layer import retain_frozen_layer, verify_frozen_layer
from cppulse.identities import canonical_json_bytes
from test_frozen_input_contract import request


@pytest.mark.parametrize(
    "field", ["container_root", "source_root", "cwd", "executable", "client"]
)
def test_double_leading_slash_is_not_canonical_input(field):
    req = request()
    if field in {"container_root", "source_root"}:
        req["path_map"][0][field] = "//" + req["path_map"][0][field].lstrip("/")
    elif field == "cwd":
        req["invocation"]["cwd"] = "//input"
    elif field == "executable":
        req["invocation"]["argv"][0] = "//runtime/native"
    else:
        req["client"]["path"] = "//usr/bin/docker"
    with pytest.raises(ContractError):
        validate_frozen_input("request", req)


def test_two_actual_roots_cannot_verify_duplicate_tar_namespace(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "same.cpp").write_bytes(b"int first;\n")
    (second / "same.cpp").write_bytes(b"int second;\n")
    req = request()
    req["path_map"] = [
        {"source_root": str(first), "container_root": "/input"},
        {"source_root": str(second), "container_root": "//input"},
    ]
    artifact = tmp_path / "layer.tar.gz"
    try:
        capture = retain_frozen_layer(req, artifact)
        verify_frozen_layer(capture, artifact, request=req)
    except ContractError:
        return
    with tarfile.open(
        fileobj=io.BytesIO(gzip.decompress(artifact.read_bytes())), mode="r:"
    ) as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        contents = [
            {
                "name": member.name,
                "sha256": hashlib.sha256(
                    archive.extractfile(member).read()
                ).hexdigest(),
            }
            for member in members
            if member.isfile()
        ]
        last_lookup = archive.extractfile("input/same.cpp").read().decode()
    proof = {
        "request_sha256": hashlib.sha256(canonical_json_bytes(req)).hexdigest(),
        "capture": capture,
        "actual_tar_names": names,
        "actual_tar_file_content_sha256": contents,
        "standard_tar_last_lookup": last_lookup,
        "consumer_accepted": True,
        "qualification": "Two real source directories and distinct declared POSIX roots; no Docker or extraction required. Tar duplicate member names cannot represent two distinct retained destinations.",
    }
    (tmp_path / "collision-proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    assert len(set(names)) == len(
        names
    ), "Distinct declared /input and //input collapsed into duplicate actual tar member names"
