"""Historical tooling cannot turn inconsistent or absent facts into new cards."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def script(name: str) -> Any:
    """Load the actual script without depending on caller working directory."""
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / (name + ".py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_floating_revision_is_refused_before_cache_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script("refresh_showcase")
    monkeypatch.setattr(module, "SHOWCASE_CACHE", tmp_path / "cache")

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "No network/reset command is allowed for an unpinned selection"
        )

    monkeypatch.setattr(module, "_run", forbidden)
    with pytest.raises(ValueError, match="full upstream revision"):
        module.clone_or_update(
            {"id": "unpinned", "repo_url": "https://example.invalid/repo"}
        )
    assert not (tmp_path / "cache").exists()


def test_absent_analyzer_is_failure_not_a_successful_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script("refresh_showcase")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "EXAMPLES_DIR", tmp_path / "examples")
    with pytest.raises(FileNotFoundError, match="no derived assets"):
        module.run_analysis("sample", tmp_path / "source")
    assert not (tmp_path / "examples/sample/findings.json").exists()


def test_inconsistent_actual_records_block_derived_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script("refresh_showcase")
    source = tmp_path / "sample"
    source.mkdir()
    (source / "findings.json").write_text(
        json.dumps(
            {
                "findings": [{"category": "modernization"}],
                "summary": {"total_findings": 1, "by_category": {"modernization": 99}},
            }
        )
    )
    monkeypatch.setattr(module, "EXAMPLES_DIR", tmp_path)
    with pytest.raises(ValueError, match="counters disagree"):
        module.validate_result_counts(["sample"])


def test_pdf_download_link_depends_on_actual_file(tmp_path: Path) -> None:
    module = script("generate_example_readme")
    project = tmp_path / "sample"
    project.mkdir()
    findings = {
        "metadata": {},
        "findings": [],
        "summary": {"total_findings": 0, "by_category": {}},
    }
    # These are explicitly in-memory rendering fixtures, not analysis evidence.
    for name, document in [
        ("findings.json", findings),
        (
            "risk_scores.json",
            {"health_score": {"overall": 42, "by_category": {}}, "file_risks": []},
        ),
        ("roadmap.json", {"items": []}),
    ]:
        (project / name).write_text(json.dumps(document))
    meta = {
        "display_name": "Rendering fixture",
        "description": "Synthetic rendering input.",
    }
    rendered = module.render_readme("sample", meta, tmp_path, ROOT / "templates")
    assert "(report.pdf)" not in rendered
    (project / "report.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    rendered = module.render_readme("sample", meta, tmp_path, ROOT / "templates")
    assert "(report.pdf)" in rendered
    findings["summary"]["total_findings"] = 99
    (project / "findings.json").write_text(json.dumps(findings))
    with pytest.raises(ValueError, match="counters disagree"):
        module.render_readme("sample", meta, tmp_path, ROOT / "templates")
