"""Verify pinned original projects with actual native facts and bounded real history.

This is an explicit evidence runner, not an upstream-build or production-readiness
claim. Partial parsing, fallback context, shallow history and samples stay visible.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

from jsonschema import Draft7Validator, FormatChecker

from cppulse.contracts import validate

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = {"fmt", "grpc", "json", "leveldb", "poco", "protobuf"}
EXTENSIONS = {
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ipp",
    ".inl",
    ".tpp",
}


def validate_lock(document: dict[str, Any]) -> None:
    """Reject moving pins, missing originals, substitutions and depth-one history."""
    schema = json.loads((ROOT / "docs/schemas/six_corpus_lock.schema.json").read_text())
    errors = list(
        Draft7Validator(schema, format_checker=FormatChecker()).iter_errors(document)
    )
    if errors:
        raise ValueError("Invalid original corpus lock: " + errors[0].message)
    if {row["id"] for row in document["projects"]} != ORIGINAL:
        raise ValueError(
            "The corpus must retain each of the six original projects exactly once"
        )
    old = json.loads((ROOT / "scripts/showcase_projects.json").read_text())
    repositories = {row["id"]: row["repo_url"] for row in old}
    if any(
        row["repository"] != repositories[row["id"]] for row in document["projects"]
    ):
        raise ValueError(
            "Original project identities cannot substitute another repository"
        )


def git(source: Path, *args: str) -> str:
    """Read actual checkout/history state through Git."""
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def check_source(source: Path, expected: str, minimum_commits: int) -> dict[str, Any]:
    """Verify immutable HEAD, clean tracked/untracked state and real history count."""
    actual = git(source, "rev-parse", "HEAD")
    if actual != expected:
        raise RuntimeError(f"Unexpected revision in {source}: {actual}")
    if git(source, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError(f"Dirty original corpus source: {source}")
    count = int(git(source, "rev-list", "--count", "HEAD"))
    if count < minimum_commits:
        raise RuntimeError(f"Insufficient retained real history: {source}: {count}")
    return {
        "revision": actual,
        "retained_commits": count,
        "shallow": git(source, "rev-parse", "--is-shallow-repository") == "true",
        "oldest_retained_commit": git(source, "rev-list", "HEAD").splitlines()[-1],
        "head_commit_date": git(source, "show", "-s", "--format=%cI", "HEAD"),
    }


def verify_report(
    report: dict[str, Any], source: Path, selected: list[str]
) -> dict[str, Any]:
    """Validate real report schema, observed source hashes, totals and availability."""
    validate("findings", report, version="prototype_v1")
    native = report["metadata"]["analysis"]["native_metrics"]
    rows = native["files"]

    def relative(value: str) -> str:
        return Path(value).relative_to(source).as_posix()

    if {relative(row["path"]) for row in rows} != set(selected) or len(rows) != len(
        selected
    ):
        raise RuntimeError(
            "Native inventory does not exactly cover finite declared source selection"
        )
    physical = 0
    for row in rows:
        file = relative(row["path"])
        if row["physical_loc"] is not None:
            content = (source / file).read_bytes()
            if row["source_content_sha256"] != hashlib.sha256(content).hexdigest():
                raise RuntimeError(
                    f"Native source-buffer hash differs from source: {file}"
                )
            expected_loc = len(re.findall(rb"\r\n|\r|\n", content)) + int(
                bool(content) and content[-1:] not in [b"\r", b"\n"]
            )
            if row["physical_loc"] != expected_loc:
                raise RuntimeError(f"Native physical LOC differs from source: {file}")
            physical += row["physical_loc"]
        if row["function_count"] is not None and row["function_count"] != len(
            row["functions"]
        ):
            raise RuntimeError(f"Function inventory mismatch: {file}")
    if physical != report["metadata"]["total_loc"]:
        raise RuntimeError("Observed physical LOC differs from native aggregate")
    findings = report["findings"]
    if len(findings) != report["summary"]["total_findings"]:
        raise RuntimeError("Finding total differs from actual items")
    for name, key in [("category", "by_category"), ("severity", "by_severity")]:
        counts = Counter(row[name] for row in findings)
        if {
            category: value
            for category, value in report["summary"][key].items()
            if value
        } != dict(counts):
            raise RuntimeError(f"Finding {key} differs from actual items")
    return {
        "declared_files": len(selected),
        "physical_loc": physical,
        "findings": len(findings),
        "parse_states": dict(Counter(row["status"] for row in rows)),
        "measurement_complete_files": sum(row["measurement_complete"] for row in rows),
        "truncated_token_files": sum(
            not row["token_stream"]["complete"] for row in rows
        ),
        "unresolved_include_edges": sum(
            edge["target_kind"] == "unresolved"
            for row in rows
            for edge in row["includes"]
        ),
        "schema_and_semantic_checks": "passed",
    }


def apply_driver_limit(
    limit_bytes: int, file_size_bytes: int = 256 * 1024**2
) -> dict[str, Any]:
    """Verify a finite Linux address-space budget before large JSON processing."""
    if sys.platform != "linux":
        raise RuntimeError(
            "Corpus resource budgets are currently qualified only on Linux"
        )
    import resource

    if min(limit_bytes, file_size_bytes) <= 0:
        raise ValueError("Driver memory/output budgets must be finite and positive")
    initial_bytes = int(Path("/proc/self/statm").read_text().split()[0]) * os.sysconf(
        "SC_PAGE_SIZE"
    )
    if limit_bytes < initial_bytes + 16 * 1024**2:
        raise ValueError("Driver budget is below initial mappings plus16MiB headroom")
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY and limit_bytes > hard:
        raise RuntimeError("Driver budget exceeds inherited hard address-space limit")
    resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, hard))
    observed, _ = resource.getrlimit(resource.RLIMIT_AS)
    if observed != limit_bytes:
        raise RuntimeError("Driver address-space budget could not be verified")
    _, file_hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    if file_hard != resource.RLIM_INFINITY and file_size_bytes > file_hard:
        raise RuntimeError("Driver output budget exceeds inherited hard file limit")
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size_bytes, file_hard))
    observed_file, _ = resource.getrlimit(resource.RLIMIT_FSIZE)
    if observed_file != file_size_bytes:
        raise RuntimeError("Driver output budget could not be verified")
    return {
        "platform": "linux-posix-rlimit",
        "driver_address_space_bytes": observed,
        "driver_file_size_bytes": observed_file,
        "limitation": "Address-space limits are per process, not RSS/host memory or a benchmark.",
    }


def execute_project(
    project: dict[str, Any], args: argparse.Namespace, depth: int
) -> dict[str, Any]:
    """Fetch only with explicit permission, then execute a finite native scan."""
    source = (args.corpus / project["id"]).resolve()
    evidence = (args.output / project["id"]).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        if not args.fetch:
            raise RuntimeError(f"Missing {source}; explicit --fetch required")
        with (evidence / "fetch.log").open("w") as log:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    str(depth),
                    "--branch",
                    project["tag"],
                    project["repository"],
                    str(source),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
    state = check_source(source, project["revision"], depth)
    paths = (
        subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"])
        .decode()
        .split("\0")
    )
    all_files = sorted(
        path
        for path in paths
        if path
        and Path(path).suffix in EXTENSIONS
        and (source / path).is_file()
        and not (source / path).is_symlink()
    )
    selected = all_files[: args.max_files] if args.max_files else all_files
    if not selected:
        raise RuntimeError(f"No selected C++ source files: {source}")
    selection_path = evidence / "selection.json"
    selection_path.write_text(json.dumps(selected, indent=2) + "\n")
    command = [
        str(args.analyzer.resolve()),
        "--repo",
        str(source),
        "--output",
        str(evidence / "native"),
        "--resource-dir",
        str(args.resource_dir.resolve()),
        "--file-list",
        str(selection_path),
        "--address-space-bytes",
        str(args.address_space_bytes),
        "--file-size-bytes",
        str(args.file_size_bytes),
        "--execution-limits-report",
        str(evidence / "native-limits.json"),
    ]
    started = time.monotonic()
    with (evidence / "native.log").open("w") as log:
        log.write(json.dumps({"argv": command, "cwd": str(ROOT)}) + "\n")
        log.flush()
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=args.timeout,
        )
        log.write(f"\nExit: {result.returncode}\n")
    if result.returncode:
        raise RuntimeError(
            f"Native corpus scan failed for {project['id']}: {result.returncode}"
        )
    duration = time.monotonic() - started
    limits = json.loads((evidence / "native-limits.json").read_text())
    if (
        not limits["applied"]["address_space"]
        or not limits["applied"]["file_size"]
        or limits["requested"]["address_space_bytes"] != args.address_space_bytes
    ):
        raise RuntimeError("Native address-space budget was not observed applied")
    report_path = evidence / "native/findings.json"
    checks = verify_report(json.loads(report_path.read_text()), source, selected)
    after = check_source(source, project["revision"], depth)
    if state != after:
        raise RuntimeError("Source/history state changed during native scan")
    # This is actual retained history, not synthetic commit generation or a claim
    # that the bounded sample is complete project history.
    history = git(source, "log", "--format=%H\t%cI\t%s", "--", *selected)
    (evidence / "selected-history.tsv").write_text(history + "\n")
    result = {
        "id": project["id"],
        "repository": project["repository"],
        "tag": project["tag"],
        "source": str(source),
        "history": state,
        "tracked_cpp_files": len(all_files),
        "selection": (
            "all-tracked-cpp"
            if len(selected) == len(all_files)
            else "lexically-first-bounded-smoke"
        ),
        "selected_history_commits": len(history.splitlines()) if history else 0,
        "elapsed_seconds": duration,
        "native_execution_limits": limits,
        "native_report": str(report_path),
        "native_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "selection_sha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        **checks,
        "full_production_qualification": False,
    }
    (evidence / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=ROOT / "demo/six-corpus-lock.json")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analyzer", type=Path, required=True)
    parser.add_argument("--resource-dir", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--projects", nargs="*", choices=sorted(ORIGINAL))
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Explicit bounded smoke sample; default analyzes all tracked C++ files",
    )
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument(
        "--address-space-bytes",
        type=int,
        default=3 * 1024**3,
        help="Finite native Linux address-space budget, default3GiB",
    )
    parser.add_argument(
        "--driver-address-space-bytes",
        type=int,
        default=2 * 1024**3,
        help="Finite driver/schema-verifier address-space budget, default2GiB",
    )
    parser.add_argument(
        "--file-size-bytes",
        type=int,
        default=256 * 1024**2,
        help="Finite per-file output budget for native/driver, default256MiB",
    )
    args = parser.parse_args()
    if (
        args.max_files < 0
        or args.timeout <= 0
        or min(
            args.address_space_bytes,
            args.driver_address_space_bytes,
            args.file_size_bytes,
        )
        <= 0
    ):
        parser.error(
            "File bound must be nonnegative; timeout and memory budgets must be positive"
        )
    lock = json.loads(args.lock.read_text())
    validate_lock(lock)
    driver_limits = apply_driver_limit(
        args.driver_address_space_bytes, args.file_size_bytes
    )
    args.corpus.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lock_sha256": hashlib.sha256(args.lock.read_bytes()).hexdigest(),
        "methodology": lock["methodology"],
        "execution_limits": {
            **driver_limits,
            "native_address_space_bytes": args.address_space_bytes,
            "native_file_size_bytes": args.file_size_bytes,
        },
        "cases": [],
        "errors": [],
    }
    for project in lock["projects"]:
        if args.projects and project["id"] not in args.projects:
            continue
        try:
            result = execute_project(
                project, args, lock["methodology"]["history_depth"]
            )
            manifest["cases"].append(result)
            print(
                f"{project['id']}: {result['declared_files']} files; {result['parse_states']}; checks passed",
                flush=True,
            )
        except (
            MemoryError,
            RuntimeError,
            ValueError,
            subprocess.SubprocessError,
        ) as error:
            manifest["errors"].append(
                {"id": project["id"], "error": f"{type(error).__name__}: {error}"}
            )
            print(f"{project['id']}: {error}", flush=True)
        (args.output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
    if manifest["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
