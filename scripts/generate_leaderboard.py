#!/usr/bin/env python3
"""Auto-generate the cppulse leaderboard table in README.md.

Scans examples/*/risk_scores.json for all analyzed projects, builds a markdown
table with Unicode health bars, and replaces the content between
<!-- LEADERBOARD:START --> and <!-- LEADERBOARD:END --> markers in README.md.

Usage:
    python3 scripts/generate_leaderboard.py [--readme README.md]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _unicode_bar(score: float, width: int = 20) -> str:
    """Create a Unicode block bar for a 0-100 score.

    Uses 20 characters: each represents 5 points.
    █ (U+2588) for filled, ░ (U+2591) for empty.
    """
    filled = round(score / 100 * width)
    filled = max(0, min(width, filled))
    return "\u2588" * filled + "\u2591" * (width - filled)


def _format_loc(loc: int) -> str:
    """Format LOC as human-readable (640K, 1.2M, etc.)."""
    if loc >= 1_000_000:
        return f"{loc / 1_000_000:.1f}M"
    if loc >= 1_000:
        return f"{loc / 1_000:.0f}K"
    return f"{loc:,}"


def collect_projects(examples_dir: Path) -> list[dict]:
    """Scan examples/ for projects with risk_scores.json."""
    projects = []

    for project_dir in sorted(examples_dir.iterdir()):
        if not project_dir.is_dir():
            continue

        risk_path = project_dir / "risk_scores.json"
        findings_path = project_dir / "findings.json"

        if not risk_path.exists():
            continue

        risk_data = json.loads(risk_path.read_text())
        health = risk_data["health_score"]["overall"]

        # Get findings count
        total_findings = 0
        rules_hit = 0
        total_loc = 0
        if findings_path.exists():
            findings_data = json.loads(findings_path.read_text())
            total_findings = findings_data.get("summary", {}).get("total_findings", 0)
            rules_hit = len(set(f["rule_id"] for f in findings_data.get("findings", [])))
            total_loc = findings_data.get("metadata", {}).get("total_loc", 0)

        # Check for PDF
        has_pdf = (project_dir / "report.pdf").exists()

        projects.append({
            "name": project_dir.name,
            "dir": project_dir,
            "health": health,
            "findings": total_findings,
            "rules_hit": rules_hit,
            "loc": total_loc,
            "has_pdf": has_pdf,
        })

    # Sort by LOC descending (largest first)
    projects.sort(key=lambda p: p["loc"], reverse=True)
    return projects


def _display_name(name: str) -> str:
    """Convert directory name to display name."""
    names = {
        "poco": "POCO C++ Libraries",
        "opencv": "OpenCV",
        "godot": "Godot Engine",
        "boost-asio": "Boost.Asio",
        "cppulse": "cppulse (self-analysis)",
        "grpc": "gRPC",
        "protobuf": "Protocol Buffers",
        "json": "nlohmann/json",
        "fmt": "fmt",
        "leveldb": "LevelDB",
    }
    return names.get(name, name.replace("-", " ").title())


def generate_table(projects: list[dict]) -> str:
    """Generate the markdown leaderboard table."""
    lines = [
        "| # | Project | LOC | Health | Findings | Rules | Report |",
        "|--:|---------|----:|:------:|---------:|:-----:|:------:|",
    ]

    for i, p in enumerate(projects, 1):
        name = f"**{_display_name(p['name'])}**"
        loc = _format_loc(p["loc"]) if p["loc"] > 0 else "—"
        bar = _unicode_bar(p["health"])
        health = f"`{p['health']:.1f}` {bar}"
        findings = f"{p['findings']:,}" if p["findings"] > 0 else "—"
        rules = f"{p['rules_hit']}/22" if p["rules_hit"] > 0 else "—"

        report_parts = [f"[Details](examples/{p['name']}/)"]
        if p["has_pdf"]:
            report_parts.append(f"[PDF](examples/{p['name']}/report.pdf)")
        report = " · ".join(report_parts)

        lines.append(f"| {i} | {name} | {loc} | {health} | {findings} | {rules} | {report} |")

    return "\n".join(lines)


def update_readme(readme_path: Path, table: str) -> None:
    """Replace content between leaderboard markers in README."""
    content = readme_path.read_text()

    start_marker = "<!-- LEADERBOARD:START -->"
    end_marker = "<!-- LEADERBOARD:END -->"

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print(f"Warning: markers not found in {readme_path}, skipping update")
        return

    new_content = (
        content[: start_idx + len(start_marker)]
        + "\n"
        + table
        + "\n"
        + content[end_idx:]
    )

    readme_path.write_text(new_content)
    print(f"Updated leaderboard in {readme_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate cppulse leaderboard table.")
    parser.add_argument("--readme", type=Path, default=Path("README.md"), help="Path to README.md")
    parser.add_argument("--examples", type=Path, default=Path("examples"), help="Path to examples directory")
    args = parser.parse_args()

    projects = collect_projects(args.examples)
    if not projects:
        print("No projects found in examples/")
        return

    print(f"Found {len(projects)} project(s):")
    for p in projects:
        print(f"  {p['name']}: {p['health']:.1f}/100, {p['findings']:,} findings")

    table = generate_table(projects)
    update_readme(args.readme, table)


if __name__ == "__main__":
    main()
