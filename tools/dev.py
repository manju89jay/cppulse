#!/usr/bin/env python3
"""One explicit local path for development, measurements and candidate review.

Commands never publish, deploy, update Git references or execute project recipes
merely by inspecting a checkout. Full verification includes configured candidate,
installed-artifact and reference-measurement work; missing prerequisites block it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from types import ModuleType
from typing import Any
import uuid

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
_FULL_EXTRA = ("candidate-integrity", "installed-smoke", "reference-benchmarks")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Local developer component is unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def local_runner() -> ModuleType:
    """Load the existing shared runner; component commands remain authoritative."""
    return _module(ROOT / "scripts/check_local.py", "cppulse_development_checks")


@lru_cache(maxsize=1)
def _candidate_builder() -> ModuleType:
    return _module(
        ROOT / "scripts/package_candidate.py", "cppulse_development_candidate"
    )


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "python") + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    return environment


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _source() -> dict[str, Any]:
    return _candidate_builder().source_state(ROOT)


def _default_output(operation: str) -> Path:
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "review/development" / f"{name}-{operation}-{uuid.uuid4().hex[:8]}"


def _new_output(path: Path | None, operation: str) -> Path:
    output = (path or _default_output(operation)).resolve()
    if ROOT.is_relative_to(output) or (
        output.is_relative_to(ROOT)
        and not any(output.is_relative_to(ROOT / name) for name in ("review", "output"))
    ):
        raise ValueError(
            "Inside the checkout, developer evidence must be under review/ or output/; otherwise use an external directory"
        )
    output.mkdir(parents=True, exist_ok=False)
    return output


def _schema() -> dict[str, Any]:
    return json.loads(
        (ROOT / "tools/contracts/development-result.schema.json").read_text()
    )


def _publish(document: dict[str, Any], output: Path) -> None:
    document["finished_at"] = _now()
    jsonschema.validate(document, _schema())
    target = output / "development-results.json"
    temporary = output / ".development-results.json.tmp"
    temporary.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
    temporary.replace(target)


def _print(document: dict[str, Any], format: str) -> None:
    if format == "json":
        print(json.dumps(document, indent=2, allow_nan=False))
        return
    print(
        f"{document.get('operation', 'doctor')}: {document.get('status', 'inspected')}"
    )
    for row in document.get("checks", []):
        reason = f" — {row['reason']}" if row.get("reason") else ""
        print(f"  {row['status']}: {row['name']}{reason}")
    for row in document.get("tools", {}).values():
        print(f"  {'available' if row['available'] else 'unavailable'}: {row['name']}")
    if document.get("evidence"):
        print(f"Evidence: {document['evidence']}")


def source_checks(args: argparse.Namespace, output: Path) -> list[Any]:
    """Plan the full conservative source closure or an explicit CI subset."""
    runner = local_runner()
    sections = set(args.section or runner.DEFAULT_SECTIONS)
    if args.with_docker:
        sections.add("docker")
    checks = runner.build_checks(
        ROOT,
        sections,
        output,
        python=args.python,
        cmake=args.cmake,
        ctest=args.ctest,
        npm=args.npm,
        clang_format=args.clang_format,
        jobs=args.jobs,
    )
    if args.component:
        prefixes = {
            "analyzer-core": "analyzer-",
            "cli": "cli-",
            "git-miner": "git-miner-",
            "predictor": "predictor-",
            "report-engine": "report-engine-",
            "dashboard": "dashboard-",
        }
        selected = tuple(prefixes[name] for name in args.component)
        checks = [check for check in checks if check.name.startswith(selected)]
        if not checks:
            raise ValueError(
                "Selected components have no checks in the requested sections"
            )
    return checks


def _result(operation: str, scope: str, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "operation": operation,
        "scope": scope,
        "status": "blocked",
        "exit_status": 2,
        "started_at": _now(),
        "finished_at": _now(),
        "source": source,
        "candidate": None,
        "checks": [],
        "limitations": [
            "Verification applies to the selected commands, source identity, candidate bytes and host. It is not proof of every production requirement or platform.",
            "Changed-scope checks conservatively execute the source closure; no dependency-aware reduction or cache equivalence is claimed by this runner.",
            "Docker is executed only when requested. An unrequested Docker check is not evidence that Compose passed.",
        ],
    }


def _blocked(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "status": "blocked", "returncode": None, "reason": reason}


def _run(check: Any, output: Path, environment: dict[str, str]) -> dict[str, Any]:
    result = local_runner().run_check(check, output, environment, ROOT)
    log = result.get("log")
    if log and Path(log).is_file():
        result["log_sha256"] = _digest(Path(log))
    return result


def verify_candidate(candidate: Path) -> dict[str, Any]:
    """Reject missing, modified, extra or unsafe files in an existing candidate.

    Hashes identify bytes; this does not authenticate the producer or establish
    that these artifacts were installed or analyzed correctly.
    """
    candidate = candidate.resolve(strict=True)
    if not candidate.is_dir():
        raise ValueError("Candidate must be an existing directory")
    expected: dict[str, str] = {}
    for line in (candidate / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ValueError("Invalid candidate checksum record")
        digest, relative = match.groups()
        path = PurePosixPath(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in relative
            or ":" in relative
            or path.as_posix() != relative
            or relative in expected
        ):
            raise ValueError("Unsafe or duplicate candidate checksum path")
        expected[relative] = digest
    actual: set[str] = set()
    for path in candidate.rglob("*"):
        if path.is_symlink():
            raise ValueError("Candidate integrity cannot follow symlinks")
        if path.is_file() and path.relative_to(candidate).as_posix() != "SHA256SUMS":
            relative = path.relative_to(candidate).as_posix()
            actual.add(relative)
            if expected.get(relative) != _digest(path):
                raise ValueError(f"Candidate hash integrity mismatch: {relative}")
    if not expected or actual != set(expected):
        raise ValueError("Candidate checksum inventory has missing or extra files")
    manifest = json.loads((candidate / "candidate.json").read_text())
    if (
        not isinstance(manifest, dict)
        or manifest.get("candidate_status") != "prepared"
        or manifest.get("version") != "1.0.0"
    ):
        raise ValueError("Candidate is not a supported prepared artifact")
    return {
        "path": str(candidate),
        "manifest_sha256": _digest(candidate / "candidate.json"),
        "checksums_sha256": _digest(candidate / "SHA256SUMS"),
        "files": len(expected),
        "manifest": manifest,
    }


def _native_matches(archive_path: Path, prefix: Path) -> None:
    if not prefix.is_dir():
        raise ValueError("Installed native prefix is unavailable")
    expected: set[str] = set()
    with tarfile.open(archive_path, "r:*") as archive:
        roots: set[str] = set()
        for member in archive.getmembers():
            parts = PurePosixPath(member.name).parts
            if not parts or ".." in parts or PurePosixPath(member.name).is_absolute():
                raise ValueError("Unsafe native candidate archive path")
            roots.add(parts[0])
            if member.isdir():
                continue
            if not member.isfile() or len(parts) < 2:
                raise ValueError("Native candidate requires regular files")
            relative = Path(*parts[1:])
            expected.add(relative.as_posix())
            target = prefix / relative
            if any(path.is_symlink() for path in (target, *target.parents)):
                raise ValueError("Native installed prefix must not follow symlinks")
            stream = archive.extractfile(member)
            if stream is None or not target.is_file():
                raise ValueError("Installed native prefix lacks an archive member")
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            if _digest(target) != digest.hexdigest():
                raise ValueError("Installed native prefix differs from candidate bytes")
        if len(roots) != 1:
            raise ValueError("Native archive has ambiguous prefix roots")
    actual = {
        path.relative_to(prefix).as_posix()
        for path in prefix.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise ValueError("Installed native prefix has extra or missing files")


def _full_checks(
    args: argparse.Namespace,
    output: Path,
    document: dict[str, Any],
    environment: dict[str, str],
) -> list[dict[str, Any]]:
    runner = local_runner()
    results: list[dict[str, Any]] = []
    candidate: dict[str, Any] | None = None
    if args.candidate is None:
        results.append(
            _blocked("candidate-integrity", "Full verification requires --candidate")
        )
    else:
        try:
            candidate = verify_candidate(args.candidate)
            if candidate["manifest"].get("source") != document["source"]:
                raise ValueError(
                    "Candidate source identity differs from the current checkout"
                )
            document["candidate"] = {
                key: value for key, value in candidate.items() if key != "manifest"
            }
            results.append(
                {
                    "name": "candidate-integrity",
                    "status": "passed",
                    "candidate": document["candidate"],
                }
            )
        except (OSError, ValueError, KeyError) as error:
            candidate = None
            results.append(
                {
                    "name": "candidate-integrity",
                    "status": "failed",
                    "reason": str(error),
                }
            )
    if candidate is None or args.native_prefix is None:
        results.append(
            _blocked(
                "installed-smoke",
                "A checked candidate and --native-prefix are required",
            )
        )
    elif os.name != "posix":
        results.append(
            _blocked(
                "installed-smoke",
                "The current installed smoke driver is POSIX-only; this host is unqualified",
            )
        )
    else:
        try:
            candidate_path = Path(candidate["path"])
            archive = candidate_path / candidate["manifest"]["native"]["artifact"]
            _native_matches(archive, args.native_prefix.resolve())
            wheels = list((candidate_path / "core-wheelhouse").glob("cppulse-*.whl"))
            if len(wheels) != 1:
                raise ValueError("Candidate must contain one cppulse wheel")
            check = runner.Check(
                "installed-smoke",
                "package",
                (
                    args.python,
                    str(ROOT / "scripts/verify_installed.py"),
                    "--wheel",
                    str(wheels[0]),
                    "--native-prefix",
                    str(args.native_prefix.resolve()),
                    "--wheelhouse",
                    str(candidate_path / "core-wheelhouse"),
                    "--evidence",
                    str(output / "installed-smoke"),
                ),
                ROOT,
            )
            results.append(_run(check, output, environment))
            if results[-1]["status"] == "interrupted":
                return results
        except (OSError, ValueError, KeyError, tarfile.TarError) as error:
            results.append(
                {"name": "installed-smoke", "status": "failed", "reason": str(error)}
            )
    suite = _suite(args.benchmark_suite) if args.benchmark_suite else None
    if suite is None or not suite.is_file():
        results.append(
            _blocked(
                "reference-benchmarks",
                "Full verification requires an available --benchmark-suite",
            )
        )
    else:
        try:
            suite_document = json.loads(suite.read_text())
            if (
                not isinstance(suite_document, dict)
                or suite_document.get("id") != "reference"
            ):
                raise ValueError(
                    "Full verification requires a configured suite with id 'reference'; custom measurements remain available through benchmark"
                )
        except (OSError, ValueError) as error:
            results.append(
                _blocked(
                    "reference-benchmarks", "Invalid selected suite: " + str(error)
                )
            )
            return results
        check = runner.Check(
            "reference-benchmarks",
            "benchmark",
            (
                args.python,
                str(ROOT / "tools/benchmark.py"),
                "--suite",
                str(suite),
                "--output-dir",
                str(output / "benchmarks"),
            ),
            ROOT,
        )
        results.append(_run(check, output, environment))
    return results


def verify(args: argparse.Namespace) -> int:
    """Execute shared source checks and all mandatory requested full stages."""
    output = (args.output_dir or _default_output("verify")).resolve()
    document = _result("verify", args.scope, _source())
    if args.section or args.component:
        document["limitations"].append(
            "Explicit CI subset: sections="
            + ",".join(args.section or [])
            + "; components="
            + ",".join(args.component or [])
            + ". This subset does not establish full verification."
        )
    checks = source_checks(args, output)
    if args.plan:
        document.update(status="planned", exit_status=None)
        document["checks"] = [
            {
                "name": check.name,
                "status": "planned",
                "argv": list(check.argv),
                "cwd": str(check.cwd),
            }
            for check in checks
        ]
        if args.scope == "full":
            document["checks"] += [
                {"name": name, "status": "planned"} for name in _FULL_EXTRA
            ]
        _print(document, args.format)
        return 0
    output = _new_output(output, "verify")
    environment = _environment()
    try:
        for check in checks:
            prior = {row["name"]: row for row in document["checks"]}
            unmet = [
                name
                for name in check.depends_on
                if prior.get(name, {}).get("status") != "passed"
            ]
            if unmet:
                result = _blocked(
                    check.name,
                    "Earlier required checks did not pass: " + ", ".join(unmet),
                )
            else:
                result = _run(check, output, environment)
            document["checks"].append(result)
            document["exit_status"] = local_runner().exit_status(document["checks"])
            document["status"] = {
                0: "passed",
                1: "failed",
                2: "blocked",
                130: "interrupted",
            }[document["exit_status"]]
            if args.scope == "full" and document["status"] == "passed":
                document.update(status="blocked", exit_status=2)
            _publish(document, output)
            if result["status"] == "interrupted":
                break
        if args.scope == "full" and document["status"] != "interrupted":
            document["checks"].extend(_full_checks(args, output, document, environment))
        after = _source()
        if after != document["source"]:
            document["checks"].append(
                _blocked(
                    "stable-source",
                    "Source changed during verification; rerun on a stable tree",
                )
            )
        document["exit_status"] = local_runner().exit_status(document["checks"])
        document["status"] = {
            0: "passed",
            1: "failed",
            2: "blocked",
            130: "interrupted",
        }[document["exit_status"]]
    except KeyboardInterrupt:
        document["checks"].append(
            {
                "name": "verification-interrupted",
                "status": "interrupted",
                "reason": "Explicit cancellation; remaining work was not executed",
            }
        )
        document.update(status="interrupted", exit_status=130)
    _publish(document, output)
    printed = dict(document)
    printed["evidence"] = str(output / "development-results.json")
    _print(printed, args.format)
    return int(document["exit_status"])


def _tool(name: str, executable: str) -> dict[str, Any]:
    selected = shutil.which(executable)
    record: dict[str, Any] = {
        "name": name,
        "available": selected is not None,
        "path": selected,
        "version": None,
    }
    if selected:
        try:
            result = subprocess.run(
                [selected, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                shell=False,
            )
            record["version"] = next(
                iter((result.stdout or result.stderr).splitlines()), ""
            )
            record["version_probe_exit"] = result.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            record["version_probe_error"] = str(error)
    return record


def doctor(args: argparse.Namespace) -> int:
    """Inspect the selected developer tools without running project build recipes."""
    formatter = (
        args.clang_format
        or os.environ.get("CPPULSE_CLANG_FORMAT")
        or shutil.which("clang-format-19")
        or "clang-format"
    )
    tools = {
        name: _tool(name, executable)
        for name, executable in {
            "python": args.python,
            "cmake": args.cmake,
            "ctest": args.ctest,
            "git": "git",
            "cxx": os.environ.get("CXX", "cl" if os.name == "nt" else "c++"),
            "clang-format": formatter,
            "npm": args.npm,
            "docker": "docker",
        }.items()
    }
    missing = [
        name for name, row in tools.items() if not row["available"] and name != "docker"
    ]
    document = {
        "operation": "doctor",
        "root": str(ROOT),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "tools": tools,
        "status": "blocked" if missing else "inspected",
        "missing_required_tools": missing,
        "limitations": [
            "Tool presence/version inspection is not installed-product, Docker or platform qualification. No project build recipes were executed."
        ],
    }
    _print(document, args.format)
    return 2 if missing else 0


def _suite(value: str | Path) -> Path:
    return (
        ROOT / "tools/benchmarks/reference.json"
        if str(value) == "reference"
        else Path(value).resolve()
    )


def _check_logs(document: dict[str, Any]) -> None:
    for row in document["checks"]:
        if row["name"] != "candidate-integrity" and (
            not row.get("argv") or not row.get("log") or row.get("returncode") != 0
        ):
            raise ValueError(
                "Verification lacks actual passing command and log evidence"
            )
        if row.get("log"):
            path = Path(row["log"])
            if not path.is_file() or _digest(path) != row.get("log_sha256"):
                raise ValueError("Verification command log is missing or modified")


def release_review(args: argparse.Namespace) -> int:
    """Review exact candidate/check bytes; no publication capability exists."""
    candidate = verify_candidate(args.candidate)
    verification = json.loads(args.verification.read_text())
    jsonschema.validate(verification, _schema())
    if (
        verification["operation"] != "verify"
        or verification["scope"] != "full"
        or verification["status"] != "passed"
    ):
        raise ValueError("Release review requires a passed full verification record")
    required = set(_schema()["x-required-full-checks"])
    if not required <= {row["name"] for row in verification["checks"]}:
        raise ValueError("Full verification record omits required work")
    current = _source()
    if (
        verification["source"] != candidate["manifest"].get("source")
        or current != verification["source"]
    ):
        raise ValueError("Candidate, verification and current source identities differ")
    binding = verification.get("candidate")
    if (
        not isinstance(binding, dict)
        or binding.get("manifest_sha256") != candidate["manifest_sha256"]
    ):
        raise ValueError("Verification names different candidate bytes")
    _check_logs(verification)
    output = _new_output(args.output_dir, "release-review")
    document = _result("release-dry-run", "candidate", current)
    document["candidate"] = {
        key: value for key, value in candidate.items() if key != "manifest"
    }
    document["checks"] = [
        {
            "name": "verified-candidate-review",
            "status": "passed",
            "verification_sha256": _digest(args.verification),
        }
    ]
    if args.require_complete:
        check = local_runner().Check(
            "production-scope-complete",
            "scope",
            (
                args.python,
                str(ROOT / "scripts/verify_delivery.py"),
                "--require-complete",
            ),
            ROOT,
        )
        document["checks"].append(_run(check, output, _environment()))
    document["exit_status"] = local_runner().exit_status(document["checks"])
    document["status"] = {0: "passed", 1: "failed", 2: "blocked", 130: "interrupted"}[
        document["exit_status"]
    ]
    document["limitations"].append(
        "This is a local dry-run review. No tag, Git reference, release, upload, deployment or notification was created."
    )
    _publish(document, output)
    _print(document, args.format)
    return int(document["exit_status"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--format", choices=["text", "json"], default="text")
        command.add_argument("--python", default=sys.executable)

    def build_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--cmake", default="cmake")
        command.add_argument("--ctest", default="ctest")
        command.add_argument("--npm", default="npm.cmd" if os.name == "nt" else "npm")
        command.add_argument("--clang-format")

    inspect = commands.add_parser(
        "doctor", help="Inspect tools without running project recipes"
    )
    common(inspect)
    build_options(inspect)
    checks = commands.add_parser(
        "verify", help="Run the shared checks and mandatory full-verification stages"
    )
    common(checks)
    build_options(checks)
    checks.add_argument("--scope", choices=["changed", "full"], default="changed")
    checks.add_argument("--section", action="append", choices=local_runner().SECTIONS)
    checks.add_argument(
        "--component",
        action="append",
        choices=[
            "analyzer-core",
            "cli",
            "git-miner",
            "predictor",
            "report-engine",
            "dashboard",
        ],
    )
    checks.add_argument("--output-dir", type=Path)
    checks.add_argument("--jobs", type=int, default=4)
    checks.add_argument("--plan", action="store_true")
    checks.add_argument("--with-docker", action="store_true")
    checks.add_argument("--candidate", type=Path)
    checks.add_argument("--native-prefix", type=Path)
    checks.add_argument("--benchmark-suite")
    for kind in ["rule", "adapter", "policy"]:
        scaffold = commands.add_parser(
            f"new-{kind}", help=f"Generate an explicitly incomplete {kind} draft"
        )
        common(scaffold)
        scaffold.add_argument("name")
        scaffold.add_argument("--destination", type=Path, default=Path.cwd())
    benchmark = commands.add_parser(
        "benchmark",
        help="Measure an explicit suite without inferring a performance budget",
    )
    benchmark.add_argument("--suite", required=True)
    benchmark.add_argument("--output-dir", type=Path)
    benchmark.add_argument("--python", default=sys.executable)
    package = commands.add_parser(
        "package", help="Prepare local candidate artifacts; never publish"
    )
    common(package)
    package.add_argument("--candidate", action="store_true", required=True)
    package.add_argument("--native-archive", type=Path, required=True)
    package.add_argument("--wheelhouse", type=Path, required=True)
    package.add_argument("--output-dir", type=Path, required=True)
    package.add_argument("--version")
    release = commands.add_parser(
        "release", help="Review a verified candidate with an explicit local dry-run"
    )
    common(release)
    release.add_argument("--dry-run", action="store_true", required=True)
    release.add_argument("--candidate", type=Path, required=True)
    release.add_argument("--verification", type=Path, required=True)
    release.add_argument("--output-dir", type=Path)
    release.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch only documented local operations using literal argument vectors."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "verify":
        if args.jobs < 1:
            parser.error("--jobs must be positive")
        if args.scope == "full" and (args.section or args.component):
            parser.error(
                "--scope full cannot omit required sections; use changed for explicit CI subsets"
            )
    try:
        if args.command == "doctor":
            return doctor(args)
        if args.command == "verify":
            return verify(args)
        if args.command.startswith("new-"):
            sys.path.insert(0, str(ROOT / "python"))
            from cppulse.tooling import scaffold

            name = args.name.lower() if args.command == "new-rule" else args.name
            location = scaffold(
                args.command.removeprefix("new-"), name, args.destination
            )
            document = {
                "path": str(location),
                "status": "incomplete-draft",
                "requested_name": args.name,
            }
            _print(document, args.format)
            if args.format == "text":
                print(
                    f"Draft: {location}; implementation and meaningful fixtures are required before registration"
                )
            return 0
        if args.command == "benchmark":
            suite = _suite(args.suite)
            if not suite.is_file():
                raise ValueError(f"Selected benchmark suite is unavailable: {suite}")
            return subprocess.run(
                [
                    args.python,
                    str(ROOT / "tools/benchmark.py"),
                    "--suite",
                    str(suite),
                    "--output-dir",
                    str(args.output_dir or _default_output("benchmark")),
                ],
                cwd=ROOT,
                env=_environment(),
                shell=False,
                check=False,
            ).returncode
        if args.command == "package":
            result = _candidate_builder().build_candidate(
                args.native_archive,
                args.wheelhouse,
                args.output_dir,
                expected_version=args.version,
            )
            _print(
                {
                    "operation": "package",
                    "status": "prepared",
                    "candidate": str(result),
                },
                args.format,
            )
            if args.format == "text":
                print(f"Candidate: {result}; installed verification is still required")
            return 0
        if args.command == "release":
            return release_review(args)
    except KeyboardInterrupt:
        return 130
    except (
        OSError,
        ValueError,
        KeyError,
        jsonschema.ValidationError,
        subprocess.SubprocessError,
        _candidate_builder().CandidateError,
    ) as error:
        sys.stderr.write(f"Developer operation could not complete: {error}\n")
        return 2
    raise AssertionError("Unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
