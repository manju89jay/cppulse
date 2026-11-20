"""Regression inputs are synthetic local-only histories with current timestamps."""

from __future__ import annotations

import json
from pathlib import Path

import git
import pytest

from src.main import run
from src.miner import GitMiner
from src.silo_detector import SiloDetector
from src.szz_labeler import SZZLabeler


@pytest.fixture()
def history(tmp_path: Path) -> git.Repo:
    """Create a synthetic repository without changing project Git state."""
    repo = git.Repo.init(tmp_path / "source")
    with repo.config_writer() as config:
        config.set_value("user", "name", "Synthetic Fixture Automation")
        config.set_value("user", "email", "fixture@example.invalid")
        config.set_value("commit", "gpgsign", "false")
    return repo


def commit_file(repo: git.Repo, path: str, content: str, message: str) -> None:
    """Commit one explicitly synthetic input using the actual current time."""
    (Path(repo.working_tree_dir) / path).write_text(content)
    repo.index.add([path])
    repo.index.commit(message)


def test_non_git_source_produces_explicit_unavailable_history(tmp_path: Path) -> None:
    """Static analysis is useful without a Git checkout, but history is unknown."""
    source = tmp_path / "plain"
    source.mkdir()
    (source / "a.cpp").write_text("void a() {}\n")
    output = tmp_path / "out"
    assert run(source, output) == 0
    document = json.loads((output / "git_metrics.json").read_text())
    assert document["metadata"]["history_status"] == "unavailable"
    assert document["metadata"]["total_commits"] == 0
    assert document["metadata"]["limitations"]
    assert document["file_metrics"] == []
    assert document["knowledge_silos"] == []


def test_deleted_files_are_not_current_metrics_silos_or_labels(
    history: git.Repo,
) -> None:
    """Historical paths cannot inflate the current analysis file universe."""
    root = Path(history.working_tree_dir)
    commit_file(
        history, "deleted.cpp", "int f() { return 0; }\n", "Synthetic initial code"
    )
    commit_file(
        history, "deleted.cpp", "int f() { return 1; }\n", "fix: synthetic return bug"
    )
    history.index.remove(["deleted.cpp"], working_tree=True)
    history.index.commit("Synthetic removal")
    commit_file(
        history, "current.cpp", "void current() {}\n", "Synthetic current source"
    )
    assert {metric.file for metric in GitMiner(root).mine()} == {"current.cpp"}
    assert {silo.file for silo in SiloDetector(root).detect()} == {"current.cpp"}
    assert SZZLabeler(root).label() == {}


def test_rename_preserves_history_under_current_identity(history: git.Repo) -> None:
    """An exact rename carries earlier change/contributor history to the new path."""
    root = Path(history.working_tree_dir)
    commit_file(
        history, "old.cpp", "int f() { return 0; }\n", "Synthetic initial source"
    )
    commit_file(
        history, "old.cpp", "int f() { return 1; }\n", "fix: synthetic return bug"
    )
    history.git.mv("old.cpp", "new.cpp")
    history.index.commit("Synthetic rename")
    metrics = GitMiner(root).mine()
    assert [metric.file for metric in metrics] == ["new.cpp"]
    assert metrics[0].change_frequency == 3
    assert metrics[0].bug_fix_commits == 1
    assert metrics[0].lines_of_code == 1
    assert {silo.file for silo in SiloDetector(root).detect()} == {"new.cpp"}
    assert SZZLabeler(root).label().get("new.cpp", 0) >= 1


def test_deleted_worktree_file_is_not_a_live_metric(history: git.Repo) -> None:
    """An unstaged deletion is still absent from the analyzed tree."""
    root = Path(history.working_tree_dir)
    commit_file(history, "a.cpp", "void a() {}\n", "Synthetic initial source")
    (root / "a.cpp").unlink()
    assert GitMiner(root).mine() == []
    assert SiloDetector(root).detect() == []


def test_keyword_does_not_match_unrelated_substrings() -> None:
    """A synthetic fixture or prefix change is not automatically a bug fix."""
    assert not GitMiner._is_bug_fix_commit("Add synthetic fixture and prefix")
    assert not SZZLabeler._is_bug_fix("Add synthetic fixture and prefix")
    assert GitMiner._is_bug_fix_commit("fix: handle error")
    assert SZZLabeler._is_bug_fix("BUG: fix overflow")


def test_shallow_history_is_explicitly_partial(
    history: git.Repo, tmp_path: Path
) -> None:
    """A depth-one checkout cannot claim a complete history scan."""
    commit_file(history, "a.cpp", "void a() {}\n", "Synthetic first change")
    commit_file(history, "a.cpp", "void a() { }\n", "Synthetic second change")
    clone = tmp_path / "shallow"
    git.Repo.clone_from(Path(history.working_tree_dir).as_uri(), clone, depth=1)
    output = tmp_path / "out"
    assert run(clone, output) == 0
    document = json.loads((output / "git_metrics.json").read_text())
    assert document["metadata"]["history_status"] == "partial"
    assert any(
        "shallow" in note.lower() for note in document["metadata"]["limitations"]
    )


