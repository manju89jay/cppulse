"""Independent actual archive byte/metadata verification controls."""

from copy import deepcopy
import gzip
import hashlib
import os
import stat

import pytest

from cppulse.errors import ContractError
from test_frozen_input_inventory import selected
from cppulse import frozen_layer as module


def test_actual_candidate_retained_layer_passes_independent_consumer(tmp_path):
    _, req = selected(tmp_path)
    path = tmp_path / "layer.gz"
    result = module.retain_frozen_layer(req, path)
    module.verify_frozen_layer(result, path, request=req)
    assert path.with_name(path.name + ".partial").stat().st_ino == path.stat().st_ino
    assert path.stat().st_nlink == 2


@pytest.mark.parametrize("field", ["bytes", "mtime", "mode", "path", "size", "closure"])
def test_pinned_artifact_does_not_validate_forged_expected_metadata(tmp_path, field):
    _, req = selected(tmp_path)
    path = tmp_path / "layer.gz"
    result = module.retain_frozen_layer(req, path)
    bad = deepcopy(result)
    if field == "bytes":
        bad["entries"][1]["content"]["sha256"] = "e" * 64
    elif field == "mtime":
        bad["entries"][1]["mtime_ns"] += 1
    elif field == "mode":
        bad["entries"][1]["mode"] ^= 1
    elif field == "path":
        bad["entries"][1]["path"] = "/input/b.cpp"
    elif field == "size":
        bad["entries"][1]["content"]["size_bytes"] += 1
    else:
        bad["closure"] = "qualified"
    with pytest.raises(ContractError):
        module.verify_frozen_layer(bad, path, request=req)


def test_changed_archive_even_with_rebound_raw_and_compressed_hashes_fails_contents(
    tmp_path,
):
    _, req = selected(tmp_path)
    path = tmp_path / "layer.gz"
    result = module.retain_frozen_layer(req, path)
    raw = gzip.decompress(path.read_bytes()).replace(b"int a;\n", b"int b;\n")
    path.write_bytes(gzip.compress(raw, mtime=0))
    result["raw_layer"] = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }
    result["compressed_layer"] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }
    with pytest.raises(ContractError, match="member bytes"):
        module.verify_frozen_layer(result, path, request=req)


def test_failure_after_final_link_preserves_verified_partial_and_removes_owned_final(
    tmp_path, monkeypatch
):
    _, req = selected(tmp_path)
    path = tmp_path / "layer.gz"
    original = os.fsync
    failed = False

    def fsync(fd):
        nonlocal failed
        if stat.S_ISDIR(os.fstat(fd).st_mode) and not failed:
            failed = True
            raise OSError("injected first directory fsync failure")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(OSError):
        module.retain_frozen_layer(req, path)
    assert failed
    assert not path.exists()
    assert path.with_name(path.name + ".partial").exists()


def test_missing_proc_support_is_unqualified_and_keeps_only_partial(
    tmp_path, monkeypatch
):
    _, req = selected(tmp_path)
    path = tmp_path / "layer.gz"
    original = os.path.exists
    monkeypatch.setattr(
        os.path,
        "exists",
        lambda p: False if str(p).startswith("/proc/self/fd/") else original(p),
    )
    with pytest.raises(ContractError, match="Linux procfs"):
        module.retain_frozen_layer(req, path)
    assert not path.exists()
    assert path.with_name(path.name + ".partial").exists()


def test_ambient_decimal_context_cannot_round_archive_nanoseconds(tmp_path):
    from decimal import localcontext
    import tarfile

    root, req = selected(tmp_path)
    precise = 1800000000123456789
    os.utime(root / "a.cpp", ns=(precise, precise))
    path = tmp_path / "layer.gz"
    with localcontext() as context:
        context.prec = 6
        result = module.retain_frozen_layer(req, path)
    with tarfile.open(path, "r:gz") as archive:
        timestamp = archive.getmember("input/a.cpp").pax_headers["mtime"]
    seconds, dot, fractional = timestamp.partition(".")
    recovered = int(seconds) * 10**9 + int(fractional.ljust(9, "0") if dot else "0")
    assert recovered == precise
    module.verify_frozen_layer(result, path, request=req)


def test_consumer_binds_original_selected_request_not_just_archive_shape(tmp_path):
    _, req = selected(tmp_path)
    path = tmp_path / "layer.gz"
    result = module.retain_frozen_layer(req, path)
    changed = deepcopy(req)
    changed["invocation"]["environment"]["TZ"] = "UTC"
    with pytest.raises(ContractError, match="original selected request"):
        module.verify_frozen_layer(result, path, request=changed)
