"""CLI entry point for git-miner.

Usage:
    python -m src.main --repo /path/to/repo --output ./output
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import git

from .miner import FileMetrics, GitMiner
from .schema_validator import SchemaValidator
from .silo_detector import SiloDetector, SiloEntry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_output(
    repo_path: Path,
    file_metrics: list[FileMetrics],
    silos: list[SiloEntry],
    repo: git.Repo,
) -> dict[str, Any]:
    """Assemble the full git_metrics output dictionary.

    Args:
        repo_path: Resolved path to the analyzed repository.
        file_metrics: List of per-file metrics from GitMiner.
        silos: List of knowledge silo entries from SiloDetector.
        repo: The git.Repo object for extracting commit range metadata.

    Returns:
        Dictionary conforming to the git_metrics.schema.json schema.
    """
    try:
        all_commits = list(repo.iter_commits())
        total_commits = len(all_commits)
        if total_commits > 0:
            first_sha = all_commits[-1].hexsha[:8]
            last_sha = all_commits[0].hexsha[:8]
            commit_range = f"{first_sha}..{last_sha}"
        else:
            commit_range = "empty"
    except (ValueError, git.GitCommandError):
        total_commits = 0
        commit_range = "empty"

    analyzed_at = datetime.now(tz=timezone.utc).isoformat()

    serialized_metrics = [
        {
            "file": m.file,
            "change_frequency": m.change_frequency,
            "unique_contributors": m.unique_contributors,
            "age_days": m.age_days,
            "last_modified_days": m.last_modified_days,
            "lines_of_code": m.lines_of_code,
            "lines_added_total": m.lines_added_total,
            "lines_removed_total": m.lines_removed_total,
            "churn_rate": m.churn_rate,
            "bug_fix_commits": m.bug_fix_commits,
            "contributor_list": m.contributor_list,
        }
        for m in file_metrics
    ]

    serialized_silos = [
        {
            "file": s.file,
            "sole_contributor": s.sole_contributor,
            "last_commit_date": s.last_commit_date,
            "risk_note": s.risk_note,
        }
        for s in silos
    ]

    return {
        "version": "1.0.0",
        "metadata": {
            "repo_path": str(repo_path),
            "analyzed_at": analyzed_at,
            "commit_range": commit_range,
            "total_commits": total_commits,
        },
        "file_metrics": serialized_metrics,
        "knowledge_silos": serialized_silos,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list, defaults to sys.argv when None.

    Returns:
        Parsed namespace with attributes: repo (Path), output (Path).
    """
    parser = argparse.ArgumentParser(
        prog="git-miner",
        description="Analyze git history of a C++ repository for cppulse.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
        metavar="PATH",
        help="Path to the git repository to analyze.",
    )
    parser.add_argument(
        "--output",
        default=Path("./output"),
        type=Path,
        metavar="DIR",
        help="Output directory for git_metrics.json (default: ./output).",
    )
    return parser.parse_args(argv)


def run(repo_path: Path, output_dir: Path) -> int:
    """Execute the full git-miner pipeline.

    Args:
        repo_path: Path to the target git repository.
        output_dir: Directory where git_metrics.json will be written.

    Returns:
        0 on success, 1 on fatal error.
    """
    repo_path = repo_path.resolve()

    if not repo_path.exists():
        logger.error("Repository path does not exist: %s", repo_path)
        return 1

    try:
        repo = git.Repo(str(repo_path))
    except git.InvalidGitRepositoryError:
        logger.error("Not a valid git repository: %s", repo_path)
        return 1

    logger.info("Analyzing repository: %s", repo_path)

    # Mine file metrics
    try:
        miner = GitMiner(repo_path)
        file_metrics = miner.mine()
        logger.info("Extracted metrics for %d C++ files", len(file_metrics))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "GitMiner encountered an error: %s — producing partial output", exc
        )
        file_metrics = []

    # Detect knowledge silos
    try:
        detector = SiloDetector(repo_path)
        silos = detector.detect()
        logger.info("Detected %d knowledge silos", len(silos))
    except Exception as exc:  # noqa: BLE001
        logger.warning("SiloDetector encountered an error: %s — skipping silos", exc)
        silos = []

    # Build output document
    output_doc = build_output(repo_path, file_metrics, silos, repo)

    # Validate against schema
    try:
        validator = SchemaValidator()
        validator.validate(output_doc)
        logger.info("Schema validation passed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Schema validation failed: %s — writing output anyway", exc)

    # Write output
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "git_metrics.json"

    with output_file.open("w", encoding="utf-8") as fh:
        json.dump(output_doc, fh, indent=2)

    logger.info("Written: %s", output_file)
    return 0


def main() -> None:
    """Entry point called by ``python -m src.main``."""
    args = parse_args()
    sys.exit(run(args.repo, args.output))


if __name__ == "__main__":
    main()
