"""Actual stdio MCP client checks over synthetic shared snapshot contracts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from cppulse.presentation import build_snapshot_view
from test_presentation import publish_snapshot


def session(root: Path, requests: list[dict | str]) -> list[dict]:
    """Connect an actual subprocess client using newline-framed JSON-RPC."""
    payload = "\n".join(x if isinstance(x, str) else json.dumps(x) for x in requests)
    result = subprocess.run(
        [sys.executable, "-m", "cppulse.mcp_server", "--store", str(root)],
        input=payload + "\n",
        text=True,
        capture_output=True,
        timeout=20,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "python")},
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return [json.loads(line) for line in result.stdout.splitlines()]


def init() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pytest-client", "version": "1"},
        },
    }


def call(name: str, arguments: dict, identifier: int = 2) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def value(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


@pytest.mark.parametrize("gate", ["passed", "failed", "insufficient_evidence"])
def test_actual_client_shares_gate_pins_and_no_writes(
    tmp_path: Path, gate: str
) -> None:
    snapshot = publish_snapshot(tmp_path, gate=gate, legacy=True)
    root = tmp_path / "store"
    before = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    replies = session(
        root,
        [
            init(),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
            call("run_status", pin),
            call("health", pin),
            call("policy_gaps", pin),
        ],
    )
    assert replies[0]["result"]["protocolVersion"] == "2024-11-05"
    assert set(t["name"] for t in replies[1]["result"]["tools"]) == {
        "run_status",
        "health",
        "findings",
        "hotspots",
        "policy_gaps",
        "documentation",
        "artifact",
    }
    view = build_snapshot_view(snapshot)
    assert value(replies[2])["run"] == view["run"]
    assert value(replies[3])["assessment"] == view["assessment"]["display"]
    assert value(replies[4])["items"] == view["gaps"]
    assert {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    } == before


def test_invalid_pins_tools_paths_and_oversized_arguments(tmp_path: Path) -> None:
    snapshot = publish_snapshot(tmp_path)
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    bad = [
        call("health", {**pin, "manifest_sha256": "0" * 64}),
        call("execute", pin),
        call("artifact", {**pin, "artifact_id": "../../secret"}),
        call("findings", {**pin, "limit": 101}),
        call("health", {**pin, "shell": "true"}),
    ]
    replies = session(tmp_path / "store", [init(), *bad])
    assert all(r["result"]["isError"] for r in replies[1:])


def test_artifact_original_hash_and_chunk_bounds(tmp_path: Path) -> None:
    snapshot = publish_snapshot(tmp_path)
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    replies = session(
        tmp_path / "store",
        [
            init(),
            call(
                "artifact",
                {**pin, "artifact_id": "selected-assessment", "offset": 0, "limit": 17},
            ),
        ],
    )
    data = value(replies[1])
    raw = snapshot.read_bytes("selected-assessment")
    assert data["sha256"] == hashlib.sha256(raw).hexdigest()
    assert data["text"].encode() == raw[:17]
    assert data["next_offset"] == 17


def test_protocol_errors_and_notifications_do_not_corrupt_stream(
    tmp_path: Path,
) -> None:
    publish_snapshot(tmp_path)
    replies = session(
        tmp_path / "store",
        [
            "{broken",
            {"jsonrpc": "2.0", "id": 9, "method": "tools/list"},
            init(),
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 1},
            },
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        ],
    )
    assert replies[0]["error"]["code"] == -32700
    assert replies[1]["error"]["code"] == -32002
    assert replies[-1] == {"jsonrpc": "2.0", "id": 7, "result": {}}


def test_unknown_protocol_rejected_and_rule_docs_available(tmp_path: Path) -> None:
    publish_snapshot(tmp_path)
    wrong = init()
    wrong["params"]["protocolVersion"] = "unknown"
    replies = session(
        tmp_path / "store",
        [wrong, init(), call("documentation", {"kind": "rule", "id": "CPP-MEM-001"})],
    )
    assert replies[0]["error"]["code"] == -32602
    assert value(replies[-1])["document"]["id"] == "CPP-MEM-001"


def test_tampered_artifact_never_becomes_clean_tool_output(tmp_path: Path) -> None:
    snapshot = publish_snapshot(tmp_path)
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    selected = snapshot.path / "assessment/selected.json"
    selected.write_bytes(selected.read_bytes() + b" ")
    replies = session(tmp_path / "store", [init(), call("health", pin)])
    assert replies[-1]["result"]["isError"] is True
    assert "INTEGRITY_ERROR" in replies[-1]["result"]["content"][0]["text"]


def test_policy_document_is_original_retained_policy(tmp_path: Path) -> None:
    snapshot = publish_snapshot(tmp_path)
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    replies = session(
        tmp_path / "store",
        [
            init(),
            call("documentation", {**pin, "kind": "policy", "id": "policy"}),
            call(
                "documentation", {**pin, "kind": "policy", "id": "selected-assessment"}
            ),
        ],
    )
    assert value(replies[1])["document"] == snapshot.read_json("policy")
    assert replies[2]["result"]["isError"] is True


def test_oversized_frame_drained_then_valid_request_succeeds(tmp_path: Path) -> None:
    publish_snapshot(tmp_path)
    replies = session(tmp_path / "store", [" " * 70000, init()])
    assert replies[0]["error"]["code"] == -32600
    assert replies[1]["result"]["protocolVersion"] == "2024-11-05"


def test_paged_gaps_preserve_pin_and_index(tmp_path: Path) -> None:
    snapshot = publish_snapshot(tmp_path, gate="insufficient_evidence")
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    replies = session(
        tmp_path / "store",
        [
            init(),
            call("policy_gaps", {**pin, "offset": 0, "limit": 1}),
            call("policy_gaps", {**pin, "offset": 1, "limit": 1}),
        ],
    )
    expected = build_snapshot_view(snapshot)["gaps"]
    assert value(replies[1])["items"] == expected[:1]
    assert value(replies[2])["items"] == expected[1:2]
    assert value(replies[1])["manifest_sha256"] == snapshot.manifest_sha256
    assert value(replies[1])["next_offset"] == 1


def test_shared_reader_total_payload_budget_and_compatible_default(
    tmp_path: Path,
) -> None:
    from cppulse.errors import ContractError, IntegrityError
    from cppulse.run_store import RunStore

    snapshot = publish_snapshot(tmp_path)
    store = RunStore.open_existing(tmp_path / "store")
    total = len(snapshot.read_manifest_bytes()) + sum(
        entry["size_bytes"] for entry in snapshot.manifest["artifacts"]
    )
    assert (
        store.open_run(snapshot.run_id, max_snapshot_bytes=total).run_id
        == snapshot.run_id
    )
    assert store.open_run(snapshot.run_id).run_id == snapshot.run_id
    with pytest.raises(IntegrityError, match="total read byte limit"):
        store.open_run(snapshot.run_id, max_snapshot_bytes=total - 1)
    with pytest.raises(IntegrityError, match="read byte limit"):
        store.open_run(snapshot.run_id, max_snapshot_bytes=1)
    for invalid in [0, -1, True, "100"]:
        with pytest.raises(ContractError, match="positive integer"):
            store.open_run(snapshot.run_id, max_snapshot_bytes=invalid)


def test_shared_reader_actual_growth_enforces_bounded_read(tmp_path: Path) -> None:
    from cppulse.errors import IntegrityError
    from cppulse.run_store import RunStore

    snapshot = publish_snapshot(tmp_path)
    total = len(snapshot.read_manifest_bytes()) + sum(
        entry["size_bytes"] for entry in snapshot.manifest["artifacts"]
    )
    bounded = RunStore.open_existing(tmp_path / "store").open_run(
        snapshot.run_id, max_snapshot_bytes=total
    )
    (snapshot.path / "assessment/selected.json").write_bytes(b" " * (total + 1))
    with pytest.raises(IntegrityError, match="read byte limit"):
        bounded.read_bytes("selected-assessment")


def test_normalized_findings_preserve_occurrences_and_context(tmp_path: Path) -> None:
    from cppulse.run_store import RunStore
    from test_contracts_v2 import manifest_document, source_document

    source = source_document()
    rows = [
        {
            "id": f"finding-{index}",
            "producer": {"name": "cppulse", "version": "0.2"},
            "rule_id": "cppulse:CPP-MOD-001",
            "rule_version": "1",
            "file": "src/main.cpp",
            "context_id": "gcc17",
            "line": index + 1,
            "severity": "warning",
            "message": "Synthetic duplicate rule occurrence",
            "fingerprint": str(index) * 64,
            "fingerprint_version": "1",
            "evidence_ids": [],
        }
        for index in range(2)
    ]
    with RunStore(tmp_path / "store").begin("normalized") as stage:
        stage.write_json(
            "observations.json",
            {"version": "2.0.0", "source_digest": source["digest"], "items": rows},
            artifact_id="observations",
            contract="observations",
        )
        manifest = manifest_document()
        manifest.update(run_id="normalized", artifacts=stage.artifacts)
        snapshot = stage.publish(manifest)
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    replies = session(tmp_path / "store", [init(), call("findings", pin)])
    assert value(replies[1])["items"] == rows
    assert value(replies[1])["availability"] == "stored-observations"


def test_deeply_nested_request_fails_without_killing_session(tmp_path: Path) -> None:
    publish_snapshot(tmp_path)
    replies = session(tmp_path / "store", ["[" * 2000 + "0" + "]" * 2000, init()])
    # A parser may reject nesting first; otherwise an array is an invalid RPC request.
    assert replies[0]["error"]["code"] in {-32700, -32600}
    assert replies[1]["result"]["protocolVersion"] == "2024-11-05"


def test_measured_health_copies_exact_stored_document_and_hash(tmp_path: Path) -> None:
    from cppulse.analysis import persist_native_analysis
    from cppulse.maintenance import persist_maintenance_health
    from cppulse.tooling import load_rule_registry
    from test_analysis_inventory import native_snapshot
    from test_measured_normalization import add_metrics

    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    selection["requested_rules"] = [row["id"] for row in load_rule_registry()["rules"]]
    normalized = persist_native_analysis(
        snapshot, workspace=tmp_path, store=tmp_path / "store", **selection
    )
    measured = persist_maintenance_health(
        normalized,
        workspace=tmp_path,
        store=tmp_path / "store",
        required_context_ids=["native", "missing-required"],
    )
    view = build_snapshot_view(measured)
    expected = [
        {
            "artifact_id": fact["artifact_id"],
            "sha256": fact["sha256"],
            "document": json.loads(fact["raw_json"]),
        }
        for fact in view["facts"]
        if fact["kind"] == "maintenance_health"
    ]
    assert len(expected) == 1
    assert expected[0]["document"]["aggregate"]["overall"] is None
    replies = session(
        tmp_path / "store",
        [
            init(),
            call(
                "health",
                {
                    "run_id": measured.run_id,
                    "manifest_sha256": measured.manifest_sha256,
                },
            ),
        ],
    )
    assert value(replies[1])["measured_health"] == expected


def test_hotspot_method_and_unavailable_scope_match_retained_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import test_presentation as fixtures

    original = fixtures.legacy_documents
    scope = {
        "status": "unavailable",
        "declared_files": 1,
        "measured_files": 0,
        "unavailable_files": [
            {"file": "a.cpp", "reason": "Native metrics unavailable."}
        ],
    }

    def documents() -> dict:
        result = original()
        result["risk_scores"]["metadata"].update(
            hotspot_method="measured-cc-physical-kloc-v1", hotspot_scope=scope
        )
        return result

    monkeypatch.setattr(fixtures, "legacy_documents", documents)
    snapshot = fixtures.publish_snapshot(tmp_path, legacy=True)
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    result = value(session(tmp_path / "store", [init(), call("hotspots", pin)])[1])
    assert result["items"] == []
    assert result["method"] == "measured-cc-physical-kloc-v1"
    assert result["scope"] == scope
