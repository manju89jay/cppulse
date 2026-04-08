#!/usr/bin/env python3
"""Generate per-project example READMEs from JSON data and Jinja2 template.

Loads analysis JSON (risk_scores.json, findings.json, roadmap.json) from
examples/<project>/ and renders a README.md using the Jinja2 template at
templates/example_readme.md.j2.

Usage:
    python scripts/generate_example_readme.py --project poco
    python scripts/generate_example_readme.py --all
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Short display names for rule IDs, used in the "Key Issues" column.
RULE_SHORT_NAMES: dict[str, str] = {
    "CPP-MEM-001": "Raw `new`",
    "CPP-MEM-002": "explicit `delete`",
    "CPP-MEM-003": "C-style array params",
    "CPP-CX-001": "high cyclomatic complexity",
    "CPP-CX-002": "long functions",
    "CPP-CX-003": "too many params",
    "CPP-MOD-001": "C-style casts",
    "CPP-MOD-002": "deprecated C headers",
    "CPP-MOD-003": "missing `override`",
    "CPP-MOD-004": "raw string literal",
    "CPP-MOD-005": "`auto` opportunities",
    "CPP-MOD-006": "range-for opportunities",
    "CPP-MOD-007": "NULL vs nullptr",
    "CPP-MOD-008": "unscoped `enum`",
    "CPP-MOD-009": "`typedef`",
}

CATEGORY_DISPLAY = {
    "memory_safety": "Memory Safety",
    "complexity": "Complexity",
    "modernization": "Modernization",
}

CATEGORY_ORDER = ["memory_safety", "complexity", "modernization"]


def _format_number(value: int | float) -> str:
    """Format a number with thousands separator."""
    if isinstance(value, float):
        return f"{value:,.1f}"
    return f"{value:,}"


def _format_loc(loc: int) -> str:
    """Format LOC as human-readable (640,665 or similar)."""
    if loc >= 1_000_000:
        return f"{loc:,}"
    if loc >= 1_000:
        return f"{loc:,}"
    return f"{loc:,}"


def _strip_repo_prefix(filepath: str) -> str:
    """Strip the /tmp/<project>/ prefix from file paths."""
    parts = filepath.split("/")
    # Find the index after /tmp/<project>/
    for i, part in enumerate(parts):
        if part == "tmp" and i > 0:
            return "/".join(parts[i + 2 :])
    # Fallback: return as-is if no /tmp/ prefix found
    return filepath


def _build_key_issues(findings: list[dict], category: str) -> str:
    """Build the 'Key Issues' string for a category (top 3 rules by count)."""
    rule_counts: Counter[str] = Counter()
    for f in findings:
        if f["category"] == category:
            rule_counts[f["rule_id"]] += 1

    if not rule_counts:
        return "—"

    top_rules = rule_counts.most_common(3)
    parts = []
    for rule_id, count in top_rules:
        name = RULE_SHORT_NAMES.get(rule_id, rule_id)
        parts.append(f"{name} ({count})")
    return ", ".join(parts)


def _build_top_factors(file_risk: dict) -> str:
    """Build the 'Top Factors' string from a file risk entry."""
    factors = file_risk.get("top_factors", [])
    parts = []

    total = 0
    memory = 0
    modernization = 0
    complexity = 0

    for factor in factors:
        name = factor["feature"]
        val = int(factor["value"])
        if name == "finding_count":
            total = val
        elif name == "memory_findings":
            memory = val
        elif name == "modernization_findings":
            modernization = val
        elif name == "complexity_findings":
            complexity = val

    # Build a human-readable summary
    if memory > 0:
        parts.append(f"Memory issues ({memory})")
    if complexity > 0:
        parts.append(f"Complexity findings ({complexity})")
    if modernization > 0:
        parts.append(f"Modernization issues ({modernization})")

    if not parts:
        if total > 0:
            parts.append(f"{total} total findings")
        else:
            parts.append("Multiple minor findings")
    elif total > 0 and len(parts) < 2:
        # Add total if we only have one specific category
        parts.insert(0, f"{total} total findings")

    return ", ".join(parts)


def _build_risk_summary(file_risks: list[dict]) -> str:
    """Build the risk level summary line."""
    level_counts: Counter[str] = Counter()
    for fr in file_risks:
        level_counts[fr["risk_level"].lower()] += 1

    total = len(file_risks)
    parts = []
    for level in ["critical", "high", "medium", "low"]:
        count = level_counts.get(level, 0)
        if count > 0:
            label = level.capitalize()
            parts.append(
                f"**{count} {'file' if count == 1 else 'files'}** flagged {label}"
            )

    return " · ".join(parts) + f" risk (of {total} total)"


def _build_score_summary(
    display_name: str,
    health_score: float,
    categories: dict[str, float],
) -> str:
    """Build the one-line score summary that appears after the description."""
    cat_parts = []
    for cat_id in CATEGORY_ORDER:
        if cat_id in categories:
            cat_parts.append(
                f"{CATEGORY_DISPLAY[cat_id].lower()} ({categories[cat_id]:.1f})"
            )

    # Find weak and strong categories
    if cat_parts:
        summary = f"cppulse scores it at {health_score:.1f}/100 — reflecting strong {', '.join(cat_parts)}."
    else:
        summary = f"cppulse scores it at {health_score:.1f}/100."

    return summary


def build_context(
    project_id: str,
    project_meta: dict,
    examples_dir: Path,
) -> dict:
    """Build the full template context from JSON data files."""
    project_dir = examples_dir / project_id

    # Load JSON data
    risk_data = json.loads((project_dir / "risk_scores.json").read_text())
    findings_data = json.loads((project_dir / "findings.json").read_text())
    roadmap_data = json.loads((project_dir / "roadmap.json").read_text())

    health = risk_data["health_score"]
    findings_meta = findings_data["metadata"]
    summary = findings_data["summary"]
    findings = findings_data["findings"]
    file_risks = risk_data["file_risks"]
    roadmap_items = roadmap_data["items"]

    # Basic metadata
    analyzed_at = findings_meta.get("analyzed_at", "")
    if analyzed_at:
        dt = datetime.fromisoformat(analyzed_at.replace("Z", "+00:00"))
        analyzed_date = dt.strftime("%Y-%m-%d")
    else:
        analyzed_date = "unknown"

    total_loc = findings_meta.get("total_loc", 0)
    file_count = findings_meta.get("file_count", 0)

    # Total findings from by_category (not the buggy total_findings field)
    by_category = summary.get("by_category", {})
    total_findings = sum(by_category.values())

    # Rules hit
    rules_hit = len(set(f["rule_id"] for f in findings))

    # Category breakdown
    categories = []
    for cat_id in CATEGORY_ORDER:
        if cat_id in health["by_category"]:
            categories.append(
                {
                    "display_name": CATEGORY_DISPLAY[cat_id],
                    "score": f"{health['by_category'][cat_id]:.1f}",
                    "findings": by_category.get(cat_id, 0),
                    "key_issues": _build_key_issues(findings, cat_id),
                }
            )

    # Score summary line
    score_summary = _build_score_summary(
        project_meta["display_name"],
        health["overall"],
        health["by_category"],
    )

    # Top 10 riskiest files (sorted by bug_probability descending)
    sorted_risks = sorted(file_risks, key=lambda x: x["bug_probability"], reverse=True)
    top_files = []
    for fr in sorted_risks[:10]:
        top_files.append(
            {
                "file": _strip_repo_prefix(fr["file"]),
                "bug_probability": f"{fr['bug_probability'] * 100:.1f}",
                "risk_level": fr["risk_level"].capitalize(),
                "top_factors": _build_top_factors(fr),
            }
        )

    # Risk summary
    risk_summary = _build_risk_summary(file_risks)

    # Roadmap (top 10)
    sorted_roadmap = sorted(roadmap_items, key=lambda x: x["priority"])[:10]
    roadmap_display = []
    for item in sorted_roadmap:
        roadmap_display.append(
            {
                "priority": item["priority"],
                "file": _strip_repo_prefix(item["file"]),
                "action": item["action"],
                "category": item["category"],
                "hours": int(item["estimated_hours"]),
                "impact": f"{item['impact_score']:.1f}",
            }
        )

    total_hours = int(sum(item["estimated_hours"] for item in roadmap_items))

    # Check for PDF page count (from filename pattern or just existence)
    pdf_path = project_dir / "report.pdf"
    pdf_pages = None
    if pdf_path.exists():
        # Try to get page count from file size heuristic (optional)
        try:
            content = pdf_path.read_bytes()
            # Count page markers in PDF
            pdf_pages = content.count(b"/Type /Page") - content.count(b"/Type /Pages")
            if pdf_pages <= 0:
                pdf_pages = None
        except Exception:
            pdf_pages = None

    return {
        "project_id": project_id,
        "display_name": project_meta["display_name"],
        "description": project_meta["description"],
        "analyzed_date": analyzed_date,
        "loc_display": _format_number(total_loc),
        "file_count": file_count,
        "health_score": f"{health['overall']:.1f}",
        "score_summary": score_summary,
        "categories": categories,
        "total_findings": total_findings,
        "rules_hit": rules_hit,
        "top_files": top_files,
        "risk_summary": risk_summary,
        "roadmap_items": roadmap_display,
        "roadmap_count": len(roadmap_items),
        "roadmap_hours": total_hours,
        "pdf_pages": pdf_pages,
    }


def load_project_registry(scripts_dir: Path) -> list[dict]:
    """Load showcase_projects.json registry."""
    registry_path = scripts_dir / "showcase_projects.json"
    return json.loads(registry_path.read_text())


def render_readme(
    project_id: str,
    project_meta: dict,
    examples_dir: Path,
    templates_dir: Path,
) -> str:
    """Render a project README from the Jinja2 template."""
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["format_number"] = _format_number

    template = env.get_template("example_readme.md.j2")
    context = build_context(project_id, project_meta, examples_dir)
    return template.render(**context)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate per-project example READMEs from JSON data."
    )
    parser.add_argument(
        "--project", type=str, help="Project ID (e.g. poco). Omit for --all."
    )
    parser.add_argument(
        "--all", action="store_true", help="Generate READMEs for all projects."
    )
    parser.add_argument(
        "--examples",
        type=Path,
        default=Path("examples"),
        help="Path to examples directory",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=Path("templates"),
        help="Path to templates directory",
    )
    parser.add_argument(
        "--scripts",
        type=Path,
        default=Path("scripts"),
        help="Path to scripts directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output instead of writing files.",
    )
    args = parser.parse_args()

    registry = load_project_registry(args.scripts)
    registry_map = {p["id"]: p for p in registry}

    if args.all:
        project_ids = [p["id"] for p in registry]
    elif args.project:
        project_ids = [args.project]
    else:
        parser.error("Specify --project <id> or --all")
        return

    for pid in project_ids:
        project_dir = args.examples / pid
        if not (project_dir / "risk_scores.json").exists():
            print(f"Skipping {pid}: no risk_scores.json")
            continue

        if pid not in registry_map:
            print(f"Skipping {pid}: not in showcase_projects.json")
            continue

        meta = registry_map[pid]
        content = render_readme(pid, meta, args.examples, args.templates)

        if args.dry_run:
            print(f"=== {pid} ===")
            print(content)
            print()
        else:
            output_path = project_dir / "README.md"
            output_path.write_text(content, encoding="utf-8")
            print(f"Generated {output_path}")


if __name__ == "__main__":
    main()
