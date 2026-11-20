"""Observable contracts for one truthful local developer entry point."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

ROOT = next(
    parent for parent in Path(__file__).parents if (parent / "TASK_SPEC.md").is_file()
)


@pytest.fixture
def dev() -> ModuleType:
    """Load only the selected source tool, not an unrelated installed module."""
    spec = importlib.util.spec_from_file_location(
        "cppulse_test_dev", ROOT / "tools/dev.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the public developer command from an arbitrary directory."""
    return subprocess.run(
        [sys.executable, str(ROOT / "tools/dev.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_doctor_outside_checkout_does_not_execute_project_commands(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "project-must-not-run"
    (tmp_path / "CMakeLists.txt").write_text(
        f"execute_process(COMMAND touch {marker})\n"
    )
    result = cli("doctor", "--format", "json", cwd=tmp_path)
    assert result.returncode in (0, 2)
    document = json.loads(result.stdout)
    assert document["root"] == str(ROOT)
    assert document["tools"]["python"]["available"]
    assert not marker.exists()


def test_full_plan_contains_unskippable_package_and_benchmark_work(
    tmp_path: Path,
) -> None:
    result = cli(
        "verify", "--scope", "full", "--plan", "--format", "json", cwd=tmp_path
    )
    assert result.returncode == 0
    document = json.loads(result.stdout)
    assert document["status"] == "planned"
    assert document["exit_status"] is None
    names = {row["name"] for row in document["checks"]}
    assert {
        "native-format",
        "root-tests",
        "analyzer-tests",
        "cli-tests",
        "git-miner-tests",
        "predictor-tests",
        "report-engine-tests",
        "dashboard-tests",
        "dashboard-build",
        "native-integration",
        "candidate-integrity",
        "installed-smoke",
        "reference-benchmarks",
    } <= names
    assert all(row["status"] == "planned" for row in document["checks"])


def test_full_cannot_be_reduced_to_one_selected_section(tmp_path: Path) -> None:
    result = cli(
        "verify", "--scope", "full", "--section", "root", "--plan", cwd=tmp_path
    )
    assert result.returncode == 2
    assert "full" in result.stderr.lower()


def test_full_cannot_be_reduced_to_one_selected_component(tmp_path: Path) -> None:
    result = cli(
        "verify", "--scope", "full", "--component", "predictor", "--plan", cwd=tmp_path
    )
    assert result.returncode == 2
    assert "full" in result.stderr.lower()


def test_explicit_ci_component_uses_canonical_coverage_command(tmp_path: Path) -> None:
    result = cli(
        "verify",
        "--scope",
        "changed",
        "--section",
        "python",
        "--component",
        "git-miner",
        "--plan",
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    document = json.loads(result.stdout)
    assert [check["name"] for check in document["checks"]] == ["git-miner-tests"]
    argv = document["checks"][0]["argv"]
    assert "--cov=src" in argv
    assert "--cov=cppulse.git_miner" in argv
    assert any(value.startswith("--cov-report=xml:") for value in argv)
    assert any("subset" in value.lower() for value in document["limitations"])


def test_changed_plan_declares_conservative_source_closure(tmp_path: Path) -> None:
    result = cli(
        "verify", "--scope", "changed", "--plan", "--format", "json", cwd=tmp_path
    )
    assert result.returncode == 0
    document = json.loads(result.stdout)
    assert document["scope"] == "changed"
    assert any("conservative" in value.lower() for value in document["limitations"])
    assert all(row["status"] == "planned" for row in document["checks"])


def test_full_missing_package_inputs_cannot_pass(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = dev.local_runner()
    checks = [
        runner.Check(
            "source-fact", "root", (sys.executable, "-c", "print('executed')"), tmp_path
        )
    ]
    monkeypatch.setattr(dev, "source_checks", lambda *args, **kwargs: checks)
    result = dev.main(
        [
            "verify",
            "--scope",
            "full",
            "--output-dir",
            str(tmp_path / "evidence"),
            "--format",
            "json",
        ]
    )
    assert result == 2
    document = json.loads((tmp_path / "evidence/development-results.json").read_text())
    assert document["status"] == "blocked"
    assert document["checks"][0]["status"] == "passed"
    for name in ["candidate-integrity", "installed-smoke", "reference-benchmarks"]:
        assert (
            next(row for row in document["checks"] if row["name"] == name)["status"]
            == "blocked"
        )


def test_invalid_benchmark_input_preserves_completed_source_facts(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = dev.local_runner()
    check = runner.Check(
        "source-fact", "root", (sys.executable, "-c", "pass"), tmp_path
    )
    monkeypatch.setattr(dev, "source_checks", lambda *args, **kwargs: [check])
    suite = tmp_path / "invalid-suite.json"
    suite.write_text("{invalid JSON")
    assert (
        dev.main(
            [
                "verify",
                "--scope",
                "full",
                "--benchmark-suite",
                str(suite),
                "--output-dir",
                str(tmp_path / "evidence"),
                "--format",
                "json",
            ]
        )
        == 2
    )
    document = json.loads((tmp_path / "evidence/development-results.json").read_text())
    assert document["checks"][0]["status"] == "passed"
    benchmark = next(
        row for row in document["checks"] if row["name"] == "reference-benchmarks"
    )
    assert benchmark["status"] == "blocked"
    assert benchmark["reason"]


def test_full_intermediate_record_cannot_look_passed_before_package_checks(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = dev.local_runner()
    check = runner.Check(
        "source-fact", "root", (sys.executable, "-c", "pass"), tmp_path
    )
    monkeypatch.setattr(dev, "source_checks", lambda *args, **kwargs: [check])
    observed: list[dict[str, object]] = []
    publish = dev._publish

    def observe(document: dict[str, object], output: Path) -> None:
        observed.append(json.loads(json.dumps(document)))
        publish(document, output)

    monkeypatch.setattr(dev, "_publish", observe)
    assert (
        dev.main(
            [
                "verify",
                "--scope",
                "full",
                "--output-dir",
                str(tmp_path / "evidence"),
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert observed
    assert all(record["status"] != "passed" for record in observed)


def test_developer_evidence_cannot_be_written_into_project_git_metadata(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    monkeypatch.setattr(dev, "ROOT", checkout)
    with pytest.raises(ValueError, match="source|review|output|checkout"):
        dev._new_output(checkout / ".git" / "development-evidence", "verify")


def test_failed_source_cannot_be_hidden_by_successful_independent_work(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = dev.local_runner()
    checks = [
        runner.Check(
            "failed", "root", (sys.executable, "-c", "raise SystemExit(7)"), tmp_path
        ),
        runner.Check(
            "independent", "root", (sys.executable, "-c", "print('observed')"), tmp_path
        ),
    ]
    monkeypatch.setattr(dev, "source_checks", lambda *args, **kwargs: checks)
    assert (
        dev.main(
            [
                "verify",
                "--scope",
                "changed",
                "--output-dir",
                str(tmp_path / "evidence"),
                "--format",
                "json",
            ]
        )
        == 1
    )
    document = json.loads((tmp_path / "evidence/development-results.json").read_text())
    assert [row["status"] for row in document["checks"]] == ["failed", "passed"]


def test_generator_is_explicit_and_keeps_draft_status(tmp_path: Path) -> None:
    result = cli(
        "new-adapter",
        "example-tool",
        "--destination",
        str(tmp_path),
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    location = Path(json.loads(result.stdout)["path"])
    assert location == tmp_path / "example-tool"
    assert "NotImplementedError" in (location / "adapter.py").read_text()
    assert "incomplete" in (location / "README.md").read_text().lower()


def test_release_without_explicit_dry_run_is_rejected(tmp_path: Path) -> None:
    result = cli("release", "--candidate", str(tmp_path), cwd=tmp_path)
    assert result.returncode == 2
    assert "dry-run" in result.stderr


def test_rejects_candidate_modification_before_release_review(
    dev: ModuleType, tmp_path: Path
) -> None:
    artifact = tmp_path / "payload.txt"
    artifact.write_text("changed payload")
    (tmp_path / "SHA256SUMS").write_text("0" * 64 + "  payload.txt\n")
    with pytest.raises(ValueError, match="[Hh]ash|checksum|integrity"):
        dev.verify_candidate(tmp_path)


def test_unknown_benchmark_suite_cannot_claim_measurement_success(
    tmp_path: Path,
) -> None:
    result = cli(
        "benchmark",
        "--suite",
        "reference",
        "--output-dir",
        str(tmp_path / "evidence"),
        cwd=tmp_path,
    )
    if not (ROOT / "tools/benchmarks/reference.json").exists():
        assert result.returncode == 2
        assert (
            "unavailable" in result.stderr.lower() or "missing" in result.stderr.lower()
        )


def test_doctor_and_plan_leave_project_git_refs_unchanged(tmp_path: Path) -> None:
    before = subprocess.check_output(["git", "for-each-ref"], cwd=ROOT)
    cli("doctor", "--format", "json", cwd=tmp_path)
    cli("verify", "--scope", "full", "--plan", cwd=tmp_path)
    assert subprocess.check_output(["git", "for-each-ref"], cwd=ROOT) == before
