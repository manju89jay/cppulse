"""Candidate text-package checks; these do not close clean-session AC-16."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

import pytest

from cppulse.cli import _parser

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrations/skill"
SPEC = importlib.util.spec_from_file_location("skill_package", SOURCE / "package.py")
assert SPEC is not None and SPEC.loader is not None
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)


def test_candidate_skill_archive_is_deterministic_text_only(tmp_path: Path) -> None:
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    assert PACKAGER.package_skill(SOURCE, first) == PACKAGER.package_skill(
        SOURCE, second
    )
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == set(PACKAGER.FILES)
        assert archive.namelist().count("SKILL.md") == 1
        assert not any(
            name.endswith((".py", ".exe", ".so", ".dll", ".whl"))
            for name in archive.namelist()
        )
        for name in archive.namelist():
            assert archive.read(name).decode("utf-8") == (SOURCE / name).read_text()
    with pytest.raises(FileExistsError):
        PACKAGER.package_skill(SOURCE, first)


def test_command_metadata_parses_against_actual_public_candidate_cli(capsys) -> None:
    metadata = json.loads((SOURCE / "references/commands.json").read_text())
    assert metadata["maturity"] == "candidate-preflight"
    for argv in metadata["commands"]:
        if argv == ["--version"]:
            with pytest.raises(SystemExit) as raised:
                _parser().parse_args(argv)
            assert raised.value.code == 0
        else:
            parsed = _parser().parse_args(argv)
            assert parsed.command == argv[0]
    capsys.readouterr()


@pytest.mark.parametrize("mutation", ["binary", "oversize", "symlink"])
def test_packager_refuses_unsafe_or_nontext_inputs(
    tmp_path: Path, mutation: str
) -> None:
    source = tmp_path / "source"
    shutil.copytree(SOURCE, source)
    path = source / "references/commands.md"
    if mutation == "binary":
        path.write_bytes(b"\0binary")
    elif mutation == "oversize":
        path.write_bytes(b"a" * (PACKAGER.MAX_FILE_BYTES + 1))
    else:
        path.unlink()
        path.symlink_to(SOURCE / "references/commands.md")
    with pytest.raises(ValueError):
        PACKAGER.package_skill(source, tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()


def test_skill_preserves_candidate_historical_and_execution_boundaries() -> None:
    text = (SOURCE / "SKILL.md").read_text()
    assert "candidate preflight" in text
    assert "not a released-command qualification" in text
    assert "Loading it installs no executable" in text
    assert "historical" in text and "current-source" in text
    assert "Do not clone/bootstrap" in text
    assert "separate" in text and "publish" in text
    assert "unknown" in text and "failed" in text
    assert (SOURCE / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
