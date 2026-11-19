"""Actual local controlled Git histories for shared checked stream/checkpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
import json
import sqlite3

import git
import pytest

from cppulse.errors import ContractError, IntegrityError
from cppulse.git_miner.history import scan_history
from cppulse.git_miner.history_cache import HistoryOptions
from cppulse.git_miner.miner import GitMiner
from cppulse.git_miner.silo_detector import SiloDetector
from cppulse.git_miner.szz_labeler import SZZLabeler
from test_git_behavior import config, CUTOFF
from cppulse.git_miner.behavior import analyze_behavior, records_from_scan


def commit(
    repo: git.Repo,
    number: int,
    *,
    file: str = "a.cpp",
    message: str = "change",
    author: str = "Alice",
):
    path = Path(repo.working_tree_dir) / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"int number_{number} = {number};\n")
    repo.index.add([file])
    actor = git.Actor(author, author.casefold() + "@example.com")
    date = CUTOFF - timedelta(days=20 - number)
    return repo.index.commit(
        message, author=actor, committer=actor, author_date=date, commit_date=date
    )


def repository(path: Path):
    repo = git.Repo.init(path)
    with repo.config_writer() as writer:
        writer.set_value("user", "name", "Controlled Fixture")
        writer.set_value("user", "email", "fixture@example.invalid")
        writer.set_value("commit", "gpgsign", "false")
    return repo


def options(path: Path, **changes):
    return HistoryOptions.from_document({"cache_dir": str(path), **changes})


def semantics(repo: git.Repo, scan):
    root = Path(repo.working_tree_dir)
    miner = GitMiner(root)
    miner._now = CUTOFF
    silo = SiloDetector(root)
    silo._now = CUTOFF
    silo._window_start = CUTOFF - timedelta(days=365)
    return {
        "metrics": [asdict(row) for row in miner.mine(history=scan)],
        "silos": [asdict(row) for row in silo.detect(history=scan)],
        "szz": SZZLabeler(root, max_fix_commits=500).label(history=scan),
        "changes": [
            (r.file, r.parent_file, r.commit.hexsha, r.insertions, r.deletions)
            for r in scan.changes
        ],
        "commits": [c.hexsha for c in scan.commits],
        "limitations": scan.limitations,
    }


def test_cold_warm_and_append_reuse_one_checked_stream_with_clean_equality(
    tmp_path: Path,
):
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2, message="fix defect", author="Bob")
    first = scan_history(repo, options=options(tmp_path / "cache"))
    baseline = semantics(repo, first)
    assert first.cache_info["records_extracted"] == 2
    warm = scan_history(repo, options=options(tmp_path / "cache"))
    assert warm.cache_info["mode"] == "warm"
    assert warm.cache_info["records_extracted"] == 0
    assert semantics(repo, warm) == baseline
    commit(repo, 3)
    appended = scan_history(repo, options=options(tmp_path / "cache"))
    assert appended.cache_info["mode"] == "append"
    assert appended.cache_info["records_extracted"] == 1
    assert appended.cache_info["records_reused"] == 2
    clean = scan_history(repo, options=options(tmp_path / "clean"))
    assert semantics(repo, appended) == semantics(repo, clean)


def test_rename_current_scope_and_delete_recreate_reproject_cached_raw_facts(
    tmp_path: Path,
):
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2, message="fix return")
    scan_history(repo, options=options(tmp_path / "cache"))
    repo.git.mv("a.cpp", "renamed.cpp")
    repo.index.commit("rename")
    renamed = scan_history(repo, options=options(tmp_path / "cache"))
    assert {r.file for r in renamed.changes} == {"renamed.cpp"}
    assert semantics(repo, renamed) == semantics(
        repo, scan_history(repo, options=options(tmp_path / "clean"))
    )
    (Path(repo.working_tree_dir) / "renamed.cpp").unlink()
    missing = scan_history(repo, options=options(tmp_path / "cache"))
    assert missing.files == set() and list(missing.changes) == []
    assert missing.cache_info["records_extracted"] == 0


def test_rewrite_never_reuses_obsolete_branch_projection(tmp_path: Path):
    repo = repository(tmp_path / "repo")
    original = commit(repo, 1)
    commit(repo, 2, author="Bob")
    before = scan_history(repo, options=options(tmp_path / "cache"))
    old_head = before.commits[0].hexsha
    repo.git.reset("--hard", original.hexsha)
    replacement = commit(repo, 3, author="Carol")
    rewritten = scan_history(repo, options=options(tmp_path / "cache"))
    assert rewritten.cache_info["mode"] == "rewrite"
    assert rewritten.commits[0].hexsha == replacement.hexsha
    assert old_head not in {row.hexsha for row in rewritten.commits}
    assert semantics(repo, rewritten) == semantics(
        repo, scan_history(repo, options=options(tmp_path / "clean"))
    )


def test_interrupted_accepted_records_resume_but_pending_does_not_pass(
    tmp_path: Path, monkeypatch
):
    from cppulse.git_miner import history_cache

    repo = repository(tmp_path / "repo")
    for i in range(5):
        commit(repo, i + 1)
    reached = []

    def interrupt(sha):
        reached.append(sha)
        if len(reached) == 2:
            raise RuntimeError("controlled interruption")

    monkeypatch.setattr(history_cache, "_accepted_checkpoint", interrupt)
    with pytest.raises(RuntimeError, match="controlled interruption"):
        scan_history(repo, options=options(tmp_path / "cache"))
    monkeypatch.setattr(history_cache, "_accepted_checkpoint", lambda _: None)
    resumed = scan_history(repo, options=options(tmp_path / "cache"))
    assert resumed.cache_info["mode"] == "resume"
    assert resumed.cache_info["records_extracted"] == 3
    assert resumed.cache_info["records_reused"] == 2
    assert semantics(repo, resumed) == semantics(
        repo, scan_history(repo, options=options(tmp_path / "clean"))
    )


def test_corrupted_raw_record_is_recollected_before_positive_reuse(tmp_path: Path):
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2)
    baseline = scan_history(repo, options=options(tmp_path / "cache"))
    before = semantics(repo, baseline)
    with sqlite3.connect(tmp_path / "cache/history-v1.sqlite3") as db:
        db.execute(
            "UPDATE raw_records SET payload=? WHERE commit_id=?",
            (b"{}", baseline.commits[0].hexsha),
        )
    recovered = scan_history(repo, options=options(tmp_path / "cache"))
    assert recovered.cache_info["recovered_records"] == 1
    assert recovered.cache_info["records_extracted"] == 1
    assert semantics(repo, recovered) == before


def test_shallow_boundary_change_rebuilds_and_agrees_after_deepen(tmp_path: Path):
    source = repository(tmp_path / "source")
    commit(source, 1)
    commit(source, 2)
    commit(source, 3)
    repo = git.Repo.clone_from(
        Path(source.working_tree_dir).as_uri(), tmp_path / "shallow", depth=1
    )
    shallow = scan_history(repo, options=options(tmp_path / "cache"))
    assert any("shallow" in note.lower() for note in shallow.limitations)
    repo.git.fetch("--unshallow")
    deep = scan_history(repo, options=options(tmp_path / "cache"))
    assert deep.cache_info["mode"] == "shallow_rebuild"
    assert not any("shallow" in note.lower() for note in deep.limitations)
    assert semantics(repo, deep) == semantics(
        repo, scan_history(repo, options=options(tmp_path / "clean"))
    )


def test_bounds_are_explicit_and_expanding_scope_matches_clean(tmp_path: Path):
    repo = repository(tmp_path / "repo")
    for i in range(5):
        commit(repo, i + 1)
    limited = scan_history(repo, options=options(tmp_path / "cache", max_commits=2))
    assert len(limited.commits) == 2
    assert limited.cache_info["history_truncated"] is True
    assert any("max_commits" in note for note in limited.limitations)
    expanded = scan_history(repo, options=options(tmp_path / "cache", max_commits=10))
    assert len(expanded.commits) == 5 and expanded.cache_info["records_extracted"] == 3
    assert semantics(repo, expanded) == semantics(
        repo, scan_history(repo, options=options(tmp_path / "clean"))
    )


def test_alias_window_and_cutoff_recompute_behavior_without_extraction(tmp_path: Path):
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2, author="Bob")
    original = scan_history(repo, options=options(tmp_path / "cache"))
    a = config(aliases={"alice@example.com": "merged@example.com"}, window_days=365)
    old = analyze_behavior(
        records_from_scan(original, a), original.files, a, cutoff=CUTOFF
    )
    current = scan_history(repo, options=options(tmp_path / "cache"))
    b = config(aliases={"alice@example.com": "bob@example.com"}, window_days=365)
    new = analyze_behavior(
        records_from_scan(current, b),
        current.files,
        b,
        cutoff=CUTOFF - timedelta(days=1),
    )
    assert current.cache_info["records_extracted"] == 0
    assert old["configuration_digest"] != new["configuration_digest"]
    assert len(old["files"][0]["authors"]) == 2 and len(new["files"][0]["authors"]) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"max_commits": 0},
        {"max_commits": True},
        {"max_record_bytes": 0},
        {"max_cache_bytes": 0},
        {"timeout_seconds": float("nan")},
        {"unknown_key": 1},
    ],
)
def test_invalid_history_options_reject_before_git_or_cache_writes(
    tmp_path: Path, changes
):
    with pytest.raises(ContractError):
        options(tmp_path / "absent", **changes)
    assert not (tmp_path / "absent").exists()


def test_cache_directory_symlinks_and_git_metadata_are_rejected(tmp_path: Path):
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(IntegrityError):
        scan_history(repo, options=options(tmp_path / "linked"))
    with pytest.raises(IntegrityError):
        scan_history(repo, options=options(Path(repo.git_dir) / "history"))
    assert list(outside.iterdir()) == []


def test_checkpoint_header_corruption_rebuilds_without_reusing_a_forged_view(
    tmp_path: Path,
):
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2)
    scan = scan_history(repo, options=options(tmp_path / "cache"))
    expected = semantics(repo, scan)
    with sqlite3.connect(tmp_path / "cache/history-v1.sqlite3") as db:
        db.execute("UPDATE views SET descriptor=? WHERE state='ready'", ("{}",))
    recovered = scan_history(repo, options=options(tmp_path / "cache"))
    assert recovered.cache_info["mode"] == "checkpoint_rebuild"
    assert recovered.cache_info["records_extracted"] == 0
    assert semantics(repo, recovered) == expected


def test_raw_byte_cap_is_incomplete_and_is_never_a_warm_positive_hit(tmp_path: Path):
    repo = repository(tmp_path / "repo")
    commit(repo, 1, message="x" * 3000)
    scan = scan_history(
        repo, options=options(tmp_path / "cache", max_record_bytes=1024)
    )
    assert any("max_record_bytes" in note for note in scan.limitations)
    assert list(scan.changes) == []
    repeated = scan_history(
        repo, options=options(tmp_path / "cache", max_record_bytes=1024)
    )
    assert repeated.cache_info["records_extracted"] == 1
    assert repeated.cache_info["records_reused"] == 0
    expanded = scan_history(
        repo, options=options(tmp_path / "cache", max_record_bytes=65536)
    )
    assert expanded.cache_info["mode"] == "profile_rebuild"
    assert len(list(expanded.changes)) == 1


def test_cache_capacity_failure_leaves_only_valid_accepted_checkpoints(tmp_path: Path):
    repo = repository(tmp_path / "repo")
    for index in range(3):
        commit(repo, index + 1, message="bounded large metadata " * 25000)
    with pytest.raises((IntegrityError, sqlite3.DatabaseError)):
        scan_history(
            repo,
            options=options(
                tmp_path / "cache", max_cache_bytes=1048576, max_record_bytes=1048576
            ),
        )
    database = tmp_path / "cache/history-v1.sqlite3"
    assert database.stat().st_size <= 1048576
    resumed = scan_history(
        repo,
        options=options(
            tmp_path / "cache", max_cache_bytes=8388608, max_record_bytes=1048576
        ),
    )
    clean = scan_history(
        repo,
        options=options(
            tmp_path / "clean", max_cache_bytes=8388608, max_record_bytes=1048576
        ),
    )
    assert semantics(repo, resumed) == semantics(repo, clean)


def test_unrelated_cache_database_is_preserved_and_rejected(tmp_path: Path):
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    target = tmp_path / "cache"
    target.mkdir()
    database = target / "history-v1.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")
        db.execute("INSERT INTO unrelated VALUES(?)", ("preserve unrelated user data",))
    before = database.read_bytes()
    with pytest.raises(IntegrityError):
        scan_history(repo, options=options(target))
    assert database.read_bytes() == before


def test_pipeline_shared_scan_is_not_repeated_by_silo_szz_or_metadata(
    tmp_path: Path, monkeypatch
):
    from cppulse.git_miner import main, miner, silo_detector, szz_labeler

    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2, message="fix defect")
    calls = []
    scanner = main.scan_history

    def observed(repository, **keywords):
        calls.append(repository.working_tree_dir)
        return scanner(repository, **keywords)

    def forbidden(*args, **kwargs):
        raise AssertionError("A producer repeated the complete history scan")

    monkeypatch.setattr(main, "scan_history", observed)
    for module in [miner, silo_detector, szz_labeler]:
        monkeypatch.setattr(module, "scan_history", forbidden)
    monkeypatch.setattr(git.Repo, "iter_commits", forbidden)
    output = tmp_path / "output"
    assert (
        main.run(
            Path(repo.working_tree_dir),
            output,
            history_options={"cache_dir": str(tmp_path / "cache")},
        )
        == 0
    )
    assert len(calls) == 1
    document = json.loads((output / "git_metrics.json").read_text())
    assert document["metadata"]["history_status"] == "available"
    assert document["metadata"]["total_commits"] == 2
    assert (
        document["knowledge_silos"]
        and document["file_metrics"][0]["szz_bug_introductions"] >= 1
    )
    assert (
        json.loads((output / "git_history.json").read_text())["records_extracted"] == 2
    )


def test_selected_immutable_revision_does_not_checkout_or_mutate_refs(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path / "repo")
    first = commit(repo, 1)
    second = commit(repo, 2)
    source_before = (Path(repo.working_tree_dir) / "a.cpp").read_bytes()
    selected = scan_history(
        repo, options=options(tmp_path / "cache"), revision=first.hexsha
    )
    assert selected.cache_info["head"] == first.hexsha
    assert [record.hexsha for record in selected.commits] == [first.hexsha]
    assert repo.head.commit.hexsha == second.hexsha
    assert (Path(repo.working_tree_dir) / "a.cpp").read_bytes() == source_before
    with pytest.raises(ContractError):
        scan_history(repo, options=options(tmp_path / "cache"), revision="HEAD~1")


def test_actual_nonstandard_sqlite_pages_cannot_bypass_file_budget(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    scan = scan_history(repo, options=options(tmp_path / "cache"))
    scan._cache_owner.close()
    database = tmp_path / "cache/history-v1.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA page_size=8192")
        db.execute("VACUUM")
        db.execute("CREATE TABLE filler(value BLOB)")
        db.execute("INSERT INTO filler VALUES(zeroblob(1200000))")
    before = database.read_bytes()
    assert len(before) > 1048576
    with pytest.raises(IntegrityError, match="byte budget"):
        scan_history(repo, options=options(tmp_path / "cache", max_cache_bytes=1048576))
    assert database.read_bytes() == before


def test_raw_failure_does_not_fallback_to_unbounded_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    from cppulse.git_miner.main import run

    repo = repository(tmp_path / "repo")
    for number in range(3):
        commit(repo, number + 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("Unbounded fallback traversal")

    monkeypatch.setattr(git.Repo, "iter_commits", forbidden)
    output = tmp_path / "output"
    assert (
        run(
            Path(repo.working_tree_dir),
            output,
            history_options={
                "cache_dir": str(Path(repo.git_dir) / "cache"),
                "max_commits": 1,
            },
        )
        == 1
    )
    assert not (output / "git_metrics.json").exists()


def test_worktree_attributes_do_not_change_commit_pinned_warm_facts(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2)
    original = scan_history(repo, options=options(tmp_path / "cache"))
    before = semantics(repo, original)
    (Path(repo.working_tree_dir) / ".gitattributes").write_text("*.cpp -diff\n")
    warm = scan_history(repo, options=options(tmp_path / "cache"))
    clean = scan_history(repo, options=options(tmp_path / "clean"))
    assert warm.cache_info["records_extracted"] == 0
    assert semantics(repo, warm) == semantics(repo, clean) == before


def test_info_attributes_are_explicit_raw_profile_inputs(tmp_path: Path) -> None:
    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2)
    original = scan_history(repo, options=options(tmp_path / "cache"))
    info = Path(repo.common_dir) / "info/attributes"
    info.parent.mkdir(exist_ok=True)
    info.write_text("*.cpp -diff\n")
    changed = scan_history(repo, options=options(tmp_path / "cache"))
    clean = scan_history(repo, options=options(tmp_path / "clean"))
    assert changed.cache_info["profile_digest"] != original.cache_info["profile_digest"]
    assert changed.cache_info["mode"] == "profile_rebuild"
    assert semantics(repo, changed) == semantics(repo, clean)
    assert any("Binary history" in note for note in changed.limitations)


def test_incompatible_optional_sidecars_are_preserved_and_refused(
    tmp_path: Path,
) -> None:
    from cppulse.git_miner.main import run

    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    output = tmp_path / "output"
    assert (
        run(
            Path(repo.working_tree_dir),
            output,
            behavior_config=config().document,
            behavior_cutoff=CUTOFF.isoformat(),
        )
        == 0
    )
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    plain = tmp_path / "plain"
    plain.mkdir()
    assert run(plain, output) == 1
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert run(Path(repo.working_tree_dir), output) == 1
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def test_attribute_change_during_collection_invalidates_unclosed_generation(
    tmp_path: Path, monkeypatch
) -> None:
    from cppulse.git_miner import history_cache

    repo = repository(tmp_path / "repo")
    commit(repo, 1)
    commit(repo, 2)
    info = Path(repo.common_dir) / "info/attributes"
    info.parent.mkdir(exist_ok=True)
    changed = []

    def mutate(_):
        if not changed:
            info.write_text("*.cpp -diff\n")
            changed.append(True)

    monkeypatch.setattr(history_cache, "_accepted_checkpoint", mutate)
    with pytest.raises(IntegrityError, match="changed during collection"):
        scan_history(repo, options=options(tmp_path / "cache"))
    with sqlite3.connect(tmp_path / "cache/history-v1.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM raw_records").fetchone()[0] == 0


@pytest.mark.parametrize(
    "phase", ["after_accept", "during_raw_transaction", "during_final_checkpoint"]
)
def test_actual_process_kill_recovers_only_durable_accepted_records(
    tmp_path: Path, phase: str
) -> None:
    import os
    import signal
    import subprocess
    import sys

    repo = repository(tmp_path / "repo")
    for number in range(4):
        commit(repo, number + 1)
    cache = tmp_path / "cache"
    injected = """
