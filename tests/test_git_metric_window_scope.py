"""Emitted time scopes distinguish legacy metrics from configured behavior."""

from copy import deepcopy
from datetime import datetime, timezone
import json

import git

from cppulse.git_miner.history_cache import validate_history_document
from cppulse.git_miner.main import run
from test_behavior_identity_history import configuration


def test_configured_behavior_windows_disclose_unfiltered_legacy_scope(
    tmp_path,
    monkeypatch,
):
    import cppulse.git_miner.main as producer

    scan = producer.scan_history
    cache_results = []

    def observe(*args, **kwargs):
        result = scan(*args, **kwargs)
        cache_results.append((result.cache_info, deepcopy(result.cache_info)))
        return result

    monkeypatch.setattr(producer, "scan_history", observe)
    source = tmp_path / "source"
    source.mkdir()
    repo = git.Repo.init(source)
    actor = git.Actor("Local scope fixture", "scope@example.invalid")
    for day, value in [(1, 1), (12, 2), (16, 3)]:
        (source / "main.cpp").write_text(f"int value() {{ return {value}; }}\n")
        repo.index.add(["main.cpp"])
        stamp = datetime(2026, 11, day, 12, tzinfo=timezone.utc)
        repo.index.commit(
            f"Local fixture {day}",
            author=actor,
            committer=actor,
            author_date=stamp,
            commit_date=stamp,
        )
    metrics = []
    for days in (None, 7, 2):
        output = tmp_path / f"window-{days}"
        behavior_request = (
            {
                "behavior_config": configuration(window_days=days).document,
                "behavior_cutoff": "2026-11-17T00:00:00Z",
            }
            if days is not None
            else {}
        )
        assert run(source, output, **behavior_request) == 0
        legacy = json.loads((output / "git_metrics.json").read_text())
        history = json.loads((output / "git_history.json").read_text())
        notes = legacy["metadata"]["limitations"]
        scope = next((note for note in notes if "Legacy file metrics" in note), None)
        metrics.append(legacy["file_metrics"])
        if days is None:
            assert scope is None
            assert not (output / "git_behavior.json").exists()
            continue
        behavior = json.loads((output / "git_behavior.json").read_text())
        assert scope is not None, "Legacy metrics omit their retained-history scope"
        assert "only to behavioral metrics" in scope
        assert scope in history["limitations"]
        assert "90" not in scope
        validate_history_document("result", history)
        assert legacy["metadata"]["total_commits"] == 3
        assert legacy["metadata"]["history_status"] == "available"
        assert behavior["configuration"]["window_days"] == days
    assert metrics[0] == metrics[1] == metrics[2]
    assert cache_results and all(actual == frozen for actual, frozen in cache_results)
