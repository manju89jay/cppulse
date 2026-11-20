"""Weighted file familiarity and denominators from actual shared Git scans."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess

import pytest

from cppulse.errors import ContractError
from cppulse.git_miner.behavior import analyze_behavior, validate_behavior_report
from test_behavior_coupling114 import (
    CUTOFF, behavior_config, produce, repository,
    controlled_history as controlled_history,
    installed_origin_when_requested as installed_origin_when_requested,
)


def test_real_recency_pair_alias_bot_and_former_weights_are_literal(controlled_history):
    repo, ids = controlled_history
    config = behavior_config(exclude_commit_ids=[ids["seed"]])
    report, scan = produce(repo, config)
    rows = {row["file"]: row for row in report["files"]}
    a, b, generated = rows["a.cpp"], rows["b.cpp"], rows["generated/g.cpp"]
    assert a["touches"] == 3 and b["touches"] == 2
    assert a["weighted_changes"] == pytest.approx(7 / 4)
    assert b["weighted_changes"] == pytest.approx(3 / 4)
    masses = {row["id"]: row["weighted_changes"] for row in a["authors"]}
    assert masses == pytest.approx({"alice@example.invalid": 5 / 8, "bob@example.invalid": 9 / 8})
    assert {row["id"]: row["share"] for row in a["authors"]} == pytest.approx(
        {"alice@example.invalid": 5 / 14, "bob@example.invalid": 9 / 14})
    assert a["fragmentation"] == pytest.approx(45 / 98)
    assert a["effective_authors"] == pytest.approx(98 / 53)
    assert b["fragmentation"] == pytest.approx(5 / 18)
    assert a["offboarding"]["removed_share"] == pytest.approx(5 / 14)
    assert a["offboarding"]["remaining_share"] == pytest.approx(9 / 14)
    assert next(x for x in a["authors"] if x["id"] == "alice@example.invalid")["former_contributor"]
    assert all(x["id"] != "bot@example.invalid" for row in rows.values() for x in row["authors"])
    assert generated["availability"] == "unavailable" and generated["weighted_changes"] == 0
    assert generated["fragmentation"] is None
    core = next(row["ownership"] for row in report["components"] if row["id"] == "core")
    assert core["touches"] == 5  # File-touch mass, not duplicated commit support.
    assert core["weighted_changes"] == pytest.approx(5 / 2)
    assert {x["id"]: x["share"] for x in core["authors"]} == pytest.approx(
        {"alice@example.invalid": 1 / 2, "bob@example.invalid": 1 / 2})
    assert core["fragmentation"] == pytest.approx(1 / 2)
    assert core["offboarding"]["remaining_share"] == pytest.approx(1 / 2)
    assert any("familiarity" in x and "expertise" in x for x in report["limitations"])
    from cppulse.git_miner.behavior import records_from_scan
    shuffled = analyze_behavior(reversed(list(records_from_scan(scan, config))),
        reversed(sorted(scan.files)), config, cutoff=CUTOFF, head=repo.head.commit.hexsha,
        history_limitations=scan.limitations)
    assert shuffled == report


def test_same_team_keeps_author_fragmentation_and_known_team_denominator(controlled_history):
    repo, ids = controlled_history
    report, _ = produce(repo, behavior_config(exclude_commit_ids=[ids["seed"]],
        teams={"alice@example.invalid": "core", "bob@example.invalid": "core"}))
    a = next(row for row in report["files"] if row["file"] == "a.cpp")
    assert a["fragmentation"] == pytest.approx(45 / 98)
    assert a["team_fragmentation"] == 0
    assert a["teams"] == [{"id": "team:core", "weighted_changes": 7 / 4, "share": 1}]


def test_real_local_shallow_history_has_observed_only_finite_metrics(controlled_history, tmp_path):
    repo, ids = controlled_history
    target = tmp_path / "shallow"
    subprocess.run(["git", "-c", "protocol.file.allow=always", "clone", "--quiet",
        "--no-local", "--depth", "4", str(Path(repo.working_tree_dir)), str(target)],
        capture_output=True, text=True, check=True)
    import git
    shallow = git.Repo(target)
    assert shallow.git.rev_parse("--is-shallow-repository") == "true"
    report, scan = produce(shallow, behavior_config(exclude_commit_ids=[ids["seed"]], minimum_support=1))
    assert len(scan.commits) == 4
    assert report["history_status"] == "partial"
    assert any("shallow" in text.lower() for text in report["limitations"])
    # A shallow boundary is a tree snapshot, not a known parent delta. All
    # later events here are explicit bulk/generated/bot exclusions.
    assert report["counts"]["accepted_commits"] == 0
    a = next(row for row in report["files"] if row["file"] == "a.cpp")
    assert a["weighted_changes"] == 0 and a["touches"] == 0
    assert a["authors"] == [] and a["fragmentation"] is None
    relaxed, _ = produce(shallow, behavior_config(exclude_commit_ids=[ids["seed"]],
                                                 minimum_support=1, max_files_per_commit=4))
    (tmp_path / "observed-shallow-default.json").write_text(json.dumps(report, indent=2) + "\n")
    (tmp_path / "observed-shallow-relaxed.json").write_text(json.dumps(relaxed, indent=2) + "\n")
    assert relaxed["counts"]["accepted_commits"] == 1
    assert all(author["id"] != "bob@example.invalid"
               for row in relaxed["files"] for author in row["authors"])
    assert relaxed["coupling"][0]["support"] == 1
    assert relaxed["coupling"][0]["jaccard"] == 1
    from cppulse.git_miner.behavior import records_from_scan
    projected = list(records_from_scan(scan, behavior_config()))
    boundary = next(row for row in projected if row.commit_id == ids["alone"])
    assert any("parent" in note.lower() for note in boundary.limitations), (
        "Unknown-parent boundary needs explicit delta provenance, not a known root-tree change count")
    from cppulse.git_miner.behavior import has_known_change_delta
    assert not has_known_change_delta(boundary)
    assert boundary.files == ()
    assert all(has_known_change_delta(row) for row in projected if row is not boundary)
    for row in report["files"]:
        assert math.isfinite(row["weighted_changes"])
        assert row["fragmentation"] is None or math.isfinite(row["fragmentation"])


def test_real_unborn_history_and_declared_empty_projection_have_no_denominator(tmp_path):
    repo = repository(tmp_path / "empty")
    report, scan = produce(repo, behavior_config())
    assert not scan.commits and report["history_status"] != "available"
    assert report["counts"]["accepted_commits"] == 0
    assert report["coupling"] == [] and report["files"] == []
    # Authored file declaration, not a Git/symbol producer observation.
    declared = analyze_behavior([], ["declared.cpp"], behavior_config(), cutoff=CUTOFF)
    row, = declared["files"]
    assert row["availability"] == "unavailable" and row["weighted_changes"] == 0
    assert row["authors"] == [] and row["fragmentation"] is None
    assert row["effective_authors"] is None and row["offboarding"]["remaining_share"] is None


def test_forged_derived_weight_and_fragmentation_are_not_accepted(controlled_history):
    """Authored corruption cannot become an observed contributor fact."""
    repo, ids = controlled_history
    report, _ = produce(repo, behavior_config(exclude_commit_ids=[ids["seed"]]))
    bad = deepcopy(report)
    bad["files"][0]["fragmentation"] = 0
    with pytest.raises(ContractError):
        validate_behavior_report(bad)
