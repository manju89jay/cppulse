"""Finite co-change eligibility and mathematical evidence constraints."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import git
import pytest

from cppulse.errors import ContractError
from cppulse.git_miner.behavior import (
    analyze_behavior,
    records_from_scan,
    validate_behavior_report,
)
from cppulse.git_miner.history import scan_history
from cppulse.identities import digest_json
from test_git_behavior import CUTOFF, config, record


@pytest.mark.parametrize("selected_cpp", [True, False])
def test_missing_all_path_total_cannot_qualify_bulk_as_selected_cpp_pair(
    tmp_path: Path,
    selected_cpp: bool,
) -> None:
    repo = git.Repo.init(tmp_path)
    paths = (["a.cpp", "b.cpp"] if selected_cpp else []) + [
        f"generated-{i}.txt" for i in range(3)
    ]
    for path in paths:
        (tmp_path / path).write_text("small controlled fixture\n")
    repo.index.add(paths)
    actor = git.Actor("Fixture", "fixture@example.invalid")
    repo.index.commit(
        "Bulk fixture",
        author=actor,
        committer=actor,
        author_date=CUTOFF,
        commit_date=CUTOFF,
    )
    scan = scan_history(repo)
    cfg = config(max_files_per_commit=2, minimum_support=1)
    qualified = analyze_behavior(
        records_from_scan(scan, cfg), scan.files, cfg, cutoff=CUTOFF
    )
    assert qualified["counts"]["excluded_commits"] == {"bulk": 1}
    assert qualified["coupling"] == []
    missing = replace(scan, commit_file_counts={})
    with pytest.raises(ContractError, match="changed-file"):
        analyze_behavior(
            records_from_scan(missing, cfg), scan.files, cfg, cutoff=CUTOFF
        )


def set_pair(pair: dict, *, support: int, left: int, right: int) -> None:
    pair.update(
        support=support,
        left_touches=left,
        right_touches=right,
        jaccard=support / (left + right - support),
        left_confidence=support / left,
        right_confidence=support / right,
    )


def test_ratio_consistent_impossible_file_intersection_is_rejected() -> None:
    result = analyze_behavior(
        [record(i, files=("a.cpp", "b.cpp")) for i in range(1, 5)],
        ["a.cpp", "b.cpp"],
        config(minimum_support=1),
        cutoff=CUTOFF,
    )
    set_pair(result["coupling"][0], support=1, left=4, right=4)
    with pytest.raises(ContractError, match="support"):
        validate_behavior_report(result)


@pytest.mark.parametrize("mutation", ["below_members", "above_members", "inconsistent"])
def test_component_pair_denominators_obey_member_bounds_and_one_universe(
    mutation: str,
) -> None:
    cfg = config(
        minimum_support=1,
        components={"A": ["a.cpp", "a2.cpp"], "B": ["b.cpp"], "C": ["c.cpp"]},
    )
    if mutation == "below_members":
        records = [record(i, files=("a.cpp", "b.cpp")) for i in range(1, 5)]
    elif mutation == "above_members":
        records = [
            record(1, files=("a.cpp", "b.cpp")),
            *[record(i, files=("c.cpp",)) for i in range(2, 5)],
        ]
    else:
        records = [
            record(1, files=("a.cpp", "b.cpp", "c.cpp")),
            record(2, files=("a2.cpp", "b.cpp", "c.cpp")),
            record(3, files=("d.cpp",)),
        ]
    result = analyze_behavior(
        records, ["a.cpp", "a2.cpp", "b.cpp", "c.cpp", "d.cpp"], cfg, cutoff=CUTOFF
    )
    pair = next(
        row
        for row in result["component_coupling"]
        if row["left"] == "A" and row["right"] == "B"
    )
    if mutation == "below_members":
        set_pair(pair, support=1, left=1, right=4)
    elif mutation == "above_members":
        set_pair(pair, support=1, left=4, right=1)
    else:
        set_pair(pair, support=1, left=1, right=2)
    with pytest.raises(ContractError, match="[Cc]omponent"):
        validate_behavior_report(result)


def test_declared_excluded_file_cannot_retain_observed_touches() -> None:
    result = analyze_behavior(
        [record(1, files=("a.cpp", "b.cpp"))],
        ["a.cpp", "b.cpp"],
        config(minimum_support=1),
        cutoff=CUTOFF,
    )
    result["configuration"]["exclude_paths"] = ["a.cpp"]
    result["configuration_digest"] = digest_json(result["configuration"])
    with pytest.raises(ContractError, match="[Ee]xcluded"):
        validate_behavior_report(result)


def test_component_coupling_uses_commit_touches_not_sum_of_member_file_touches() -> (
    None
):
    cfg = config(
        minimum_support=1, components={"A": ["a.cpp", "a2.cpp"], "B": ["b.cpp"]}
    )
    result = analyze_behavior(
        [
            record(1, files=("a.cpp", "a2.cpp", "b.cpp")),
            record(2, files=("a.cpp", "b.cpp")),
        ],
        ["a.cpp", "a2.cpp", "b.cpp"],
        cfg,
        cutoff=CUTOFF,
    )
    assert result["components"][0]["ownership"]["touches"] == 3
    assert result["component_coupling"][0]["left_touches"] == 2
    assert result["component_coupling"][0]["support"] == 2
    assert result["component_coupling"][0]["jaccard"] == 1
    validate_behavior_report(result)
