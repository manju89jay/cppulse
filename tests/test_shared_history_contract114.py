"""Real local Git -> shared history, plus explicitly authored contract negatives.

These histories are disposable local fixtures. Symbol associations below are
consumer-authored declarations and never evidence of an implemented symbol
history/native producer. No fixture commit is uploaded.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import hashlib
import os
from pathlib import Path

import cppulse
import git
import pytest

from cppulse.contracts import load_schema, validate
from cppulse.contracts.history_contract import (
    from_history_scan,
    validate_history_binding,
)
from cppulse.errors import ContractError, UnsupportedVersion
from cppulse.git_miner.behavior import BehaviorConfig
from cppulse.git_miner.history import scan_history
from cppulse.identities import digest_json

CUTOFF = datetime(2026, 11, 18, tzinfo=timezone.utc)
CONTEXT = "history-context114"


@pytest.fixture(autouse=True)
def installed_prefix_if_requested():
    expected = os.environ.get("CPPULSE_HISTORY_EXPECT_PREFIX114")
    if expected:
        assert (
            Path(cppulse.__file__).resolve().parent
            == Path(expected).resolve() / "cppulse"
        )


def config(**changes):
    document = {
        "version": "1.0.0",
        "window_days": 365,
        "half_life_days": 10,
        "max_commits": 100,
        "max_files_per_commit": 2,
        "max_pair_records": 100,
        "minimum_support": 1,
        "aliases": {"old-alice@example.test": "alice@example.test"},
        "bot_ids": ["robot@example.test"],
        "former_contributor_ids": ["bob@example.test"],
        "offboarding_ids": [],
        "teams": {},
        "components": {"api": ["api/*"], "core": ["b.cpp", "side.cpp"]},
        "exclude_paths": [],
        "exclude_commit_ids": [],
        "include_merges": False,
        "pair_attribution": "coauthor_trailers",
    }
    document.update(changes)
    return BehaviorConfig.from_document(document)


def repository(path):
    repo = git.Repo.init(path)
    with repo.config_writer() as writer:
        writer.set_value("user", "name", "Controlled Fixture")
        writer.set_value("user", "email", "fixture@example.test")
        writer.set_value("commit", "gpgsign", "false")
    return repo


def commit(
    repo,
    number,
    paths=("a.cpp", "b.cpp"),
    *,
    author="alice@example.test",
    message="change",
):
    root = Path(repo.working_tree_dir)
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"int value_{number} = {number};\n")
    if paths:
        repo.index.add(list(paths))
    actor = git.Actor(author, author)
    timestamp = CUTOFF - timedelta(days=20 - number)
    return repo.index.commit(
        message,
        author=actor,
        committer=actor,
        author_date=timestamp,
        commit_date=timestamp,
    )


def project(repo, cache, cfg=None):
    scan = scan_history(repo, options={"cache_dir": str(cache)})
    root = Path(repo.working_tree_dir)
    source = {
        "head": repo.head.commit.hexsha if repo.head.is_valid() else None,
        "tracked_cpp_bytes": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in sorted(scan.files)
        },
    }
    selected_digest = digest_json(source)
    (cache.parent / (cache.name + "-declared-source-inputs.json")).write_text(
        json.dumps({**source, "source_digest": selected_digest}, indent=2) + "\n"
    )
    return from_history_scan(
        scan,
        cfg or config(),
        source_digest=selected_digest,
        context_id=CONTEXT,
        repository_id="controlled-repository114",
        cutoff=CUTOFF,
        head=source["head"],
    )


@pytest.fixture(scope="module")
def actual_history(tmp_path_factory):
    base = tmp_path_factory.mktemp("shared-history114")
    repo = repository(base / "repo")
    root = commit(repo, 1, author="old-alice@example.test")
    pair = commit(
        repo,
        2,
        message="pair\n\nCo-authored-by: Bob <bob@example.test>\nCo-authored-by: Alias <old-alice@example.test>",
    )
    bot = commit(repo, 3, author="robot@example.test")
    bulk = commit(repo, 4, ("a.cpp", "b.cpp", "notes.txt"))
    (Path(repo.working_tree_dir) / "api").mkdir()
    repo.git.mv("a.cpp", "api/a.cpp")
    rename = commit(repo, 5, paths=(), message="rename only")
    main = repo.active_branch.name
    side = repo.create_head("side114")
    side.checkout()
    side_commit = commit(repo, 6, ("side.txt",))
    repo.heads[main].checkout()
    main_commit = commit(repo, 7, ("b.cpp",))
    date = (CUTOFF - timedelta(days=1)).isoformat()
    with repo.git.custom_environment(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date):
        repo.git.merge("--no-ff", "--no-edit", "-m", "controlled merge", side.name)
    merge = repo.head.commit.hexsha
    refs = repo.git.show_ref()
    document = project(repo, base / "cache")
    (base / "actual-shared-history.json").write_text(
        json.dumps(document, indent=2) + "\n"
    )
    assert repo.head.commit.hexsha == merge and repo.git.show_ref() == refs
    return document, {
        "root": root.hexsha,
        "pair": pair.hexsha,
        "bot": bot.hexsha,
        "bulk": bulk.hexsha,
        "rename": rename.hexsha,
        "side": side_commit.hexsha,
        "main": main_commit.hexsha,
        "merge": merge,
    }


def test_actual_scan_identity_rename_support_and_exclusions(actual_history):
    document, commits = actual_history
    validate("shared_history", document)
    validate_history_binding(
        document, source_digest=document["source_digest"], context_id=CONTEXT
    )
    people = {r["id"]: r for r in document["contributors"]}
    assert people["alice@example.test"]["aliases"] == ["old-alice@example.test"]
    assert people["bob@example.test"]["former"] is True
    assert people["robot@example.test"]["bot"] is True
    by_commit = {r["id"]: r for r in document["commits"]}
    assert by_commit[commits["pair"]]["participant_ids"] == [
        "alice@example.test",
        "bob@example.test",
    ]
    assert by_commit[commits["bot"]]["participant_ids"] == []
    assert by_commit[commits["bot"]]["excluded_reason"] == "bot_only"
    assert by_commit[commits["bulk"]]["total_files"] == 3
    assert len(by_commit[commits["bulk"]]["file_ids"]) == 2
    assert by_commit[commits["bulk"]]["excluded_reason"] == "bulk"
    assert by_commit[commits["merge"]]["excluded_reason"] == "merge"
    assert document["scope"]["observed_commits"] == 8
    assert by_commit[commits["side"]]["excluded_reason"] == "no_selected_files"
    assert document["scope"]["accepted_commits"] == 4
    assert document["scope"]["availability"] == "partial"
    files = {r["current_path"]: r for r in document["files"]}
    a, b = files["api/a.cpp"]["id"], files["b.cpp"]["id"]
    assert files["api/a.cpp"]["anchor_path"] == "a.cpp"
    assert files["api/a.cpp"]["anchor_commit_id"] == commits["root"]
    assert document["renames"] == [
        {
            "file_id": a,
            "commit_id": commits["rename"],
            "from_path": "a.cpp",
            "to_path": "api/a.cpp",
        }
    ]
    pair = next(
        r
        for r in document["coupling"]["pairs"]
        if r["entity_kind"] == "file" and {r["left_id"], r["right_id"]} == {a, b}
    )
    assert pair["commit_ids"] == sorted([commits["root"], commits["pair"]])
    assert pair["support"] == 2 and pair["left_touches"] == pair["right_touches"] == 3
    assert (
        document["symbol_history"]["availability"] == "unavailable"
        and document["symbols"] == []
    )
    assert document["producer"]["authenticated"] is False
    assert any("not proof of expertise" in value for value in document["limitations"])


def test_file_identity_survives_real_append_and_rename(tmp_path):
    repo = repository(tmp_path / "repo")
    root = commit(repo, 1)
    before = project(repo, tmp_path / "before", config(components={}))
    identity = next(r["id"] for r in before["files"] if r["current_path"] == "a.cpp")
    (Path(repo.working_tree_dir) / "api").mkdir()
    repo.git.mv("a.cpp", "api/a.cpp")
    commit(repo, 2, (), message="rename")
    commit(repo, 3, ("api/a.cpp",))
    after = project(repo, tmp_path / "after", config(components={}))
    row = next(r for r in after["files"] if r["current_path"] == "api/a.cpp")
    assert row["id"] == identity and row["anchor_commit_id"] == root.hexsha
    assert row["identity_scope"] == "complete_first_parent_lineage"


def test_actual_shallow_boundary_never_becomes_changed_file_support(tmp_path):
    source = repository(tmp_path / "source")
    commit(source, 1)
    commit(source, 2, ("a.cpp",))
    clone = git.Repo.clone_from(
        Path(source.working_tree_dir).as_uri(), tmp_path / "shallow", depth=1
    )
    first = project(clone, tmp_path / "first", config(components={}))
    assert first["scope"]["availability"] == "unavailable"
    assert first["scope"]["accepted_commits"] == 0
    assert first["commits"][0]["delta_availability"] == "unavailable"
    assert (
        first["commits"][0]["file_ids"] == []
        and first["commits"][0]["total_files"] is None
    )
    assert first["coupling"]["pairs"] == []
    later = commit(clone, 3, ("a.cpp",))
    second = project(clone, tmp_path / "second", config(components={}))
    assert second["scope"]["availability"] == "partial"
    assert second["scope"]["accepted_commits"] == 1
    files = {r["current_path"]: r for r in second["files"]}
    assert files["a.cpp"]["commit_ids"] == [later.hexsha]
    assert files["b.cpp"]["commit_ids"] == []
    assert second["coupling"]["pairs"] == []
    (tmp_path / "actual-shallow-history.json").write_text(
        json.dumps(second, indent=2) + "\n"
    )


def test_actual_empty_history_remains_defined_and_unavailable(tmp_path):
    repo = repository(tmp_path / "empty")
    document = project(repo, tmp_path / "cache", config(components={}))
    assert document["scope"]["observed_commits"] == 0
    assert document["scope"]["availability"] == "unavailable"
    assert (
        document["files"] == document["commits"] == document["coupling"]["pairs"] == []
    )


def authored_symbols(actual_history):
    original, commits = actual_history
    document = deepcopy(original)
    document["origin"] = "consumer_authored"
    document["producer"]["name"] = "consumer-authored"
    document["symbol_history"] = {
        "availability": "partial",
        "origin": "consumer_authored",
        "limitations": [
            "Consumer-authored synthetic symbol associations; no symbol producer executed."
        ],
    }
    file = next(r for r in document["files"] if r["current_path"] == "api/a.cpp")
    for key in ("example::work(int)", "example::helper()"):
        document["symbols"].append(
            {
                "id": "symbol-"
                + digest_json([document["repository_id"], file["id"], key])[:32],
                "file_id": file["id"],
                "anchor_key": key,
                "current_key": key,
                "previous_keys": [],
                "lineage": "declared",
                "availability": "partial",
                "commit_ids": [commits["pair"]],
                "origin": "consumer_authored",
                "limitations": [
                    "Synthetic consumer-authored association, not native/Git symbol provenance."
                ],
            }
        )
    left, right = sorted(s["id"] for s in document["symbols"])
    document["coupling"]["pairs"].append(
        {
            "entity_kind": "symbol",
            "left_id": left,
            "right_id": right,
            "commit_ids": [commits["pair"]],
            "support": 1,
            "left_touches": 1,
            "right_touches": 1,
        }
    )
    return document


def test_typed_symbol_fixture_is_explicitly_authored_not_a_real_producer(
    actual_history, tmp_path
):
    document = authored_symbols(actual_history)
    validate("shared_history", document)
    (tmp_path / "CONSUMER-AUTHORED-SYMBOL-DECLARATION.json").write_text(
        json.dumps(document, indent=2) + "\n"
    )
    assert document["origin"] == "consumer_authored"
    assert document["producer"]["authenticated"] is False
    unavailable = deepcopy(document)
    unavailable["symbol_history"]["availability"] = "unavailable"
    unavailable["coupling"]["pairs"] = [
        r for r in unavailable["coupling"]["pairs"] if r["entity_kind"] != "symbol"
    ]
    for row in unavailable["symbols"]:
        row.update(lineage="ambiguous", availability="unavailable", commit_ids=[])
    validate("shared_history", unavailable)


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_contributor",
        "alias_conflict",
        "unknown_contributor",
        "duplicate_participant",
        "bot_participant",
        "duplicate_commit",
        "duplicate_parent",
        "cyclic_ancestry",
        "unknown_file",
        "impossible_total",
        "wrong_exclusion",
        "wrong_observed_count",
        "wrong_accepted_count",
        "duplicate_file_path",
        "invalid_path",
        "unknown_anchor",
        "duplicate_rename",
        "invalid_rename_path",
        "disconnected_rename",
        "duplicate_support",
        "unknown_support",
        "inflated_support",
        "inflated_denominator",
        "missing_pair",
        "wrong_truncation",
        "component_overlap",
        "component_unknown_file",
        "component_wrong_support",
        "producer_authentication",
        "source_format",
        "unavailable_delta_with_changes",
    ],
)
def test_meaningful_history_contract_negatives(actual_history, tmp_path, case):
    original, _ = actual_history
    d = deepcopy(original)
    commit_row = next(
        r
        for r in d["commits"]
        if r["excluded_reason"] is None and len(r["file_ids"]) == 2
    )
    pair = next(r for r in d["coupling"]["pairs"] if r["entity_kind"] == "file")
    if case == "duplicate_contributor":
        d["contributors"].append(deepcopy(d["contributors"][0]))
    elif case == "alias_conflict":
        d["contributors"][-1]["aliases"] = ["old-alice@example.test"]
    elif case == "unknown_contributor":
        commit_row["declared_contributor_ids"] = ["unknown@example.test"]
    elif case == "duplicate_participant":
        commit_row["participant_ids"] *= 2
    elif case == "bot_participant":
        commit_row["participant_ids"].append("robot@example.test")
    elif case == "duplicate_commit":
        d["commits"].append(deepcopy(commit_row))
    elif case == "duplicate_parent":
        next(r for r in d["commits"] if r["parent_ids"])["parent_ids"] *= 2
    elif case == "cyclic_ancestry":
        next(r for r in d["commits"] if not r["parent_ids"])["parent_ids"] = [
            d["commits"][0]["id"]
        ]
    elif case == "unknown_file":
        commit_row["file_ids"].append("unknown-file")
    elif case == "impossible_total":
        commit_row["total_files"] = 1
    elif case == "wrong_exclusion":
        next(r for r in d["commits"] if r["excluded_reason"] == "bulk")[
            "excluded_reason"
        ] = None
    elif case == "wrong_observed_count":
        d["scope"]["observed_commits"] += 1
    elif case == "wrong_accepted_count":
        d["scope"]["accepted_commits"] += 1
    elif case == "duplicate_file_path":
        d["files"][1]["current_path"] = d["files"][0]["current_path"]
    elif case == "invalid_path":
        d["files"][0]["current_path"] = "../outside.cpp"
    elif case == "unknown_anchor":
        d["files"][0]["anchor_commit_id"] = "f" * 40
    elif case == "duplicate_rename":
        d["renames"].append(deepcopy(d["renames"][0]))
    elif case == "invalid_rename_path":
        d["renames"][0]["from_path"] = "../before.cpp"
    elif case == "disconnected_rename":
        d["renames"][0]["to_path"] = "unrelated.cpp"
    elif case == "duplicate_support":
        pair["commit_ids"].append(pair["commit_ids"][0])
    elif case == "unknown_support":
        pair["commit_ids"][0] = "f" * 40
    elif case == "inflated_support":
        pair["support"] += 1
    elif case == "inflated_denominator":
        pair["left_touches"] += 1
    elif case == "missing_pair":
        d["coupling"]["pairs"].remove(pair)
    elif case == "wrong_truncation":
        d["coupling"]["truncated"] = True
    elif case == "component_overlap":
        d["components"][0]["file_ids"].append(d["components"][1]["file_ids"][0])
    elif case == "component_unknown_file":
        d["components"][0]["file_ids"].append("missing-file")
    elif case == "component_wrong_support":
        d["components"][0]["commit_ids"].append("f" * 40)
    elif case == "producer_authentication":
        d["producer"]["authenticated"] = True
    elif case == "source_format":
        d["source_digest"] = "not-a-digest"
    elif case == "unavailable_delta_with_changes":
        commit_row["delta_availability"] = "unavailable"
    (tmp_path / (case + ".json")).write_text(json.dumps(d, indent=2) + "\n")
    with pytest.raises(ContractError):
        validate("shared_history", d)


@pytest.mark.parametrize(
    "case",
    [
        "unknown_symbol_file",
        "ambiguous_available",
        "duplicate_symbol",
        "unknown_symbol_commit",
        "actual_scan_claims_symbols",
        "native_origin",
        "available_without_support",
        "aggregate_full_from_partial",
    ],
)
def test_symbol_history_declarations_reject_false_availability(
    actual_history, tmp_path, case
):
    d = authored_symbols(actual_history)
    if case == "unknown_symbol_file":
        d["symbols"][0]["file_id"] = "missing-file"
    elif case == "ambiguous_available":
        d["symbols"][0]["lineage"] = "ambiguous"
    elif case == "duplicate_symbol":
        d["symbols"].append(deepcopy(d["symbols"][0]))
    elif case == "unknown_symbol_commit":
        d["symbols"][0]["commit_ids"] = ["f" * 40]
    elif case == "actual_scan_claims_symbols":
        d["origin"] = "git_scan"
        d["producer"]["name"] = "cppulse-history-scan"
    elif case == "native_origin":
        d["symbols"][0]["origin"] = "native"
    elif case == "available_without_support":
        for row in d["symbols"]:
            row["commit_ids"] = []
        d["coupling"]["pairs"] = [
            r for r in d["coupling"]["pairs"] if r["entity_kind"] != "symbol"
        ]
    elif case == "aggregate_full_from_partial":
        d["symbol_history"]["availability"] = "available"
    (tmp_path / (case + ".json")).write_text(json.dumps(d, indent=2) + "\n")
    with pytest.raises(ContractError):
        validate("shared_history", d)


def test_unknown_versions_options_and_expected_source_context_reject(actual_history):
    original, _ = actual_history
    assert load_schema("shared_history")["$id"].endswith(
        "/v2/shared_history.schema.json"
    )
    d = deepcopy(original)
    d["version"] = "3.0.0"
    with pytest.raises(UnsupportedVersion):
        validate("shared_history", d)
    d = deepcopy(original)
    d["invented_clean_flag"] = True
    with pytest.raises(ContractError):
        validate("shared_history", d)
    with pytest.raises(ContractError):
        validate_history_binding(original, source_digest="b" * 64, context_id=CONTEXT)
    with pytest.raises(ContractError):
        validate_history_binding(
            original,
            source_digest=original["source_digest"],
            context_id="different-context",
        )
