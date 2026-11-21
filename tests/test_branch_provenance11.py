"""Explicit mocked Git packets test agreement, never producer authentication."""

from __future__ import annotations

import hashlib

import pytest

from cppulse import branch_delivery as candidate
from cppulse.errors import ContractError
from cppulse.identities import digest_json


def packet() -> tuple[dict, dict]:
    sha = "a" * 40
    cfg = {
        "version": "1.0.0",
        "id": "scope",
        "target_ref_id": "main",
        "refs": [{"id": "main", "ref": "refs/heads/main", "expected_tip": sha}],
        "window_start": "2026-01-01T00:00:00Z",
        "cutoff": "2026-01-04T00:00:00Z",
        "delivery_inventory_complete": True,
        "tasks": [],
        "deliveries": [],
        "limits": {
            "max_commits": 10,
            "max_output_bytes": 4096,
            "command_timeout_seconds": 5,
            "total_timeout_seconds": 30,
        },
    }
    tool = "/usr/bin/git"
    repo = "/selected/project"
    prefix = [
        tool,
        "--no-pager",
        "--no-replace-objects",
        "--no-optional-locks",
        "--no-lazy-fetch",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "gc.auto=0",
        "-c",
        "maintenance.auto=false",
        "-c",
        "protocol.allow=never",
        "-C",
        repo,
    ]

    def command(arguments: list[str], raw: bytes) -> dict:
        return {
            "argv": arguments,
            "status": "passed",
            "returncode": 0,
            "wall_seconds": 0.01,
            "stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "stdout_bytes": len(raw),
            "stderr_bytes": 0,
            "captured_bytes": len(raw),
            "truncated": False,
            "stderr_tail": "",
        }

    probe = ["rev-parse", "--verify", "--end-of-options", "refs/heads/main^{commit}"]
    raw = f"1767225600 {sha}\n"
    capture = {
        "version": "1.0.0",
        "configuration_digest": digest_json(cfg),
        "repo_path": repo,
        "observed_at": "2026-01-04T00:00:00Z",
        "tool": {
            "path": tool,
            "version": "git version 2.52.0",
            "sha256_before": "1" * 64,
            "sha256_after": "1" * 64,
            "stable": True,
        },
        "refs": [
            {
                **cfg["refs"][0],
                "observed_tip": sha,
                "status": "matched",
                "reason": "Explicit authored pin",
            }
        ],
        "nodes": [{"id": sha, "committed_at": 1767225600, "parents": []}],
        "raw_graph": raw,
        "raw_graph_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "shallow": False,
        "truncated": False,
        "graph_command_complete": True,
        "limitations": [],
        "commands": [
            command([tool, "--version"], b"git version 2.52.0\n"),
            command(prefix + ["rev-parse", "--is-shallow-repository"], b"false\n"),
            command(prefix + probe, (sha + "\n").encode()),
            command(
                prefix
                + [
                    "rev-list",
                    "--topo-order",
                    "--timestamp",
                    "--parents",
                    "--max-count=11",
                    sha,
                    "--",
                ],
                raw.encode(),
            ),
            command(prefix + probe, (sha + "\n").encode()),
        ],
    }
    return cfg, capture


@pytest.mark.parametrize(
    "mutation",
    [
        "repository",
        "tool",
        "unsafe_prefix",
        "version",
        "missing_version",
        "graph_byte_count",
        "log_cap",
        "probe_order",
    ],
)
def test_contradictory_command_provenance_cannot_qualify_capture(mutation: str) -> None:
    cfg, capture = packet()
    candidate.validate_capture(capture, config=cfg)
    if mutation == "repository":
        capture["repo_path"] = "/foreign/project"
    elif mutation == "tool":
        capture["tool"]["path"] = "/foreign/git"
    elif mutation == "unsafe_prefix":
        capture["commands"][3]["argv"].insert(-8, "--no-pager")
    elif mutation == "version":
        capture["commands"][0]["stdout_sha256"] = hashlib.sha256(
            b"git version 9.0.0\n"
        ).hexdigest()
    elif mutation == "missing_version":
        capture["commands"].pop(0)
    elif mutation == "graph_byte_count":
        capture["commands"][3]["stdout_bytes"] += 1
        capture["commands"][3]["captured_bytes"] += 1
    elif mutation == "log_cap":
        cfg["limits"]["max_output_bytes"] = 64
        capture["configuration_digest"] = digest_json(cfg)
        capture["commands"][3]["stderr_bytes"] = 100
        capture["commands"][3]["captured_bytes"] += 100
    else:
        last = capture["commands"].pop()
        capture["commands"].insert(3, last)
    with pytest.raises(ContractError):
        candidate.validate_capture(capture, config=cfg)


