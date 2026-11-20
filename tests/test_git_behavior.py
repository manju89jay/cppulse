"""Hand-calculated bounded behavioral facts; authored histories are not expertise."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import json

import git
import pytest

from cppulse.errors import ContractError
from cppulse.git_miner.behavior import (
    BehaviorConfig,
    CommitRecord,
    analyze_behavior,
    records_from_scan,
    validate_behavior_report,
)
from cppulse.git_miner.history import scan_history

CUTOFF = datetime(2026, 11, 16, tzinfo=timezone.utc)


def config(**changes):
    document = {
        "version": "1.0.0",
        "window_days": 365,
        "half_life_days": 10,
        "max_commits": 100,
        "max_files_per_commit": 20,
        "max_pair_records": 100,
        "minimum_support": 2,
        "aliases": {},
        "bot_ids": [],
        "former_contributor_ids": [],
        "offboarding_ids": [],
        "teams": {},
        "components": {},
        "exclude_paths": [],
        "exclude_commit_ids": [],
        "include_merges": False,
        "pair_attribution": "author_only",
    }
    document.update(changes)
    return BehaviorConfig.from_document(document)


def record(number, author="alice@example.com", files=("a.cpp",), *, age=0, **changes):
    value = CommitRecord(
        commit_id=f"{number:040x}",
        committed_at=int(CUTOFF.timestamp()) - age * 86400,
        authors=(author,),
        files=files,
        total_files=len(files),
        is_merge=False,
    )
    return replace(value, **changes)


def by_file(report, path="a.cpp"):
    return next(row for row in report["files"] if row["file"] == path)


def test_known_recency_alias_pair_ownership_and_offboarding_are_hand_calculated():
    cfg = config(
        aliases={"alice-old@example.com": "alice@example.com"},
        teams={"alice@example.com": "core", "bob@example.com": "support"},
        former_contributor_ids=["alice@example.com"],
        offboarding_ids=["alice@example.com"],
        pair_attribution="coauthor_trailers",
    )
    commits = [
        record(1, "alice-old@example.com", age=10),
        record(2, authors=("alice@example.com", "bob@example.com")),
    ]
    result = analyze_behavior(commits, ["a.cpp"], cfg, cutoff=CUTOFF)
    row = by_file(result)
    assert row["weighted_changes"] == pytest.approx(1.5)
    assert {a["id"]: a["share"] for a in row["authors"]} == pytest.approx(
        {"alice@example.com": 2 / 3, "bob@example.com": 1 / 3}
    )
    assert row["fragmentation"] == pytest.approx(4 / 9)
    assert row["effective_authors"] == pytest.approx(1.8)
    assert row["offboarding"]["removed_share"] == pytest.approx(2 / 3)
    assert row["offboarding"]["remaining_share"] == pytest.approx(1 / 3)
    assert row["authors"][0]["former_contributor"] is True
    assert result["method"] == "cppulse-git-behavior-1"
    assert any("expertise" in note for note in result["limitations"])
    validate_behavior_report(result)


def test_bots_bulk_generated_merges_and_time_windows_do_not_pollute_denominators():
    records = [
        record(1),
        record(2, "build-bot@example.com"),
        record(3, age=366),
        record(4, total_files=21),
        record(5, is_merge=True),
        record(6, files=("generated/g.cpp",)),
        record(7, age=-1),
    ]
    result = analyze_behavior(
        records,
        ["a.cpp", "generated/g.cpp"],
        config(bot_ids=["build-bot@example.com"], exclude_paths=["generated/**"]),
        cutoff=CUTOFF,
    )
    assert by_file(result)["touches"] == 1
    assert by_file(result)["authors"][0]["share"] == 1
    assert result["counts"]["accepted_commits"] == 1
    assert result["counts"]["excluded_commits"] == {
        "bot_only": 1,
        "bulk": 1,
        "generated_only": 1,
        "merge": 1,
        "outside_window": 1,
        "future": 1,
    }


def test_historical_coupling_has_support_and_denominators_and_component_aggregation():
    records = [
        record(1, files=("a.cpp", "b.cpp")),
        record(2, files=("a.cpp", "b.cpp")),
        record(3, files=("a.cpp",)),
    ]
    result = analyze_behavior(
        records,
        ["a.cpp", "b.cpp", "no-history.hpp"],
        config(components={"api": ["a.cpp"], "impl": ["b.cpp"]}),
        cutoff=CUTOFF,
    )
    pair = result["coupling"][0]
    assert (pair["left"], pair["right"], pair["support"]) == ("a.cpp", "b.cpp", 2)
    assert pair["left_touches"] == 3 and pair["right_touches"] == 2
    assert pair["jaccard"] == pytest.approx(2 / 3)
    assert pair["left_confidence"] == pytest.approx(2 / 3)
    assert pair["right_confidence"] == 1
    assert result["component_coupling"][0]["support"] == 2
    assert by_file(result, "no-history.hpp")["availability"] == "unavailable"
    assert by_file(result, "no-history.hpp")["fragmentation"] is None
    assert result["relationship_kind"] == "historical_cochange"


def test_minimum_support_and_capped_pair_inventory_are_explicit():
    records = [record(1, files=("a.cpp", "b.cpp", "c.cpp"))]
    result = analyze_behavior(
        records,
        ["a.cpp", "b.cpp", "c.cpp"],
        config(minimum_support=1, max_pair_records=1),
        cutoff=CUTOFF,
    )
    assert result["history_status"] == "partial"
    assert len(result["coupling"]) == 1
    assert result["counts"]["dropped_pair_updates"] == 2
    assert (
        analyze_behavior(records, ["a.cpp", "b.cpp", "c.cpp"], config(), cutoff=CUTOFF)[
            "coupling"
        ]
        == []
    )


def test_commit_bound_consumes_only_one_sentinel_and_does_not_claim_complete_history():
    consumed = []

    def stream():
        for i in range(100):
            consumed.append(i)
            yield record(i)

    result = analyze_behavior(stream(), ["a.cpp"], config(max_commits=2), cutoff=CUTOFF)
    assert consumed == [0, 1, 2]
    assert result["counts"]["observed_commits"] == 2
    assert result["history_status"] == "partial"
    assert by_file(result)["touches"] == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"aliases": {"a": "b", "b": "a"}},
        {"minimum_support": 0},
        {"half_life_days": 0},
        {"max_commits": 0},
        {"exclude_paths": ["../outside"]},
        {"unknown_option": True},
    ],
)
def test_invalid_configuration_fails_before_history_processing(changes):
    with pytest.raises(ContractError):
        config(**changes)


def test_ambiguous_components_and_invalid_record_or_time_do_not_invent_results():
    with pytest.raises(ContractError, match="component"):
        analyze_behavior(
            [record(1)],
            ["a.cpp"],
            config(components={"a": ["*.cpp"], "b": ["a.cpp"]}),
            cutoff=CUTOFF,
        )
    with pytest.raises(ContractError):
        analyze_behavior([record(1), record(1)], ["a.cpp"], config(), cutoff=CUTOFF)
    with pytest.raises(ContractError):
        analyze_behavior(
            [record(1, files=("../escape.cpp",))], ["a.cpp"], config(), cutoff=CUTOFF
        )
    with pytest.raises(ContractError):
        analyze_behavior(
            [record(1)], ["a.cpp"], config(), cutoff=CUTOFF.replace(tzinfo=None)
        )


def test_order_and_repeated_authors_are_deterministic_below_bounds():
    records = [
        record(1),
        record(
            2,
            authors=("bob@example.com", "bob@example.com", "alice@example.com"),
            age=10,
        ),
    ]
    before = deepcopy(records)
    a = analyze_behavior(
        records, ["a.cpp"], config(pair_attribution="coauthor_trailers"), cutoff=CUTOFF
    )
    b = analyze_behavior(
        reversed(records),
        ["a.cpp"],
        config(pair_attribution="coauthor_trailers"),
        cutoff=CUTOFF,
    )
    assert a == b and records == before


def test_empty_history_has_no_perfect_ownership_or_coupling_claim():
    result = analyze_behavior([], ["a.cpp"], config(), cutoff=CUTOFF)
    assert result["history_status"] == "unavailable"
    assert by_file(result)["authors"] == []
    assert by_file(result)["offboarding"]["remaining_share"] is None


def test_actual_controlled_git_alias_bot_pair_rename_and_bulk_projection(
    tmp_path: Path,
):
    repo = git.Repo.init(tmp_path)

    def commit(index, author, paths, message):
        for path in paths:
            (tmp_path / path).write_text(f"int value_{index} = {index};\n")
        repo.index.add(paths)
        actor = git.Actor(author, author)
        date = datetime(2026, 11, index, 12, tzinfo=timezone.utc)
        return repo.index.commit(
            message, author=actor, committer=actor, author_date=date, commit_date=date
        )

    commit(1, "old-alice@example.com", ["a.cpp", "b.cpp"], "initial")
    commit(2, "build-bot@example.com", ["a.cpp"], "automated")
    commit(
        3,
        "bob@example.com",
        ["a.cpp", "b.cpp"],
        "paired\n\nCo-authored-by: Alice <alice@example.com>",
    )
    repo.git.mv("a.cpp", "renamed.cpp")
    actor = git.Actor("bob@example.com", "bob@example.com")
    date = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    repo.index.commit(
        "rename", author=actor, committer=actor, author_date=date, commit_date=date
    )
    scan = scan_history(repo)
    cfg = config(
        aliases={"old-alice@example.com": "alice@example.com"},
        bot_ids=["build-bot@example.com"],
        pair_attribution="coauthor_trailers",
        minimum_support=2,
    )
    result = analyze_behavior(
        records_from_scan(scan, cfg),
        scan.files,
        cfg,
        cutoff=CUTOFF,
        head=repo.head.commit.hexsha,
        history_limitations=scan.limitations,
    )
    assert {row["file"] for row in result["files"]} == {"renamed.cpp", "b.cpp"}
    assert result["coupling"][0]["support"] == 2
    assert "build-bot@example.com" not in {
        row["id"] for row in by_file(result, "renamed.cpp")["authors"]
    }
    assert result["counts"]["excluded_commits"]["bot_only"] == 1
    assert any(
        row["id"] == "alice@example.com"
        for row in by_file(result, "renamed.cpp")["authors"]
    )
    validate_behavior_report(result)


def test_optional_miner_document_preserves_original_output_and_reuses_one_scan(
    tmp_path, monkeypatch
):
    from cppulse.git_miner import main as main_module
    from cppulse.git_miner.main import run

    repo = git.Repo.init(tmp_path / "repo")
    source = Path(repo.working_tree_dir)
    (source / "a.cpp").write_text("int a = 0;\n")
    repo.index.add(["a.cpp"])
    actor = git.Actor("Alice", "alice@example.com")
    repo.index.commit(
        "controlled fixture",
        author=actor,
        committer=actor,
        author_date=CUTOFF,
        commit_date=CUTOFF,
    )
    output = tmp_path / "output"
    assert run(source, output, szz_cutoff=CUTOFF.isoformat()) == 0
    original = json.loads((output / "git_metrics.json").read_text())
    assert not (output / "git_behavior.json").exists()
    configured = tmp_path / "behavior.json"
    configured.write_text(json.dumps(config().document))
    seen = []
    scanner = main_module.scan_history

    def observed(repository, **options):
        seen.append(repository.working_tree_dir)
        return scanner(repository, **options)

    monkeypatch.setattr(main_module, "scan_history", observed)
    assert (
        run(
            source,
            output,
            behavior_config=configured,
            behavior_cutoff=CUTOFF.isoformat(),
            szz_cutoff=CUTOFF.isoformat(),
        )
        == 0
    )
    assert len(seen) == 1
    after = json.loads((output / "git_metrics.json").read_text())
    original["metadata"].pop("analyzed_at")
    after["metadata"].pop("analyzed_at")
    assert after == original
    behavior = json.loads((output / "git_behavior.json").read_text())
    assert behavior["head"] == repo.head.commit.hexsha
    assert by_file(behavior)["authors"][0]["id"] == "alice@example.com"
    validate_behavior_report(behavior)
    prior = (output / "git_metrics.json").read_bytes()
    assert run(source, output, behavior_config=configured) == 1
    assert (output / "git_metrics.json").read_bytes() == prior


@pytest.mark.parametrize(
    "mutation",
    ["shares", "fragmentation", "offboarding", "coupling", "counts", "component_mass"],
)
def test_modified_stored_behavior_calculations_are_rejected(mutation):
    result = analyze_behavior(
        [record(1, files=("a.cpp", "b.cpp")), record(2, files=("a.cpp", "b.cpp"))],
        ["a.cpp", "b.cpp"],
        config(),
        cutoff=CUTOFF,
    )
    if mutation == "shares":
        result["files"][0]["authors"][0]["share"] = 0.5
    elif mutation == "fragmentation":
        result["files"][0]["fragmentation"] = 0.5
    elif mutation == "offboarding":
        result["files"][0]["offboarding"]["remaining_share"] = 0.5
    elif mutation == "coupling":
        result["coupling"][0]["jaccard"] = 0.5
    elif mutation == "counts":
        result["counts"]["accepted_commits"] = 1
    else:
        result["components"][0]["ownership"]["weighted_changes"] = 1
    with pytest.raises(ContractError):
        validate_behavior_report(result)


def test_actual_bulk_exclusion_counts_non_cpp_changed_files(tmp_path: Path) -> None:
    repo = git.Repo.init(tmp_path)
    paths = ["a.cpp", *[f"generated-{i}.txt" for i in range(25)]]
    for path in paths:
        (tmp_path / path).write_text("controlled generated fixture\n")
    repo.index.add(paths)
    actor = git.Actor("Alice", "alice@example.com")
    commit = repo.index.commit(
        "bulk generated fixture",
        author=actor,
        committer=actor,
        author_date=CUTOFF,
        commit_date=CUTOFF,
    )
    scan = scan_history(repo)
    assert scan.commit_file_counts[commit.hexsha] == 26
    cfg = config(max_files_per_commit=20)
    result = analyze_behavior(
        records_from_scan(scan, cfg), scan.files, cfg, cutoff=CUTOFF
    )
    assert result["counts"]["excluded_commits"] == {"bulk": 1}
    assert by_file(result)["availability"] == "unavailable"


def test_extreme_recency_loss_remains_explicit_unavailable_not_perfect_ownership() -> (
    None
):
    result = analyze_behavior(
        [record(1, age=1)], ["a.cpp"], config(half_life_days=0.000001), cutoff=CUTOFF
    )
    assert result["history_status"] == "partial"
    assert by_file(result)["availability"] == "unavailable"
    assert by_file(result)["fragmentation"] is None
    assert any("underflow" in note for note in result["limitations"])


@pytest.mark.parametrize("path", ["src//a.cpp", "src/a.cpp/", "./a.cpp"])
def test_noncanonical_path_aliases_are_rejected(path: str) -> None:
    with pytest.raises(ContractError, match="canonical"):
        analyze_behavior([record(1, files=(path,))], [path], config(), cutoff=CUTOFF)


def test_body_coauthor_example_is_not_a_configured_footer_attribution(
    tmp_path: Path,
) -> None:
    repo = git.Repo.init(tmp_path)
    (tmp_path / "a.cpp").write_text("int value = 0;\n")
    repo.index.add(["a.cpp"])
    actor = git.Actor("Alice", "alice@example.com")
    repo.index.commit(
        "Document trailer format\n\nCo-authored-by: Example <example@example.com>\nThis is quoted documentation, not a trailer footer.",
        author=actor,
        committer=actor,
        author_date=CUTOFF,
        commit_date=CUTOFF,
    )
    scan = scan_history(repo)
    cfg = config(pair_attribution="coauthor_trailers")
    result = analyze_behavior(
        records_from_scan(scan, cfg), scan.files, cfg, cutoff=CUTOFF
    )
    assert [row["id"] for row in by_file(result)["authors"]] == ["alice@example.com"]
