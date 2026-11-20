"""Public Git producer preserves explicit label scope and history availability."""
import json
from pathlib import Path

import pytest

from cppulse.git_miner import main
from tests.test_szz_cutoff_history79 import cutoff_history  # noqa: F401


def test_public_cutoff_is_recorded_without_relabeling_history_partial(cutoff_history, tmp_path):
    output = tmp_path / "output"
    assert main.run(
        Path(cutoff_history.working_tree_dir), output,
        szz_cutoff="2020-01-05T00:00:00Z",
    ) == 0
    document = json.loads((output / "git_metrics.json").read_bytes())
    assert document["metadata"]["history_status"] == "available"
    assert document["metadata"]["total_commits"] == 4
    assert document["metadata"]["szz"]["analysis_cutoff"] == "2020-01-05T00:00:00Z"
    assert document["metadata"]["szz"]["cutoff_source"] == "explicit"
    assert document["metadata"]["szz"]["label_kind"] == "imperfect_candidate"
    assert document["metadata"]["szz"]["feature_history_scope"] == "retained_history_not_cutoff_filtered"
    metrics = {row["file"]: row for row in document["file_metrics"]}
    assert metrics["old.cpp"]["szz_bug_introductions"] == 1
    assert metrics["new.cpp"]["szz_bug_introductions"] == 0
    assert any("not a historical feature snapshot" in note for note in document["metadata"]["limitations"])


@pytest.mark.parametrize("value", ["bad", "2020-01-05T00:00:00", "2020-01-05T01:00:00+01:00", True])
def test_invalid_public_cutoff_refuses_without_history_or_output(tmp_path, monkeypatch, value):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid cutoff caused a history scan")
    monkeypatch.setattr(main, "scan_history", forbidden)
    output = tmp_path / "output"
    assert main.run(tmp_path, output, szz_cutoff=value) == 1
    assert not output.exists()


def test_component_cli_accepts_independent_szz_cutoff(tmp_path):
    args = main.parse_args(["--repo", str(tmp_path), "--szz-cutoff", "2020-01-05T00:00:00Z"])
    assert args.szz_cutoff == "2020-01-05T00:00:00Z"
    assert args.behavior_cutoff is None
