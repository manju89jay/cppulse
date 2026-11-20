"""Build and analyze pinned real libraries and a consumer, retaining exact logs."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

try:
    from .verify_pipeline import verify_pipeline
except ImportError:
    from verify_pipeline import verify_pipeline

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path, log: Path) -> None:
    """Run one explicit command with a retained command/exit transcript."""
    with log.open("w") as output:
        output.write(json.dumps({"argv": command, "cwd": str(cwd)}) + "\n")
        output.flush()
        result = subprocess.run(
            command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT
        )
        output.write(f"\nExit: {result.returncode}\n")
    if result.returncode:
        raise RuntimeError(f"Command failed: {command[0]}; see {log}")


def pinned_revision(source: Path, expected: str) -> str:
    """Verify locked HEAD and reject locally changed or untracked source inputs."""
    actual = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != expected:
        raise RuntimeError(f"Revision mismatch for {source}: {actual}")
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
        text=True,
    )
    if dirty:
        raise RuntimeError(f"Pinned checkout has local changes: {source}")
    return actual


def main() -> None:
    """Explicitly fetch if requested, build, test and verify the native corpus."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "tests/tmp/corpus")
    parser.add_argument("--output", type=Path, default=ROOT / "output/corpus")
    parser.add_argument(
        "--evidence", type=Path, default=ROOT / "review/autonomous/corpus"
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Explicitly permit downloading missing pinned sources",
    )
    args = parser.parse_args()
    corpus, output, evidence = (
        path.resolve() for path in [args.corpus, args.output, args.evidence]
    )
    for path in [corpus, output, evidence]:
        path.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / "demo/corpus-lock.json").read_text())
    for project in lock["projects"]:
        source = corpus / project["id"]
        if not source.exists():
            if not args.fetch:
                raise RuntimeError(
                    f"Missing {source}; rerun with --fetch to permit source download"
                )
            run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    project["tag"],
                    project["repository"],
                    str(source),
                ],
                ROOT,
                evidence / f"{project['id']}-fetch.log",
            )
        pinned_revision(source, project["revision"])
    run(
        [
            "cmake",
            "-S",
            str(corpus / "fmt"),
            "-B",
            str(corpus / "fmt/build"),
            "-DFMT_TEST=OFF",
            "-DFMT_DOC=OFF",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ],
        ROOT,
        evidence / "fmt-configure.log",
    )
    run(
        ["cmake", "--build", str(corpus / "fmt/build"), "-j4"],
        ROOT,
        evidence / "fmt-build.log",
    )
    build = corpus / "consumer-build"
    run(
        [
            "cmake",
            "-S",
            str(ROOT / "demo/real-consumer"),
            "-B",
            str(build),
            f"-DCPPULSE_CORPUS_ROOT={corpus}",
        ],
        ROOT,
        evidence / "consumer-configure.log",
    )
    run(["cmake", "--build", str(build), "-j4"], ROOT, evidence / "consumer-build.log")
    run(
        ["ctest", "--test-dir", str(build), "--output-on-failure"],
        ROOT,
        evidence / "consumer-tests.log",
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projects": lock["projects"],
        "cases": [],
        "limitations": [
            "Only the selected consumer test executes; upstream test suites are not claimed passed.",
            "Shallow source checkouts provide limited Git history.",
            "Standalone/inferred headers and unsupported module sources may be partially analyzed; these do not establish every consumer configuration.",
        ],
    }
    for name, source, database, config in [
        ("fmt", corpus / "fmt", corpus / "fmt/build", ROOT / "demo/fmt-analysis.json"),
        ("utfcpp", corpus / "utfcpp", build, ROOT / "demo/utfcpp-analysis.json"),
        ("consumer", ROOT / "demo/real-consumer", build, None),
    ]:
        target = output / name
        command = [
            str(ROOT / "cli/build/cppulse"),
            "--project-root",
            str(ROOT),
            "analyze",
            "--repo",
            str(source),
            "--output",
            str(target),
            "--compilation-database",
            str(database),
        ]
        if config:
            command += ["--config", str(config)]
        run(command, ROOT, evidence / f"{name}-pipeline.log")
        result = verify_pipeline(target, require_pdf=True)
        findings = json.loads((target / "findings.json").read_text())
        coverage = findings["metadata"]["analysis"]["files"]
        result.update(
            {
                "id": name,
                "output": str(target),
                "parse_states": dict(Counter(item["status"] for item in coverage)),
                "compile_contexts": dict(
                    Counter(item["compile_context"] for item in coverage)
                ),
            }
        )
        if name == "consumer" and not all(
            item["status"] == "analyzed" for item in coverage
        ):
            raise RuntimeError("The selected real consumer did not parse completely")
        manifest["cases"].append(result)
    (evidence / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
