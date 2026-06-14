#!/usr/bin/env python3
"""Master orchestrator for refreshing all showcase analysis data and derived files.

Phases:
  1. Clone/update repos in .showcase-repos/ cache
  2. Run analyzer-core + git-miner + predictor per project
  3. Regenerate: SVGs, example READMEs, leaderboard, architecture.md markers
  4. Print score diff summary

Usage:
    python scripts/refresh_showcase.py                   # full refresh
    python scripts/refresh_showcase.py --project poco    # single project
    python scripts/refresh_showcase.py --skip-analysis   # regen from existing JSON only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
EXAMPLES_DIR = REPO_ROOT / "examples"
ASSETS_DIR = REPO_ROOT / "assets"
TEMPLATES_DIR = REPO_ROOT / "templates"
SHOWCASE_CACHE = REPO_ROOT / ".showcase-repos"


def load_registry() -> list[dict]:
    """Load the showcase project registry."""
    registry_path = SCRIPTS_DIR / "showcase_projects.json"
    return json.loads(registry_path.read_text())


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, printing the command and raising on failure."""
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


# ── Phase 1: Clone/update repos ──────────────────────────────────────────────


def clone_or_update(project: dict) -> Path:
    """Clone or update a project repo in the showcase cache."""
    repo_dir = SHOWCASE_CACHE / project["id"]
    SHOWCASE_CACHE.mkdir(parents=True, exist_ok=True)

    if repo_dir.exists():
        print(f"  Updating {project['id']}...")
        depth = str(project.get("clone_depth", 1))
        _run(["git", "-C", str(repo_dir), "fetch", "--depth", depth])
        _run(["git", "-C", str(repo_dir), "reset", "--hard", "FETCH_HEAD"])
    else:
        print(f"  Cloning {project['id']}...")
        depth = str(project.get("clone_depth", 1))
        _run(
            [
                "git",
                "clone",
                "--depth",
                depth,
                project["repo_url"],
                str(repo_dir),
            ]
        )

    return repo_dir


# ── Phase 2: Run analysis pipeline ───────────────────────────────────────────


def run_analysis(project_id: str, repo_dir: Path) -> None:
    """Run the cppulse analysis pipeline on a cloned repo."""
    output_dir = EXAMPLES_DIR / project_id
    output_dir.mkdir(parents=True, exist_ok=True)

    analyzer_bin = REPO_ROOT / "analyzer-core" / "build" / "cppulse-analyzer"
    if not analyzer_bin.exists():
        # Try Windows extension
        analyzer_bin = analyzer_bin.with_suffix(".exe")

    if not analyzer_bin.exists():
        print(f"  WARNING: analyzer-core binary not found at {analyzer_bin}")
        print("  Skipping analysis — build analyzer-core first (cmake --build)")
        return

    # Step 1: analyzer-core → findings.json (--output takes a directory)
    print(f"  Running analyzer-core on {project_id}...")
    _run(
        [
            str(analyzer_bin),
            "--repo",
            str(repo_dir),
            "--output",
            str(output_dir),
        ]
    )

    # Step 2: git-miner → git_metrics.json (module CLI, run from its component dir)
    print(f"  Running git-miner on {project_id}...")
    _run(
        [
            sys.executable,
            "-m",
            "src.main",
            "--repo",
            str(repo_dir),
            "--output",
            str(output_dir),
        ],
        cwd=REPO_ROOT / "git-miner",
    )

    # Sanity gate: a shallow clone whose history can't be mined yields empty
    # file_metrics, which silently degrades the predictor to tautological
    # heuristic labels. Fail loudly here rather than publish bad showcase data.
    git_metrics = json.loads((output_dir / "git_metrics.json").read_text())
    if not git_metrics.get("file_metrics"):
        raise RuntimeError(
            f"{project_id}: git-miner produced no file_metrics — history likely "
            "unreachable (increase clone_depth in showcase_projects.json)."
        )

    # Step 3: predictor → risk_scores.json + roadmap.json
    print(f"  Running predictor on {project_id}...")
    _run(
        [
            sys.executable,
            "-m",
            "src.main",
            "--input",
            str(output_dir),
            "--output",
            str(output_dir),
        ],
        cwd=REPO_ROOT / "predictor",
    )


# ── Phase 3: Regenerate derived files ────────────────────────────────────────


def regen_svgs(project_id: str) -> None:
    """Regenerate SVG assets for a project."""
    print(f"  Regenerating SVGs for {project_id}...")
    _run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "generate_readme_assets.py"),
            "--project",
            project_id,
            "--data-dir",
            str(EXAMPLES_DIR / project_id),
            "--output-dir",
            str(ASSETS_DIR / project_id),
        ]
    )


def regen_example_readmes(project_ids: list[str] | None = None) -> None:
    """Regenerate example README(s) from Jinja2 template."""
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "generate_example_readme.py"),
        "--examples",
        str(EXAMPLES_DIR),
        "--templates",
        str(TEMPLATES_DIR),
        "--scripts",
        str(SCRIPTS_DIR),
    ]
    if project_ids and len(project_ids) == 1:
        cmd += ["--project", project_ids[0]]
    else:
        cmd += ["--all"]
    _run(cmd)


def regen_leaderboard() -> None:
    """Regenerate the README leaderboard table."""
    print("  Regenerating leaderboard...")
    _run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "generate_leaderboard.py"),
            "--readme",
            str(REPO_ROOT / "README.md"),
            "--examples",
            str(EXAMPLES_DIR),
        ]
    )


