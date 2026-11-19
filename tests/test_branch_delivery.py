"""Actual finite local Git graphs plus explicitly declared task/delivery data."""

from __future__ import annotations

from copy import deepcopy
import os
import shlex
from pathlib import Path
import subprocess

import pytest

from cppulse.branch_delivery import (
    collect_branch_graph,
    analyze_branch_delivery,
    validate_config,
    validate_capture,
    validate_report,
)
from cppulse.errors import ContractError


def git(repo: Path, *args: str, at: str = "2026-01-01T00:00:00Z") -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_AUTHOR_DATE": at, "GIT_COMMITTER_DATE": at},
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def history(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo's literal $(touch forbidden)"
    repo.mkdir()
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Authored Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    ids = {}

    def commit(name: str, at: str) -> str:
        (repo / (name + ".cpp")).write_text("int " + name + " = 0;\n")
        git(repo, "add", name + ".cpp")
        git(repo, "commit", "-m", name, at=at)
        return git(repo, "rev-parse", "HEAD")

    ids["root"] = commit("root", "2026-01-01T00:00:00Z")
    git(repo, "checkout", "-b", "feature")
    ids["feature1"] = commit("feature1", "2026-01-02T00:00:00Z")
    ids["feature"] = commit("feature2", "2026-01-03T00:00:00Z")
    git(repo, "checkout", "main")
    ids["main_change"] = commit("main_change", "2026-01-04T00:00:00Z")
    git(repo, "merge", "--no-ff", "--no-edit", "feature", at="2026-01-05T00:00:00Z")
    ids["main"] = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-b", "unmerged", ids["root"])
    ids["unmerged"] = commit("unmerged", "2026-01-06T00:00:00Z")
    git(repo, "checkout", "main")
    return repo, ids


def config(ids: dict[str, str]) -> dict:
    return {
        "version": "1.0.0",
        "id": "authored-branch-delivery",
        "target_ref_id": "main",
        "refs": [
            {"id": name, "ref": "refs/heads/" + name, "expected_tip": ids[name]}
            for name in ("main", "feature", "unmerged")
        ],
        "window_start": "2026-01-02T00:00:00Z",
        "cutoff": "2026-01-06T00:00:00Z",
        "delivery_inventory_complete": False,
        "tasks": [
            {
                "id": "task-feature",
                "environment": "staging",
                "commit_ids": [ids["feature1"], ids["feature"]],
                "started_at": "2026-01-02T00:00:00Z",
                "completed_at": "2026-01-04T00:00:00Z",
                "recorded_at": "2026-01-04T01:00:00Z",
            },
            {
                "id": "task-unmerged",
                "environment": "staging",
                "commit_ids": [ids["unmerged"]],
                "started_at": None,
                "completed_at": None,
                "recorded_at": "2026-01-05T00:00:00Z",
            },
        ],
        "deliveries": [
            {
                "id": "claimed-shipment",
                "environment": "staging",
                "commit_id": ids["main"],
                "occurred_at": "2026-01-05T12:00:00Z",
                "recorded_at": "2026-01-05T13:00:00Z",
                "status": "succeeded",
            },
            {
                "id": "claimed-failure",
                "environment": "staging",
                "commit_id": ids["main"],
                "occurred_at": "2026-01-05T15:00:00Z",
                "recorded_at": "2026-01-05T16:00:00Z",
                "status": "failed",
            },
        ],
        "limits": {
            "max_commits": 100,
            "max_output_bytes": 1048576,
            "command_timeout_seconds": 5,
            "total_timeout_seconds": 30,
        },
    }


def test_actual_all_parent_merge_reachability_and_window_counts(history) -> None:
    repo, ids = history
    cfg = config(ids)
    before = {
        str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()
    }
    capture = collect_branch_graph(repo, cfg)
    report = analyze_branch_delivery(cfg, capture)
    rows = {row["id"]: row for row in report["branches"]}
    assert rows["feature"]["relation_to_target"] == "ancestor_of_target"
    assert rows["feature"]["ahead"] == 0 and rows["feature"]["behind"] == 2
    assert rows["feature"]["merge_bases"] == [ids["feature"]]
    assert rows["main"]["complete_in_window_count"] == 4
    assert rows["unmerged"]["ahead"] == 1 and rows["unmerged"]["behind"] == 4
    assert rows["unmerged"]["merge_bases"] == [ids["root"]]
    assert rows["unmerged"]["complete_in_window_count"] == 0
    assert report["historical_ref_state"] == "not_reconstructed"
    assert before == {
        str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()
    }
    validate_report(report, config=cfg, capture=capture)


def test_declared_delivery_links_do_not_infer_task_workflow_or_causality(
    history,
) -> None:
    repo, ids = history
    cfg = config(ids)
    capture = collect_branch_graph(repo, cfg)
    report = analyze_branch_delivery(cfg, capture)
    tasks = {row["id"]: row for row in report["tasks"]}
    assert tasks["task-feature"]["status"] == "declared_delivery_observed"
    assert tasks["task-feature"]["first_selected_delivery_id"] == "claimed-shipment"
    assert tasks["task-feature"]["task_to_selected_delivery_seconds"] == 302400
    assert tasks["task-feature"]["declared_cycle_seconds"] == 172800
    assert tasks["task-unmerged"]["status"] == "not_observed_in_selected_deliveries"
    assert tasks["task-unmerged"]["task_to_selected_delivery_seconds"] is None
    assert report["delivery_counts"] == {"succeeded": 1, "failed": 1, "unknown": 0}
    assert report["delivery_origin"] == "caller_declarations_not_execution_receipts"
    assert report["policy_acceptance"] == "not_assessed"


def test_caps_are_partial_unknown_not_false_zero_or_no_common_ancestry(history) -> None:
    repo, ids = history
    cfg = config(ids)
    cfg["limits"]["max_commits"] = 1
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    rows = {row["id"]: row for row in report["branches"]}
    assert report["graph_status"] == "partial"
    assert rows["feature"]["ahead"] is None and rows["feature"]["merge_bases"] is None
    assert rows["feature"]["complete_in_window_count"] is None
    assert rows["feature"]["relation_to_target"] == "unknown"


def test_mismatched_ref_pin_preserves_other_observed_refs(history) -> None:
    repo, ids = history
    cfg = config(ids)
    cfg["refs"][1]["expected_tip"] = "a" * 40
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    rows = {row["id"]: row for row in report["branches"]}
    assert rows["feature"]["availability"] == "unavailable"
    assert rows["main"]["availability"] == "available"
    assert rows["main"]["complete_in_window_count"] == 4


def test_future_or_missing_task_and_event_metadata_never_borrow_positive_links(
    history,
) -> None:
    repo, ids = history
    cfg = config(ids)
    cfg["tasks"][0]["recorded_at"] = "2026-01-07T00:00:00Z"
    cfg["deliveries"][0]["recorded_at"] = "2026-01-07T00:00:00Z"
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["tasks"][0]["status"] == "unknown"
    assert report["tasks"][0]["task_to_selected_delivery_seconds"] is None
    assert report["delivery_counts"]["succeeded"] == 0
    assert report["delivery_counts"]["failed"] == 1


def test_absent_git_is_explicit_and_does_not_make_empty_graph_clean(
    history, monkeypatch
) -> None:
    repo, ids = history
    monkeypatch.setattr("cppulse.branch_delivery.shutil.which", lambda _: None)
    cfg = config(ids)
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["graph_status"] == "unavailable"
    assert all(row["ahead"] is None for row in report["branches"])
    assert report["tasks"][0]["status"] == "unknown"


@pytest.mark.parametrize(
    "mutation",
    ["ref_option", "ref_expression", "duplicate", "naive", "window", "task_time"],
)
def test_invalid_scope_and_time_contracts_reject(history, mutation) -> None:
    _, ids = history
    cfg = config(ids)
    if mutation == "ref_option":
        cfg["refs"][0]["ref"] = "--all"
    if mutation == "ref_expression":
        cfg["refs"][0]["ref"] = "main~2"
    if mutation == "duplicate":
        cfg["refs"][1]["id"] = "main"
    if mutation == "naive":
        cfg["cutoff"] = "2026-01-06T00:00:00"
    if mutation == "window":
        cfg["window_start"] = cfg["cutoff"]
    if mutation == "task_time":
        cfg["tasks"][0]["completed_at"] = "2025-01-01T00:00:00Z"
    with pytest.raises(ContractError):
        validate_config(cfg)


def test_changed_capture_or_report_is_not_accepted_as_same_pins(history) -> None:
    repo, ids = history
    cfg = config(ids)
    capture = collect_branch_graph(repo, cfg)
    modified = deepcopy(capture)
    modified["nodes"][0]["parents"] = []
    with pytest.raises(ContractError):
        validate_capture(modified, config=cfg)
    report = analyze_branch_delivery(cfg, capture)
    report["branches"][1]["ahead"] = 999
    with pytest.raises(ContractError):
        validate_report(report, config=cfg, capture=capture)


def test_earlier_unavailable_delivery_cannot_create_a_false_first_link(history) -> None:
    repo, ids = history
    cfg = config(ids)
    cfg["deliveries"].append(
        {
            "id": "earlier-unknown",
            "environment": "staging",
            "commit_id": "a" * 40,
            "occurred_at": "2026-01-05T06:00:00Z",
            "recorded_at": "2026-01-05T07:00:00Z",
            "status": "succeeded",
        }
    )
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["tasks"][0]["status"] == "unknown"
    assert report["tasks"][0]["first_selected_delivery_id"] is None
    assert report["tasks"][0]["task_to_selected_delivery_seconds"] is None


def test_delivery_before_git_commit_timestamp_is_explicitly_inconsistent(
    history,
) -> None:
    repo, ids = history
    cfg = config(ids)
    cfg["deliveries"][0].update(
        occurred_at="2026-01-04T12:00:00Z", recorded_at="2026-01-04T13:00:00Z"
    )
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["tasks"][0]["status"] == "unknown"
    assert report["tasks"][0]["task_to_selected_delivery_seconds"] is None
    assert report["deliveries"][0]["git_timestamp_consistent"] is False
    assert (
        report["delivery_counts"]["succeeded"] == 1
    )  # Original caller claim survives.


@pytest.mark.parametrize("mutation", ["tool_hash", "matched_pin", "malformed_raw"])
def test_capture_positive_flags_cannot_disagree_with_original_metadata(
    history, mutation
) -> None:
    import hashlib

    repo, ids = history
    cfg = config(ids)
    capture = collect_branch_graph(repo, cfg)
    if mutation == "tool_hash":
        capture["tool"]["sha256_after"] = "0" * 64
    if mutation == "matched_pin":
        capture["refs"][0]["observed_tip"] = ids["root"]
    if mutation == "malformed_raw":
        capture["raw_graph"] += "malformed graph row\n"
        capture["raw_graph_sha256"] = hashlib.sha256(
            capture["raw_graph"].encode()
        ).hexdigest()
    with pytest.raises(ContractError):
        validate_capture(capture, config=cfg)


def test_task_environment_cannot_borrow_staging_delivery(history) -> None:
    repo, ids = history
    cfg = config(ids)
    cfg["tasks"][0]["environment"] = "production"
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["tasks"][0]["status"] == "unknown"
    assert report["tasks"][0]["first_selected_delivery_id"] is None


def test_declared_timezones_preserve_same_elapsed_duration(history) -> None:
    repo, ids = history
    cfg = config(ids)
    cfg["tasks"][0].update(
        started_at="2026-01-02T01:00:00+01:00", completed_at="2026-01-04T01:00:00+01:00"
    )
    cfg["deliveries"][0]["occurred_at"] = "2026-01-05T13:00:00+01:00"
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["tasks"][0]["task_to_selected_delivery_seconds"] == 302400
    assert report["tasks"][0]["declared_cycle_seconds"] == 172800


def test_missing_task_start_is_not_zero_lead_duration(history) -> None:
    repo, ids = history
    cfg = config(ids)
    cfg["tasks"][0]["started_at"] = None
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["tasks"][0]["status"] == "declared_delivery_observed"
    assert report["tasks"][0]["task_to_selected_delivery_seconds"] is None
    assert report["tasks"][0]["declared_cycle_seconds"] is None


def test_actual_shallow_clone_does_not_manufacture_complete_ancestry(
    history, tmp_path: Path
) -> None:
    repo, ids = history
    shallow = tmp_path / "shallow"
    subprocess.run(
        [
            "git",
            "clone",
            "--depth=2",
            "--no-local",
            "--branch",
            "main",
            str(repo),
            str(shallow),
        ],
        capture_output=True,
        check=True,
        timeout=10,
    )
    cfg = config(ids)
    capture = collect_branch_graph(shallow, cfg)
    assert capture["shallow"] is True
    report = analyze_branch_delivery(cfg, capture)
    assert report["branches"][0]["history_complete"] is False
    assert report["branches"][0]["complete_in_window_count"] is None
    assert report["tasks"][0]["status"] == "unknown"


def test_output_budget_and_cancelled_capture_remain_unknown(history) -> None:
    from cppulse.execution import CancellationToken

    repo, ids = history
    cfg = config(ids)
    cfg["limits"]["max_output_bytes"] = 64
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["graph_status"] in {"partial", "unavailable"}
    assert all(row["complete_in_window_count"] is None for row in report["branches"])
    cfg = config(ids)
    token = CancellationToken()
    token.cancel()
    capture = collect_branch_graph(repo, cfg, cancel=token)
    assert any(row["status"] == "cancelled" for row in capture["commands"])
    assert analyze_branch_delivery(cfg, capture)["graph_status"] == "unavailable"


def test_promisor_repository_is_not_allowed_to_trigger_lazy_fetch(history) -> None:
    repo, ids = history
    git(repo, "config", "remote.origin.promisor", "true")
    git(repo, "config", "remote.origin.url", "https://example.invalid/no-fetch")
    cfg = config(ids)
    capture = collect_branch_graph(repo, cfg)
    assert any("Promisor" in note for note in capture["limitations"])
    assert not any("rev-list" in command["argv"] for command in capture["commands"])
    assert analyze_branch_delivery(cfg, capture)["graph_status"] == "unavailable"


def test_cherry_pick_patch_similarity_does_not_invent_original_commit_delivery(
    history,
) -> None:
    repo, ids = history
    git(repo, "checkout", "-b", "rebased", ids["root"])
    git(repo, "cherry-pick", ids["feature1"], at="2026-01-07T00:00:00Z")
    rewritten = git(repo, "rev-parse", "HEAD")
    assert rewritten != ids["feature1"]
    cfg = config(ids)
    cfg["cutoff"] = "2026-01-10T00:00:00Z"
    cfg["refs"].append(
        {"id": "rebased", "ref": "refs/heads/rebased", "expected_tip": rewritten}
    )
    cfg["tasks"][0]["commit_ids"] = [ids["feature1"]]
    cfg["deliveries"] = [
        {
            "id": "rewritten-delivery",
            "environment": "staging",
            "commit_id": rewritten,
            "occurred_at": "2026-01-08T00:00:00Z",
            "recorded_at": "2026-01-08T01:00:00Z",
            "status": "succeeded",
        }
    ]
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["tasks"][0]["status"] == "not_observed_in_selected_deliveries"
    assert report["tasks"][0]["task_to_selected_delivery_seconds"] is None


def test_sha256_repository_uses_its_actual_object_identity_format(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "sha256"
    repo.mkdir()
    git(repo, "init", "--object-format=sha256", "--initial-branch=main")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / "a.cpp").write_text("int value = 0;\n")
    git(repo, "add", "a.cpp")
    git(repo, "commit", "-m", "root")
    tip = git(repo, "rev-parse", "HEAD")
    assert len(tip) == 64
    cfg = config({"main": tip, "feature": tip, "feature1": tip, "unmerged": tip})
    cfg["refs"] = cfg["refs"][:1]
    cfg["tasks"] = []
    cfg["deliveries"] = []
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["branches"][0]["relation_to_target"] == "equal"
    assert report["branches"][0]["history_complete"] is True


def test_unknown_git_version_is_not_used_for_project_graph_reads(
    history, tmp_path: Path, monkeypatch
) -> None:
    repo, ids = history
    fake = tmp_path / "git"
    sentinel = tmp_path / "unexpected-project-read"
    fake.write_text(
        '#!/bin/sh\nif [ "$1" = "--version" ]; then echo \'git version 9.0.0\'; exit 0; fi\ntouch '
        + shlex.quote(str(sentinel))
        + "\nexit 1\n"
    )
    fake.chmod(0o755)
    monkeypatch.setattr("cppulse.branch_delivery.shutil.which", lambda _: str(fake))
    cfg = config(ids)
    capture = collect_branch_graph(repo, cfg)
    assert analyze_branch_delivery(cfg, capture)["graph_status"] == "unavailable"
    assert not sentinel.exists()


def test_environment_counts_preserve_explicit_scope(history) -> None:
    repo, ids = history
    cfg = config(ids)
    extra = deepcopy(cfg["deliveries"][0])
    extra.update(id="production-claim", environment="production", status="unknown")
    cfg["deliveries"].append(extra)
    report = analyze_branch_delivery(cfg, collect_branch_graph(repo, cfg))
    assert report["delivery_counts_by_environment"]["staging"] == {
        "succeeded": 1,
        "failed": 1,
        "unknown": 0,
    }
    assert report["delivery_counts_by_environment"]["production"] == {
        "succeeded": 0,
        "failed": 0,
        "unknown": 1,
    }


def test_timestamp_precision_is_not_silently_truncated(history) -> None:
    _, ids = history
    cfg = config(ids)
    cfg["cutoff"] = "2026-01-06T00:00:00.0000001Z"
    with pytest.raises(ContractError):
        validate_config(cfg)


@pytest.mark.parametrize(
    "key", ["GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"]
)
def test_literal_zero_repository_override_is_denied(history, monkeypatch, key) -> None:
    repo, ids = history
    monkeypatch.setenv(key, "0")
    cfg = config(ids)
    capture = collect_branch_graph(repo, cfg)
    assert capture["commands"] == []
    assert analyze_branch_delivery(cfg, capture)["graph_status"] == "unavailable"


def test_shallow_boundary_flag_is_bound_to_probe_receipt(history) -> None:
    repo, ids = history
    cfg = config(ids)
    capture = collect_branch_graph(repo, cfg)
    assert capture["shallow"] is False
    capture["shallow"] = True
    with pytest.raises(ContractError, match="Shallow boundary"):
        validate_capture(capture, config=cfg)


@pytest.mark.parametrize(
    "variable", ["GIT_TRACE_REFS", "GIT_TRACE2_EVENT", "GIT_TRACE_PACK_ACCESS"]
)
def test_inherited_git_trace_destinations_never_write(
    history, tmp_path, monkeypatch, variable
):
    repo, ids = history
    marker = tmp_path / "unauthorized-trace"
    monkeypatch.setenv(variable, str(marker))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "unrelated-index"))
    monkeypatch.setenv("GIT_ATTR_SOURCE", "not-a-revision")
    cfg = config(ids)
    capture = collect_branch_graph(repo, cfg)
    assert analyze_branch_delivery(cfg, capture)["graph_status"] == "available"
    assert not marker.exists()
    assert not (tmp_path / "unrelated-index").exists()


def test_ambient_shallow_boundary_override_is_denied(history, tmp_path, monkeypatch):
    repo, ids = history
    monkeypatch.setenv("GIT_SHALLOW_FILE", str(tmp_path / "invented-boundary"))
    capture = collect_branch_graph(repo, config(ids))
    assert capture["commands"] == []


def test_repository_trace2_configuration_does_not_write(history, tmp_path):
    repo, ids = history
    marker = tmp_path / "local-trace"
    git(repo, "config", "trace2.eventTarget", str(marker))
    capture = collect_branch_graph(repo, config(ids))
    assert analyze_branch_delivery(config(ids), capture)["graph_status"] == "available"
    assert not marker.exists()