import os, signal
from cppulse.git_miner import history_cache as module
phase = PHASE
if phase == 'after_accept':
    accepted = []
    def stop(sha):
        accepted.append(sha)
        if len(accepted) == 2:
            os.kill(os.getpid(), signal.SIGKILL)
    module._accepted_checkpoint = stop
else:
    initialize = module.HistoryDatabase.__init__
    def selected_init(self, *args, **kwargs):
        initialize(self, *args, **kwargs)
        self.db.create_function('stop_owned_fixture', 0, lambda: os.kill(os.getpid(), signal.SIGKILL))
        if phase == 'during_raw_transaction':
            self.db.execute("CREATE TEMP TRIGGER interrupt_owned_raw AFTER INSERT ON raw_records BEGIN SELECT stop_owned_fixture(); END")
        else:
            self.db.execute("CREATE TEMP TRIGGER interrupt_owned_final AFTER UPDATE OF state ON views WHEN NEW.state='ready' BEGIN SELECT stop_owned_fixture(); END")
    module.HistoryDatabase.__init__ = selected_init
""".replace(
        "PHASE", repr(phase)
    )
    driver = (
        injected
        + "\nimport git\nfrom cppulse.git_miner.history import scan_history\nscan_history(git.Repo("
        + repr(str(Path(repo.working_tree_dir)))
        + '), options={"cache_dir":'
        + repr(str(cache))
        + "})\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "python")},
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == -signal.SIGKILL, result.stderr.decode()
    resumed = scan_history(repo, options=options(cache))
    clean = scan_history(repo, options=options(tmp_path / "clean"))
    assert resumed.cache_info["mode"] == "resume"
    assert (
        resumed.cache_info["records_reused"]
        == {
            "after_accept": 2,
            "during_raw_transaction": 0,
            "during_final_checkpoint": 4,
        }[phase]
    )
    assert semantics(repo, resumed) == semantics(repo, clean)
