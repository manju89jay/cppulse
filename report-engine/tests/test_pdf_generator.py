"""Tests for the PDFGenerator class."""

from __future__ import annotations

from pathlib import Path

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
