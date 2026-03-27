"""Tests for the PDFGenerator class."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# HTML rendering (always runs)
# ---------------------------------------------------------------------------


def test_render_html_returns_string(data_dir: Path) -> None:
    """render_html() produces a non-empty HTML string."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    assert isinstance(html, str)
    assert len(html) > 100


def test_render_html_contains_repo_path(data_dir: Path) -> None:
    """Rendered HTML includes the repo path from sample data."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    assert "/tmp/my_project" in html


def test_render_html_contains_health_score(data_dir: Path) -> None:
    """Rendered HTML includes the overall health score value."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    assert "72.5" in html


def test_render_html_contains_all_seven_sections(data_dir: Path) -> None:
    """Rendered HTML includes all 7 required section headings."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()

    expected_headings = [
        "Executive Summary",
        "Health Score Breakdown",
        "Hotspot Map",
        "Detection Findings",
        "Knowledge Silo Alerts",
        "Bug Prediction",
        "Refactoring Roadmap",
    ]
    for heading in expected_headings:
        assert heading in html, f"Missing section heading: {heading!r}"


def test_render_html_contains_findings(data_dir: Path) -> None:
    """Rendered HTML includes sample finding rule IDs."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    assert "CPP-MEM-001" in html
    assert "CPP-MOD-004" in html


def test_render_html_contains_silo(data_dir: Path) -> None:
    """Rendered HTML includes knowledge silo contributor name."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    assert "alice" in html


def test_render_html_contains_roadmap_actions(data_dir: Path) -> None:
    """Rendered HTML includes roadmap action text."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    assert "unique_ptr" in html


def test_render_html_empty_data_dir(tmp_path: Path) -> None:
    """render_html() does not raise when data files are absent."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(tmp_path)
    html = gen.render_html()
    assert isinstance(html, str)
    assert "cppulse" in html


def test_chart_generated_when_scores_present(data_dir: Path) -> None:
    """HTML contains embedded base64 PNG chart when category scores are non-zero."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    assert "data:image/png;base64," in html


def test_collect_data_keys(data_dir: Path) -> None:
    """_collect_data returns dict with all four expected keys."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    data = gen._collect_data()
    assert set(data.keys()) == {"findings", "git_metrics", "risk_scores", "roadmap"}


def test_collect_data_missing_files(tmp_path: Path) -> None:
    """_collect_data returns empty dicts for missing files without raising."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(tmp_path)
    data = gen._collect_data()
    assert data["findings"] == {}
    assert data["git_metrics"] == {}
    assert data["risk_scores"] == {}
    assert data["roadmap"] == {}


# ---------------------------------------------------------------------------
# _strip_prefix unit tests
# ---------------------------------------------------------------------------


def test_strip_prefix_removes_matching_prefix() -> None:
    """_strip_prefix strips the repo root from an absolute path."""
    from src.pdf_generator import _strip_prefix

    result = _strip_prefix("/tmp/poco/Foundation/src/Foo.cpp", "/tmp/poco")
    assert result == "Foundation/src/Foo.cpp"


def test_strip_prefix_no_match_returns_original() -> None:
    """_strip_prefix returns the original string when prefix does not match."""
    from src.pdf_generator import _strip_prefix

    result = _strip_prefix("/other/path/Foo.cpp", "/tmp/poco")
    assert result == "/other/path/Foo.cpp"


def test_strip_prefix_empty_prefix_returns_original() -> None:
    """_strip_prefix returns original string unchanged when prefix is empty."""
    from src.pdf_generator import _strip_prefix

    result = _strip_prefix("/tmp/poco/Foo.cpp", "")
    assert result == "/tmp/poco/Foo.cpp"


def test_strip_prefix_trailing_slash_in_prefix() -> None:
    """_strip_prefix handles a prefix that already ends with a slash."""
    from src.pdf_generator import _strip_prefix

    result = _strip_prefix("/tmp/poco/src/Foo.cpp", "/tmp/poco/")
    assert result == "src/Foo.cpp"


# ---------------------------------------------------------------------------
# _cluster_findings unit tests
# ---------------------------------------------------------------------------


def _make_finding(
    rule_id: str,
    category: str,
    severity: str,
    file: str,
    message: str,
    suggestion: str = "",
) -> dict[str, Any]:
    """Build a minimal finding dict for test fixtures."""
    return {
        "rule_id": rule_id,
        "category": category,
        "severity": severity,
        "file": file,
        "message": message,
        "suggestion": suggestion,
    }


