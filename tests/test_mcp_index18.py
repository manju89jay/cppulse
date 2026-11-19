"""Explicit opt-in MCP query cache; original store remains read-only."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from cppulse.errors import ContractError
from cppulse.mcp_server import Reader
from cppulse.run_store import RunStore
from test_mcp_server import call, init, value
from test_result_index import finding, source


def files(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def session(root, cache, requests, extra=None):
    command = [sys.executable, "-m", "cppulse.mcp_server", "--store", str(root)]
    if cache is not None:
        command += ["--query-cache", str(cache)]
    command += extra or []
    result = subprocess.run(
        command,
        input="\n".join(json.dumps(p) for p in requests) + "\n",
        text=True,
        capture_output=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "python")},
    )
    return result, [json.loads(p) for p in result.stdout.splitlines()]


def test_explicit_tool_advertisement_does_not_create_cache(tmp_path):
    store, snapshot, _ = source(tmp_path)
    cache = tmp_path / "cache"
    before = files(store.root)
    listing = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    result, replies = session(store.root, cache, [init(), listing])
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "indexed_findings" in {t["name"] for t in replies[-1]["result"]["tools"]}
    assert not cache.exists() and files(store.root) == before
    result, replies = session(store.root, None, [init(), listing])
    assert result.returncode == 0
    assert "indexed_findings" not in {t["name"] for t in replies[-1]["result"]["tools"]}


@pytest.mark.parametrize("version", ["2.0.0", "3.0.0"])
def test_actual_stdio_selected_artifact_pages_filters_and_reuse(tmp_path, version):
    store, snapshot, _ = source(
        tmp_path,
        [finding(), finding(message="second"), finding()],
        format_version=version,
    )
    cache = tmp_path / "cache"
    before = files(store.root)
    pin = {
        "run_id": snapshot.run_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "artifact_id": "report",
    }
    result, replies = session(
        store.root,
        cache,
        [
            init(),
            call("indexed_findings", {**pin, "page": 2, "per_page": 1}),
            call(
                "indexed_findings",
                {**pin, "text": "literal % _", "per_page": 1, "page": 2},
            ),
        ],
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    first, second = value(replies[1]), value(replies[2])
    assert first["items"] == [finding(message="second")]
    assert first["total"] == 3 and first["page"] == 2
    assert second["items"] == [finding()] and second["total"] == 2
    assert first["index"] == second["index"]
    assert first["source"]["run_id"] == snapshot.run_id
    assert first["selection"] == "historical-pinned"
    assert first["current_source_verified"] is False
    assert (
        first["read_scope"] == "selected_artifact_only"
        and first["analysis_cache_eligible"] is False
    )
    assert cache.is_dir() and files(store.root) == before


def test_index_tool_never_opens_original_full_snapshot(tmp_path, monkeypatch):
    store, snapshot, _ = source(tmp_path)
    original = RunStore.open_run

    def checked(self, *args, **kwargs):
        assert self.root != store.root
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RunStore, "open_run", checked)
    reader = Reader(store.root, query_cache_root=tmp_path / "cache")
    result = reader.call(
        "indexed_findings",
        {
            "run_id": snapshot.run_id,
            "manifest_sha256": snapshot.manifest_sha256,
            "artifact_id": "report",
        },
    )
    assert result["total"] == 2 and result["items"] == [finding(), finding()]


@pytest.mark.parametrize(
    "bad",
    [
        {"run_id": "../escape"},
        {"run_id": "original\n"},
        {"manifest_sha256": "A" * 64},
        {"page": True},
        {"page": 1.0},
        {"page": 2**63},
        {"page": 2**63 - 1, "per_page": 100},
        {"per_page": 101},
        {"text": "\0"},
        {"text": "é" * 2049},
        {"text": "\ud800"},
        {"artifact_id": "report\n"},
        {"shell": "true"},
        {"assessment_artifact_id": "assessment"},
    ],
)
def test_invalid_args_refuse_before_cache_action(tmp_path, bad):
    store, snapshot, _ = source(tmp_path)
    cache = tmp_path / "cache"
    reader = Reader(store.root, query_cache_root=cache)
    with pytest.raises(ContractError):
        reader.call(
            "indexed_findings",
            {
                "run_id": snapshot.run_id,
                "manifest_sha256": snapshot.manifest_sha256,
                "artifact_id": "report",
                **bad,
            },
        )
    assert not cache.exists()


def test_default_reader_refuses_index_tool_without_writing(tmp_path):
    store, snapshot, _ = source(tmp_path)
    before = files(store.root)
    with pytest.raises(ContractError):
        Reader(store.root).call(
            "indexed_findings",
            {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256},
        )
    assert files(store.root) == before


@pytest.mark.parametrize(
    "relative", [".", ".query-index", "runs/new", "../original/query"]
)
def test_cache_inside_original_store_is_refused(tmp_path, relative):
    store, _, _ = source(tmp_path)
    before = files(store.root)
    with pytest.raises(ContractError):
        Reader(store.root, query_cache_root=store.root / relative)
    assert files(store.root) == before


def test_incomplete_and_corrupt_source_never_publishes_cache(tmp_path):
    store, snapshot, _ = source(tmp_path)
    manifest = snapshot.manifest
    manifest["status"] = "partial"
    from cppulse.identities import canonical_json_bytes

    raw = canonical_json_bytes(manifest)
    (snapshot.path / "run_manifest.json").write_bytes(raw)
    cache = tmp_path / "cache"
    reader = Reader(store.root, query_cache_root=cache)
    with pytest.raises(ContractError):
        reader.call(
            "indexed_findings",
            {
                "run_id": snapshot.run_id,
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "artifact_id": "report",
            },
        )
    assert not cache.exists()


@pytest.mark.parametrize(
    "raw", ["{}", "[]", "null", '{"max_rows":1,"max_rows":2}', "NaN", "x" * 4097]
)
def test_bad_explicit_cli_limits_refuse_without_cache(tmp_path, raw):
    store, _, _ = source(tmp_path)
    cache = tmp_path / "cache"
    result, _ = session(store.root, cache, [], extra=["--query-limits", raw])
    assert result.returncode == 2
    assert not cache.exists()


def test_bounded_framed_reply_with_large_raw_finding(tmp_path):
    store, snapshot, _ = source(tmp_path, [finding(message='"\\\t\n' * 32768)])
    result, replies = session(
        store.root,
        tmp_path / "cache",
        [
            init(),
            call(
                "indexed_findings",
                {
                    "run_id": snapshot.run_id,
                    "manifest_sha256": snapshot.manifest_sha256,
                    "artifact_id": "report",
                },
            ),
        ],
    )
    assert result.returncode == 0, result.stderr
    assert max(len(line.encode()) for line in result.stdout.splitlines()) <= 524288
    assert replies[-1].get("error") or replies[-1].get("result", {}).get(
        "isError"
    ), "Oversized result must not become a partial successful page"
