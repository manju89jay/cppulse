#!/usr/bin/env python3
"""Generate SVG chart assets for a cppulse project report.

Usage:
    python3 scripts/generate_readme_assets.py \\
        --project poco \\
        --data-dir examples/poco/ \\
        --output-dir assets/poco/

Reads risk_scores.json and findings.json from data-dir, produces SVG files in output-dir.
No external dependencies — pure Python stdlib.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _score_color(score: float) -> str:
    """Return hex color for a health score."""
    if score > 70:
        return "#16a34a"  # green
    if score >= 40:
        return "#d97706"  # amber/orange
    return "#dc2626"  # red


def _score_label(score: float) -> str:
    if score > 70:
        return "Good"
    if score >= 40:
        return "Needs Work"
    return "Critical"


def generate_health_gauge(score: float, output_path: Path) -> None:
    """Generate a semi-circular health gauge SVG."""
    w, h = 280, 180
    cx, cy = 140, 150
    r = 110
    stroke_w = 20

    # Arc helpers
    def arc_point(angle_deg: float) -> tuple[float, float]:
        rad = math.radians(angle_deg)
        return cx + r * math.cos(rad), cy - r * math.sin(rad)

    def arc_path(start_deg: float, end_deg: float) -> str:
        sx, sy = arc_point(start_deg)
        ex, ey = arc_point(end_deg)
        large = 1 if (end_deg - start_deg) > 180 else 0
        return f"M {sx:.1f} {sy:.1f} A {r} {r} 0 {large} 0 {ex:.1f} {ey:.1f}"

    # Score maps to 0-180 degrees (left to right arc)
    score_angle = 180 * (score / 100)
    color = _score_color(score)
    label = _score_label(score)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <defs>
    <linearGradient id="bg-grad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f8fafc"/>
      <stop offset="100%" stop-color="#f1f5f9"/>
    </linearGradient>
  </defs>
  <rect width="{w}" height="{h}" rx="12" fill="url(#bg-grad)" stroke="#e2e8f0" stroke-width="1"/>

  <!-- Background arc (gray) -->
  <path d="{arc_path(180, 0)}" fill="none" stroke="#e5e7eb" stroke-width="{stroke_w}" stroke-linecap="round"/>

  <!-- Score arc (colored) -->
  <path d="{arc_path(180, 180 - score_angle)}" fill="none" stroke="{color}" stroke-width="{stroke_w}" stroke-linecap="round"/>

  <!-- Score text -->
  <text x="{cx}" y="{cy - 30}" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="42" font-weight="800" fill="{color}">{score:.1f}</text>
  <text x="{cx}" y="{cy - 5}" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="14" fill="#64748b">/ 100</text>
  <text x="{cx}" y="{cy + 20}" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="13" font-weight="600" fill="{color}">{label}</text>
</svg>"""

    output_path.write_text(svg)


def generate_category_bars(categories: dict[str, float], output_path: Path) -> None:
    """Generate horizontal bar chart SVG for category scores."""
    w = 440
    bar_h = 28
    gap = 12
    label_w = 150
    bar_area_w = 200
    score_w = 60
    padding = 20
    n = len(categories)
    h = padding * 2 + n * bar_h + (n - 1) * gap + 30  # +30 for title

    bars_svg = ""
    y = padding + 30
    for name, score in categories.items():
        display_name = name.replace("_", " ").title()
        color = _score_color(score)
        bar_w = bar_area_w * (score / 100)

        bars_svg += f"""
  <!-- {display_name} -->
  <text x="{padding}" y="{y + bar_h / 2 + 5}" font-family="system-ui, -apple-system, sans-serif" font-size="13" fill="#374151">{display_name}</text>
  <rect x="{label_w}" y="{y}" width="{bar_area_w}" height="{bar_h}" rx="4" fill="#f3f4f6"/>
  <rect x="{label_w}" y="{y}" width="{max(bar_w, 2):.1f}" height="{bar_h}" rx="4" fill="{color}"/>
  <text x="{label_w + bar_area_w + 10}" y="{y + bar_h / 2 + 5}" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="700" fill="{color}">{score:.1f}</text>"""
        y += bar_h + gap

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <defs>
    <linearGradient id="bg-grad2" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f8fafc"/>
      <stop offset="100%" stop-color="#f1f5f9"/>
    </linearGradient>
  </defs>
  <rect width="{w}" height="{h}" rx="12" fill="url(#bg-grad2)" stroke="#e2e8f0" stroke-width="1"/>
  <text x="{padding}" y="{padding + 16}" font-family="system-ui, -apple-system, sans-serif" font-size="15" font-weight="700" fill="#1e293b">Category Scores</text>
{bars_svg}
</svg>"""

    output_path.write_text(svg)


def generate_badge(label: str, value: str, color: str, output_path: Path) -> None:
    """Generate a shields.io-style badge SVG."""
    # Estimate text widths (approximate)
    label_w = len(label) * 6.5 + 12
    value_w = len(value) * 7 + 12
    total_w = label_w + value_w
    h = 20

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{h}">
  <rect width="{label_w:.0f}" height="{h}" rx="3" fill="#555"/>
  <rect x="{label_w:.0f}" width="{value_w:.0f}" height="{h}" rx="3" fill="{color}"/>
  <rect x="{label_w:.0f}" width="4" height="{h}" fill="{color}"/>
  <text x="{label_w / 2:.0f}" y="14" text-anchor="middle" font-family="Verdana,Geneva,sans-serif" font-size="11" fill="#fff">{label}</text>
  <text x="{label_w + value_w / 2:.0f}" y="14" text-anchor="middle" font-family="Verdana,Geneva,sans-serif" font-size="11" font-weight="bold" fill="#fff">{value}</text>
</svg>"""

    output_path.write_text(svg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SVG assets for a cppulse project report.")
    parser.add_argument("--project", required=True, help="Project name (e.g. poco)")
    parser.add_argument("--data-dir", required=True, type=Path, help="Directory containing JSON output files")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to write SVG files")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    risk_path = args.data_dir / "risk_scores.json"
    findings_path = args.data_dir / "findings.json"

    if not risk_path.exists():
        print(f"Error: {risk_path} not found")
        return

    risk_data = json.loads(risk_path.read_text())
    health = risk_data["health_score"]

    # Generate health gauge
    generate_health_gauge(health["overall"], args.output_dir / "health-gauge.svg")
    print(f"  Generated {args.output_dir / 'health-gauge.svg'}")

    # Generate category bars
    categories = health.get("by_category", {})
    if categories:
        generate_category_bars(categories, args.output_dir / "category-bars.svg")
        print(f"  Generated {args.output_dir / 'category-bars.svg'}")

    # Generate badges
    score = health["overall"]
    badge_color = _score_color(score).lstrip("#")
    generate_badge("health score", f"{score:.1f}/100", f"#{badge_color}", args.output_dir / "health-score.svg")

    if findings_path.exists():
        findings_data = json.loads(findings_path.read_text())
        total = findings_data.get("summary", {}).get("total_findings", 0)
        generate_badge("findings", f"{total:,}", "#e05d44", args.output_dir / "findings.svg")

    rules_hit = len(set(
        f["rule_id"]
        for f in json.loads(findings_path.read_text()).get("findings", [])
    )) if findings_path.exists() else 0
    generate_badge("rules triggered", f"{rules_hit}/22", "#007ec6", args.output_dir / "rules.svg")

    print(f"Done: {args.project} assets in {args.output_dir}")


if __name__ == "__main__":
    main()
