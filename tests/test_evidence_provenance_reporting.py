"""Supplied review metadata is reported as a claim, with explicit provenance.

All records in these presentation fixtures are synthetic transport inputs;
they do not claim that a producer ran or that a human approved anything.
"""
from copy import deepcopy
import json

from cppulse.presentation import (
    build_snapshot_view,
    render_snapshot_html,
    render_snapshot_json,
)
from cppulse.run_store import RunStore
from test_contracts_v2 import evidence_document
from test_policy_extensions_contract import declared_review
from test_presentation import publish_snapshot


def mixed_snapshot(tmp_path, *, legacy=False, hostile=False, review_count=1):
    base = publish_snapshot(tmp_path, assessed=False)
    document = evidence_document()
    execution = deepcopy(document["records"][0])
    execution["id"] = "controlled-execution"
    imported = deepcopy(execution)
    imported.update(id="controlled-import", origin="import", receipt_id=None)
    imported["producer"] = {"name": "controlled-importer", "version": "1.0.0"}
    review = declared_review()["records"][0]
    review.update(
        reviewer="controlled-reviewer",
        scope={
            "files": execution["scope"]["files"],
            "tests": ["declared-review-scope"],
        },
    )
    review["review_details"]["source_digest"] = document["source_digest"]
    actual = next(r for r in base.manifest["artifacts"] if r["id"] == "findings")
    review["review_details"]["reviewed_artifact_sha256"] = {
        "findings": actual["sha256"]
    }
    review["review_details"][
        "rationale"
    ] = "Synthetic supplied rationale; no actual human approval."
    if hostile:
        review["reviewer"] = "<script>attester()</script>"
        review["review_details"]["rationale"] = '<img src=x onerror="attest()">'
    if legacy:
        review.pop("review_details")
    reviews = [
        dict(deepcopy(review), id="controlled-review-" + str(i))
        for i in range(review_count)
    ]
    document["records"] = [execution, imported, *reviews]
    store = RunStore(tmp_path / "store")
    with store.begin("mixed-origins") as stage:
        for row in base.manifest["artifacts"]:
            if row["id"] == "evidence":
                continue
            stage.copy_artifact(
                row["id"],
                base.path / row["path"],
                row["path"],
                row["media_type"],
                contract=row.get("contract"),
            )
        stage.write_json(
            "facts/evidence.json", document, artifact_id="evidence", contract="evidence"
        )
        manifest = base.manifest
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        snapshot = stage.publish(manifest)
    return snapshot, document


def test_html_distinguishes_all_record_origins_and_supplied_review_metadata(tmp_path):
    snapshot, _ = mixed_snapshot(tmp_path)
    html = render_snapshot_html(build_snapshot_view(snapshot))
    for expected in [
        "Execution-derived",
        "Imported producer claim",
        "Human attestation",
        "controlled-reviewer",
        "Synthetic supplied rationale; no actual human approval.",
        "2026-12-13T12:00:00Z",
        "declared-review-scope",
        "self_declared",
        "Reviewer identity has not been authenticated.",
    ]:
        assert expected in html, expected
    assert "Identity assurance" in html


def test_legacy_attestation_retains_supplied_reviewer_and_expiry_without_invention(
    tmp_path,
):
    snapshot, _ = mixed_snapshot(tmp_path, legacy=True)
    html = render_snapshot_html(build_snapshot_view(snapshot))
    assert "controlled-reviewer" in html and "2026-12-13T12:00:00Z" in html
    assert "No structured review details supplied" in html
    assert "Synthetic supplied rationale" not in html


def test_review_claims_are_escaped_for_html_and_preserved_in_json(tmp_path):
    snapshot, document = mixed_snapshot(tmp_path, hostile=True)
    view = build_snapshot_view(snapshot)
    html = render_snapshot_html(view)
    assert "<script>attester()</script>" not in html
    assert "&lt;script&gt;attester()&lt;/script&gt;" in html
    assert "<img src=x" not in html and "&lt;img" in html
    raw = next(
        f["raw_json"]
        for f in json.loads(render_snapshot_json(view))["facts"]
        if f["kind"] == "evidence"
    )
    assert json.loads(raw) == document


def test_every_supplied_record_is_preserved_in_json_when_html_is_bounded(tmp_path):
    snapshot, document = mixed_snapshot(tmp_path, review_count=51)
    view = build_snapshot_view(snapshot)
    html = render_snapshot_html(view)
    assert "Showing 50 of 53 evidence records" in html
    exported = json.loads(render_snapshot_json(view))
    raw = next(f["raw_json"] for f in exported["facts"] if f["kind"] == "evidence")
    assert json.loads(raw) == document and len(document["records"]) == 53


def test_reporting_does_not_mutate_record_origin_status_or_identity_assurance(tmp_path):
    snapshot, document = mixed_snapshot(tmp_path)
    view = build_snapshot_view(snapshot)
    before = deepcopy(view)
    render_snapshot_html(view)
    assert view == before
    raw = next(f["raw_json"] for f in view["facts"] if f["kind"] == "evidence")
    assert json.loads(raw) == document
    assert (
        document["records"][-1]["review_details"]["identity_assurance"]
        == "self_declared"
    )
