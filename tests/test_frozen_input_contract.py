"""Finite frozen namespace contracts cannot confer cache eligibility."""

from copy import deepcopy
import hashlib

import pytest

from cppulse.contracts.frozen_input import (
    load_frozen_input,
    validate_frozen_bundle,
    validate_frozen_input,
)
from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes


def manifest():
    return {
        "version": "0.1.0",
        "cache_eligible": False,
        "closure": "unqualified",
        "request_sha256": "a" * 64,
        "entries": [
            {
                "path": "/input",
                "kind": "directory",
                "mode": 365,
                "mtime_ns": 0,
                "source_root": "/host/project",
                "source_relative": ".",
                "content": None,
                "target": None,
            },
            {
                "path": "/input/a.cpp",
                "kind": "regular",
                "mode": 292,
                "mtime_ns": 0,
                "source_root": "/host/project",
                "source_relative": "a.cpp",
                "content": {"sha256": "b" * 64, "size_bytes": 1},
                "target": None,
            },
        ],
        "layer": {"sha256": "c" * 64, "size_bytes": 4096},
        "config": {"sha256": "d" * 64, "size_bytes": 128},
    }


def request():
    return {
        "version": "0.1.0",
        "cache_eligible": False,
        "closure": "unqualified",
        "original_request_sha256": "a" * 64,
        "native": {"sha256": "b" * 64, "size_bytes": 1},
        "client": {"path": "/usr/bin/docker", "sha256": "d" * 64, "size_bytes": 1},
        "runtime_manifest_sha256": "c" * 64,
        "platform": "linux-x86_64",
        "path_map": [{"source_root": "/host/project", "container_root": "/input"}],
        "invocation": {
            "argv": ["/runtime/native", "--input", "/input"],
            "cwd": "/input",
            "environment": {"LANG": "C"},
        },
        "limits": {
            "wall_seconds": 10,
            "max_stream_bytes": 4096,
            "max_entries": 100,
            "max_payload_bytes": 1000000,
        },
    }


def test_actual_namespace_manifest_and_explicit_request_validate():
    validate_frozen_input("manifest", manifest())
    validate_frozen_input("request", request())
    assert load_frozen_input("request", canonical_json_bytes(request())) == request()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"version":"0.1.0","version":"0.1.0"}',
        b'{"version":"\\ud800"}',
        b'{"version":"\xff"}',
        b"[]",
        b"[" * 2000 + b"]" * 2000,
        b" " * (8 * 1024**2 + 1),
    ],
)
def test_raw_documents_cannot_hide_duplicate_or_invalid_json(raw):
    with pytest.raises(ContractError):
        load_frozen_input("request", raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cache_eligible", True),
        ("closure", "qualified"),
        ("version", "0.2.0"),
        ("unknown", True),
        ("entries", []),
    ],
)
def test_no_authority_or_silent_protocol_widening(field, value):
    doc = manifest()
    doc[field] = value
    with pytest.raises(ContractError):
        validate_frozen_input("manifest", doc)


@pytest.mark.parametrize(
    "change",
    [
        lambda rows: rows.reverse(),
        lambda rows: rows.append(deepcopy(rows[-1])),
        lambda rows: rows[1].update(path="/input/../escape"),
        lambda rows: rows[1].update(path="//input/a.cpp"),
        lambda rows: rows[1].update(content=None),
        lambda rows: rows[0].update(target="a.cpp"),
        lambda rows: rows[1].update(kind="symlink", content=None, target="../outside"),
        lambda rows: rows[0].update(kind="symlink", target="other"),
        lambda rows: rows[1].update(source_relative="/absolute"),
        lambda rows: rows[1].update(mtime_ns=-1),
    ],
)
def test_malformed_or_ambiguous_namespace_fails(change):
    doc = manifest()
    change(doc["entries"])
    with pytest.raises(ContractError):
        validate_frozen_input("manifest", doc)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["path_map"].append(
            {"source_root": "/other", "container_root": "/input/nested"}
        ),
        lambda d: d.update(path_map=[]),
        lambda d: d["invocation"].update(cwd="relative"),
        lambda d: d["invocation"].update(argv=["/runtime/native", "nul\x00"]),
        lambda d: d["invocation"].update(environment={"ACCESS_TOKEN": "secret"}),
        lambda d: d["invocation"].update(environment={"LANG": "é" * 4096}),
        lambda d: d["limits"].update(max_payload_bytes=2**40),
    ],
)
def test_request_cannot_expand_unsafe_runtime_boundary(change):
    doc = request()
    change(doc)
    with pytest.raises(ContractError):
        validate_frozen_input("request", doc)


def bundle():
    req, doc = request(), manifest()
    req["invocation"]["argv"] = ["/input/a.cpp"]
    doc["request_sha256"] = hashlib.sha256(canonical_json_bytes(req)).hexdigest()
    pin = {"sha256": "f" * 64, "size_bytes": 0}
    report = {
        "version": "0.1.0",
        "cache_eligible": False,
        "closure": "unqualified",
        "request_sha256": doc["request_sha256"],
        "manifest_sha256": hashlib.sha256(canonical_json_bytes(doc)).hexdigest(),
        "image_id": "sha256:" + "1" * 64,
        "container_id": "2" * 64,
        "frozen_filesystem_observed": False,
        "unresolved_inputs": ["clock", "host_cpu", "implicit_mounts"],
        "client_receipts": [],
        "native_receipt": None,
        "inspect": pin,
        "diff": pin,
    }
    return req, doc, report


def test_bundle_binds_original_request_manifest_and_unobserved_report():
    validate_frozen_bundle(*bundle())


@pytest.mark.parametrize(
    "change",
    [
        lambda q, m, r: m.update(request_sha256="e" * 64),
        lambda q, m, r: m["entries"][1].update(source_relative="other.cpp"),
        lambda q, m, r: m["entries"][1].update(source_root="/undeclared"),
        lambda q, m, r: m["entries"][1]["content"].update(sha256="f" * 64),
        lambda q, m, r: m["entries"].pop(0),
        lambda q, m, r: r.update(manifest_sha256="e" * 64),
        lambda q, m, r: r.update(frozen_filesystem_observed=True),
    ],
)
def test_bundle_rejects_forged_namespace_and_observation(change):
    req, doc, report = bundle()
    change(req, doc, report)
    with pytest.raises(ContractError):
        validate_frozen_bundle(req, doc, report)


def test_inside_native_receipt_cannot_be_docker_client_or_host_invocation():
    req, doc, report = bundle()
    pin = {"sha256": "f" * 64, "size_bytes": 0}
    report["native_receipt"] = {
        "invocation": deepcopy(req["invocation"]),
        "exit_status": 0,
        "stdout": pin,
        "stderr": pin,
    }
    validate_frozen_bundle(req, doc, report)
    report["native_receipt"]["invocation"]["argv"] = ["/usr/bin/docker", "run"]
    with pytest.raises(ContractError, match="Inside native"):
        validate_frozen_bundle(req, doc, report)


def test_observation_receipt_client_identity_is_explicit():
    req, doc, report = bundle()
    pin = {"sha256": "f" * 64, "size_bytes": 0}
    report["client_receipts"] = [
        {
            "argv": ["/wrong/docker", "inspect"],
            "exit_status": 0,
            "stdout": pin,
            "stderr": pin,
        }
    ]
    with pytest.raises(ContractError, match="selected client"):
        validate_frozen_bundle(req, doc, report)
