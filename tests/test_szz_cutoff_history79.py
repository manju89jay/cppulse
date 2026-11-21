"""Controlled local histories for imperfect SZZ label cutoffs.

These authored histories test temporal selection, not predictive accuracy or
the authenticity of repository timestamps. Fixture commits remain local.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import git
import pytest

from cppulse.errors import ContractError
from cppulse.git_miner.history import scan_history
from cppulse.git_miner.history_cache import HistoryOptions
from cppulse.git_miner.szz_labeler import SZZLabeler


def repository(path: Path) -> git.Repo:
    """Create an isolated local repository without signing or hooks."""
    repo = git.Repo.init(path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "SZZ controlled fixture")
        config.set_value("user", "email", "szz@example.invalid")
        config.set_value("commit", "gpgsign", "false")
        config.set_value("core", "hooksPath", "/dev/null")
    return repo


def commit(repo: git.Repo, file: str, value: int | str, message: str, date: str) -> str:
    """Write deterministic source text and commit with an explicit date."""
    source = Path(repo.working_tree_dir) / file
    source.write_text(f"int value = {value};\n" if isinstance(value, int) else value)
    repo.index.add([file])
    actor = git.Actor("SZZ controlled fixture", "szz@example.invalid")
    # This GitPython version accepts aware datetime objects, while its string
    # parser does not accept the colon in an ISO UTC offset.
    instant = datetime.fromisoformat(date)
    item = repo.index.commit(
        message,
        author=actor,
        committer=actor,
        author_date=instant,
        commit_date=instant,
    )
    return item.hexsha


@pytest.fixture
def cutoff_history(tmp_path: Path) -> git.Repo:
    """One observed fix and one later fix, with both current files retained."""
    repo = repository(tmp_path / "repo")
    commit(repo, "old.cpp", 0, "Initial old code", "2020-01-01T00:00:00+00:00")
    commit(repo, "old.cpp", 1, "fix old defect", "2020-01-02T00:00:00+00:00")
    commit(repo, "new.cpp", 0, "Initial new code", "2020-01-03T00:00:00+00:00")
    commit(repo, "new.cpp", 1, "fix later defect", "2020-01-10T00:00:00+00:00")
    return repo


def test_explicit_cutoff_excludes_later_fix_labels(cutoff_history: git.Repo) -> None:
    root = Path(cutoff_history.working_tree_dir)
    scan = scan_history(cutoff_history)
    labeler = SZZLabeler(root)
    assert labeler.label(
        history=scan, cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc)
    ) == {"old.cpp": 1}
    assert labeler.analysis_cutoff == "2020-01-05T00:00:00Z"
    provenance = labeler.provenance
    notes = provenance["limitations"]
    assert provenance["analysis_cutoff"] == "2020-01-05T00:00:00Z"
    assert provenance["profile"] == "szz-keyword-whole-parent-file/1"
    assert provenance["cutoff_basis"] == "git_committed_date"
    assert provenance["cutoff_source"] == "explicit"
    assert provenance["cutoff_inclusive"] is True
    assert provenance["blame_scope"] == "whole_parent_file"
    assert provenance["label_kind"] == "imperfect_candidate"
    assert provenance["skipped_post_cutoff_fix_commits_encountered"] == 1
    assert any("2020-01-05T00:00:00Z" in item for item in notes)
    assert any("whole parent file" in item for item in notes)
    assert any("not validated future-defect" in item for item in notes)
    assert any("1 post-cutoff bug-fix" in item for item in notes)
    assert labeler.limitations == []


def test_post_cutoff_fix_does_not_consume_fix_cap(cutoff_history: git.Repo) -> None:
    labeler = SZZLabeler(Path(cutoff_history.working_tree_dir), max_fix_commits=1)
    assert labeler.label(cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc)) == {
        "old.cpp": 1
    }


def test_cutoff_is_inclusive_and_repeatable(cutoff_history: git.Repo) -> None:
    scan = scan_history(cutoff_history)
    root = Path(cutoff_history.working_tree_dir)
    labeler = SZZLabeler(root)
    cutoff = datetime(2020, 1, 2, tzinfo=timezone.utc)
    assert labeler.label(history=scan, cutoff=cutoff) == {"old.cpp": 1}
    before = list(labeler.limitations)
    provenance_before = dict(labeler.provenance)
    assert labeler.label(history=scan, cutoff=cutoff) == {"old.cpp": 1}
    assert labeler.limitations == before
    assert labeler.provenance == provenance_before


def test_before_first_fix_remains_no_label(cutoff_history: git.Repo) -> None:
    labeler = SZZLabeler(Path(cutoff_history.working_tree_dir))
    assert labeler.label(cutoff=datetime(2020, 1, 1, tzinfo=timezone.utc)) == {}


@pytest.mark.parametrize(
    "cutoff",
    [
        datetime(2020, 1, 2),
        "2020-01-02T00:00:00Z",
        True,
    ],
)
def test_invalid_cutoff_refuses_before_history_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cutoff: object
) -> None:
    from cppulse.git_miner import szz_labeler

    repo = repository(tmp_path / "repo")
    labeler = SZZLabeler(Path(repo.working_tree_dir))

    def forbidden_scan(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid cutoff caused a history read")

    monkeypatch.setattr(szz_labeler, "scan_history", forbidden_scan)
    with pytest.raises(ContractError):
        labeler.label(cutoff=cutoff)


def test_default_cutoff_records_invocation_and_rejects_future_fix(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path / "repo")
    commit(repo, "old.cpp", 0, "Initial", "2020-01-01T00:00:00+00:00")
    commit(repo, "old.cpp", 1, "fix observed defect", "2020-01-02T00:00:00+00:00")
    commit(repo, "future.cpp", 0, "Initial future", "2020-01-03T00:00:00+00:00")
    commit(repo, "future.cpp", 1, "fix future defect", "2099-01-01T00:00:00+00:00")
    before = datetime.now(timezone.utc)
    labeler = SZZLabeler(Path(repo.working_tree_dir))
    assert labeler.label() == {"old.cpp": 1}
    after = datetime.now(timezone.utc)
    observed = datetime.fromisoformat(labeler.analysis_cutoff.replace("Z", "+00:00"))
    assert before <= observed <= after
    assert labeler.provenance["cutoff_source"] == "invocation_time"
    assert any("Git timestamps" in item for item in labeler.provenance["limitations"])


@pytest.mark.parametrize(
    "origin_date, expected",
    [
        ("2020-01-10T00:00:00+00:00", {}),
        ("2020-01-05T00:00:00+00:00", {"a.cpp": 1}),
    ],
)
def test_non_monotonic_dates_apply_cutoff_to_origins_inclusively(
    tmp_path: Path, origin_date: str, expected: dict[str, int]
) -> None:
    """An earlier-dated fix cannot smuggle a later-dated ancestor origin."""
    repo = repository(tmp_path / "repo")
    commit(repo, "a.cpp", 0, "Initial implementation", origin_date)
    commit(repo, "a.cpp", 1, "fix defect", "2020-01-02T00:00:00+00:00")
    labeler = SZZLabeler(Path(repo.working_tree_dir))
    assert labeler.label(cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc)) == expected
    assert labeler.provenance["filtered_post_cutoff_origin_commits"] == (
        1 if not expected else 0
    )
    assert labeler.limitations == []


@pytest.mark.parametrize("embedded_prefix", ["", "\v"])
def test_source_text_cannot_spoof_a_porcelain_origin(
    tmp_path: Path, embedded_prefix: str
) -> None:
    """A real unrelated SHA embedded in source must not acquire blame credit."""
    repo = repository(tmp_path / "repo")
    decoy = commit(repo, "decoy.cpp", 0, "Unrelated", "2020-01-01T00:00:00+00:00")
    body = f"int value = 0;\n{embedded_prefix}{decoy} 1 1\n"
    origin = commit(repo, "a.cpp", body, "Initial a", "2020-01-02T00:00:00+00:00")
    fix = commit(
        repo,
        "a.cpp",
        body.replace("value = 0", "value = 1"),
        "fix defect",
        "2020-01-03T00:00:00+00:00",
    )
    labeler = SZZLabeler(Path(repo.working_tree_dir))
    assert labeler._blame_file(repo.commit(fix).parents[0], "a.cpp") == {origin}
    assert labeler.label(cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc)) == {
        "a.cpp": 1
    }


def test_unavailable_origin_metadata_remains_an_operational_gap(
    cutoff_history: git.Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed origin lookup cannot become a validated or clean label."""
    labeler = SZZLabeler(Path(cutoff_history.working_tree_dir))
    monkeypatch.setattr(labeler, "_blame_file", lambda *args: {"f" * 40})
    assert labeler.label(cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc)) == {}
    assert labeler.provenance["unavailable_origin_commits"] == 1
    assert any(
        "SZZ origin metadata unavailable" in item for item in labeler.limitations
    )


