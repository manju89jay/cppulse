"""Pure presentation contracts, not evidence of native producer execution.

The CLI persistence boundary is replaced only to supply exact stored facts.
The legacy math and packaged HTML renderer execute their real implementation.
"""

from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
import importlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

import pandas as pd
import pytest

from cppulse.maintenance import compute_maintenance_health
from cppulse.predictor.feature_engineer import FEATURE_COLUMNS
from cppulse.predictor.health_scorer import HealthScorer
from cppulse.predictor.main import build_risk_scores
from cppulse.predictor.model import BugPredictor
from tests.test_measured_maintenance import inputs as measured_inputs


@pytest.fixture(autouse=True)
def installed_origin_when_requested():
    selected = os.environ.get("CPPULSE_PRESENTATION_EXPECT_PREFIX117")
    if selected:
        expected = Path(selected).resolve() / "cppulse"
        for name in (
            "cppulse",
            "cppulse.cli",
            "cppulse.maintenance",
            "cppulse.predictor.main",
            "cppulse.predictor.health_scorer",
            "cppulse.report_engine.pdf_generator",
        ):
            assert (
                Path(importlib.import_module(name).__file__)
                .resolve()
                .is_relative_to(expected)
            )


def stored_health(state):
    """Actual pure v4 calculator over explicitly synthetic measured contracts."""
    arguments = measured_inputs()
    if state == "partial":
        arguments["required_context_ids"].append("required-missing117")
    elif state == "no_data":
        arguments.update(inventories=[], metrics=[], observations=[])
    result = compute_maintenance_health(**arguments)
    assert result["aggregate"]["availability"] == state
    return result


@pytest.mark.parametrize("state", ["scored", "partial", "no_data"])
def test_cli_maintenance_copies_stored_method_scope_and_completeness(
    tmp_path, monkeypatch, capsys, state
):
    import cppulse.cli as cli
    import cppulse.maintenance as maintenance
    import cppulse.workflows as workflows

    health = stored_health(state)
    before = deepcopy(health)
    parent = object()
    child = SimpleNamespace(run_id="derived117", manifest_sha256="b" * 64)
    calls = []

    def persist(snapshot, **keywords):
        assert snapshot is parent
        calls.append(keywords)
        return child

    def documents(snapshot):
        assert snapshot is child
        return {"maintenance_health": [health]}

    monkeypatch.setattr(cli, "_selected_run", lambda arguments: parent)
    monkeypatch.setattr(maintenance, "persist_maintenance_health", persist)
    monkeypatch.setattr(workflows, "read_documents", documents)
    arguments = [
        "maintenance",
        "--store",
        str(tmp_path / "store"),
        "--workspace",
        str(tmp_path / "workspace"),
    ]
    for context in health["required_context_ids"]:
        arguments += ["--required-context", context]
    status = cli.main(arguments)
    output = json.loads(capsys.readouterr().out)
    assert status == (0 if state == "scored" else 3)
    assert output["run_id"] == child.run_id
    assert output["manifest_sha256"] == child.manifest_sha256
    assert output["scorer"] == health["scorer"]["id"]  # Existing string stays stable.
    assert output["maintenance"] == health["aggregate"]
    assert output["scorer_details"] == health["scorer"]
    assert output["contexts"] == health["contexts"]
    assert output["required_context_ids"] == health["required_context_ids"]
    assert output["optional_context_ids"] == health["optional_context_ids"]
    assert output["formula_reference"] == "docs/contracts/maintenance-metrics.md"
    assert output["consumer_assurance"] == "not_assessed"
    assert health == before
    assert (
        len(calls) == 1
        and calls[0]["required_context_ids"] == health["required_context_ids"]
    )
    if state == "scored":
        assert output["scorer_details"]["version"] == "4.0.0"
        assert output["contexts"][0]["physical_loc"] == 1000
        assert output["maintenance"]["overall"] == pytest.approx(81.81818181818181)
    else:
        assert output["maintenance"]["overall"] is None
        assert output["maintenance"]["incomplete_required_context_ids"]


