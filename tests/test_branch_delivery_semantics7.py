"""Pinned all-parent graph receipts must actually name the declared inputs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import git
import pytest

from cppulse.branch_delivery import (
    analyze_branch_delivery,
    collect_branch_graph,
    validate_capture,
)
from cppulse.errors import ContractError


@pytest.fixture
def merge_capture(tmp_path: Path) -> tuple[dict, dict]:
    """Four local fixture objects include a task reachable only by merge parent2."""
    repo = git.Repo.init(tmp_path, initial_branch="main")
    actor = git.Actor("Fixture", "fixture@example.invalid")
    at = datetime(2026, 1, 2, tzinfo=timezone.utc)

    def commit(name: str, **options: object) -> git.Commit:
        path = tmp_path / "a.cpp"
        path.write_text(name + "\n", encoding="utf-8")
        repo.index.add(["a.cpp"])
        return repo.index.commit(
            name,
            author=actor,
            committer=actor,
            author_date=at,
            commit_date=at,
            **options,
        )

    root = commit("root")
    left = commit("left")
    right = commit("right", parent_commits=(root,), head=False)
    merged = commit("merged", parent_commits=(left, right))
    cfg = {
        "version": "1.0.0",
        "id": "receipt-semantics",
        "target_ref_id": "main",
        "refs": [
            {"id": "main", "ref": "refs/heads/main", "expected_tip": merged.hexsha}
        ],
        "window_start": "2026-01-01T00:00:00Z",
        "cutoff": "2026-01-10T00:00:00Z",
        "delivery_inventory_complete": True,
        "tasks": [
            {
                "id": "second-parent-task",
                "environment": "staging",
                "commit_ids": [right.hexsha],
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": None,
                "recorded_at": "2026-01-03T00:00:00Z",
            }
        ],
        "deliveries": [
            {
                "id": "declared-success",
                "environment": "staging",
                "commit_id": merged.hexsha,
                "status": "succeeded",
                "occurred_at": "2026-01-04T00:00:00Z",
                "recorded_at": "2026-01-04T01:00:00Z",
            }
        ],
        "limits": {
            "max_commits": 100,
            "max_output_bytes": 1048576,
            "command_timeout_seconds": 5,
            "total_timeout_seconds": 30,
        },
    }
    return cfg, collect_branch_graph(tmp_path, cfg)


@pytest.mark.parametrize(
    "mutation", ["first_parent", "different_tip", "bound", "window"]
)
def test_wrong_graph_command_cannot_qualify_selected_all_parent_facts(
    merge_capture: tuple[dict, dict], mutation: str
) -> None:
    cfg, capture = merge_capture
    changed = deepcopy(capture)
    command = next(row for row in changed["commands"] if "rev-list" in row["argv"])
    args = command["argv"]
    if mutation == "first_parent":
        args.insert(args.index("--topo-order"), "--first-parent")
    elif mutation == "different_tip":
        args[-2] = cfg["tasks"][0]["commit_ids"][0]
    elif mutation == "bound":
        args[args.index("--max-count=101")] = "--max-count=1"
    else:
        args.insert(args.index("--timestamp"), "--since=2026-01-03")
    # All original raw/parsed bytes and output digests still agree: that alone
    # cannot prove this was the requested finite all-parent extraction.
    with pytest.raises(ContractError, match="Graph command"):
        validate_capture(changed, config=cfg)
    with pytest.raises(ContractError, match="Graph command"):
        analyze_branch_delivery(cfg, changed)


def test_exact_graph_receipt_preserves_second_parent_task_linkage(
    merge_capture: tuple[dict, dict],
) -> None:
    cfg, capture = merge_capture
    validate_capture(capture, config=cfg)
    result = analyze_branch_delivery(cfg, capture)
    assert result["branches"][0]["observed_commit_count"] == 4
    assert result["branches"][0]["history_complete"] is True
    assert result["tasks"][0]["status"] == "declared_delivery_observed"
    assert result["tasks"][0]["task_to_selected_delivery_seconds"] == 259200


@pytest.mark.parametrize("status", ["changed", "unavailable"])
def test_original_graph_receipt_survives_later_pin_or_tool_instability(
    merge_capture: tuple[dict, dict], status: str
) -> None:
    cfg, capture = merge_capture
    changed = deepcopy(capture)
    changed["refs"][0].update(status=status, reason="Became unstable after extraction")
    if status == "unavailable":
        changed["tool"].update(stable=False, sha256_after="0" * 64)
    # These original graph arguments remain truthful even though the final
    # stability probe prevents a branch from qualifying as available.
    validate_capture(changed, config=cfg)
    result = analyze_branch_delivery(cfg, changed)
    assert result["branches"][0]["availability"] == "unavailable"
    assert result["branches"][0]["history_complete"] is False
    if status == "unavailable":
        assert result["tasks"][0]["status"] == "unknown"
        assert result["graph_status"] == "unavailable"