def test_origin_metadata_lookup_is_reused_across_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared origin identity requires one lookup, without another history scan."""
    repo = repository(tmp_path / "repo")
    actor = git.Actor("SZZ controlled fixture", "szz@example.invalid")
    for name in ["a.cpp", "b.cpp"]:
        (Path(repo.working_tree_dir) / name).write_text("int value = 0;\n")
    repo.index.add(["a.cpp", "b.cpp"])
    origin = repo.index.commit(
        "Initial files",
        author=actor,
        committer=actor,
        author_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        commit_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
    ).hexsha
    for name in ["a.cpp", "b.cpp"]:
        (Path(repo.working_tree_dir) / name).write_text("int value = 1;\n")
    repo.index.add(["a.cpp", "b.cpp"])
    repo.index.commit(
        "fix both defects",
        author=actor,
        committer=actor,
        author_date=datetime(2020, 1, 2, tzinfo=timezone.utc),
        commit_date=datetime(2020, 1, 2, tzinfo=timezone.utc),
    )
    scan = scan_history(repo)
    labeler = SZZLabeler(Path(repo.working_tree_dir))
    lookup = labeler._repo.commit
    observed = []

    def tracked_lookup(revision: str) -> git.Commit:
        observed.append(revision)
        return lookup(revision)

    monkeypatch.setattr(labeler._repo, "commit", tracked_lookup)
    assert labeler.label(
        history=scan, cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc)
    ) == {"a.cpp": 1, "b.cpp": 1}
    assert observed == [origin]


def test_ambient_git_overrides_cannot_redirect_origin_metadata(
    cutoff_history: git.Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Original labels remain available while ambient Git points elsewhere."""
    scan = scan_history(cutoff_history)
    unrelated = repository(tmp_path / "unrelated")
    commit(unrelated, "else.cpp", 7, "Elsewhere", "2020-01-01T00:00:00+00:00")
    monkeypatch.setenv("GIT_DIR", unrelated.git_dir)
    monkeypatch.setenv(
        "GIT_OBJECT_DIRECTORY", str(Path(unrelated.common_dir) / "objects")
    )
    labeler = SZZLabeler(Path(cutoff_history.working_tree_dir))
    assert labeler.label(
        history=scan, cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc)
    ) == {"old.cpp": 1}
    assert labeler.limitations == []
    assert labeler.provenance["unavailable_origin_commits"] == 0