def calibration_risk(*, state="scored", profile="default", declared=2):
    """Synthetic math API with declared prerequisite attrs; no execution claim."""
    rows = []
    if state != "no_data":
        for name in ("a.cpp", "b.cpp"):
            row = dict.fromkeys(FEATURE_COLUMNS, 0)
            row.update(file=name, age_days=365, unique_contributors=1)
            rows.append(row)
        rows[0].update(
            memory_findings=1,
            complexity_findings=2,
            modernization_findings=5,
            misra_findings=3,
            finding_count=11,
        )
    frame = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    frame.attrs.update(
        health_availability=state,
        health_profile=profile,
        health_prerequisites="normalized-required-context-v4",
    )
    if declared is not None:
        frame.attrs["health_declared_file_count"] = declared
    predictor = BugPredictor(profile=profile)
    predictor.train(frame, pd.Series([0] * len(frame), dtype=int))
    return (
        build_risk_scores(
            frame, predictor.predict(frame), predictor, HealthScorer(profile)
        ),
        frame,
    )


def test_legacy_calculation_metadata_reproduces_independent_two_file_equation():
    risk, frame = calibration_risk()
    metadata = risk["metadata"]["health_calculation"]
    assert (
        metadata["method"]
        == risk["metadata"]["score_model"]
        == "weighted-findings-per-attempted-file-v2"
    )
    assert metadata["version"] == "2" and metadata["profile"] == "default"
    assert metadata["weights"] == {
        "memory_findings": 3.0,
        "complexity_findings": 1.5,
        "modernization_findings": 1.0,
    }
    assert metadata["category_scales"] == {
        "memory_safety": 15.0,
        "complexity": 10.0,
        "modernization": 5.0,
    }
    assert metadata["denominator_files"] == 2 == len(frame)
    assert metadata["declared_files"] == 2 and metadata["availability"] == "scored"
    assert isinstance(metadata["formula"], str) and metadata["formula"].strip()
    # Independent historical arithmetic, deliberately different from v4's caps/KLOC.
    assert (
        risk["health_score"]["overall"] == 100 - (1 * 3 + 2 * 1.5 + 5 * 1) / 2 == 94.5
    )
    assert risk["health_score"]["by_category"] == {
        "memory_safety": 92.5,
        "complexity": 90.0,
        "modernization": 87.5,
    }


@pytest.mark.parametrize(
    "state,declared", [("partial", 7), ("no_data", 0), ("scored", None)]
)
def test_legacy_scope_is_literal_and_partial_or_missing_inputs_are_not_full_health(
    state, declared
):
    risk, frame = calibration_risk(state=state, declared=declared)
    metadata = risk["metadata"]["health_calculation"]
    assert metadata["denominator_files"] == len(frame)
    assert metadata["declared_files"] == declared
    assert metadata["availability"] == risk["health_score"]["status"] == state
    if state != "scored":
        assert risk["health_score"]["overall"] is None
        assert all(v is None for v in risk["health_score"]["by_category"].values())


def test_safety_critical_metadata_and_math_retain_selected_profile():
    risk, _ = calibration_risk(profile="safety-critical")
    metadata = risk["metadata"]["health_calculation"]
    assert metadata["profile"] == "safety-critical"
    assert metadata["weights"]["misra_findings"] == 2.5
    assert metadata["category_scales"]["misra_compliance"] == 12.0
    assert risk["health_score"]["overall"] == 100 - (3 + 3 + 5 + 3 * 2.5) / 2 == 90.75


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)


def render(risk, tmp_path, monkeypatch):
    import cppulse.report_engine.pdf_generator as reports

    data = {
        "risk_scores": deepcopy(risk),
        "findings": {"summary": {"total_findings": 991}},
        "git_metrics": {},
        "roadmap": {},
    }
    unchanged = deepcopy(data)
    generator = reports.PDFGenerator(tmp_path)
    # Isolate data loading and optional chart graphics only; real context/Jinja run.
    monkeypatch.setattr(generator, "_collect_data", lambda: data)
    monkeypatch.setattr(reports, "_bar_chart_base64", lambda *args, **kwargs: None)
    html = generator.render_html()
    assert data == unchanged
    parser = VisibleText()
    parser.feed(html)
    text = " ".join(" ".join(parser.parts).split())
    executive = text.split("1. Executive Summary", 1)[1].split(
        "2. Health Score Breakdown", 1
    )[0]
    (tmp_path / "actual-rendered.html").write_text(html)
    return executive, text