def test_recreated_name_does_not_inherit_deleted_lineage(history: git.Repo) -> None:
    """A later new file at an old path is a new history lineage."""
    root = Path(history.working_tree_dir)
    commit_file(history, "a.cpp", "int old() { return 0; }\n", "Synthetic old source")
    history.index.remove(["a.cpp"], working_tree=True)
    history.index.commit("Synthetic removal")
    commit_file(history, "a.cpp", "void replacement() {}\n", "Synthetic replacement")
    metric = GitMiner(root).mine()[0]
    assert metric.change_frequency == 1
    assert metric.lines_added_total == 1
    assert metric.lines_removed_total == 0


def test_extended_cpp_headers_are_included(history: git.Repo) -> None:
    """Current header/template input suffixes match analyzer discovery."""
    root = Path(history.working_tree_dir)
    for suffix in ("hh", "ipp", "inl", "tpp"):
        commit_file(
            history, f"include.{suffix}", "// synthetic header\n", "Synthetic header"
        )
    assert {m.file for m in GitMiner(root).mine()} == {
        "include.hh",
        "include.ipp",
        "include.inl",
        "include.tpp",
    }


def test_merge_history_discloses_lineage_limit(
    history: git.Repo, tmp_path: Path
) -> None:
    """First-parent deltas are not presented as complete cross-branch lineage."""
    root = Path(history.working_tree_dir)
    commit_file(history, "root.cpp", "void root() {}\n", "Synthetic root source")
    initial_branch = history.active_branch.name
    history.git.checkout("-b", "synthetic-side")
    commit_file(history, "side.cpp", "void side() {}\n", "Synthetic side source")
    history.git.checkout(initial_branch)
    commit_file(history, "main.cpp", "void main_side() {}\n", "Synthetic main source")
    history.git.merge("synthetic-side", no_ff=True, m="Synthetic merge")
    output = tmp_path / "out"
    assert run(root, output) == 0
    document = json.loads((output / "git_metrics.json").read_text())
    assert document["metadata"]["history_status"] == "partial"
    assert any("merge" in note.lower() for note in document["metadata"]["limitations"])
    assert {metric["file"] for metric in document["file_metrics"]} == {
        "root.cpp",
        "main.cpp",
        "side.cpp",
    }


def test_tracked_directory_symlink_cannot_read_external_files(
    history: git.Repo, tmp_path: Path
) -> None:
    """Replacing a tracked parent directory must not import outside file contents."""
    root = Path(history.working_tree_dir)
    (root / "nested").mkdir()
    commit_file(
        history, "nested/a.cpp", "void inside() {}\n", "Synthetic internal source"
    )
    (root / "nested/a.cpp").unlink()
    (root / "nested").rmdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "a.cpp").write_text("// external synthetic content\n" * 20)
    (root / "nested").symlink_to(external, target_is_directory=True)
    miner = GitMiner(root)
    assert miner.mine() == []
    assert any("symlink" in note.lower() for note in miner.limitations)
    assert SiloDetector(root).detect() == []
    assert SZZLabeler(root).label() == {}
    output = tmp_path / "out"
    assert run(root, output) == 0
    document = json.loads((output / "git_metrics.json").read_text())
    assert document["metadata"]["history_status"] == "partial"
    assert any(
        "symlink" in note.lower() for note in document["metadata"]["limitations"]
    )
    assert document["file_metrics"] == []


def test_tracked_leaf_symlink_is_explicitly_excluded(
    history: git.Repo, tmp_path: Path
) -> None:
    """A tracked leaf link is excluded and its omission is recorded."""
    root = Path(history.working_tree_dir)
    commit_file(history, "a.cpp", "void inside() {}\n", "Synthetic source")
    (root / "a.cpp").unlink()
    external = tmp_path / "outside.cpp"
    external.write_text("void outside() {}\n")
    (root / "a.cpp").symlink_to(external)
    miner = GitMiner(root)
    assert miner.mine() == []
    assert miner.limitations == ["Skipped tracked symlink path: a.cpp."]


def test_internal_directory_symlink_is_not_a_second_source_identity(
    history: git.Repo,
) -> None:
    """Even an in-root symlink cannot duplicate one input under a tracked name."""
    root = Path(history.working_tree_dir)
    (root / "nested").mkdir()
    commit_file(history, "nested/a.cpp", "void a() {}\n", "Synthetic source")
    (root / "nested/a.cpp").unlink()
    (root / "nested").rmdir()
    (root / "target").mkdir()
    (root / "target/a.cpp").write_text("void target() {}\n")
    (root / "nested").symlink_to(root / "target", target_is_directory=True)
    miner = GitMiner(root)
    assert miner.mine() == []
    assert any("symlink" in note.lower() for note in miner.limitations)