def test_oversized_origin_is_refused_before_commit_metadata_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A small accepted fix cannot bypass its history producer's origin cap."""
    repo = repository(tmp_path / "repo")
    origin = commit(
        repo,
        "a.cpp",
        0,
        "Short summary\n\n" + "x" * 4096,
        "2020-01-01T00:00:00+00:00",
    )
    commit(repo, "a.cpp", 1, "fix observed defect", "2020-01-02T00:00:00+00:00")
    options = HistoryOptions.from_document({"max_record_bytes": 1024})
    scan = scan_history(repo, options=options)
    labeler = SZZLabeler(Path(repo.working_tree_dir))
    original_lookup = labeler._repo.commit

    def no_oversized_decode(revision: str) -> git.Commit:
        if revision == origin:
            pytest.fail(
                "Oversized origin metadata was decoded before enforcing its raw-object cap"
            )
        return original_lookup(revision)

    monkeypatch.setattr(labeler._repo, "commit", no_oversized_decode)
    assert (
        labeler.label(history=scan, cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc))
        == {}
    )
    assert labeler.provenance["origin_max_record_bytes"] == 1024
    assert labeler.provenance["unavailable_origin_commits"] == 1
    assert any(
        "SZZ origin metadata unavailable" in item and "max_record_bytes" in item
        for item in labeler.limitations
    )


def test_shared_history_cannot_mix_another_repositorys_origins(
    cutoff_history: git.Repo, tmp_path: Path
) -> None:
    """Same-shaped file histories from another object database must not mix."""
    unrelated = repository(tmp_path / "unrelated")
    labeler = SZZLabeler(Path(unrelated.working_tree_dir))
    with pytest.raises(ContractError, match="different repository"):
        labeler.label(
            history=scan_history(cutoff_history),
            cutoff=datetime(2020, 1, 5, tzinfo=timezone.utc),
        )
