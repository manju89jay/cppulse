"""CLI entry point for git-miner.

Usage:
    python -m cppulse.git_miner.main --repo /path/to/repo --output ./output
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

from cppulse.errors import ContractError
from .history import HistoryScan, scan_history
from .history_cache import HistoryOptions, validate_history_document
from .miner import FileMetrics, GitMiner
from .schema_validator import SchemaValidator
from .silo_detector import SiloDetector, SiloEntry
from .szz_labeler import SZZLabeler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_RETAINED_HISTORY_SCOPE = (
    "Legacy file metrics use the retained history scope. The configured behavior "
    "lookback and cutoff apply only to behavioral metrics; history collection "
    "bounds and other limitations still apply."
)


def build_output(
    repo_path: Path,
    file_metrics: list[FileMetrics],
    silos: list[SiloEntry],
    repo: git.Repo | None,
    szz_counts: dict[str, int] | None = None,
    limitations: list[str] | None = None,
    *,
    history: HistoryScan | None = None,
) -> dict[str, Any]:
    """Assemble the full git_metrics output dictionary.

    Args:
        repo_path: Resolved path to the analyzed repository.
        file_metrics: List of per-file metrics from GitMiner.
        silos: List of knowledge silo entries from SiloDetector.
        repo: The git.Repo object for extracting commit range metadata.
        szz_counts: Per-file counts of distinct SZZ bug-introducing commits.

    Returns:
        Dictionary conforming to the git_metrics.schema.json schema.
    """
    szz_counts = szz_counts or {}
    limitations = list(limitations or [])
    try:
        if history is not None:
            total_commits = len(history.commits)
            first_sha = history.commits[-1].hexsha[:8] if total_commits else ""
            last_sha = history.commits[0].hexsha[:8] if total_commits else ""
        else:
            total_commits = 0
            first_sha = last_sha = ""
            for commit in repo.iter_commits() if repo is not None else ():
                if not total_commits:
                    last_sha = commit.hexsha[:8]
                first_sha = commit.hexsha[:8]
                total_commits += 1
        commit_range = f"{first_sha}..{last_sha}" if total_commits else "empty"
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
            "szz_bug_introductions": szz_counts.get(m.file, 0),
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
            "history_status": (
                "unavailable"
                if repo is None or total_commits == 0
                else "partial" if limitations else "available"
            ),
            "limitations": list(dict.fromkeys(limitations)),
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
    parser.add_argument(
        "--szz-max-fix-commits",
        default=500,
        type=int,
        metavar="N",
        help=(
            "Trace at most the N most recent bug-fix commits in the SZZ "
            "analysis (bounds blame runtime on large histories; default: 500)."
        ),
    )
    parser.add_argument(
        "--behavior-config",
        type=Path,
        help="Optional explicit JSON configuration for separate git_behavior.json.",
    )
    parser.add_argument(
        "--behavior-cutoff",
        help="Explicit UTC cutoff for behavior facts (required with --behavior-config).",
    )
    parser.add_argument(
        "--szz-cutoff",
        help="Inclusive UTC bug-fix cutoff for SZZ labels (default: invocation time; independent of behavior cutoff).",
    )
    return parser.parse_args(argv)


def run(
    repo_path: Path,
    output_dir: Path,
    szz_max_fix_commits: int = 500,
    *,
    behavior_config: Path | dict[str, Any] | None = None,
    behavior_cutoff: str | None = None,
    history_options: dict[str, Any] | None = None,
    szz_cutoff: str | None = None,
) -> int:
    """Execute the full git-miner pipeline.

    Args:
        repo_path: Path to the target git repository.
        output_dir: Directory where git_metrics.json will be written.
        szz_max_fix_commits: Cap on bug-fix commits traced by the SZZ labeler.

    Returns:
        0 on success, 1 on fatal error.
    """
    repo_path = repo_path.resolve()
    selected_szz_cutoff = None
    if szz_cutoff is not None:
        try:
            selected_szz_cutoff = datetime.fromisoformat(szz_cutoff.replace("Z", "+00:00"))
            if selected_szz_cutoff.tzinfo is None or selected_szz_cutoff.utcoffset() != timezone.utc.utcoffset(selected_szz_cutoff):
                raise ContractError("SZZ cutoff must be an aware UTC timestamp")
        except (ContractError, ValueError, TypeError, AttributeError) as exc:
            logger.error("Invalid SZZ cutoff: %s", exc)
            return 1
    try:
        selected_history = HistoryOptions.from_document(history_options)
    except (ContractError, TypeError) as exc:
        logger.error("Invalid history bounds: %s", exc)
        return 1
    selected_behavior = None
    cutoff = None
    if behavior_config is not None or behavior_cutoff is not None:
        from .behavior import BehaviorConfig

        try:
            if behavior_config is None or behavior_cutoff is None:
                raise ContractError(
                    "Both behavior configuration and UTC cutoff are required"
                )
            if isinstance(behavior_config, dict):
                selected_behavior = BehaviorConfig.from_document(behavior_config)
            else:
                with behavior_config.open("rb") as source:
                    raw = source.read(65537)
                if len(raw) > 65536:
                    raise ContractError("Behavior configuration exceeds 64 KiB")
                selected_behavior = BehaviorConfig.from_document(json.loads(raw))
            cutoff = datetime.fromisoformat(behavior_cutoff.replace("Z", "+00:00"))
            if cutoff.tzinfo is None or cutoff.utcoffset() != timezone.utc.utcoffset(
                cutoff
            ):
                raise ContractError("Behavior cutoff must be an aware UTC timestamp")
        except (ContractError, OSError, ValueError, TypeError) as exc:
            logger.error("Invalid behavior request: %s", exc)
            return 1

    if not repo_path.is_dir():
        logger.error("Repository path does not exist: %s", repo_path)
        return 1

    try:
        repo = git.Repo(str(repo_path))
    except git.InvalidGitRepositoryError:
        repo = None
        logger.warning("Git history is unavailable for source directory: %s", repo_path)

    # Preserve historical producer bytes; a new successful request must not
    # leave optional positive sidecars from a disabled/unavailable old scope.
    existing = output_dir.absolute()
    if any(
        (existing / name).is_symlink()
        for name in ("git_metrics.json", "git_history.json", "git_behavior.json")
    ):
        logger.error(
            "Producer outputs cannot be symlinks; choose a fresh output directory"
        )
        return 1
    if ((existing / "git_behavior.json").exists() and selected_behavior is None) or (
        repo is None and (existing / "git_history.json").exists()
    ):
        logger.error(
            "Output contains historical optional Git facts incompatible with this request; choose a fresh output directory"
        )
        return 1

    logger.info("Analyzing repository: %s", repo_path)

    limitations: list[str] = []
    file_metrics: list[FileMetrics] = []
    silos: list[SiloEntry] = []
    szz_counts: dict[str, int] = {}
    szz_provenance = None
    shared_scan = None
    if repo is None:
        limitations.append(
            "No Git repository: static analysis may proceed, but history metrics are unavailable."
        )
    else:
        try:
            shared_scan = scan_history(repo, options=selected_history)
        except Exception as exc:  # noqa: BLE001
            logger.error("Shared history collection unavailable: %s", exc)
            return 1
        try:
            miner = GitMiner(repo_path)
            file_metrics = miner.mine(history=shared_scan)
            limitations.extend(miner.limitations)
            logger.info("Extracted metrics for %d current C++ files", len(file_metrics))
        except Exception as exc:  # noqa: BLE001
            limitations.append(f"Git metrics unavailable: {type(exc).__name__}.")
            logger.warning("GitMiner error: %s - producing partial output", exc)
        try:
            detector = SiloDetector(repo_path)
            if shared_scan is None:
                raise ValueError("Shared Git history stream unavailable")
            silos = detector.detect(history=shared_scan)
            limitations.extend(detector.limitations)
        except Exception as exc:  # noqa: BLE001
            limitations.append(
                f"Contributor analysis unavailable: {type(exc).__name__}."
            )
            logger.warning("SiloDetector error: %s - skipping silos", exc)
        try:
            labeler = SZZLabeler(repo_path, max_fix_commits=szz_max_fix_commits)
            if shared_scan is None:
                raise ValueError("Shared Git history stream unavailable")
            szz_counts = labeler.label(history=shared_scan, cutoff=selected_szz_cutoff)
            szz_provenance = labeler.provenance
            limitations.extend(labeler.limitations)
        except Exception as exc:  # noqa: BLE001
            limitations.append(f"SZZ labels unavailable: {type(exc).__name__}.")
            logger.warning("SZZLabeler error: %s - skipping SZZ", exc)
    output_doc = build_output(
        repo_path,
        file_metrics,
        silos,
        repo,
        szz_counts,
        limitations,
        history=shared_scan,
    )
    if szz_provenance is not None:
        # Informational method/cutoff notes must not turn complete retained
        # history into a collection failure. Actual caps/blame failures remain
        # in the operational limitations used by build_output above.
        output_doc["metadata"]["szz"] = {
            **szz_provenance,
            "feature_history_scope": "retained_history_not_cutoff_filtered",
        }
        output_doc["metadata"]["limitations"].extend(szz_provenance["limitations"])
        output_doc["metadata"]["limitations"].append(
            "The SZZ cutoff selects bug-fix labels only. Other metrics use retained "
            "history; this output is not a historical feature snapshot or future-defect validation."
        )
    # Scope disclosure is informational, not a new collection failure. Preserve
    # the availability and values derived from the actual retained history.
    output_doc["metadata"]["limitations"].append(_RETAINED_HISTORY_SCOPE)
    behavior_doc = None
    if selected_behavior is not None:
        from .behavior import analyze_behavior, records_from_scan

        try:
            if shared_scan is None:
                raise ValueError(
                    "Behavior facts require a readable shared Git history scan"
                )
            behavior_doc = analyze_behavior(
                records_from_scan(shared_scan, selected_behavior),
                shared_scan.files,
                selected_behavior,
                cutoff=cutoff,
                head=shared_scan.commits[0].hexsha if shared_scan.commits else None,
                history_limitations=shared_scan.limitations,
            )
            behavior_doc["limitations"].append(
                "Shared raw Git facts and rename projection were reused across miner/silo/SZZ; "
                "cross-branch symbol lineage and representative large-history resource budgets remain unqualified."
            )
        except (ValueError, TypeError, ContractError) as exc:
            logger.error("Behavior facts unavailable: %s", exc)
            return 1

    # Validate against schema
    try:
        validator = SchemaValidator()
        validator.validate(output_doc)
        logger.info("Schema validation passed")
    except Exception as exc:  # noqa: BLE001
        logger.error("Schema validation failed: %s", exc)
        return 1

    # Write output
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "git_metrics.json"

    with output_file.open("w", encoding="utf-8") as fh:
        json.dump(output_doc, fh, indent=2)

    logger.info("Written: %s", output_file)
    if shared_scan is not None:
        # Keep the shared cache result immutable for its metric consumers.
        history_doc = dict(shared_scan.cache_info)
        if selected_behavior is not None:
            history_doc["limitations"] = list(
                dict.fromkeys([*history_doc["limitations"], _RETAINED_HISTORY_SCOPE])
            )
        validate_history_document("result", history_doc)
        (output_dir / "git_history.json").write_text(
            json.dumps(history_doc, indent=2) + "\n", encoding="utf-8"
        )
    if behavior_doc is not None:
        behavior_file = output_dir / "git_behavior.json"
        behavior_file.write_text(
            json.dumps(behavior_doc, indent=2) + "\n", encoding="utf-8"
        )
        logger.info("Written: %s", behavior_file)
    return 0


def main() -> None:
    """Entry point called by ``python -m cppulse.git_miner.main``."""
    args = parse_args()
    sys.exit(
        run(
            args.repo,
            args.output,
            args.szz_max_fix_commits,
            behavior_config=args.behavior_config,
            behavior_cutoff=args.behavior_cutoff,
            szz_cutoff=args.szz_cutoff,
        )
    )


if __name__ == "__main__":
    main()
