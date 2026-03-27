"""PDF report generation for cppulse using WeasyPrint and Jinja2."""

from __future__ import annotations

import base64
import io
import json
from collections import defaultdict
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


def _strip_prefix(path_str: str, prefix: str) -> str:
    """Strip a common path prefix from a file path string.

    Args:
        path_str: The file path to strip.
        prefix: The prefix to remove.  Must end without a trailing slash.

    Returns:
        The relative path with the prefix removed, or the original string if
        the prefix does not match.
    """
    if not prefix:
        return path_str
    norm_prefix = prefix.rstrip("/") + "/"
    if path_str.startswith(norm_prefix):
        return path_str[len(norm_prefix) :]
    return path_str


def _cluster_findings(
    findings: list[dict[str, Any]],
    max_per_category: int = 30,
) -> dict[str, list[dict[str, Any]]]:
    """Group findings by (category, rule_id, message) into compact clusters.

    Each cluster represents all occurrences of one rule+message combination,
    collecting the set of affected files and a total occurrence count so the
    report can render one row per rule rather than one row per finding.

    Args:
        findings: List of raw finding dicts from ``findings.json``.
        max_per_category: Maximum number of clusters to return per category.
            Clusters are sorted by ``total_count`` descending before truncation.

    Returns:
        Dict mapping category name to a list of cluster dicts.  Each cluster
        has keys: ``rule_id``, ``severity``, ``message``, ``suggestion``,
        ``files`` (sorted list of unique paths), ``total_count``.
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        key = (
            finding.get("category", "other"),
            finding.get("rule_id", ""),
            finding.get("message", ""),
        )
        groups[key].append(finding)

    clusters_by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (category, rule_id, message), items in groups.items():
        files = sorted({item.get("file", "") for item in items})
        cluster: dict[str, Any] = {
            "rule_id": rule_id,
            "severity": items[0].get("severity", "info"),
            "message": message,
            "suggestion": items[0].get("suggestion", ""),
            "files": files,
            "total_count": len(items),
        }
        clusters_by_cat[category].append(cluster)

    result: dict[str, list[dict[str, Any]]] = {}
    for cat, clusters in clusters_by_cat.items():
        clusters.sort(key=lambda c: c["total_count"], reverse=True)
        result[cat] = clusters[:max_per_category]

    return result


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

        # Determine repo root for path stripping
        path_prefix = (
            findings.get("metadata", {}).get("repo_path")
            or git_metrics.get("metadata", {}).get("repo_path")
            or ""
        )

        def strip(p: str) -> str:
            return _strip_prefix(p, path_prefix)

        # Hotspots — strip prefix from file field, limit to 20
        raw_hotspots = risk_scores.get("hotspots", [])[:20]
        hotspots = [{**h, "file": strip(h.get("file", ""))} for h in raw_hotspots]

        # File risks — strip prefix, sort by bug_probability descending, limit 10
        raw_file_risks = sorted(
            risk_scores.get("file_risks", []),
            key=lambda x: x.get("bug_probability", 0),
            reverse=True,
        )[:10]
        file_risks = [{**r, "file": strip(r.get("file", ""))} for r in raw_file_risks]

        # Findings — strip prefix then cluster
        raw_findings: list[dict[str, Any]] = findings.get("findings", [])
        stripped_findings = [
            {**f, "file": strip(f.get("file", ""))} for f in raw_findings
        ]
        findings_clustered = _cluster_findings(stripped_findings)

        # Knowledge silos — strip prefix from file field
        raw_silos = git_metrics.get("knowledge_silos", [])
        silos = [{**s, "file": strip(s.get("file", ""))} for s in raw_silos]

        # Roadmap — strip prefix, sort by priority, limit 20
        raw_roadmap = sorted(
            roadmap.get("items", []),
            key=lambda x: x.get("priority", 999),
        )[:20]
        roadmap_items = [
            {**item, "file": strip(item.get("file", ""))} for item in raw_roadmap
        ]

        findings_summary = findings.get("summary", {})

        return {
            "repo_path": repo_path,
            "analyzed_at": analyzed_at,
            "overall_score": overall,
            "by_category": by_category,
            "category_chart_b64": chart_b64,
            "hotspots": hotspots,
            "file_risks": file_risks,
            "findings_clustered": findings_clustered,
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