@pytest.mark.parametrize(
    "state,declared", [("scored", 2), ("partial", 7), ("no_data", 0)]
)
def test_legacy_html_labels_same_stored_method_scope_and_availability(
    tmp_path, monkeypatch, state, declared
):
    risk, _ = calibration_risk(state=state, declared=declared)
    calculation = deepcopy(risk["metadata"]["health_calculation"])
    executive, text = render(risk, tmp_path, monkeypatch)
    assert calculation["method"] in executive
    assert calculation["formula"] in executive
    assert "version" in executive.lower() and calculation["version"] in executive
    assert "denominator" in executive.lower() and "declared" in executive.lower()
    assert str(calculation["denominator_files"]) in executive
    assert str(declared) in executive
    assert calculation["availability"] in executive
    assert "historical" in executive.lower()
    if state == "scored":
        assert "94.5" in executive
    elif state == "partial":
        assert "No score: analysis is incomplete" in executive
    else:
        assert "No score: no input files were assessed" in executive
    assert risk["metadata"]["health_calculation"] == calculation


def test_old_report_without_calculation_metadata_remains_unknown(tmp_path, monkeypatch):
    risk, _ = calibration_risk()
    calculation = risk["metadata"].pop("health_calculation")
    executive, _ = render(risk, tmp_path, monkeypatch)
    assert "unknown" in executive.lower()
    assert calculation["formula"] not in executive
    assert "denominator" in executive.lower()
    denominator = re.search(r"Observed denominator files: ([^;]+);", executive)
    declared = re.search(r"declared nonexcluded files: ([^;]+);", executive)
    assert denominator and denominator.group(1).strip() == "Not recorded"
    assert declared and declared.group(1).strip() == "Not recorded"


@pytest.mark.parametrize("fresh", [True, False])
def test_repeated_stored_calculation_checks_freshness_without_duplicate_fact(
    tmp_path, monkeypatch, fresh
):
    import cppulse.maintenance as maintenance
    import cppulse.workflows as workflows
    from cppulse.errors import InputChanged

    data = measured_inputs()
    health = compute_maintenance_health(**data)
    documents = {
        "analysis_inventory": data["inventories"],
        "analysis_metrics": data["metrics"],
        "observations": data["observations"],
        "maintenance_health": [health],
    }
    checks = []

    class Snapshot:
        manifest = {
            "source": {"digest": data["source_digest"]},
            "input_verification": "verified",
        }

        def verify(self):
            checks.append("verified")

        def read_json(self, identifier, *, contract):
            assert contract == "rule_registry"
            assert identifier in {
                row["registry_artifact_id"] for row in data["inventories"]
            }
            return data["registry"]

    parent = Snapshot()
    monkeypatch.setattr(workflows, "read_documents", lambda snapshot: documents)

    def freshness(snapshot, workspace):
        assert snapshot is parent and workspace == tmp_path
        checks.append("freshness")
        if not fresh:
            raise InputChanged("Controlled changed source")

    monkeypatch.setattr(workflows, "ensure_current_materials", freshness)
    monkeypatch.setattr(
        workflows,
        "_derive",
        lambda *a, **k: pytest.fail("Duplicate calculation published"),
    )

    def call():
        return maintenance.persist_maintenance_health(
            parent,
            workspace=tmp_path,
            store=tmp_path / "unused-store",
            required_context_ids=data["required_context_ids"],
        )

    if fresh:
        assert call() is parent
    else:
        with pytest.raises(InputChanged):
            call()
    assert "verified" in checks and checks.count("freshness") == 1
    assert documents["maintenance_health"] == [health]


def test_cli_replay_selects_requested_calculation_from_retained_contexts(
    tmp_path, monkeypatch, capsys
):
    import cppulse.cli as cli
    import cppulse.maintenance as maintenance
    import cppulse.workflows as workflows

    health = stored_health("scored")
    later = stored_health("partial")
    parent = SimpleNamespace(run_id="existing117", manifest_sha256="c" * 64)
    monkeypatch.setattr(cli, "_selected_run", lambda args: parent)
    monkeypatch.setattr(
        maintenance, "persist_maintenance_health", lambda *a, **k: parent
    )
    monkeypatch.setattr(
        workflows,
        "read_documents",
        lambda snapshot: {"maintenance_health": [health, later]},
    )
    arguments = [
        "maintenance",
        "--store",
        str(tmp_path / "store"),
        "--workspace",
        str(tmp_path),
    ]
    for context in health["required_context_ids"]:
        arguments += ["--required-context", context]
    assert cli.main(arguments) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["maintenance"] == health["aggregate"]
    assert output["contexts"] == health["contexts"]
    assert output["run_id"] == parent.run_id
    assert later["aggregate"]["overall"] is None
