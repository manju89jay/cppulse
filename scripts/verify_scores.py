"""Independently verify that every published health score reproduces from
its own ``findings.json``, using only the documented ADR-007 formula.

This is a credibility / audit tool, **not** part of the scoring pipeline. It
deliberately does *not* import the predictor. For each project it re-derives the
health score from scratch using the finding densities in ``findings.json`` and
the calibration constants published in ``docs/architecture.md`` (ADR-007), then
asserts the result equals the score the predictor wrote to ``risk_scores.json``.

If the two agree, the leaderboard number is reproducible from public evidence:
anyone with a copy of ``findings.json`` and the documented caps/weights can
recompute it by hand and land on the same value.

Formula (ADR-007)::

    density(cat) = findings(cat) / KLOC          # KLOC from findings metadata
    penalty(cat) = min(1.0, density(cat) / cap)
    category     = (1 - penalty(cat)) * 100
    overall      = (1 - sum(penalty * weight) / sum(weight)) * 100

Usage::

    python scripts/verify_scores.py                       # all examples/*/
    python scripts/verify_scores.py output                # one pipeline output dir
    python scripts/verify_scores.py examples/grpc examples/json

Exit code is 0 if every score reproduces (within rounding), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Category -> (key in findings.json summary.by_category, weight, density cap).
# These literals are the published ADR-007 constants (docs/architecture.md,
# "Health Score Algorithm"). They are intentionally duplicated here rather than
# imported from predictor/src/health_scorer.py so this check is an *independent*
# re-derivation, not the scorer agreeing with itself.
PROFILES: dict[str, dict[str, tuple[str, float, float]]] = {
    "default": {
        "memory_safety": ("memory_safety", 3.0, 5.0),
        "complexity": ("complexity", 1.5, 10.0),
        "modernization": ("modernization", 1.0, 50.0),
    },
    "safety-critical": {
        "memory_safety": ("memory_safety", 3.0, 5.0),
        "misra_compliance": ("misra", 2.5, 10.0),
        "complexity": ("complexity", 1.5, 10.0),
        "modernization": ("modernization", 1.0, 50.0),
    },
}

# Stored scores are rounded to one decimal; allow half a rounding unit of slack.
TOLERANCE = 0.05


class ReproResult:
    """Outcome of re-deriving one project's score from its findings.

    Attributes:
        name: Project directory name.
        ok: True if every recomputed score matched the stored score.
        lines: Human-readable audit lines for the printed report.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.ok = True
        self.lines: list[str] = []


def _detect_profile(by_category: dict[str, float]) -> str:
    """Pick the scoring profile from the categories present in risk_scores.json.

    Args:
        by_category: ``health_score.by_category`` mapping from risk_scores.json.

    Returns:
        ``"safety-critical"`` if a MISRA category is scored, else ``"default"``.
    """
    return "safety-critical" if "misra_compliance" in by_category else "default"


def verify_project(project_dir: Path) -> ReproResult:
    """Re-derive a project's health score and compare it to the stored score.

    Args:
        project_dir: Directory holding ``findings.json`` and ``risk_scores.json``.

    Returns:
        A :class:`ReproResult` carrying the match verdict and audit lines.
    """
    result = ReproResult(project_dir.name)

    findings = json.loads((project_dir / "findings.json").read_text())
    risk = json.loads((project_dir / "risk_scores.json").read_text())

    by_cat_counts = findings.get("summary", {}).get("by_category", {})
    total_loc = int(findings.get("metadata", {}).get("total_loc", 0))
    stored = risk.get("health_score", {})
    stored_overall = float(stored.get("overall", 0.0))
    stored_by_cat = stored.get("by_category", {})

    profile = _detect_profile(stored_by_cat)
    categories = PROFILES[profile]
    kloc = max(total_loc, 1) / 1000.0
    weight_sum = sum(w for (_k, w, _cap) in categories.values())

    result.lines.append(
        f"  {project_dir.name}  ·  {total_loc:,} LOC  ·  profile: {profile}"
    )
    header = (
        f"    {'category':<16}{'findings':>9}{'dens/KLOC':>11}"
        f"{'cap':>6}{'penalty':>9}{'weight':>8}{'score':>8}{'stored':>8}"
    )
    result.lines.append(header)
    result.lines.append(f"    {'-' * (len(header) - 4)}")

    weighted_penalty = 0.0
    for cat, (key, weight, cap) in categories.items():
        count = float(by_cat_counts.get(key, 0))
        density = count / kloc
        penalty = min(1.0, density / cap)
        weighted_penalty += penalty * weight
        cat_score = round((1.0 - penalty) * 100.0, 1)
        cat_stored = float(stored_by_cat.get(cat, 0.0))
        match = abs(cat_score - cat_stored) <= TOLERANCE
        result.ok = result.ok and match
        flag = "" if match else "  <-- MISMATCH"
        result.lines.append(
            f"    {cat:<16}{int(count):>9}{density:>11.3f}{cap:>6.0f}"
            f"{penalty:>9.3f}{weight:>8.1f}{cat_score:>8.1f}{cat_stored:>8.1f}{flag}"
        )

    overall = round((1.0 - weighted_penalty / weight_sum) * 100.0, 1)
    overall_match = abs(overall - stored_overall) <= TOLERANCE
    result.ok = result.ok and overall_match
    verdict = "MATCH" if overall_match else "MISMATCH"
    result.lines.append(
        f"    => overall = (1 - {weighted_penalty:.4f}/{weight_sum:.1f}) x 100 "
        f"= {overall:.1f}   stored {stored_overall:.1f}   [{verdict}]"
    )
    return result


def _discover(targets: list[str]) -> list[Path]:
    """Resolve CLI targets into project directories that have both JSON files.

    Args:
        targets: Explicit directories, or empty to scan ``examples/*``.

    Returns:
        Sorted list of directories containing findings.json and risk_scores.json.
    """
    repo_root = Path(__file__).resolve().parent.parent
    if targets:
        candidates = [Path(t) for t in targets]
    else:
        candidates = sorted((repo_root / "examples").iterdir())

    dirs: list[Path] = []
    for c in candidates:
        if (c / "findings.json").exists() and (c / "risk_scores.json").exists():
            dirs.append(c)
    return dirs


def main() -> int:
    """Run the reproducibility check and print an audit report.

    Returns:
        Process exit code: 0 if all scores reproduce, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Verify health scores reproduce from findings.json (ADR-007)."
    )
    parser.add_argument(
        "dirs",
        nargs="*",
        help="Project dirs to check (default: all examples/*/).",
    )
    args = parser.parse_args()

    dirs = _discover(args.dirs)
    if not dirs:
        print("No project directories with findings.json + risk_scores.json found.")
        return 1

    print("cppulse score reproducibility check (independent re-derivation, ADR-007)")
    print("=" * 78)

    results = [verify_project(project_dir) for project_dir in dirs]
    for result in results:
        print("\n".join(result.lines))
        print()

    print("=" * 78)
    passed = sum(1 for r in results if r.ok)
    all_ok = passed == len(results)
    status = "PASS" if all_ok else "FAIL"
    print(f"{status}: {passed}/{len(dirs)} project scores reproduce from findings.json")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
