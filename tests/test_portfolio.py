"""Private local portfolio contracts and actual RunStore schedule scenarios."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from cppulse.errors import ContractError
from cppulse.identities import digest_json
from cppulse.portfolio import build_portfolio, schedule_tick, validate_config
from test_presentation import publish_snapshot

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def settings(tmp_path: Path, *, schedules: bool = False) -> dict:
    projects = []
    for index in range(3):
        root = tmp_path / f"project-{index}"
        root.mkdir()
        snapshot = publish_snapshot(
            root,
            run_id=f"run-{index}",
            gate="passed" if index == 0 else "insufficient_evidence",
            legacy=True,
        )
        projects.append(
            {
                "id": f"p{index}",
                "store": str(root / "store"),
                "run_id": snapshot.run_id,
                "manifest_sha256": snapshot.manifest_sha256,
            }
        )
    return {
        "version": "1.0.0",
        "id": "local-portfolio",
        "authorized_roots": [str(tmp_path / f"project-{index}") for index in range(3)],
        "projects": projects,
        "goals": [],
        "team_history": [
            {
                "project_id": "p0",
                "team_id": "core",
                "effective_from": "2026-01-01T00:00:00Z",
                "effective_until": "2026-11-17T00:00:00Z",
            },
            {
                "project_id": "p0",
                "team_id": "platform",
                "effective_from": "2026-11-17T00:00:00Z",
                "effective_until": None,
            },
        ],
        "schedules": (
            [
                {
                    "id": "daily",
                    "timezone": "Europe/Berlin",
                    "hour": 9,
                    "minute": 0,
                    "start_date": "2026-11-15",
                    "lookback_days": 2,
                    "max_attempts": 3,
                    "retry_seconds": 60,
                    "enabled": True,
                }
            ]
            if schedules
            else []
        ),
    }


def test_actual_three_project_snapshots_keep_scope_and_no_average(
    tmp_path: Path,
) -> None:
    cfg = settings(tmp_path)
    report = build_portfolio(cfg, now=NOW)
    assert len(report["projects"]) == 3
    assert report["aggregate_health"] is None
    assert report["current_source_verified"] is False
    assert report["selection"] == "historical-pinned"
    assert report["teams"] == [{"team_id": "core", "project_ids": ["p0"]}]
    after = build_portfolio(cfg, now=datetime(2026, 11, 18, tzinfo=timezone.utc))
    assert after["teams"] == [{"team_id": "platform", "project_ids": ["p0"]}]
    assert [r["run_id"] for r in after["projects"]] == [
        r["run_id"] for r in report["projects"]
    ]


def test_unverified_health_goal_is_unknown_not_passed(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    cfg["goals"] = [
        {
            "id": "health-goal",
            "project_id": "p0",
            "minimum_health": 80,
            "scope_digest": "a" * 64,
            "scorer_digest": "b" * 64,
            "required_context_ids": ["debug"],
        }
    ]
    row = build_portfolio(cfg, now=NOW)["goals"][0]
    assert row["outcome"] == "unknown"
    assert row["current_source_verified"] is False


@pytest.mark.parametrize(
    "mutation", ["outside", "duplicate", "bad_hash", "unknown_goal", "overlap"]
)
def test_malformed_access_or_scope_is_rejected(tmp_path: Path, mutation: str) -> None:
    cfg = settings(tmp_path)
    if mutation == "outside":
        cfg["projects"][0]["store"] = "/unapproved/store"
    if mutation == "duplicate":
        cfg["projects"][1]["id"] = "p0"
    if mutation == "bad_hash":
        cfg["projects"][0]["manifest_sha256"] = "bad"
    if mutation == "unknown_goal":
        cfg["team_history"][0]["project_id"] = "unselected"
    if mutation == "overlap":
        cfg["team_history"][0]["effective_until"] = None
    with pytest.raises(ContractError):
        validate_config(cfg)


def test_one_corrupt_project_preserves_other_pins_as_partial(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    cfg["projects"][1]["manifest_sha256"] = "0" * 64
    report = build_portfolio(cfg, now=NOW)
    assert report["status"] == "partial"
    assert [r["availability"] for r in report["projects"]] == [
        "available",
        "unavailable",
        "available",
    ]
    assert report["projects"][0]["run_id"] == "run-0"


def test_schedule_tick_executes_local_reports_and_is_idempotent(tmp_path: Path) -> None:
    cfg = settings(tmp_path, schedules=True)
    output = tmp_path / "delivery"
    output.mkdir()
    first = schedule_tick(cfg, output_root=output, now=NOW)
    assert len(first["outcomes"]) == 2
    assert all(row["status"] == "succeeded" for row in first["outcomes"])
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    second = schedule_tick(cfg, output_root=output, now=NOW)
    assert second["outcomes"] == []
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    for path in output.glob("report-*.json"):
        report = json.loads(path.read_bytes())
        assert report["aggregate_health"] is None
        assert report["current_source_verified"] is False


def test_retry_records_failure_then_exact_local_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.portfolio as module

    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    output = tmp_path / "delivery"
    output.mkdir()
    original = module._publish_report

    def fail(*args, **kwargs):
        raise OSError("Authored local write failure")

    monkeypatch.setattr(module, "_publish_report", fail)
    first = schedule_tick(cfg, output_root=output, now=NOW)
    assert first["outcomes"][0]["status"] == "failed"
    waiting = schedule_tick(cfg, output_root=output, now=NOW)
    assert waiting["outcomes"] == []
    assert waiting["active_job_counts"]["failed"] == 1
    assert waiting["next_retry_at"] is not None
    monkeypatch.setattr(module, "_publish_report", original)
    later = schedule_tick(
        cfg, output_root=output, now=datetime(2026, 11, 16, 12, 2, tzinfo=timezone.utc)
    )
    assert later["outcomes"][0]["status"] == "succeeded"
    assert later["outcomes"][0]["attempts"] == 2


def test_dst_nonexistent_is_skipped_and_ambiguous_runs_once(tmp_path: Path) -> None:
    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0].update(
        hour=2, minute=30, start_date="2026-03-29", lookback_days=1
    )
    spring = tmp_path / "spring"
    spring.mkdir()
    assert (
        schedule_tick(
            cfg, output_root=spring, now=datetime(2026, 3, 29, 12, tzinfo=timezone.utc)
        )["outcomes"]
        == []
    )
    cfg["schedules"][0]["start_date"] = "2026-10-25"
    autumn = tmp_path / "autumn"
    autumn.mkdir()
    first = schedule_tick(
        cfg, output_root=autumn, now=datetime(2026, 10, 25, 0, 45, tzinfo=timezone.utc)
    )
    assert len(first["outcomes"]) == 1
    assert first["outcomes"][0]["intended_at"] == "2026-10-25T00:30:00+00:00"
    assert (
        schedule_tick(
            cfg,
            output_root=autumn,
            now=datetime(2026, 10, 25, 1, 45, tzinfo=timezone.utc),
        )["outcomes"]
        == []
    )


def test_verified_measured_goal_requires_exact_method_scope_and_context(
    tmp_path: Path,
) -> None:
    from cppulse.analysis import persist_native_analysis
    from cppulse.maintenance import persist_maintenance_health
    from cppulse.tooling import load_rule_registry
    from test_analysis_inventory import native_snapshot
    from test_measured_normalization import add_metrics

    cfg = settings(tmp_path)
    root = tmp_path / "measured"
    root.mkdir()
    raw, selection = native_snapshot(root, mutate=add_metrics)
    selection["requested_rules"] = [row["id"] for row in load_rule_registry()["rules"]]
    normalized = persist_native_analysis(
        raw, workspace=root, store=root / "store", **selection
    )
    snapshot = persist_maintenance_health(
        normalized,
        workspace=root,
        store=root / "store",
        required_context_ids=["native"],
    )
    as_of = datetime.now(timezone.utc)
    cfg["authorized_roots"].append(str(root))
    cfg["projects"][0].update(
        store=str(root / "store"),
        run_id=snapshot.run_id,
        manifest_sha256=snapshot.manifest_sha256,
    )
    selected = build_portfolio(cfg, now=as_of)["projects"][0]
    health = selected["health"]["document"]
    assert health["aggregate"]["overall"] is not None
    cfg["goals"] = [
        {
            "id": "selected-health",
            "project_id": "p0",
            "minimum_health": 0,
            "scope_digest": selected["scope_digest"],
            "scorer_digest": digest_json(health["scorer"]),
            "required_context_ids": ["native"],
        }
    ]
    goal = build_portfolio(cfg, now=as_of)["goals"][0]
    # The shared fixture explicitly retains an independent unattempted build.
    assert selected["collection_status"] == "partial"
    assert goal["outcome"] == "unknown"
    assert goal["current_source_verified"] is False
    # Isolated pure predicate control: a hypothetically completed collection of
    # these exact measured facts may satisfy a historical goal, never a gate.
    from cppulse.portfolio import _goal

    from cppulse.portfolio import validate_report

    for mutation in ["hash", "raw", "document", "contexts"]:
        changed_report = build_portfolio(cfg, now=as_of)
        row = changed_report["projects"][0]
        if mutation == "hash":
            row["health"]["sha256"] = "0" * 64
        if mutation == "raw":
            row["health"]["raw_json"] += " "
        if mutation == "document":
            row["health"]["document"]["aggregate"]["overall"] = 0
        if mutation == "contexts":
            row["contexts"] = []
        with pytest.raises(ContractError):
            validate_report(changed_report, expected_config=cfg)
    complete = {**selected, "collection_status": "completed"}
    assert _goal(cfg["goals"][0], complete)["outcome"] == "observed_met"
    for key, value in [
        ("scope_digest", "a" * 64),
        ("scorer_digest", "b" * 64),
        ("required_context_ids", ["unselected"]),
    ]:
        changed = deepcopy(cfg)
        changed["goals"][0][key] = value
        assert build_portfolio(changed, now=as_of)["goals"][0]["outcome"] == "unknown"
        assert _goal(changed["goals"][0], complete)["outcome"] == "unknown"


def test_modified_delivered_report_cannot_remain_succeeded(tmp_path: Path) -> None:
    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    output = tmp_path / "delivery"
    output.mkdir()
    schedule_tick(cfg, output_root=output, now=NOW)
    next(output.glob("report-*.json")).write_text("{}")
    result = schedule_tick(cfg, output_root=output, now=NOW)
    assert result["outcomes"][0]["status"] == "failed"
    assert "differs" in result["outcomes"][0]["error"]


def test_interrupted_final_journal_recovers_same_report_without_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.portfolio as module

    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    output = tmp_path / "delivery"
    output.mkdir()
    original = module._replace_at
    calls = 0

    def interrupt(descriptor, name, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Authored crash after report publication")
        return original(descriptor, name, content)

    monkeypatch.setattr(module, "_replace_at", interrupt)
    with pytest.raises(OSError, match="Authored crash"):
        schedule_tick(cfg, output_root=output, now=NOW)
    original_bytes = next(output.glob("report-*.json")).read_bytes()
    assert (
        json.loads((output / "schedule-state.json").read_bytes())["jobs"][0]["status"]
        == "pending"
    )
    monkeypatch.setattr(module, "_replace_at", original)
    result = schedule_tick(
        cfg, output_root=output, now=datetime(2026, 11, 16, 12, 2, tzinfo=timezone.utc)
    )
    assert result["outcomes"][0]["status"] == "succeeded"
    assert len(list(output.glob("report-*.json"))) == 1
    assert next(output.glob("report-*.json")).read_bytes() == original_bytes


def test_output_symlink_and_changed_journal_binding_are_rejected(
    tmp_path: Path,
) -> None:
    cfg = settings(tmp_path, schedules=True)
    output = tmp_path / "delivery"
    output.mkdir()
    link = tmp_path / "link"
    link.symlink_to(output, target_is_directory=True)
    with pytest.raises(OSError):
        schedule_tick(cfg, output_root=link, now=NOW)
    schedule_tick(cfg, output_root=output, now=NOW)
    journal = json.loads((output / "schedule-state.json").read_bytes())
    journal["jobs"][0]["schedule_id"] = "foreign"
    (output / "schedule-state.json").write_text(json.dumps(journal))
    with pytest.raises(ContractError):
        schedule_tick(cfg, output_root=output, now=NOW)


def test_context_method_scope_goals_and_report_tampering_are_rejected(
    tmp_path: Path,
) -> None:
    from cppulse.portfolio import validate_report

    cfg = settings(tmp_path)
    cfg["goals"] = [
        {
            "id": "health-goal",
            "project_id": "p0",
            "minimum_health": 80,
            "scope_digest": "a" * 64,
            "scorer_digest": "b" * 64,
            "required_context_ids": ["debug"],
        }
    ]
    report = build_portfolio(cfg, now=NOW)
    report["goals"][0].update(outcome="observed_met", value=100, reasons=[])
    with pytest.raises(ContractError, match="contradicts"):
        validate_report(report)


def test_changed_team_config_creates_distinct_delivery_and_preserves_old_bytes(
    tmp_path: Path,
) -> None:
    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    output = tmp_path / "delivery"
    output.mkdir()
    first = schedule_tick(cfg, output_root=output, now=NOW)
    old = next(output.glob("report-*.json"))
    old_bytes = old.read_bytes()
    cfg["team_history"][0]["team_id"] = "new-core"
    second = schedule_tick(cfg, output_root=output, now=NOW)
    assert len(second["outcomes"]) == 1
    assert second["outcomes"][0]["id"] != first["outcomes"][0]["id"]
    assert old.read_bytes() == old_bytes
    assert len(list(output.glob("report-*.json"))) == 2
    generations = [
        json.loads(path.read_bytes()) for path in output.glob("configuration-*.json")
    ]
    assert len(generations) == 2
    assert {row["team_history"][0]["team_id"] for row in generations} == {
        "core",
        "new-core",
    }


def test_retry_exhaustion_and_pending_budget_do_not_launch_extra_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.portfolio as module

    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0].update(lookback_days=1, max_attempts=2)
    output = tmp_path / "delivery"
    output.mkdir()

    def fail(*args, **kwargs):
        raise OSError("Authored persistent disk failure")

    monkeypatch.setattr(module, "_publish_report", fail)
    assert (
        schedule_tick(cfg, output_root=output, now=NOW)["outcomes"][0]["status"]
        == "failed"
    )
    later = datetime(2026, 11, 16, 12, 2, tzinfo=timezone.utc)
    row = schedule_tick(cfg, output_root=output, now=later)["outcomes"][0]
    assert row["status"] == "exhausted" and row["attempts"] == 2
    assert schedule_tick(cfg, output_root=output, now=later)["outcomes"] == []


def test_scheduled_partial_delivery_never_becomes_policy_acceptance(
    tmp_path: Path,
) -> None:
    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    cfg["projects"][1]["manifest_sha256"] = "0" * 64
    output = tmp_path / "delivery"
    output.mkdir()
    tick = schedule_tick(cfg, output_root=output, now=NOW)
    assert tick["outcomes"][0]["status"] == "succeeded"
    assert tick["outcomes"][0]["report_status"] == "partial"
    assert tick["policy_acceptance"] == "not_assessed"


def test_explicit_local_tick_never_calls_commands_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket
    import subprocess

    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    output = tmp_path / "delivery"
    output.mkdir()

    def deny(*args, **kwargs):
        raise AssertionError("Unexpected external execution")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    assert (
        schedule_tick(cfg, output_root=output, now=NOW)["outcomes"][0]["status"]
        == "succeeded"
    )


def test_latest_pointer_movement_does_not_redirect_configured_pin(
    tmp_path: Path,
) -> None:
    cfg = settings(tmp_path)
    before = build_portfolio(cfg, now=NOW)["projects"][0]
    publish_snapshot(tmp_path / "project-0", run_id="later-run", legacy=True)
    after = build_portfolio(cfg, now=NOW)["projects"][0]
    assert after["run_id"] == before["run_id"] == "run-0"
    assert after["manifest_sha256"] == before["manifest_sha256"]


def test_unknown_timezone_and_concurrent_delivery_lock_are_actionable(
    tmp_path: Path,
) -> None:
    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["timezone"] = "Not/A_Zone"
    with pytest.raises(ContractError, match="timezone"):
        validate_config(cfg)
    cfg["schedules"][0]["timezone"] = "Europe/Berlin"
    output = tmp_path / "delivery"
    output.mkdir()
    (output / ".portfolio.lock").write_text("Existing writer; do not delete")
    with pytest.raises(FileExistsError):
        schedule_tick(cfg, output_root=output, now=NOW)
    assert (output / ".portfolio.lock").read_text() == "Existing writer; do not delete"


def test_timezone_provider_change_blocks_silent_rescheduling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.portfolio as module

    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    output = tmp_path / "delivery"
    output.mkdir()
    schedule_tick(cfg, output_root=output, now=NOW)
    original = module._timezone

    def changed(name):
        zone, _ = original(name)
        return zone, "0" * 64

    monkeypatch.setattr(module, "_timezone", changed)
    with pytest.raises(ContractError, match="Timezone provider bytes changed"):
        schedule_tick(cfg, output_root=output, now=NOW)
    assert len(list(output.glob("report-*.json"))) == 1


def test_missing_timezone_journal_binding_cannot_allow_new_rules(
    tmp_path: Path,
) -> None:
    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    output = tmp_path / "delivery"
    output.mkdir()
    schedule_tick(cfg, output_root=output, now=NOW)
    path = output / "schedule-state.json"
    journal = json.loads(path.read_bytes())
    journal["timezone_bindings"] = {}
    path.write_text(json.dumps(journal))
    with pytest.raises(ContractError, match="retained timezone"):
        schedule_tick(cfg, output_root=output, now=NOW)


def test_lost_journal_with_retained_reports_is_not_silently_restarted(
    tmp_path: Path,
) -> None:
    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0]["lookback_days"] = 1
    output = tmp_path / "delivery"
    output.mkdir()
    schedule_tick(cfg, output_root=output, now=NOW)
    (output / "schedule-state.json").unlink()
    with pytest.raises(ContractError, match="missing from their delivery journal"):
        schedule_tick(cfg, output_root=output, now=NOW)
    assert len(list(output.glob("report-*.json"))) == 1


def test_recorded_retry_survives_midnight_outside_new_occurrence_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.portfolio as module

    cfg = settings(tmp_path, schedules=True)
    cfg["schedules"][0].update(hour=23, minute=59, lookback_days=1, retry_seconds=120)
    output = tmp_path / "delivery"
    output.mkdir()
    original = module._publish_report

    def fail(*args, **kwargs):
        raise OSError("Authored midnight write failure")

    monkeypatch.setattr(module, "_publish_report", fail)
    first = schedule_tick(
        cfg, output_root=output, now=datetime(2026, 11, 16, 22, 59, tzinfo=timezone.utc)
    )
    assert first["outcomes"][0]["status"] == "failed"
    monkeypatch.setattr(module, "_publish_report", original)
    second = schedule_tick(
        cfg, output_root=output, now=datetime(2026, 11, 16, 23, 2, tzinfo=timezone.utc)
    )
    assert second["outcomes"][0]["status"] == "succeeded"
    assert second["outcomes"][0]["id"] == first["outcomes"][0]["id"]
    assert second["outcomes"][0]["attempts"] == 2


def test_existing_namespaced_context_identity_is_supported(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    cfg["goals"] = [
        {
            "id": "namespaced-context",
            "project_id": "p0",
            "minimum_health": 80,
            "scope_digest": "a" * 64,
            "scorer_digest": "b" * 64,
            "required_context_ids": ["job:" + "a" * 100],
        }
    ]
    validate_config(cfg)
    assert build_portfolio(cfg, now=NOW)["goals"][0]["outcome"] == "unknown"


@pytest.mark.parametrize("location", ["store", "run", "ancestor"])
def test_local_delivery_cannot_write_inside_or_around_selected_immutable_store(
    tmp_path: Path, location: str
) -> None:
    cfg = settings(tmp_path, schedules=True)
    store = tmp_path / "project-0/store"
    output = (
        store
        if location == "store"
        else store / "runs/run-0" if location == "run" else tmp_path
    )
    before = {
        str(path): path.read_bytes() for path in store.rglob("*") if path.is_file()
    }
    with pytest.raises(ContractError, match="must not overlap"):
        schedule_tick(cfg, output_root=output, now=NOW)
    assert before == {
        str(path): path.read_bytes() for path in store.rglob("*") if path.is_file()
    }
    assert not (output / ".portfolio.lock").exists()


def test_replay_cutoff_cannot_borrow_future_run_facts(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    report = build_portfolio(cfg, now=datetime(2026, 11, 12, tzinfo=timezone.utc))
    assert report["status"] == "partial"
    assert all(
        project["availability"] == "unavailable" for project in report["projects"]
    )
    assert all(
        "after the portfolio observation cutoff" in project["limitations"][0]
        for project in report["projects"]
    )


def test_offline_projection_cannot_change_original_contexts_or_artifact_hashes(
    tmp_path: Path,
) -> None:
    from cppulse.portfolio import validate_report

    cfg = settings(tmp_path)
    report = build_portfolio(cfg, now=NOW)
    changed = deepcopy(report)
    changed["projects"][0]["contexts"] = []
    with pytest.raises(ContractError, match="pinned original manifest"):
        validate_report(changed)
    changed = deepcopy(report)
    changed["projects"][0]["raw_manifest_json"] += " "
    with pytest.raises(ContractError, match="manifest bytes"):
        validate_report(changed)


def test_overbudget_project_retains_other_checked_project_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.portfolio as module

    cfg = settings(tmp_path)
    original = module._project

    def large(selected, **kwargs):
        row = original(selected, **kwargs)
        if selected["id"] == "p0":
            row["raw_manifest_json"] = " " * module.MAX_PROJECT_PAYLOAD_BYTES
        return row

    monkeypatch.setattr(module, "_project", large)
    report = build_portfolio(cfg, now=NOW)
    assert [row["availability"] for row in report["projects"]] == [
        "unavailable",
        "available",
        "available",
    ]
    assert "budget" in report["projects"][0]["limitations"][0]


def test_offline_report_can_bind_original_caller_configuration(tmp_path: Path) -> None:
    from cppulse.portfolio import validate_report

    cfg = settings(tmp_path)
    report = build_portfolio(cfg, now=NOW)
    validate_report(report, expected_config=cfg)
    changed = deepcopy(report)
    changed["projects"][0]["manifest_sha256"] = "0" * 64
    with pytest.raises(ContractError, match="run pins"):
        validate_report(changed, expected_config=cfg)
    changed = deepcopy(report)
    changed["team_history"][0]["team_id"] = "forged"
    with pytest.raises(ContractError, match="caller-selected configuration"):
        validate_report(changed, expected_config=cfg)
