"""Measured CC must survive finding counterfactuals through public consumers.

The baseline is one real native invocation. Altered finding rows and history
tables are explicitly authored consumer inputs, never additional native/Git
executions or authenticated receipts. Flat legacy reports retain that limit.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import cppulse
import pandas as pd
import pytest

from cppulse.contracts import validate
from cppulse.predictor.feature_engineer import FeatureEngineer
from cppulse.predictor.health_scorer import HealthScorer
from cppulse.predictor.main import build_risk_scores
from cppulse.predictor.measured_hotspots import native_hotspot_metrics
from cppulse.predictor.model import BugPredictor
import test_analysis_execution as native_fixtures

SOURCE = (
    "int classify(int value) {\n"
    "    if (value > 0 && value < 10) {\n"
    "        return 1;\n"
    "    }\n"
    "    return 0;\n"
    "}\n"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n")


@pytest.fixture(scope="module")
def genuine_complexity113(tmp_path_factory: pytest.TempPathFactory):
    """Run the real selected analyzer once; never silently choose a fake report."""
    expected_prefix = os.environ.get("CPPULSE_COMPLEXITY_EXPECT_PREFIX113")
    if expected_prefix:
        assert (
            Path(cppulse.__file__)
            .resolve()
            .is_relative_to(Path(expected_prefix).resolve())
        )
    native = native_fixtures.native.__wrapped__()
    expected_native = os.environ.get("CPPULSE_COMPLEXITY_EXPECT_NATIVE_SHA113")
    if expected_native:
        assert _sha(native.analyzer) == expected_native
    root = tmp_path_factory.mktemp("genuine-complexity113")
    repo = root / "source"
    repo.mkdir()
    source = repo / "measured.cpp"
    source.write_text(SOURCE)
    _write(
        repo / "compile_commands.json",
        [
            {
                "directory": str(repo),
                "file": str(source),
                "arguments": ["clang++", "-std=c++17", "-c", str(source)],
            }
        ],
    )
    config = root / "native-config.json"
    _write(
        config,
        {
            "rules": {
                "CPP-CX-001": {
                    "warning_threshold": 0,
                    "error_threshold": 1000,
                }
            }
        },
    )
    output = root / "native-output"
    command = [
        str(native.analyzer),
        "--repo",
        str(repo),
        "--config",
        str(config),
        "--output",
        str(output),
    ]
    if native.resource_dir is not None:
        command.extend(["--resource-dir", str(native.resource_dir)])
    result = subprocess.run(
        command,
        env=native.environment(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    (root / "native.stdout").write_text(result.stdout)
    (root / "native.stderr").write_text(result.stderr)
    _write(
        root / "producer.json",
        {
            "command": command,
            "exit_status": result.returncode,
            "native_sha256": _sha(native.analyzer),
            "source_sha256": _sha(source),
            "configuration_sha256": _sha(config),
            "resource_dir": str(native.resource_dir) if native.resource_dir else None,
            "meaning": "Actual local invocation only; no installed-kit or producer-authentication claim.",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report_path = output / "findings.json"
    report = json.loads(report_path.read_bytes())
    validate("findings", report, version="prototype_v1")
    raw = report["metadata"]["analysis"]["native_metrics"]["files"]
    assert len(raw) == 1
    assert raw[0]["status"] == "analyzed" and raw[0]["measurement_complete"]
    assert raw[0]["error_count"] == 0 and raw[0]["function_count"] == 1
    assert raw[0]["source_content_sha256"] == _sha(source)
    assert raw[0]["physical_loc"] == len(SOURCE.splitlines()) == 6
    assert raw[0]["functions"][0]["cyclomatic_complexity"] == 3
    assert any(row["rule_id"] == "CPP-CX-001" for row in report["findings"])
    original_report_sha256 = _sha(report_path)
    yield {
        "root": root,
        "repo": repo,
        "report": report,
        "report_path": report_path,
        "report_sha256": original_report_sha256,
        "source": source,
        "source_sha256": _sha(source),
    }
    assert _sha(report_path) == original_report_sha256
    assert _sha(source) == hashlib.sha256(SOURCE.encode()).hexdigest()


def _counterfactual(
    genuine: dict, *, severity: str, count: int, missing: bool = False
) -> dict:
    """Alter finding claims/census only, retaining genuine measured quantities."""
    report = deepcopy(genuine["report"])
    first = next(row for row in report["findings"] if row["rule_id"] == "CPP-CX-001")
    report["findings"] = [
        {
            **first,
            "severity": severity,
            "message": first["message"] + f" [authored counterfactual {index}]",
        }
        for index in range(count)
    ]
    report["summary"] = {
        "total_findings": count,
        "by_category": dict(Counter(row["category"] for row in report["findings"])),
        "by_severity": {severity: count},
    }
    analysis = report["metadata"]["analysis"]
    for row in [*analysis["files"], *analysis["native_metrics"]["files"]]:
        if "finding_count" in row:
            row["finding_count"] = count
    if missing:
        del analysis["native_metrics"]
    validate("findings", report, version="prototype_v1")
    return report


def _risk(report: dict, repo: Path) -> tuple[dict, dict]:
    """Exercise the actual predictor with explicitly declared history features."""
    history = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": str(repo),
            "analyzed_at": report["metadata"]["analyzed_at"],
            "commit_range": "authored-counterfactual-history",
            "total_commits": 3,
            "history_status": "available",
            "limitations": ["Authored consumer history input; not a Git execution."],
        },
        "file_metrics": [
            {
                "file": "measured.cpp",
                "change_frequency": 3,
                "unique_contributors": 1,
                "age_days": 1,
                "lines_of_code": 987654,
            }
        ],
        "knowledge_silos": [],
    }
    frame = FeatureEngineer().build_features(report, history)
    model = BugPredictor()
    model.train(frame, pd.Series([0] * len(frame), dtype=int))
    result = build_risk_scores(frame, model.predict(frame), model, HealthScorer())
    validate("risk_scores", result, version="prototype_v1")
    return result, history


def _dataset(path: Path, report: dict, risk: dict, history: dict) -> None:
    for name, document in {
        "findings": report,
        "risk_scores": risk,
        "git_metrics": history,
        "roadmap": {"version": "1.0.0", "items": []},
    }.items():
        _write(path / (name + ".json"), document)
    (path / "AUTHORED-INPUT-PROVENANCE.txt").write_text(
        "Genuine baseline native metrics; authored finding/history counterfactuals.\n"
        "No additional execution, authenticated history or immutable run receipt is claimed.\n"
    )


@pytest.mark.parametrize("severity,count", [("info", 1), ("error", 1), ("warning", 17)])
def test_real_cc_and_loc_do_not_become_severity_or_finding_count(
    genuine_complexity113: dict, tmp_path: Path, severity: str, count: int
) -> None:
    report = _counterfactual(genuine_complexity113, severity=severity, count=count)
    claims = native_hotspot_metrics(report)
    assert claims["measured.cpp"]["complexity_score"] == 3
    assert claims["measured.cpp"]["physical_loc"] == 6
    risk, history = _risk(report, genuine_complexity113["repo"])
    assert risk["metadata"]["hotspot_method"] == "measured-cc-physical-kloc-v1"
    assert len(risk["hotspots"]) == 1
    row = risk["hotspots"][0]
    assert row["complexity_score"] == 3 and row["physical_loc"] == 6
    assert row["finding_count"] == count
    assert row["hotspot_score"] == pytest.approx(3 * 3 * count * 1000 / 6)
    assert row["physical_loc"] != history["file_metrics"][0]["lines_of_code"]
    _write(tmp_path / "counterfactual-findings.json", report)
    _write(tmp_path / "actual-predictor-result.json", risk)
    assert (
        _sha(genuine_complexity113["report_path"])
        == genuine_complexity113["report_sha256"]
    )


def test_missing_measured_inventory_is_unavailable_despite_many_severe_findings(
    genuine_complexity113: dict, tmp_path: Path
) -> None:
    report = _counterfactual(
        genuine_complexity113, severity="error", count=17, missing=True
    )
    assert native_hotspot_metrics(report) == {}
    risk, _ = _risk(report, genuine_complexity113["repo"])
    assert risk["hotspots"] == []
    scope = risk["metadata"]["hotspot_scope"]
    assert scope["status"] == "unavailable" and scope["measured_files"] == 0
    assert [row["file"] for row in scope["unavailable_files"]] == ["measured.cpp"]
    _write(tmp_path / "missing-measurement-findings.json", report)
    _write(tmp_path / "actual-unavailable-result.json", risk)


@pytest.mark.parametrize("missing", [False, True])
def test_public_json_html_preserve_measured_method_and_unavailable_inventory(
    genuine_complexity113: dict, tmp_path: Path, missing: bool
) -> None:
    report = _counterfactual(
        genuine_complexity113, severity="error", count=17, missing=missing
    )
    risk, history = _risk(report, genuine_complexity113["repo"])
    data = tmp_path / "declared flat inputs"
    _dataset(data, report, risk, history)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(Path(cppulse.__file__).resolve().parent.parent)
    before = {path.name: _sha(path) for path in data.iterdir() if path.is_file()}
    for kind in ["json", "html"]:
        output = tmp_path / ("public." + kind)
        command = [
            sys.executable,
            "-m",
            "cppulse",
            "report",
            "--input",
            str(data),
            "--format",
            kind,
            "--output",
            str(output),
        ]
        result = subprocess.run(
            command,
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        (tmp_path / (kind + ".stdout")).write_text(result.stdout)
        (tmp_path / (kind + ".stderr")).write_text(result.stderr)
        _write(
            tmp_path / (kind + ".command.json"),
            {
                "argv": command,
                "exit_status": result.returncode,
                "meaning": "Flat compatibility consumer, explicitly unverified imported claims.",
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        if kind == "json":
            published = json.loads(output.read_bytes())["risk_scores"]
            assert published["hotspots"] == risk["hotspots"]
            assert (
                published["metadata"]["hotspot_scope"]
                == risk["metadata"]["hotspot_scope"]
            )
        else:
            text = output.read_text()
            assert "maximum measured cyclomatic complexity" in text
            assert "Missing prerequisites remain unavailable" in text
    assert {
        path.name: _sha(path) for path in data.iterdir() if path.is_file()
    } == before


@pytest.mark.parametrize("missing", [False, True])
def test_existing_api_hotspot_field_preserves_literal_cc_or_absent_measurement(
    genuine_complexity113: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: bool,
) -> None:
    pytest.importorskip(
        "fastapi",
        reason="Current optional API prerequisite is required for this consumer check",
    )
    from cppulse.report_engine import api

    report = _counterfactual(
        genuine_complexity113, severity="error", count=17, missing=missing
    )
    risk, history = _risk(report, genuine_complexity113["repo"])
    data = tmp_path / "actual API file inputs"
    _dataset(data, report, risk, history)
    monkeypatch.setenv("DATA_DIR", str(data))
    # Start the same filesystem selection the real request dependency uses;
    # do not mock _load_json, endpoint output or measured producer data.
    token = api._request_data.set(None)
    try:
        payload = api.hotspots()
    finally:
        api._request_data.reset(token)
    assert payload["method"] == "measured-cc-physical-kloc-v1"
    assert payload["items"] == risk["hotspots"]
    assert payload["scope"] == risk["metadata"]["hotspot_scope"]
    if missing:
        assert payload["items"] == [] and payload["scope"]["status"] == "unavailable"
    else:
        assert payload["items"][0]["complexity_score"] == 3
        assert payload["items"][0]["physical_loc"] == 6
    _write(tmp_path / "actual-api-handler-result.json", payload)
