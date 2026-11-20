"""Regression checks for truthful local verification and candidate preparation."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from types import ModuleType
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str) -> ModuleType:
    """Import a CLI script without relying on the developer's global PATH."""
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / (name + ".py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner() -> ModuleType:
    return load_script("check_local")


@pytest.fixture
def candidate() -> ModuleType:
    return load_script("package_candidate")


def wheel(
    directory: Path, name: str, version: str = "1.0", requires: tuple[str, ...] = ()
) -> Path:
    """Write data-only distribution metadata for closure/notice tests."""
    path = directory / f"{name}-{version}-py3-none-any.whl"
    metadata = (
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nLicense: MIT\n"
    )
    metadata += "".join(f"Requires-Dist: {requirement}\n" for requirement in requires)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
        archive.writestr(
            f"{name}-{version}.dist-info/licenses/LICENSE", "Test fixture notice\n"
        )
    return path


def native_archive(path: Path, metadata: dict[str, object]) -> Path:
    """Write an inert archive containing only the installation descriptor."""
    value = json.dumps(metadata).encode()
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("fixture/share/cppulse/native-install.json")
        info.size = len(value)
        archive.addfile(info, io.BytesIO(value))
    return path


def test_runner_keeps_failed_exit_and_output(
    runner: ModuleType, tmp_path: Path
) -> None:
    check = runner.Check(
        "intentional-failure",
        "root",
        (sys.executable, "-c", "print('failure evidence'); raise SystemExit(7)"),
        tmp_path,
    )
    result = runner.run_check(check, tmp_path / "logs", os.environ.copy(), tmp_path)
    assert result["status"] == "failed"
    assert result["returncode"] == 7
    assert "failure evidence" in Path(result["log"]).read_text()
    assert runner.exit_status([result, {"status": "passed"}]) == 1


def test_runner_missing_executable_is_blocked(
    runner: ModuleType, tmp_path: Path
) -> None:
    executable = str(tmp_path / "missing-local-tool")
    check = runner.Check("missing", "native", (executable,), tmp_path)
    result = runner.run_check(check, tmp_path / "logs", os.environ.copy(), tmp_path)
    assert result["status"] == "blocked"
    assert result["returncode"] is None
    assert runner.exit_status([result]) == 2


def test_runner_arguments_are_data_not_shell(
    runner: ModuleType, tmp_path: Path
) -> None:
    marker = tmp_path / "must-not-exist"
    argument = f"a path with spaces; $(touch {marker}) & literal"
    check = runner.Check(
        "argv",
        "root",
        (sys.executable, "-c", "import sys; print(repr(sys.argv[1]))", argument),
        tmp_path,
    )
    result = runner.run_check(check, tmp_path / "logs", os.environ.copy(), tmp_path)
    assert result["status"] == "passed"
    assert repr(argument) in Path(result["log"]).read_text()
    assert not marker.exists()


def test_runner_does_not_reuse_stale_coverage(
    runner: ModuleType, tmp_path: Path
) -> None:
    report = tmp_path / "git-miner-coverage.json"
    report.write_text('{"files": {}}')
    check = runner.Check(
        "git-miner-tests",
        "python",
        (sys.executable, "-c", "pass"),
        tmp_path,
        coverage_namespace="cppulse.git_miner",
        coverage_minimum=80,
    )
    result = runner.run_check(check, tmp_path, os.environ.copy(), tmp_path)
    assert result["status"] != "passed"
    assert not report.exists()


def test_canonical_coverage_excludes_legacy_shims(
    runner: ModuleType, tmp_path: Path
) -> None:
    canonical = tmp_path / "python/cppulse/predictor/model.py"
    legacy = tmp_path / "predictor/src/model.py"
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "files": {
                    str(canonical): {
                        "summary": {"covered_lines": 1, "num_statements": 4}
                    },
                    str(legacy): {
                        "summary": {"covered_lines": 100, "num_statements": 100}
                    },
                }
            }
        )
    )
    assert (
        runner.canonical_coverage(report, "cppulse.predictor", tmp_path, tmp_path)
        == 25.0
    )
    with pytest.raises(ValueError, match="No canonical coverage"):
        runner.canonical_coverage(report, "cppulse.git_miner", tmp_path, tmp_path)


