"""PDF report generation for cppulse using WeasyPrint and Jinja2."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader


matplotlib.use("Agg")

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None if missing or malformed.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dict or None on failure.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _bar_chart_base64(
    categories: list[str],
    scores: list[float],
    title: str,
) -> str:
    """Render a horizontal bar chart and return it as a base64 PNG string.

    Args:
        categories: Labels for each bar.
        scores: Numeric values (0–100) for each bar.
        title: Chart title.

    Returns:
        Base64-encoded PNG data URI string.
    """
    colors = []
    for score in scores:
        if score >= 80:
            colors.append("#22c55e")
        elif score >= 60:
            colors.append("#f59e0b")
        else:
            colors.append("#ef4444")

    fig, ax = plt.subplots(figsize=(7, 3))
    y_pos = range(len(categories))
    ax.barh(list(y_pos), scores, color=colors, height=0.5)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(categories, fontsize=10)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score", fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for i, score in enumerate(scores):
        ax.text(score + 1, i, f"{score:.1f}", va="center", fontsize=9)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class PDFGenerator:
    """Generates a PDF health report from cppulse output JSON files.

    Attributes:
        data_dir: Directory containing the JSON output files.
    """

    def __init__(self, data_dir: Path) -> None:
        """Initialise the generator.

        Args:
            data_dir: Directory containing findings.json, git_metrics.json,
                risk_scores.json, and roadmap.json.
        """
        self.data_dir = data_dir
        self._env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=True,
        )

    def _collect_data(self) -> dict[str, Any]:
        """Load all JSON data files from the data directory.

        Returns:
            Dictionary with keys 'findings', 'git_metrics', 'risk_scores',
            'roadmap', each containing the parsed JSON or an empty dict.
        """
        return {
            "findings": _load_json(self.data_dir / "findings.json") or {},
            "git_metrics": _load_json(self.data_dir / "git_metrics.json") or {},
            "risk_scores": _load_json(self.data_dir / "risk_scores.json") or {},
            "roadmap": _load_json(self.data_dir / "roadmap.json") or {},
        }

    def _build_template_context(self, data: dict[str, Any]) -> dict[str, Any]:
        """Build the Jinja2 template rendering context.

        Args:
            data: Dict returned by _collect_data().

        Returns:
            Context dict ready for template rendering.
        """
        risk_scores = data["risk_scores"]
        findings = data["findings"]
        git_metrics = data["git_metrics"]
        roadmap = data["roadmap"]

        health_score = risk_scores.get("health_score", {})
        overall = health_score.get("overall", 0.0)
        by_category = health_score.get("by_category", {})

        repo_path = (
            findings.get("metadata", {}).get("repo_path")
            or git_metrics.get("metadata", {}).get("repo_path")
            or "N/A"
        )
        analyzed_at = (
            risk_scores.get("metadata", {}).get("generated_at")
            or findings.get("metadata", {}).get("analyzed_at")
            or "N/A"
        )

        category_labels = [
            "Memory Safety",
            "Modernization",
            "Complexity",
            "MISRA Compliance",
        ]
        category_keys = [
            "memory_safety",
            "modernization",
            "complexity",
            "misra_compliance",
        ]
        category_scores = [float(by_category.get(k, 0)) for k in category_keys]

        chart_b64: str | None = None
        if any(s > 0 for s in category_scores):
            chart_b64 = _bar_chart_base64(
                category_labels, category_scores, "Health Score by Category"
            )

        hotspots = risk_scores.get("hotspots", [])[:20]
        file_risks = sorted(
            risk_scores.get("file_risks", []),
            key=lambda x: x.get("bug_probability", 0),
            reverse=True,
        )[:10]

        raw_findings = findings.get("findings", [])
        grouped: dict[str, list[dict[str, Any]]] = {}
        for f in raw_findings:
            cat = f.get("category", "other")
            grouped.setdefault(cat, []).append(f)
        for cat in grouped:
            grouped[cat].sort(
                key=lambda x: {"error": 0, "warning": 1, "info": 2}.get(
                    x.get("severity", "info"), 2
                )
            )

        silos = git_metrics.get("knowledge_silos", [])
        roadmap_items = sorted(
            roadmap.get("items", []),
            key=lambda x: x.get("priority", 999),
        )

        findings_summary = findings.get("summary", {})

        return {
            "repo_path": repo_path,
            "analyzed_at": analyzed_at,
            "overall_score": overall,
            "by_category": by_category,
            "category_chart_b64": chart_b64,
            "hotspots": hotspots,
            "file_risks": file_risks,
            "findings_grouped": grouped,
            "findings_summary": findings_summary,
            "silos": silos,
            "roadmap_items": roadmap_items,
        }

    def render_html(self) -> str:
        """Render the report as an HTML string.

        Returns:
            Full HTML document as a string.
        """
        data = self._collect_data()
        context = self._build_template_context(data)
        template = self._env.get_template("report.html")
        return template.render(**context)

    def generate_pdf(self) -> bytes:
        """Generate the PDF report.

        Returns:
            PDF content as bytes.

        Raises:
            RuntimeError: If WeasyPrint fails to generate the PDF.
        """
        try:
            from weasyprint import HTML  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "WeasyPrint is not installed. Cannot generate PDF."
            ) from exc

        html_content = self.render_html()
        base_url = str(TEMPLATES_DIR)
        pdf_bytes: bytes = HTML(string=html_content, base_url=base_url).write_pdf()
        return pdf_bytes
