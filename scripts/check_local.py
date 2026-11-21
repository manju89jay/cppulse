#!/usr/bin/env python3
"""Run shared local checks using argument vectors and retain truthful results."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from time import monotonic
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SECTIONS = (
    "format",
    "generated",
    "root",
    "native",
    "python",
    "dashboard",
    "integration",
)
SECTIONS = (*DEFAULT_SECTIONS, "docker", "root-public")
HISTORICAL_ROOT_TESTS = (
    "tests/test_elf_runtime.py::test_selected_actual_native_metadata_without_execution",
    "tests/test_generated_rule_registration.py::test_generator_metadata_preserves_existing_public_v2_contract",
    "tests/test_native_normalizer_streaming.py::test_exact_output_parity_with_preserved_prechange_normalizer",
    "tests/test_predictor_input_projection.py::test_public_predictor_preserves_frozen_legacy_results_without_eager_native_load",
    "tests/test_store_heads_v3_review.py::test_real_installed_old_wheel_fails_closed_and_reads_explicit_export",
)
COMPONENT_ROOT_TESTS = {
    "git-miner": (
        "test_git_behavior.py",
        "test_behavior_identity_history.py",
        "test_git_history_cache.py",
        "test_git_inventory_boundary.py",
        "test_git_metric_window_scope.py",
    ),
    "predictor": (
        "test_temporal_evaluation.py",
        "test_risk_semantics118.py",
        "test_roadmap_order.py",
    ),
    "report-engine": ("test_work_unit_api.py",),
}


@dataclass(frozen=True)
class Check:
    """One explicit local command and its execution prerequisites."""

    name: str
    section: str
    argv: tuple[str, ...]
    cwd: Path
    depends_on: tuple[str, ...] = ()
    coverage_namespace: str | None = None
    coverage_minimum: float | None = None
    availability_probe: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _changed_python_sources(root: Path) -> list[str]:
    """Select local edits and the explicit CI change range for Python checks."""
    scopes = ("scripts", "tests", "tools")
    base = os.environ.get("CPPULSE_FORMAT_BASE")
    head = os.environ.get("CPPULSE_FORMAT_HEAD")
    all_tracked = os.environ.get("CPPULSE_FORMAT_ALL_TRACKED", "")
    if all_tracked not in {"", "false", "true"}:
        raise ValueError("CPPULSE_FORMAT_ALL_TRACKED must be true or false")
    if bool(base) != bool(head):
        raise ValueError(
            "CPPULSE_FORMAT_BASE and CPPULSE_FORMAT_HEAD must be supplied together"
        )
    if base and all_tracked == "true":
        raise ValueError("Choose either a PR format range or all tracked Python files")

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=root)

    try:
        local = git(
            "ls-files",
            "--modified",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *scopes,
        )
        staged = git("diff", "--cached", "--name-only", "-z", "--", *scopes)
    except (OSError, subprocess.CalledProcessError):
        if base or all_tracked == "true":
            raise
        return []

    committed = b""
    if all_tracked == "true":
        committed = git("ls-files", "--cached", "-z", "--", *scopes)
    elif base and head:
        base_sha, head_sha = (
            git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
            .decode("ascii")
            .strip()
            for ref in (base, head)
        )
        committed = git(
            "diff", "--name-only", "-z", f"{base_sha}...{head_sha}", "--", *scopes
        )
    return sorted(
        {
            name
            for name in (local + staged + committed).decode().split("\0")
            if name.endswith(".py") and (root / name).is_file()
        }
    )


def build_checks(
    root: Path,
    sections: set[str],
    output: Path,
    *,
    python: str = sys.executable,
    cmake: str = "cmake",
    ctest: str = "ctest",
    npm: str = "npm",
    clang_format: str | None = None,
    jobs: int = 4,
) -> list[Check]:
    """Create a deterministic contract/producer/consumer/presentation check order."""
    checks: list[Check] = []
    if "format" in sections:
        native_sources = sorted(
            path.relative_to(root).as_posix()
            for component in ("analyzer-core", "cli")
            for path in (root / component).rglob("*")
            if path.is_file()
            and path.suffix in {".cpp", ".h", ".hpp", ".hxx"}
            and not {"build", "fixtures", "CMakeFiles", ".git"}.intersection(
                path.relative_to(root / component).parts
            )
        )
        if native_sources:
            formatter = (
                clang_format
                or os.environ.get("CPPULSE_CLANG_FORMAT")
                or shutil.which("clang-format-19")
                or "clang-format"
            )
            checks.append(
                Check(
                    "native-format",
                    "format",
                    (
                        formatter,
                        "--dry-run",
                        "--Werror",
                        "--style=file",
                        *native_sources,
                    ),
                    root,
                )
            )
        targets = [
            str(path.relative_to(root))
            for path in [
                root / "python",
                *[
                    root / name / "src"
                    for name in ("git-miner", "predictor", "report-engine")
                ],
            ]
            if path.is_dir()
        ]
        targets.extend(_changed_python_sources(root))
        if targets:
            checks += [
                Check(
                    "black-check",
                    "format",
                    (python, "-m", "black", "--check", *targets),
                    root,
                ),
                Check(
                    "ruff-check",
                    "format",
                    (python, "-m", "ruff", "check", *targets),
                    root,
                ),
            ]
    if "generated" in sections:
        checks.append(
            Check(
                "delivery-ledger",
                "generated",
                (python, "scripts/verify_delivery.py"),
                root,
            )
        )
        checks.append(
            Check(
                "generated-check",
                "generated",
                (python, "scripts/check_generated.py"),
                root,
            )
        )
    if "root" in sections:
        checks.append(
            Check("root-tests", "root", (python, "-m", "pytest", "-v", "tests/"), root)
        )
    if "root-public" in sections:
        checks.append(
            Check(
                "root-tests-public",
                "root-public",
                (
                    python,
                    "-m",
                    "pytest",
                    "-v",
                    "tests/",
                    *(f"--deselect={test}" for test in HISTORICAL_ROOT_TESTS),
                ),
                root,
            )
        )

    def native(component: str, label: str) -> None:
        configure = label + "-configure"
        build = label + "-build"
        checks.extend(
            [
                Check(
                    configure,
                    "native",
                    (
                        cmake,
                        "-S",
                        component,
                        "-B",
                        component + "/build",
                        "-DBUILD_TESTING=ON",
                    ),
                    root,
                ),
                Check(
                    build,
                    "native",
                    (cmake, "--build", component + "/build", "-j", str(jobs)),
                    root,
                    (configure,),
                ),
                Check(
                    label + "-tests",
                    "native",
                    (
                        ctest,
                        "--test-dir",
                        component + "/build",
                        "--output-on-failure",
                        "--no-tests=error",
                    ),
                    root,
                    (build,),
                ),
            ]
        )

    if "native" in sections or "integration" in sections:
        native("analyzer-core", "analyzer")
    if "python" in sections:
        for component, namespace, minimum in [
            ("git-miner", "git_miner", 80.0),
            ("predictor", "predictor", 75.0),
            ("report-engine", "report_engine", 75.0),
        ]:
            canonical = "cppulse." + namespace
            coverage_file = output / (component + "-coverage.json")
            checks.append(
                Check(
                    component + "-tests",
                    "python",
                    (
                        python,
                        "-m",
                        "pytest",
                        "-v",
                        "--cov=src",
                        "--cov=" + canonical,
                        "--cov-report=term",
                        "--cov-report=json:" + str(coverage_file),
                        "--cov-report=xml:"
                        + str(output / (component + "-coverage.xml")),
                        "tests/",
                        *(
                            f"../tests/{name}"
                            for name in COMPONENT_ROOT_TESTS[component]
                        ),
                    ),
                    root / component,
                    coverage_namespace=canonical,
                    coverage_minimum=minimum,
                )
            )
    if "dashboard" in sections:
        checks.extend(
            [
                Check(
                    "dashboard-tests", "dashboard", (npm, "test"), root / "dashboard"
                ),
                Check(
                    "dashboard-build",
                    "dashboard",
                    (npm, "run", "build"),
                    root / "dashboard",
                    ("dashboard-tests",),
                ),
            ]
        )
    if "native" in sections or "integration" in sections:
        native("cli", "cli")
    if "integration" in sections:
        checks.append(
            Check(
                "native-integration-dependencies",
                "integration",
                (python, "-c", "import pypdf, weasyprint, matplotlib"),
                root,
                availability_probe=True,
            )
        )
        prerequisites = ["analyzer-tests", "cli-tests"]
        prerequisites.append("native-integration-dependencies")
        if "python" in sections:
            prerequisites += [
                name + "-tests" for name in ("git-miner", "predictor", "report-engine")
            ]
        checks.append(
            Check(
                "native-integration",
                "integration",
                ("bash", "scripts/demo.sh", str(output / "native-demo")),
                root,
                tuple(prerequisites),
            )
        )
    if "docker" in sections:
        checks.append(
            Check(
                "compose-integration",
                "docker",
                ("bash", "scripts/integration_test.sh"),
                root,
            )
        )
    return checks


def canonical_coverage(report: Path, namespace: str, root: Path, cwd: Path) -> float:
    """Require the entire canonical Python package and measure its statements."""
    document = json.loads(report.read_text(encoding="utf-8"))
    source = (root / "python" / Path(*namespace.split("."))).resolve()
    remaining = {path.resolve() for path in source.rglob("*.py") if path.is_file()}
    covered = statements = 0
    for filename, entry in document["files"].items():
        path = Path(filename)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if path.is_relative_to(source):
            if path not in remaining:
                raise ValueError(
                    f"Unexpected or duplicate canonical coverage file: {path}"
                )
            remaining.remove(path)
            covered += entry["summary"]["covered_lines"]
            statements += entry["summary"]["num_statements"]
    if remaining:
        missing = ", ".join(
            sorted(path.relative_to(source).as_posix() for path in remaining)
        )
        raise ValueError(f"Missing canonical coverage files for {namespace}: {missing}")
    if not statements:
        raise ValueError(f"No canonical coverage statements recorded for {namespace}")
    return 100.0 * covered / statements


def wait_command(process: subprocess.Popen[str]) -> int:
    """Wait for an explicit developer command; cancellation is handled by its owner."""
    return process.wait()


def _cancel_command(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def run_check(
    check: Check, output: Path, environment: dict[str, str], root: Path
) -> dict[str, Any]:
    """Execute without a shell, recording missing tools and failures separately."""
    output.mkdir(parents=True, exist_ok=True)
    log = output / (check.name + ".log")
    start = monotonic()
    result: dict[str, Any] = {
        "name": check.name,
        "section": check.section,
        "argv": list(check.argv),
        "cwd": str(check.cwd),
        "log": str(log),
        "started_at": _now(),
        "status": "blocked",
        "returncode": None,
    }
    try:
        if check.coverage_namespace:
            report = output / (check.name.removesuffix("-tests") + "-coverage.json")
            report.unlink(missing_ok=True)
        if (
            check.section == "docker"
            and shutil.which("docker", path=environment.get("PATH")) is None
        ):
            raise FileNotFoundError(
                "Docker executable is unavailable; Compose was not run"
            )
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(
                list(check.argv),
                cwd=check.cwd,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=os.name == "posix",
            )
            try:
                wait_command(process)
            except KeyboardInterrupt:
                _cancel_command(process)
                result.update(
                    status="interrupted",
                    returncode=process.returncode,
                    reason="Explicit cancellation; selected process group was terminated on POSIX; other hosts terminate the immediate process",
                )
                stream.write("\nDeveloper check cancelled.\n")
                result.update(
                    finished_at=_now(), elapsed_seconds=round(monotonic() - start, 3)
                )
                return result
        result.update(
            returncode=process.returncode,
            status="passed" if process.returncode == 0 else "failed",
        )
        if process.returncode and check.availability_probe:
            result.update(
                status="blocked",
                reason="Required developer capability is unavailable; inspect the probe log",
            )
        if process.returncode == 0 and check.coverage_namespace:
            report = output / (check.name.removesuffix("-tests") + "-coverage.json")
            if not report.is_file():
                raise ValueError(
                    "Command did not produce a fresh canonical coverage report"
                )
            measured = canonical_coverage(
                report, check.coverage_namespace, root, check.cwd
            )
            result["canonical_coverage"] = {
                "namespace": check.coverage_namespace,
                "percent": round(measured, 2),
                "minimum": check.coverage_minimum,
            }
            if check.coverage_minimum is not None and measured < check.coverage_minimum:
                result.update(
                    status="failed",
                    reason="Canonical implementation coverage is below the required minimum",
                )
    except (FileNotFoundError, PermissionError) as error:
        result.update(status="blocked", reason=str(error))
        log.write_text(str(error) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as error:
        result.update(status="failed", reason=str(error))
        with log.open("a", encoding="utf-8") as stream:
            stream.write("\nVerification error: " + str(error) + "\n")
    result.update(finished_at=_now(), elapsed_seconds=round(monotonic() - start, 3))
    return result


def exit_status(results: list[dict[str, Any]]) -> int:
    """Never let a successful independent command mask failure or missing work."""
    if any(result["status"] == "interrupted" for result in results):
        return 130
    if any(result["status"] == "failed" for result in results):
        return 1
    return 2 if any(result["status"] == "blocked" for result in results) else 0


def main(argv: list[str] | None = None) -> int:
    """Run selected sections and retain machine-readable actual check outcomes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", action="append", choices=(*SECTIONS, "all"))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "review/logs")
    parser.add_argument(
        "--jobs", type=int, default=int(os.environ.get("CPPULSE_BUILD_JOBS", "4"))
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--ctest", default="ctest")
    parser.add_argument("--npm", default="npm.cmd" if os.name == "nt" else "npm")
    parser.add_argument("--clang-format")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    sections = set(args.section or DEFAULT_SECTIONS)
    if "all" in sections:
        sections = {*DEFAULT_SECTIONS, "docker"}
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "python") + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    document: dict[str, Any] = {
        "version": "1.0.0",
        "started_at": _now(),
        "sections": sorted(sections),
        "format_scope": "Native source/tests excluding build/fixtures; Python implementation, legacy shims and changed scripts/tests/tools; check-only",
        "docker": "requested" if "docker" in sections else "not_requested",
        "checks": [],
    }
    for check in build_checks(
        ROOT,
        sections,
        output,
        python=args.python,
        cmake=args.cmake,
        ctest=args.ctest,
        npm=args.npm,
        clang_format=args.clang_format,
        jobs=args.jobs,
    ):
        prior = {result["name"]: result for result in document["checks"]}
        unmet = [
            name
            for name in check.depends_on
            if prior.get(name, {}).get("status") != "passed"
        ]
        if unmet:
            result = {
                "name": check.name,
                "section": check.section,
                "argv": list(check.argv),
                "cwd": str(check.cwd),
                "status": "blocked",
                "returncode": None,
                "reason": "Required earlier check did not pass: " + ", ".join(unmet),
            }
        else:
            result = run_check(check, output, environment, ROOT)
        document["checks"].append(result)
        document["finished_at"] = _now()
        document["exit_status"] = exit_status(document["checks"])
        document["status"] = {
            0: "passed",
            1: "failed",
            2: "blocked",
            130: "interrupted",
        }[document["exit_status"]]
        (output / "check-results.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )
        print(f'{result["status"].upper()}: {check.name}', flush=True)
        if result["status"] == "interrupted":
            break
    document["finished_at"] = _now()
    document["exit_status"] = exit_status(document["checks"])
    document["status"] = {0: "passed", 1: "failed", 2: "blocked", 130: "interrupted"}[
        document["exit_status"]
    ]
    (output / "check-results.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    return document["exit_status"]


if __name__ == "__main__":
    raise SystemExit(main())