def test_runner_plan_preserves_component_contracts(
    runner: ModuleType, tmp_path: Path
) -> None:
    checks = runner.build_checks(
        tmp_path,
        {"python", "native", "dashboard", "generated", "root"},
        tmp_path / "logs",
        python="test-python",
        cmake="test-cmake",
        ctest="test-ctest",
        npm="test-npm",
    )
    component = next(check for check in checks if check.name == "git-miner-tests")
    assert component.argv[:4] == ("test-python", "-m", "pytest", "-v")
    assert "--cov=src" in component.argv
    assert "--cov=cppulse.git_miner" in component.argv
    assert component.argv[-1] == "tests/"
    by_name = {check.name: check for check in checks}
    assert by_name["analyzer-tests"].depends_on == ("analyzer-build",)
    assert by_name["cli-build"].depends_on == ("cli-configure",)
    assert by_name["dashboard-build"].depends_on == ("dashboard-tests",)
    assert not any(check.section == "docker" for check in checks)
    assert "docker" not in runner.DEFAULT_SECTIONS


def test_runner_docker_is_explicitly_blocked_without_tool(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner.shutil, "which", lambda *args, **kwargs: None)
    check = runner.Check(
        "compose-integration",
        "docker",
        (sys.executable, "-c", "raise SystemExit('must not execute')"),
        tmp_path,
    )
    result = runner.run_check(check, tmp_path, os.environ.copy(), tmp_path)
    assert result["status"] == "blocked"
    assert "Compose was not run" in result["reason"]


