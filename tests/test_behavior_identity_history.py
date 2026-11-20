"""Identity attribution controls over small, local, never-uploaded Git histories."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import git
import pytest

from cppulse.git_miner.behavior import (
    BehaviorConfig,
    analyze_behavior,
    records_from_scan,
    validate_behavior_report,
)
from cppulse.git_miner.history import scan_history


CUTOFF = datetime(2026, 11, 16, tzinfo=timezone.utc)


def configuration(**changes: object) -> BehaviorConfig:
    """Keep the public v1 contract explicit rather than mutating shared fixtures."""
    document = {
        "version": "1.0.0",
        "window_days": 365,
        "half_life_days": 10,
        "max_commits": 100,
        "max_files_per_commit": 20,
        "max_pair_records": 100,
        "minimum_support": 1,
        "aliases": {},
        "bot_ids": [],
        "former_contributor_ids": [],
        "offboarding_ids": [],
        "teams": {},
        "components": {},
        "exclude_paths": [],
        "exclude_commit_ids": [],
        "include_merges": False,
        "pair_attribution": "coauthor_trailers",
    }
    document.update(changes)
    return BehaviorConfig.from_document(document)


def commit(
    repo: git.Repo,
    message: str,
    *,
    author: str = "alice@example.com",
    paths: tuple[str, ...] = ("a.cpp", "b.cpp"),
    parents: tuple[git.Commit, ...] | None = None,
) -> git.Commit:
    """Create a finite local fixture with exactly controlled author/time/paths."""
    root = Path(repo.working_tree_dir)
    for path in paths:
        (root / path).write_text(message + "\n", encoding="utf-8")
    repo.index.add(list(paths))
    actor = git.Actor(author, author)
    options = {} if parents is None else {"parent_commits": parents}
    return repo.index.commit(
        message,
        author=actor,
        committer=actor,
        author_date=CUTOFF,
        commit_date=CUTOFF,
        **options,
    )


def report(repo: git.Repo, cfg: BehaviorConfig) -> dict:
    """Exercise scanner -> adapter -> calculations -> frozen report validation."""
    scan = scan_history(repo)
    result = analyze_behavior(
        records_from_scan(scan, cfg), scan.files, cfg, cutoff=CUTOFF
    )
    validate_behavior_report(result)
    return result


@pytest.mark.parametrize("crowding", ["same_author", "alias", "bot"])
def test_repeated_identity_trailers_do_not_evict_real_pair_contributor(
    tmp_path: Path, crowding: str
) -> None:
    repo = git.Repo.init(tmp_path)
    repeated = {
        "same_author": "alice@example.com",
        "alias": "old-alice@example.com",
        "bot": "build-bot@example.com",
    }[crowding]
    trailers = [f"Co-authored-by: Repeated <{repeated}>"] * 64
    trailers.append("Co-authored-by: Former partner <bob@example.com>")
    commit(repo, "Pair work\n\n" + "\n".join(trailers))
    cfg = configuration(
        aliases={"old-alice@example.com": "alice@example.com"},
        bot_ids=["build-bot@example.com"],
        former_contributor_ids=["bob@example.com"],
        offboarding_ids=["bob@example.com"],
    )
    result = report(repo, cfg)
    for row in result["files"]:
        authors = {entry["id"]: entry for entry in row["authors"]}
        assert set(authors) == {"alice@example.com", "bob@example.com"}
        assert authors["bob@example.com"]["former_contributor"] is True
        assert authors["bob@example.com"]["share"] == pytest.approx(0.5)
        assert row["offboarding"]["removed_share"] == pytest.approx(0.5)
        assert row["touches"] == 1
    assert result["coupling"][0]["support"] == 1
    assert not any("capped at" in note for note in result["limitations"])


@pytest.mark.parametrize("separator", ["\n \n", "\n\t\n", "\r\n \r\n"])
def test_whitespace_blank_line_separates_final_coauthor_footer(
    tmp_path: Path, separator: str
) -> None:
    repo = git.Repo.init(tmp_path)
    commit(repo, "Pair work" + separator + "Co-authored-by: Bob <bob@example.com>")
    result = report(repo, configuration())
    assert {entry["id"] for entry in result["files"][0]["authors"]} == {
        "alice@example.com",
        "bob@example.com",
    }


@pytest.mark.parametrize("additional_count", [63, 64])
def test_real_distinct_identity_cap_is_bounded_and_disclosed(
    tmp_path: Path, additional_count: int
) -> None:
    repo = git.Repo.init(tmp_path)
    trailers = [
        f"Co-authored-by: Partner {index} <partner-{index}@example.com>"
        for index in range(additional_count)
    ]
    commit(repo, "Many declared partners\n\n" + "\n".join(trailers))
    cfg = configuration()
    scan = scan_history(repo)
    records = list(records_from_scan(scan, cfg))
    assert len(records[0].authors) == 64
    result = analyze_behavior(records, scan.files, cfg, cutoff=CUTOFF)
    validate_behavior_report(result)
    row = result["files"][0]
    assert len(row["authors"]) == 64
    assert row["weighted_changes"] == pytest.approx(1)
    assert all(entry["share"] == pytest.approx(1 / 64) for entry in row["authors"])
    assert any("capped at" in note for note in result["limitations"]) is (
        additional_count > 63
    )


def test_author_only_does_not_attribute_even_valid_final_pair_footer(
    tmp_path: Path,
) -> None:
    repo = git.Repo.init(tmp_path)
    commit(repo, "Pair work\n\nCo-authored-by: Bob <bob@example.com>")
    result = report(repo, configuration(pair_attribution="author_only"))
    assert [entry["id"] for entry in result["files"][0]["authors"]] == [
        "alice@example.com"
    ]


def test_bot_author_can_credit_human_pair_without_crediting_bot(tmp_path: Path) -> None:
    repo = git.Repo.init(tmp_path)
    commit(
        repo,
        "Bot-assisted pair\n\nCo-authored-by: Bob <old-bob@example.com>",
        author="build-bot@example.com",
    )
    result = report(
        repo,
        configuration(
            aliases={"old-bob@example.com": "bob@example.com"},
            bot_ids=["build-bot@example.com"],
            former_contributor_ids=["old-bob@example.com"],
        ),
    )
    assert result["counts"]["accepted_commits"] == 1
    for row in result["files"]:
        assert len(row["authors"]) == 1
        assert row["authors"][0]["id"] == "bob@example.com"
        assert row["authors"][0]["former_contributor"] is True
        assert row["authors"][0]["share"] == 1


@pytest.mark.parametrize("include_merges", [False, True])
def test_actual_merge_and_bulk_commits_have_one_consistent_touch_denominator(
    tmp_path: Path, include_merges: bool
) -> None:
    repo = git.Repo.init(tmp_path)
    initial = commit(repo, "Initial selected pair")
    bulk = commit(
        repo,
        "Bulk with non-C++ paths",
        paths=("a.cpp", "b.cpp", *[f"generated-{i}.txt" for i in range(21)]),
    )
    commit(repo, "Synthetic merge touch", parents=(bulk, initial))
    result = report(repo, configuration(include_merges=include_merges))
    expected = 2 if include_merges else 1
    assert result["counts"]["accepted_commits"] == expected
    assert result["counts"]["excluded_commits"] == (
        {"bulk": 1} if include_merges else {"bulk": 1, "merge": 1}
    )
    assert result["coupling"][0]["support"] == expected
    assert result["coupling"][0]["left_touches"] == expected
    assert result["coupling"][0]["right_touches"] == expected
    assert result["coupling"][0]["jaccard"] == 1
    assert all(row["touches"] == expected for row in result["files"])
