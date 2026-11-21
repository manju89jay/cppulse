"""Actual small Git histories retain subsecond window/chronology semantics."""

from datetime import datetime, timezone

import git
import pytest

from cppulse.branch_delivery import analyze_branch_delivery, collect_branch_graph


@pytest.fixture
def far_future_graph(tmp_path):
    repo = git.Repo.init(tmp_path, initial_branch="main")
    actor = git.Actor("Time fixture", "fixture@example.invalid")
    commits = []
    for second in (58, 59):
        at = datetime(9999, 12, 31, 23, 59, second, tzinfo=timezone.utc)
        path = tmp_path / "a.cpp"
        path.write_text("int at_" + str(second) + ";\n")
        repo.index.add(["a.cpp"])
        commits.append(
            repo.index.commit(
                "authored " + str(second),
                author=actor,
                committer=actor,
                author_date=at,
                commit_date=at,
            ).hexsha
        )
    config = {
        "version": "1.0.0",
        "id": "precise-window",
        "target_ref_id": "main",
        "refs": [{"id": "main", "ref": "refs/heads/main", "expected_tip": commits[-1]}],
        "window_start": "9999-12-31T23:59:58.000001Z",
        "cutoff": "9999-12-31T23:59:59.000001Z",
        "tasks": [],
        "deliveries": [],
        "delivery_inventory_complete": True,
        "limits": {
            "max_commits": 10,
            "max_output_bytes": 65536,
            "command_timeout_seconds": 5,
            "total_timeout_seconds": 30,
        },
    }
    return tmp_path, commits, config


def test_half_open_window_preserves_supported_microsecond_boundaries(far_future_graph):
    repo, commits, config = far_future_graph
    capture = collect_branch_graph(repo, config)
    assert capture["graph_command_complete"]
    report = analyze_branch_delivery(config, capture)
    row = report["branches"][0]
    assert row["history_complete"]
    assert row["complete_in_window_count"] == 1
    assert row["sample_in_window_commit_ids"] == [commits[1]]


def test_future_revision_by_one_microsecond_is_not_chronologically_qualified(
    far_future_graph,
):
    repo, commits, config = far_future_graph
    config.update(
        window_start="9999-12-31T23:59:57Z", cutoff="9999-12-31T23:59:59.999999Z"
    )
    config["tasks"] = [
        {
            "id": "task",
            "environment": "staging",
            "commit_ids": [commits[1]],
            "started_at": "9999-12-31T23:59:58Z",
            "completed_at": None,
            "recorded_at": "9999-12-31T23:59:59Z",
        }
    ]
    config["deliveries"] = [
        {
            "id": "event",
            "environment": "staging",
            "commit_id": commits[1],
            "status": "succeeded",
            "occurred_at": "9999-12-31T23:59:58.999999Z",
            "recorded_at": "9999-12-31T23:59:59Z",
        }
    ]
    report = analyze_branch_delivery(config, collect_branch_graph(repo, config))
    assert report["deliveries"][0]["git_timestamp_consistent"] is False
    assert report["tasks"][0]["status"] == "unknown"
    assert report["tasks"][0]["first_selected_delivery_id"] is None
    assert report["tasks"][0]["task_to_selected_delivery_seconds"] is None


@pytest.mark.parametrize(
    "start,cutoff,indices",
    [
        ("58.000001", "58.999999", []),
        ("58", "59", [0]),
        ("59", "59.000001", [1]),
        ("58.999999", "59", []),
        ("58", "59.999999", [0, 1]),
    ],
)
def test_exact_half_open_boundary_controls(far_future_graph, start, cutoff, indices):
    repo, commits, config = far_future_graph
    config.update(
        window_start="9999-12-31T23:59:" + start + "Z",
        cutoff="9999-12-31T23:59:" + cutoff + "Z",
    )
    report = analyze_branch_delivery(config, collect_branch_graph(repo, config))
    assert report["branches"][0]["sample_in_window_commit_ids"] == sorted(
        commits[index] for index in indices
    )
    assert report["branches"][0]["complete_in_window_count"] == len(indices)


@pytest.mark.parametrize(
    "fraction,consistent", [("58.999999", False), ("59", True), ("59.000001", True)]
)
def test_task_and_delivery_chronology_preserve_exact_second_boundary(
    far_future_graph, fraction, consistent
):
    repo, commits, config = far_future_graph
    occurred = "9999-12-31T23:59:" + fraction + "Z"
    config.update(
        window_start="9999-12-31T23:59:57Z", cutoff="9999-12-31T23:59:59.999999Z"
    )
    config["tasks"] = [
        {
            "id": "task",
            "environment": "staging",
            "commit_ids": [commits[1]],
            "started_at": "9999-12-31T23:59:58Z",
            "completed_at": None,
            "recorded_at": "9999-12-31T23:59:59.999998Z",
        }
    ]
    config["deliveries"] = [
        {
            "id": "event",
            "environment": "staging",
            "commit_id": commits[1],
            "status": "succeeded",
            "occurred_at": occurred,
            "recorded_at": occurred,
        }
    ]
    report = analyze_branch_delivery(config, collect_branch_graph(repo, config))
    assert report["deliveries"][0]["git_timestamp_consistent"] is consistent
    if consistent:
        assert report["tasks"][0]["first_selected_delivery_id"] == "event"
        assert report["tasks"][0]["status"] == "declared_delivery_observed"
        expected = (
            datetime.fromisoformat(occurred.replace("Z", "+00:00"))
            - datetime(9999, 12, 31, 23, 59, 58, tzinfo=timezone.utc)
        ).total_seconds()
        assert report["tasks"][0]["task_to_selected_delivery_seconds"] == expected
    else:
        assert report["tasks"][0]["status"] == "unknown"
        assert report["tasks"][0]["first_selected_delivery_id"] is None


def test_microsecond_timezone_offset_keeps_same_window(far_future_graph):
    repo, commits, config = far_future_graph
    config.update(
        window_start="9999-12-31T23:00:58.000001-00:59",
        cutoff="9999-12-31T23:00:59.000001-00:59",
    )
    report = analyze_branch_delivery(config, collect_branch_graph(repo, config))
    assert report["branches"][0]["sample_in_window_commit_ids"] == [commits[1]]