def test_runner_main_records_failures_and_blocks_dependents(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "dependent-must-not-run"
    checks = [
        runner.Check(
            "first", "root", (sys.executable, "-c", "raise SystemExit(3)"), tmp_path
        ),
        runner.Check(
            "dependent",
            "root",
            (sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"),
            tmp_path,
            ("first",),
        ),
        runner.Check("independent", "root", (sys.executable, "-c", "pass"), tmp_path),
    ]
    monkeypatch.setattr(runner, "build_checks", lambda *args, **kwargs: checks)
    assert runner.main(["--section", "root", "--output-dir", str(tmp_path)]) == 1
    document = json.loads((tmp_path / "check-results.json").read_text())
    assert document["docker"] == "not_requested"
    assert [check["status"] for check in document["checks"]] == [
        "failed",
        "blocked",
        "passed",
    ]
    assert document["checks"][0]["argv"] == list(checks[0].argv)
    assert not marker.exists()


def test_offline_closure_excludes_optional_ml(
    candidate: ModuleType, tmp_path: Path
) -> None:
    wheel(
        tmp_path, "cppulse", "0.2.0.dev0", ("core_dep==1.0", 'ml_dep==9; extra == "ml"')
    )
    wheel(tmp_path, "core_dep")
    items, graph = candidate.core_inventory(
        tmp_path, {"name": "cppulse", "version": "0.2.0.dev0"}
    )
    assert {item["name"] for item in items} == {"cppulse", "core-dep"}
    assert next(item for item in graph if item["ref"].startswith("pkg:pypi/cppulse@"))[
        "dependsOn"
    ] == ["pkg:pypi/core-dep@1.0"]
    target = tmp_path / "core.lock"
    candidate.write_lock(items, target)
    lock = target.read_text()
    assert "core-dep==1.0 --hash=sha256:" in lock
    assert "ml-dep" not in lock
    candidate._licenses(tmp_path, tmp_path / "notices", items)
    assert len(list((tmp_path / "notices").rglob("LICENSE"))) == 2


@pytest.mark.parametrize(
    "requires,dependency,reason",
    [
        ("core_dep==2.0", ("core_dep", "1.0"), "Missing/incompatible"),
        ("core_dep==1.0", None, "Missing/incompatible"),
        (None, ("unused", "1.0"), "unrelated optional"),
    ],
)
def test_offline_closure_rejects_incomplete_or_extra_wheels(
    candidate: ModuleType,
    tmp_path: Path,
    requires: str | None,
    dependency: tuple[str, str] | None,
    reason: str,
) -> None:
    wheel(tmp_path, "cppulse", "0.2.0.dev0", (requires,) if requires else ())
    if dependency:
        wheel(tmp_path, *dependency)
    with pytest.raises(candidate.CandidateError, match=reason):
        candidate.core_inventory(tmp_path, {"name": "cppulse", "version": "0.2.0.dev0"})


def test_offline_resolution_rejects_url_dependencies_before_pip(
    candidate: ModuleType, tmp_path: Path
) -> None:
    artifact = wheel(
        tmp_path, "cppulse", requires=("remote @ https://example.invalid/archive.whl",)
    )
    with pytest.raises(candidate.CandidateError, match="Remote/direct dependency"):
        candidate.wheel_metadata(artifact)


def test_native_metadata_is_read_without_extraction(
    candidate: ModuleType, tmp_path: Path
) -> None:
    data = {
        "version": "1.0.0",
        "tool_version": "0.2.0.dev0",
        "target": {"platform": "linux", "machine": "x86_64"},
    }
    artifact = native_archive(tmp_path / "native.tar.gz", data)
    assert candidate.native_metadata(artifact) == data
    assert not (tmp_path / "fixture").exists()
    native_archive(artifact, {**data, "version": "unknown"})
    with pytest.raises(candidate.CandidateError, match="Unsupported native"):
        candidate.native_metadata(artifact)


def test_candidate_source_digest_tracks_dirty_sources_without_ref_updates(
    candidate: ModuleType, tmp_path: Path
) -> None:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    tracked = tmp_path / "source.py"
    tracked.write_text("initial\n")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=cppulse local test",
            "-c",
            "user.email=local-test@invalid",
            "commit",
            "--quiet",
            "-m",
            "Temporary local tooling fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    initial = candidate.source_state(tmp_path)
    tracked.write_text("changed\n")
    dirty = candidate.source_state(tmp_path)
    assert dirty["head"] == initial["head"]
    assert dirty["tracked_diff_sha256"] != initial["tracked_diff_sha256"]
    (tmp_path / "new.py").write_text("new source\n")
    untracked = candidate.source_state(tmp_path)
    assert untracked["worktree_digest"] != dirty["worktree_digest"]
    assert untracked["untracked_sources"][0]["path"] == "new.py"
    (tmp_path / "review").mkdir()
    (tmp_path / "review/log.txt").write_text("reproducible logs\n")
    assert candidate.source_state(tmp_path) == untracked


def test_candidate_command_failure_preserves_log(
    candidate: ModuleType, tmp_path: Path
) -> None:
    log = tmp_path / "logs/failure.log"
    with pytest.raises(candidate.CandidateError, match="exited 4"):
        candidate._command(
            [
                sys.executable,
                "-c",
                "print('actual builder failure'); raise SystemExit(4)",
            ],
            tmp_path,
            log,
        )
    assert "actual builder failure" in log.read_text()


def test_candidate_rejects_mismatched_version_before_build(
    candidate: ModuleType, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nbuild-backend="setuptools.build_meta"\n[project]\nname="cppulse"\nversion="0.2.0.dev0"\n'
    )
    archive = native_archive(
        tmp_path / "native.tar.gz",
        {
            "version": "1.0.0",
            "tool_version": "different",
            "target": {"platform": "linux", "machine": "x86_64"},
        },
    )
    with pytest.raises(candidate.CandidateError, match="versions disagree"):
        candidate.build_candidate(
            archive, tmp_path, tmp_path / "candidate", root=tmp_path
        )
    assert not (tmp_path / "candidate").exists()


@pytest.mark.parametrize(
    "target",
    [{"platform": "../outside", "machine": "x86_64"}, {"machine": "x86_64"}, "linux"],
)
def test_native_candidate_target_cannot_escape_output(
    candidate: ModuleType, tmp_path: Path, target: object
) -> None:
    artifact = native_archive(
        tmp_path / "native.tar.gz",
        {"version": "1.0.0", "tool_version": "0.2.0.dev0", "target": target},
    )
    with pytest.raises(candidate.CandidateError, match="target"):
        candidate.native_metadata(artifact)


def test_runner_successful_tests_cannot_mask_low_canonical_coverage(
    runner: ModuleType, tmp_path: Path
) -> None:
    report = tmp_path / "git-miner-coverage.json"
    source = tmp_path / "python/cppulse/git_miner/history.py"
    script = (
        "from pathlib import Path; Path("
        + repr(str(report))
        + ").write_text("
        + repr(
            json.dumps(
                {
                    "files": {
                        str(source): {
                            "summary": {"covered_lines": 1, "num_statements": 5}
                        }
                    }
                }
            )
        )
        + ")"
    )
    check = runner.Check(
        "git-miner-tests",
        "python",
        (sys.executable, "-c", script),
        tmp_path,
        coverage_namespace="cppulse.git_miner",
        coverage_minimum=80,
    )
    result = runner.run_check(check, tmp_path, os.environ.copy(), tmp_path)
    assert result["returncode"] == 0
    assert result["status"] == "failed"
    assert result["canonical_coverage"]["percent"] == 20.0


def test_native_runner_forces_tests_and_rejects_zero_tests(
    runner: ModuleType, tmp_path: Path
) -> None:
    checks = runner.build_checks(tmp_path, {"native"}, tmp_path / "logs")
    configure = next(check for check in checks if check.name == "analyzer-configure")
    ctest = next(check for check in checks if check.name == "analyzer-tests")
    assert "-DBUILD_TESTING=ON" in configure.argv
    assert "--no-tests=error" in ctest.argv
    check = runner.Check(
        "empty-native-tests",
        "native",
        (
            ctest.argv[0],
            "--test-dir",
            str(tmp_path),
            "--output-on-failure",
            "--no-tests=error",
        ),
        tmp_path,
    )
    result = runner.run_check(check, tmp_path / "logs", os.environ.copy(), tmp_path)
    assert result["status"] == "failed"
    assert result["returncode"] != 0
    assert "No tests were found" in Path(result["log"]).read_text()


@pytest.mark.parametrize("output_is_parent", [False, True])
def test_candidate_output_cannot_hide_checkout_sources(
    candidate: ModuleType, tmp_path: Path, output_is_parent: bool
) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[build-system]\nbuild-backend="setuptools.build_meta"\n[project]\nname="cppulse"\nversion="0.2.0.dev0"\n'
    )
    archive = native_archive(
        tmp_path / "native.tar.gz",
        {
            "version": "1.0.0",
            "tool_version": "0.2.0.dev0",
            "target": {"platform": "linux", "machine": "x86_64"},
        },
    )
    output = tmp_path if output_is_parent else root
    with pytest.raises(candidate.CandidateError, match="checkout root or its ancestor"):
        candidate.build_candidate(archive, tmp_path, output, root=root)


def test_candidate_uses_top_level_metadata_not_vendored_distributions(
    candidate: ModuleType, tmp_path: Path
) -> None:
    artifact = wheel(tmp_path, "setuptools", "75.8.0")
    with zipfile.ZipFile(artifact, "a") as archive:
        archive.writestr(
            "setuptools/_vendor/inner-9.dist-info/METADATA", "Name: inner\nVersion: 9\n"
        )
    metadata = candidate.wheel_metadata(artifact)
    assert metadata["name"] == "setuptools"
    assert metadata["version"] == "75.8.0"
