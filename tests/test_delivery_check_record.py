"""Exercise real subprocess evidence and source-race detection."""

from pathlib import Path
import subprocess
import sys

from scripts.record_delivery_check import record_check


def _checkout(path: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(path)], check=True)
    (path / "input.py").write_text("original\n")


def test_literal_argv_and_nonzero_check_are_retained(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    _checkout(root)
    command = [
        sys.executable,
        "-c",
        "import sys; print(sys.argv[1]); sys.exit(7)",
        "$(must_not_execute);literal",
    ]
    result = record_check(root, command, ["input.py"], root / "review/nonzero", 10)
    assert result["status"] == "failed"
    assert result["exit_code"] == 7
    assert result["source_stable"] is True
    assert (root / result["log"]).read_text() == "$(must_not_execute);literal\n"
    assert not (root / "must_not_execute").exists()


def test_check_success_is_not_accepted_after_a_source_race(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    _checkout(root)
    result = record_check(
        root,
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('input.py').write_text('changed')",
        ],
        ["input.py"],
        root / "review/source-race",
        10,
    )
    assert result["exit_code"] == 0
    assert result["status"] == "stale"
    assert result["source_stable"] is False
    assert result["source_files_after"] != result["source_files"]
