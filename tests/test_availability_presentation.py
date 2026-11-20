"""Immutable report views retain scope gaps in their optional legacy sections."""

from __future__ import annotations

from pathlib import Path

import pytest

from cppulse.presentation import build_snapshot_view, render_snapshot_html
import test_presentation as fixtures


def test_snapshot_report_shows_unranked_files_and_insufficient_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same checked raw bytes drive gaps in snapshot HTML and API views."""
    documents = fixtures.legacy_documents()
    documents["risk_scores"]["unranked_files"] = [
        {
            "file": "src/incomplete.hpp",
            "availability": "partial",
            "reason_codes": ["PARTIAL_ANALYSIS"],
            "reasons": ["A selected context could not be parsed."],
        }
    ]
    documents["risk_scores"]["metadata"]["ranking_scope"] = {
        "version": "file-eligibility-1",
        "declared_files": 1,
        "ranked_files": 0,
        "unranked_files": 1,
    }
    documents["git_metrics"]["metadata"].update(
        history_status="partial", limitations=["Synthetic shallow history."]
    )
    monkeypatch.setattr(fixtures, "legacy_documents", lambda: documents)
    snapshot = fixtures.publish_snapshot(tmp_path, legacy=True)

    view = build_snapshot_view(snapshot)
    rendered = render_snapshot_html(view)

    assert (
        view["legacy"]["risk_scores"]["document"]["unranked_files"]
        == documents["risk_scores"]["unranked_files"]
    )
    assert "Files without a usable rank" in rendered
    assert "src/incomplete.hpp" in rendered
    assert "A selected context could not be parsed." in rendered
    assert "Insufficient history" in rendered
    assert "No knowledge silos recorded" not in rendered
