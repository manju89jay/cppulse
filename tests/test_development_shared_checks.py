"""The facade preserves shared component tooling and its prerequisite facts."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import time
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runner() -> ModuleType:
    """Load the shared check definitions independently of facade rendering."""
    spec = importlib.util.spec_from_file_location(
        "shared_development_tests", ROOT / "scripts/check_local.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_native_format_is_check_only_and_paths_are_literal(
    runner: ModuleType, tmp_path: Path
) -> None:
    source = tmp_path / "analyzer-core/src/file with spaces.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main() {}\n")
    fixtures = source.parent.parent / "tests/fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "intentional.cpp").write_text("int intentional;\n")
    checks = runner.build_checks(
        tmp_path, {"format"}, tmp_path / "evidence", clang_format="selected-formatter"
    )
    check = next(row for row in checks if row.name == "native-format")
    assert check.argv == (
        "selected-formatter",
        "--dry-run",
        "--Werror",
        "--style=file",
        "analyzer-core/src/file with spaces.cpp",
    )


def test_native_integration_has_build_and_test_prerequisites(
    runner: ModuleType, tmp_path: Path
) -> None:
    checks = runner.build_checks(tmp_path, {"integration"}, tmp_path / "evidence")
    names = [row.name for row in checks]
    assert names.index("analyzer-tests") < names.index("native-integration")
    assert names.index("cli-tests") < names.index("native-integration")
    integration = checks[-1]
    assert integration.depends_on == (
        "analyzer-tests",
        "cli-tests",
        "native-integration-dependencies",
    )
    assert str(tmp_path / "evidence/native-demo") in integration.argv


def test_scope_integrity_guard_is_ordinary_check_not_completion_claim(
    runner: ModuleType, tmp_path: Path
) -> None:
    checks = runner.build_checks(tmp_path, {"generated"}, tmp_path / "evidence")
    guard = next(row for row in checks if row.name == "delivery-ledger")
    assert guard.argv[-1] == "scripts/verify_delivery.py"
    assert "--require-complete" not in guard.argv


def test_missing_pdf_development_capability_is_blocked_not_a_product_failure(
    runner: ModuleType, tmp_path: Path
) -> None:
    check = runner.Check(
        "required-capability",
        "integration",
        (
            sys.executable,
            "-c",
            "import deliberately_absent_cppulse_development_dependency",
        ),
        tmp_path,
        availability_probe=True,
    )
    result = runner.run_check(check, tmp_path / "evidence", os.environ.copy(), tmp_path)
    assert result["status"] == "blocked"
    assert result["returncode"] != 0
    assert "ModuleNotFoundError" in Path(result["log"]).read_text()


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="POSIX process-group proof uses Linux /proc",
)
def test_cancelled_developer_command_terminates_spawned_children(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "child.pid"
    script = "import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)"
    check = runner.Check(
        "cancelled", "root", (sys.executable, "-c", script, str(marker)), tmp_path
    )

    def interrupt(process: object) -> int:
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "wait_command", interrupt)
    result = runner.run_check(check, tmp_path / "evidence", os.environ.copy(), tmp_path)
    assert result["status"] == "interrupted"
    assert runner.exit_status([result]) == 130
    child = Path("/proc") / marker.read_text() / "stat"
    deadline = time.monotonic() + 3
    while (
        child.exists()
        and child.read_text().split()[2] != "Z"
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert not child.exists() or child.read_text().split()[2] == "Z"
