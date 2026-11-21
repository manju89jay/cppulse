"""Actual local Git co-change controls; no symbol/native facts are invented."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import git
import pytest

import cppulse
from cppulse.errors import ContractError
from cppulse.git_miner.behavior import (
    BehaviorConfig,
    analyze_behavior,
    records_from_scan,
    validate_behavior_report,
)
from cppulse.git_miner.history import scan_history

CUTOFF = datetime(2026, 11, 18, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def installed_origin_when_requested():
    prefix = os.environ.get("CPPULSE_HISTORY_EXPECT_PREFIX114")
    if prefix is not None:
        assert (
            Path(cppulse.__file__).resolve().parent
            == Path(prefix).resolve() / "cppulse"
        )


def behavior_config(**changes):
    value = {
        "version": "1.0.0",
        "window_days": 365,
        "half_life_days": 1,
        "max_commits": 100,
        "max_files_per_commit": 2,
        "max_pair_records": 100,
        "minimum_support": 2,
        "aliases": {"alice-old@example.invalid": "alice@example.invalid"},
        "bot_ids": ["bot@example.invalid"],
        "former_contributor_ids": ["alice@example.invalid"],
        "offboarding_ids": ["alice@example.invalid"],
        "teams": {"alice@example.invalid": "core", "bob@example.invalid": "ops"},
        "components": {"core": ["a.cpp", "b.cpp"], "generated": ["generated/**"]},
        "exclude_paths": ["generated/**"],
        "exclude_commit_ids": [],
        "include_merges": False,
        "pair_attribution": "coauthor_trailers",
    }
    value.update(changes)
    return BehaviorConfig.from_document(value)


def repository(path):
    repo = git.Repo.init(path, initial_branch="main")
    with repo.config_writer() as writer:
        writer.set_value("user", "name", "Controlled fixture")
        writer.set_value("user", "email", "fixture@example.invalid")
        writer.set_value("commit", "gpgsign", "false")
    return repo


def commit(
    repo, changes, *, age=0, email="alice@example.invalid", message="controlled"
):
    root = Path(repo.working_tree_dir)
    for name, content in changes.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    repo.index.add(list(changes))
    actor = git.Actor("Controlled fixture", email)
    date = CUTOFF - timedelta(days=age)
    return repo.index.commit(
        message, author=actor, committer=actor, author_date=date, commit_date=date
    )


def produce(repo, config):
    scan = scan_history(repo)
    report = analyze_behavior(
        records_from_scan(scan, config),
        scan.files,
        config,
        cutoff=CUTOFF,
        head=repo.head.commit.hexsha if scan.commits else None,
        history_limitations=scan.limitations,
    )
    validate_behavior_report(report)
    return report, scan


@pytest.fixture
def controlled_history(tmp_path):
    repo = repository(tmp_path / "history")
    seed = commit(
        repo,
        {
            "a.cpp": "// initial a\n",
            "b.cpp": "// initial b\n",
            "generated/g.cpp": "// generated initial\n",
        },
        age=3,
    )
    pair = commit(
        repo,
        {"a.cpp": "// pair a\n", "b.cpp": "// pair b\n"},
        age=2,
        email="alice-old@example.invalid",
        message=(
            "Actual pair declaration\n\n"
            "Co-authored-by: Bob <bob@example.invalid>\n"
            "Co-authored-by: Bob duplicate <bob@example.invalid>\n"
            "Co-authored-by: Alice canonical <alice@example.invalid>\n"
            "Co-authored-by: Build <bot@example.invalid>\n"
        ),
    )
    together = commit(repo, {"a.cpp": "// second a\n", "b.cpp": "// second b\n"}, age=1)
    alone = commit(repo, {"a.cpp": "// bob alone\n"}, email="bob@example.invalid")
    bulk = commit(
        repo,
        {
            "a.cpp": "// bulk a\n",
            "b.cpp": "// bulk b\n",
            "bulk-one.txt": "one\n",
            "bulk-two.txt": "two\n",
        },
        email="bulk@example.invalid",
    )
    generated = commit(repo, {"generated/g.cpp": "// regenerated\n"})
    bot = commit(
        repo,
        {"a.cpp": "// bot a\n", "b.cpp": "// bot b\n"},
        email="bot@example.invalid",
    )
    return repo, {
        "seed": seed.hexsha,
        "pair": pair.hexsha,
        "together": together.hexsha,
        "alone": alone.hexsha,
        "bulk": bulk.hexsha,
        "generated": generated.hexsha,
        "bot": bot.hexsha,
    }


def test_real_coupling_support_and_configured_bulk_generated_exclusions(
    controlled_history,
):
    repo, ids = controlled_history
    config = behavior_config(exclude_commit_ids=[ids["seed"]])
    report, scan = produce(repo, config)
    assert report["counts"]["observed_commits"] == 7
    assert report["counts"]["accepted_commits"] == 3
    assert report["counts"]["excluded_commits"] == {
        "explicit_exclusion": 1,
        "bulk": 1,
        "generated_only": 1,
        "bot_only": 1,
    }
    assert scan.commit_file_counts[ids["bulk"]] == 4
    (pair,) = report["coupling"]
    assert (pair["left"], pair["right"], pair["support"]) == ("a.cpp", "b.cpp", 2)
    assert (pair["left_touches"], pair["right_touches"]) == (3, 2)
    assert pair["jaccard"] == pytest.approx(2 / 3)
    assert pair["left_confidence"] == pytest.approx(2 / 3)
    assert pair["right_confidence"] == 1
    low, _ = produce(
        repo, behavior_config(exclude_commit_ids=[ids["seed"]], minimum_support=3)
    )
    assert low["coupling"] == []
    relaxed, _ = produce(
        repo, behavior_config(exclude_commit_ids=[ids["seed"]], max_files_per_commit=4)
    )
    assert relaxed["coupling"][0]["support"] == 3
    assert relaxed["coupling"][0]["jaccard"] == pytest.approx(3 / 4)
    explicit, _ = produce(
        repo, behavior_config(exclude_commit_ids=[ids["seed"], ids["together"]])
    )
    assert explicit["coupling"] == []
    assert any("static" in text for text in report["limitations"])


def test_real_branch_merge_is_not_recounted_as_branch_authorship(tmp_path):
    repo = repository(tmp_path / "merge")
    seed = commit(repo, {"a.cpp": "// a\n", "b.cpp": "// b\n"}, age=3)
    repo.create_head("side", seed)
    main = commit(repo, {"a.cpp": "// main a\n"}, age=2)
    repo.git.checkout("side")
    side = commit(repo, {"b.cpp": "// side b\n"}, age=1, email="bob@example.invalid")
    repo.git.checkout("main")
    stamp = f"{int(CUTOFF.timestamp())} +0000"
    with repo.git.custom_environment(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp):
        repo.git.merge("--no-ff", "side", "-m", "Actual controlled merge")
    report, scan = produce(repo, behavior_config(exclude_commit_ids=[seed.hexsha]))
    assert {c.hexsha for c in scan.commits} == {
        seed.hexsha,
        main.hexsha,
        side.hexsha,
        repo.head.commit.hexsha,
    }
    assert report["counts"]["excluded_commits"] == {"explicit_exclusion": 1, "merge": 1}
    assert report["counts"]["accepted_commits"] == 2
    assert {row["file"]: row["touches"] for row in report["files"]} == {
        "a.cpp": 1,
        "b.cpp": 1,
    }
    assert report["coupling"] == []


def test_real_rename_keeps_one_current_file_touch_per_commit(tmp_path):
    repo = repository(tmp_path / "rename")
    seed = commit(repo, {"old.cpp": "// old\n", "b.cpp": "// b\n"}, age=3)
    commit(repo, {"old.cpp": "// changed\n", "b.cpp": "// changed b\n"}, age=2)
    repo.git.mv("old.cpp", "renamed.cpp")
    actor = git.Actor("Bob", "bob@example.invalid")
    renamed = repo.index.commit(
        "Actual rename",
        author=actor,
        committer=actor,
        author_date=CUTOFF - timedelta(days=1),
        commit_date=CUTOFF - timedelta(days=1),
    )
    report, scan = produce(
        repo, behavior_config(exclude_commit_ids=[seed.hexsha], minimum_support=1)
    )
    assert scan.commit_file_counts[renamed.hexsha] == 1
    rows = {row["file"]: row for row in report["files"]}
    assert set(rows) == {"b.cpp", "renamed.cpp"}
    assert rows["renamed.cpp"]["touches"] == 2
    assert rows["renamed.cpp"]["weighted_changes"] == pytest.approx(3 / 4)
    assert report["coupling"][0]["support"] == 1
    assert report["coupling"][0]["jaccard"] == pytest.approx(1 / 2)


def test_impossible_derived_coupling_is_rejected_not_reported_clean(controlled_history):
    """Authored malformed consumer record, not another executed Git history."""
    repo, ids = controlled_history
    report, _ = produce(repo, behavior_config(exclude_commit_ids=[ids["seed"]]))
    bad = deepcopy(report)
    bad["coupling"][0]["support"] = 3
    with pytest.raises(ContractError):
        validate_behavior_report(bad)