def test_coherent_mocked_packet_has_only_declared_scope() -> None:
    cfg, capture = packet()
    result = candidate.analyze_branch_delivery(cfg, capture)
    assert result["branches"][0]["history_complete"] is True
    assert result["branches"][0]["observed_commit_count"] == 1
    assert result["delivery_origin"] == "caller_declarations_not_execution_receipts"


def test_bounded_truncated_graph_retains_partial_positive_facts() -> None:
    cfg, capture = packet()
    row = capture["commands"][3]
    row["stdout_bytes"] += 10
    row["truncated"] = True
    capture["truncated"] = True
    capture["graph_command_complete"] = False
    candidate.validate_capture(capture, config=cfg)
    report = candidate.analyze_branch_delivery(cfg, capture)
    assert report["graph_status"] == "partial"
    assert report["branches"][0]["history_complete"] is False


def test_retained_complete_stderr_is_allowed_with_consistent_counts() -> None:
    cfg, capture = packet()
    row = capture["commands"][3]
    warning = b"notice\n"
    row.update(
        stderr_bytes=len(warning),
        stderr_sha256=hashlib.sha256(warning).hexdigest(),
        stderr_tail=warning.decode(),
    )
    row["captured_bytes"] += len(warning)
    candidate.validate_capture(capture, config=cfg)


def test_unavailable_capture_does_not_need_positive_version_or_ref_proofs() -> None:
    cfg, capture = packet()
    capture.update(
        tool=None,
        commands=[],
        nodes=[],
        raw_graph="",
        raw_graph_sha256=hashlib.sha256(b"").hexdigest(),
        shallow=None,
        graph_command_complete=False,
    )
    capture["refs"][0].update(status="unavailable", observed_tip=None)
    candidate.validate_capture(capture, config=cfg)
    assert (
        candidate.analyze_branch_delivery(cfg, capture)["graph_status"] == "unavailable"
    )


def test_empty_graph_stdout_must_still_match_its_receipt_digest() -> None:
    cfg, capture = packet()
    capture.update(
        nodes=[],
        raw_graph="",
        raw_graph_sha256=hashlib.sha256(b"").hexdigest(),
        graph_command_complete=False,
    )
    capture["commands"][3].update(
        stdout_bytes=0, captured_bytes=0, stdout_sha256="f" * 64
    )
    with pytest.raises(ContractError):
        candidate.validate_capture(capture, config=cfg)


@pytest.mark.parametrize("field", ["repo", "tool"])
@pytest.mark.parametrize("suffix", ["\x00foreign", "\ud800"])
def test_impossible_process_strings_cannot_qualify_matching_receipts(
    field: str, suffix: str
) -> None:
    cfg, capture = packet()
    if field == "repo":
        previous = capture["repo_path"]
        replacement = previous + suffix
        capture["repo_path"] = replacement
    else:
        previous = capture["tool"]["path"]
        replacement = previous + suffix
        capture["tool"]["path"] = replacement
    for row in capture["commands"]:
        row["argv"] = [
            replacement if value == previous else value for value in row["argv"]
        ]
    with pytest.raises(ContractError):
        candidate.validate_capture(capture, config=cfg)


@pytest.mark.parametrize("field", ["repo", "tool"])
def test_valid_utf8_and_spaces_in_process_paths_remain_literal(field: str) -> None:
    cfg, capture = packet()
    if field == "repo":
        previous = capture["repo_path"]
        replacement = "/selected/naïve project"
        capture["repo_path"] = replacement
    else:
        previous = capture["tool"]["path"]
        replacement = "/selected/outils naïfs/git"
        capture["tool"]["path"] = replacement
    for row in capture["commands"]:
        row["argv"] = [
            replacement if value == previous else value for value in row["argv"]
        ]
    candidate.validate_capture(capture, config=cfg)