def update_architecture_showcase_result() -> None:
    """Update the SHOWCASE_RESULT markers in docs/architecture.md.

    Finds the top-scoring project and writes its result into the markers.
    """
    arch_path = REPO_ROOT / "docs" / "architecture.md"
    content = arch_path.read_text(encoding="utf-8")

    start_marker = "<!-- SHOWCASE_RESULT:START -->"
    end_marker = "<!-- SHOWCASE_RESULT:END -->"

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print("  WARNING: SHOWCASE_RESULT markers not found in architecture.md")
        return

    # Find the top-scoring project
    best_project = None
    best_score = -1.0
    registry = load_registry()

    for project in registry:
        risk_path = EXAMPLES_DIR / project["id"] / "risk_scores.json"
        if not risk_path.exists():
            continue
        risk_data = json.loads(risk_path.read_text())
        score = risk_data["health_score"]["overall"]
        if score > best_score:
            best_score = score
            best_project = project
            best_categories = risk_data["health_score"]["by_category"]

    if best_project is None:
        print("  WARNING: No projects found with risk_scores.json")
        return

    # Build the result line
    cat_parts = []
    for cat_id, display in [
        ("memory_safety", "memory safety"),
        ("complexity", "complexity"),
        ("modernization", "modernization"),
    ]:
        if cat_id in best_categories:
            cat_parts.append(f"{display} ({best_categories[cat_id]:.1f})")

    result_line = (
        f"**{best_project['display_name']} result:** {best_score:.1f}/100"
        f" — strong scores across all three\n"
        f"categories: {', '.join(cat_parts)}."
    )

    new_content = (
        content[: start_idx + len(start_marker)]
        + "\n"
        + result_line
        + "\n"
        + content[end_idx:]
    )

    arch_path.write_text(new_content, encoding="utf-8")
    print(f"  Updated architecture.md with {best_project['display_name']} result")


# ── Phase 4: Score diff summary ──────────────────────────────────────────────


def collect_scores() -> dict[str, float]:
    """Collect current health scores for all projects."""
    scores = {}
    for project_dir in sorted(EXAMPLES_DIR.iterdir()):
        risk_path = project_dir / "risk_scores.json"
        if risk_path.exists():
            data = json.loads(risk_path.read_text())
            scores[project_dir.name] = data["health_score"]["overall"]
    return scores


def print_diff(before: dict[str, float], after: dict[str, float]) -> None:
    """Print a score diff summary."""
    print("\n-- Score Diff --------------------------------------------------")
    all_ids = sorted(set(before) | set(after))
    changed = False
    for pid in all_ids:
        old = before.get(pid)
        new = after.get(pid)
        if old is None and new is not None:
            print(f"  {pid}: NEW → {new:.1f}")
            changed = True
        elif old is not None and new is None:
            print(f"  {pid}: {old:.1f} → REMOVED")
            changed = True
        elif old != new:
            delta = new - old
            arrow = "+" if delta > 0 else "-"
            print(f"  {pid}: {old:.1f} → {new:.1f} ({arrow}{abs(delta):.1f})")
            changed = True
        else:
            print(f"  {pid}: {old:.1f} (unchanged)")

    if not changed:
        print("  No score changes.")
    print("------------------------------------------------------------")


# ── Main ------------------------------------------------------------──────────────────


def main() -> None:
    # Windows consoles default to cp1252, which cannot print the arrows used
    # in the score diff; force UTF-8 with graceful replacement.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Refresh showcase analysis and regenerate all derived files."
    )
    parser.add_argument(
        "--project",
        type=str,
        help="Refresh a single project (e.g. poco). Default: all.",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip clone and analysis; only regenerate derived files from existing JSON.",
    )
    args = parser.parse_args()

    registry = load_registry()
    registry_map = {p["id"]: p for p in registry}

    if args.project:
        if args.project not in registry_map:
            print(f"Error: unknown project '{args.project}'")
            print(f"Available: {', '.join(registry_map)}")
            sys.exit(1)
        projects = [registry_map[args.project]]
        project_ids = [args.project]
    else:
        projects = registry
        project_ids = [p["id"] for p in registry]

    # Snapshot scores before
    scores_before = collect_scores()

    if not args.skip_analysis:
        # Phase 1 + 2: Clone and analyze
        print("\n=== Phase 1: Clone/update repos ===")
        for project in projects:
            repo_dir = clone_or_update(project)

        print("\n=== Phase 2: Run analysis pipeline ===")
        for project in projects:
            repo_dir = SHOWCASE_CACHE / project["id"]
            if repo_dir.exists():
                run_analysis(project["id"], repo_dir)
    else:
        print("\n=== Skipping analysis (--skip-analysis) ===")

    # Phase 3: Regenerate all derived files
    print("\n=== Phase 3: Regenerate derived files ===")

    for pid in project_ids:
        if (EXAMPLES_DIR / pid / "risk_scores.json").exists():
            regen_svgs(pid)

    regen_example_readmes(project_ids)
    regen_leaderboard()
    update_architecture_showcase_result()

    # Phase 4: Score diff
    scores_after = collect_scores()
    print_diff(scores_before, scores_after)

    print(
        "\nDone! Review changes with: git diff examples/ assets/ README.md docs/architecture.md"
    )


if __name__ == "__main__":
    main()