def test_cluster_findings_groups_same_rule() -> None:
    """Multiple findings with the same rule_id produce a single cluster."""
    from src.pdf_generator import _cluster_findings

    findings = [
        _make_finding("R001", "memory_safety", "error", "a.cpp", "Raw ptr"),
        _make_finding("R001", "memory_safety", "error", "b.cpp", "Raw ptr"),
        _make_finding("R001", "memory_safety", "error", "a.cpp", "Raw ptr"),
    ]
    result = _cluster_findings(findings)
    assert "memory_safety" in result
    clusters = result["memory_safety"]
    assert len(clusters) == 1
    assert clusters[0]["rule_id"] == "R001"
    assert clusters[0]["total_count"] == 3
    assert sorted(clusters[0]["files"]) == ["a.cpp", "b.cpp"]


def test_cluster_findings_different_messages_are_separate() -> None:
    """Two different messages under the same category stay as separate clusters."""
    from src.pdf_generator import _cluster_findings

    findings = [
        _make_finding("R001", "mod", "warning", "a.cpp", "Message A"),
        _make_finding("R001", "mod", "warning", "b.cpp", "Message B"),
    ]
    result = _cluster_findings(findings)
    assert len(result["mod"]) == 2


def test_cluster_findings_sorted_by_count_descending() -> None:
    """Clusters within a category are sorted by total_count descending."""
    from src.pdf_generator import _cluster_findings

    findings = [
        _make_finding("R001", "cat", "warning", "a.cpp", "Msg A"),
        _make_finding("R002", "cat", "warning", "a.cpp", "Msg B"),
        _make_finding("R002", "cat", "warning", "b.cpp", "Msg B"),
        _make_finding("R002", "cat", "warning", "c.cpp", "Msg B"),
    ]
    result = _cluster_findings(findings)
    counts = [c["total_count"] for c in result["cat"]]
    assert counts == sorted(counts, reverse=True)


def test_cluster_findings_respects_max_per_category() -> None:
    """Clusters are truncated to max_per_category per category."""
    from src.pdf_generator import _cluster_findings

    findings = [
        _make_finding(f"R{i:03d}", "cat", "info", "a.cpp", f"Msg {i}")
        for i in range(10)
    ]
    result = _cluster_findings(findings, max_per_category=3)
    assert len(result["cat"]) == 3


def test_cluster_findings_empty_list() -> None:
    """_cluster_findings returns an empty dict for an empty findings list."""
    from src.pdf_generator import _cluster_findings

    result = _cluster_findings([])
    assert result == {}


def test_render_html_uses_findings_clustered_structure(data_dir: Path) -> None:
    """Rendered HTML uses the clustered structure (one row per rule, not per finding)."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    # Sample data has CPP-MEM-001 once — should appear in clustered table
    assert "CPP-MEM-001" in html
    # Template header "Files Affected" only appears in the clustered findings table
    assert "Files Affected" in html


def test_render_html_strips_path_prefix(data_dir: Path) -> None:
    """File paths in rendered HTML have the repo root prefix stripped."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    html = gen.render_html()
    # Repo root is /tmp/my_project; after stripping, "src/main.cpp" should appear
    assert "src/main.cpp" in html
    # The full absolute path should NOT appear in file cells
    assert "/tmp/my_project/src/main.cpp" not in html


# ---------------------------------------------------------------------------
# PDF generation (skip if WeasyPrint is unavailable)
# ---------------------------------------------------------------------------


def _weasyprint_available() -> bool:
    """Return True if WeasyPrint is importable and functionally works.

    Returns:
        True only when WeasyPrint can be imported and produce PDF bytes
        without runtime errors.
    """
    try:
        import weasyprint  # noqa: F401
        from weasyprint import HTML

        # Quick smoke test: render a trivial HTML to verify pydyf compatibility
        HTML(string="<html><body>test</body></html>").write_pdf()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(
    not _weasyprint_available(),
    reason="WeasyPrint is not installed in this environment",
)
def test_generate_pdf_returns_nonempty_bytes(data_dir: Path) -> None:
    """generate_pdf() returns non-empty bytes."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    pdf_bytes = gen.generate_pdf()
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000


@pytest.mark.skipif(
    not _weasyprint_available(),
    reason="WeasyPrint is not installed in this environment",
)
def test_generate_pdf_starts_with_pdf_magic(data_dir: Path) -> None:
    """Generated PDF bytes start with the %PDF magic number."""
    from src.pdf_generator import PDFGenerator

    gen = PDFGenerator(data_dir)
    pdf_bytes = gen.generate_pdf()
    assert pdf_bytes[:4] == b"%PDF"
