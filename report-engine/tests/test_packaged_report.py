"""Installed-style reports use package resources and optional render backends."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


@pytest.fixture()
def package_archive(tmp_path: Path) -> Path:
    """Retain only package code/resources, without checkout docs or legacy src."""
    import cppulse

    package = Path(cppulse.__file__).resolve().parent
    archive = tmp_path / "cppulse-package.zip"
    suffixes = {
        ".py",
        ".json",
        ".html",
        ".css",
        ".cmake",
        ".js",
        ".txt",
        ".md",
        ".yaml",
    }
    with zipfile.ZipFile(archive, "w") as output:
        for path in package.rglob("*"):
            if path.is_file() and path.suffix in suffixes:
                output.write(path, Path("cppulse") / path.relative_to(package))
    return archive


def run_isolated(
    archive: Path, program: str, *arguments: Path
) -> subprocess.CompletedProcess[str]:
    """Run without source paths, injected env paths or optional plot/PDF imports."""
    bootstrap = """
import importlib.abc
import sys
sys.path.insert(0, sys.argv[1])
class BlockRenderExtras(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'matplotlib', 'weasyprint'}:
            raise ModuleNotFoundError('Optional rendering dependency blocked: ' + fullname)
sys.meta_path.insert(0, BlockRenderExtras())
import cppulse
assert cppulse.__file__.startswith(sys.argv[1] + '/'), cppulse.__file__
"""
    # This subprocess exercises a second, zipped copy of the package. Do not
    # let pytest-cov auto-register that copy as duplicate canonical source.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_"))
    }
    return subprocess.run(
        [sys.executable, "-I", "-c", bootstrap + program, str(archive)]
        + [str(argument) for argument in arguments],
        cwd=archive.parent,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        env=environment,
    )


def test_packaged_html_json_work_without_plotting_or_pdf_dependencies(
    package_archive: Path, data_dir: Path, tmp_path: Path
) -> None:
    """A zipped installed-style package renders styled HTML and validated JSON."""
    html_path = tmp_path / "nested/report.html"
    json_path = tmp_path / "report.json"
    program = """
from pathlib import Path
from cppulse.report_engine.pdf_generator import main
from cppulse.report_engine.schema_validator import load_schema
from cppulse.report_engine.api import app
assert app.title == 'cppulse Report Engine'
assert load_schema('risk_scores')['properties']['version']['const'] == '1.0.0'
assert 'matplotlib' not in sys.modules and 'weasyprint' not in sys.modules
for format, output in [('html', sys.argv[3]), ('json', sys.argv[4])]:
    assert main(['--data', sys.argv[2], '--output', output, '--format', format]) == 0
assert 'matplotlib' not in sys.modules and 'weasyprint' not in sys.modules
"""
    result = run_isolated(package_archive, program, data_dir, html_path, json_path)
    assert result.returncode == 0, result.stderr
    html = html_path.read_text()
    assert "<style>" in html
    assert "@page" in html
    assert 'href="styles.css"' not in html
    assert "Chart unavailable; category values are shown in the table" in html
    assert "72.5" in html
    assert "CPP-MEM-001" in html
    assert set(json.loads(json_path.read_text())) == {
        "findings",
        "git_metrics",
        "risk_scores",
        "roadmap",
    }


def test_missing_pdf_dependency_explains_extra_and_keeps_output_absent(
    package_archive: Path, data_dir: Path, tmp_path: Path
) -> None:
    target = tmp_path / "missing.pdf"
    program = """
from cppulse.report_engine.pdf_generator import main
assert main(['--data', sys.argv[2], '--output', sys.argv[3], '--format', 'pdf']) == 1
"""
    result = run_isolated(package_archive, program, data_dir, target)
    assert result.returncode == 0, result.stderr
    assert "cppulse[pdf]" in result.stderr
    assert "--format html or json" in result.stderr
    assert not target.exists()


def test_legacy_module_alias_preserves_monkeypatches(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy imports address the canonical module, including its API globals."""
    from fastapi.testclient import TestClient

    from cppulse.report_engine import api as canonical_api
    from cppulse.report_engine import pdf_generator as canonical_pdf
    from cppulse.report_engine import schema_validator as canonical_schema
    import src.api as legacy_api
    import src.pdf_generator as legacy_pdf
    import src.schema_validator as legacy_schema

    assert legacy_api is canonical_api
    assert legacy_pdf is canonical_pdf
    assert legacy_schema is canonical_schema
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    monkeypatch.setattr(legacy_api, "_data_dir", lambda: data_dir)
    legacy_api._json_cache.clear()
    response = TestClient(canonical_api.app).get("/api/v1/summary")
    assert response.status_code == 200
    assert response.json()["health_score"]["overall"] == 72.5


def test_html_dispatch_does_not_call_pdf_backend(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse.report_engine.pdf_generator import PDFGenerator, main

    def reject_pdf(self: PDFGenerator) -> bytes:
        raise AssertionError("PDF backend called for HTML")

    monkeypatch.setattr(PDFGenerator, "generate_pdf", reject_pdf)
    output = tmp_path / "report.html"
    assert (
        main(["--data", str(data_dir), "--output", str(output), "--format", "html"])
        == 0
    )
    assert "<style>" in output.read_text()


def test_legacy_checkout_module_still_runs_without_pythonpath(
    data_dir: Path, tmp_path: Path
) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    component = Path(__file__).resolve().parents[1]
    target = tmp_path / "legacy-report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.pdf_generator",
            "--data",
            str(data_dir),
            "--output",
            str(target),
            "--format",
            "json",
        ],
        cwd=component,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "findings" in json.loads(target.read_text())
