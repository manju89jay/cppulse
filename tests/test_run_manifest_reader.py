"""Exact original manifest-byte reads for checked presentation, not JSON rewrites."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cppulse.errors import IntegrityError
from cppulse.run_store import RunStore
from test_run_store_v2 import publish


def test_manifest_reader_preserves_original_noncanonical_bytes_and_pin(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    initial = publish(store, "synthetic-transport")
    # A valid explicitly pinned fixture can contain a different JSON layout.
    # Reconstruction from the parsed manifest must not replace its actual bytes.
    content = json.dumps(initial.manifest, separators=(",", ":")).encode() + b"\n\n"
    path = initial.path / "run_manifest.json"
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    snapshot = store.open_run(initial.run_id, manifest_sha256=expected)
    (store.root / "latest.json").write_text("unrelated malformed pointer")
    assert snapshot.read_manifest_bytes() == content
    assert hashlib.sha256(snapshot.read_manifest_bytes()).hexdigest() == expected


def test_manifest_reader_rejects_same_size_corruption(tmp_path: Path) -> None:
    snapshot = publish(
        RunStore(tmp_path / "store", format_version="2.0.0"), "synthetic-transport"
    )
    path = snapshot.path / "run_manifest.json"
    content = path.read_bytes()
    altered = content.replace(b"source", b"sourcx", 1)
    assert altered != content and len(altered) == len(content)
    path.write_bytes(altered)
    with pytest.raises(IntegrityError, match="manifest changed"):
        snapshot.read_manifest_bytes()


def test_manifest_reader_returns_the_single_checked_read_without_reopening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse import run_store

    snapshot = publish(
        RunStore(tmp_path / "store", format_version="2.0.0"), "synthetic-transport"
    )
    path = snapshot.path / "run_manifest.json"
    original_read = run_store._read
    expected = path.read_bytes()
    reads = []

    def read_then_replace(selected: Path) -> bytes:
        reads.append(selected)
        content = original_read(selected)
        selected.write_bytes(b"{}\n")
        return content

    monkeypatch.setattr(run_store, "_read", read_then_replace)
    assert snapshot.read_manifest_bytes() == expected
    assert reads == [path]
    assert path.read_bytes() == b"{}\n"


def test_manifest_reader_uses_existing_no_symlink_guard(tmp_path: Path) -> None:
    snapshot = publish(
        RunStore(tmp_path / "store", format_version="2.0.0"), "synthetic-transport"
    )
    path = snapshot.path / "run_manifest.json"
    outside = tmp_path / "copied-manifest.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(IntegrityError):
        snapshot.read_manifest_bytes()
