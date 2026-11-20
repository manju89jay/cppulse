"""Private local portfolio observations and explicit, finite scheduled delivery.

Pins select historical checked bytes. No account, remote provider, project
execution, daemon, message or current-source verification is inferred.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from importlib import resources
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterator
from uuid import uuid4
from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError

import jsonschema

from cppulse.contracts import validate
from cppulse.errors import ContractError, CppulseError, IntegrityError
from cppulse.identities import canonical_json_bytes, digest_json
from cppulse.run_store import RunStore

MAX_CONFIG_BYTES = 256 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
MAX_PROJECT_BYTES = 1024 * 1024
MAX_PROJECT_PAYLOAD_BYTES = 3 * 1024 * 1024


def _validate(kind: str, document: dict[str, Any]) -> None:
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas", "portfolio_private", kind + ".schema.json")
        .read_bytes()
    )
    try:
        jsonschema.Draft7Validator.check_schema(schema)
        jsonschema.Draft7Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(document)
        canonical_json_bytes(document)
    except (
        jsonschema.ValidationError,
        jsonschema.SchemaError,
        ValueError,
        TypeError,
    ) as error:
        raise ContractError(
            "Invalid private portfolio " + kind + ": " + str(error)
        ) from error


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError("Portfolio times require an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _now(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ContractError("Portfolio tick requires an aware timestamp")
    return value.astimezone(timezone.utc)


def _absolute(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ContractError("Portfolio roots must use canonical absolute local paths")
    return path


def validate_config(config: dict[str, Any]) -> None:
    """Reject unauthorized roots, ambiguous identities and inconsistent local scope."""
    _validate("config", config)
    if len(canonical_json_bytes(config)) > MAX_CONFIG_BYTES:
        raise ContractError("Portfolio configuration exceeds 256 KiB")
    roots = [_absolute(value) for value in config["authorized_roots"]]
    identifiers = [row["id"] for row in config["projects"]]
    if len(set(identifiers)) != len(identifiers):
        raise ContractError("Portfolio project IDs must be unique")
    stores = []
    for project in config["projects"]:
        path = _absolute(project["store"])
        if not any(path.is_relative_to(root) for root in roots):
            raise ContractError("Project store is outside explicitly authorized roots")
        stores.append(path)
    if len(set(stores)) != len(stores):
        raise ContractError("A store cannot be counted as two portfolio projects")
    for key in ["goals", "schedules"]:
        ids = [row["id"] for row in config[key]]
        if len(set(ids)) != len(ids):
            raise ContractError("Portfolio " + key + " IDs must be unique")
    for goal in config["goals"]:
        if goal["project_id"] not in identifiers:
            raise ContractError("Goal references an unselected project")
    intervals: dict[str, list[tuple[datetime, datetime | None]]] = defaultdict(list)
    for row in config["team_history"]:
        if row["project_id"] not in identifiers:
            raise ContractError("Team assignment references an unselected project")
        start = _utc(row["effective_from"])
        end = _utc(row["effective_until"]) if row["effective_until"] else None
        if end is not None and end <= start:
            raise ContractError("Team membership must have a positive interval")
        intervals[row["project_id"]].append((start, end))
    for values in intervals.values():
        values.sort(key=lambda row: row[0])
        if any(a[1] is None or a[1] > b[0] for a, b in zip(values, values[1:])):
            raise ContractError("Team assignments overlap for a selected project")
    for schedule in config["schedules"]:
        try:
            ZoneInfo(schedule["timezone"])
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ContractError("Unknown IANA schedule timezone") from error


def _project(project: dict[str, Any], *, cutoff: datetime) -> dict[str, Any]:
    snapshot = RunStore.open_existing(project["store"]).open_run(
        project["run_id"],
        manifest_sha256=project["manifest_sha256"],
        max_snapshot_bytes=MAX_SNAPSHOT_BYTES,
    )
    manifest = snapshot.manifest
    if _utc(manifest["finished_at"]) > cutoff:
        raise ContractError(
            "Selected retained run finished after the portfolio observation cutoff"
        )
    candidates = [
        row
        for row in manifest["artifacts"]
        if row.get("contract") == {"kind": "maintenance_health", "version": "2.0.0"}
    ]
    if "health_artifact_id" in project:
        candidates = [
            row for row in candidates if row["id"] == project["health_artifact_id"]
        ]
        if len(candidates) != 1:
            raise ContractError(
                "Selected health artifact is absent or not typed maintenance_health"
            )
    health = None
    reasons = []
    if len(candidates) == 1:
        entry = candidates[0]
        health_bytes = snapshot.read_bytes(entry["id"])
        document = json.loads(health_bytes)
        validate("maintenance_health", document)
        health = {
            "raw_json": health_bytes.decode("utf-8"),
            "artifact_id": entry["id"],
            "sha256": entry["sha256"],
            "document": document,
            "scorer_digest": digest_json(document["scorer"]),
        }
    else:
        reasons.append(
            "Measured health is absent or ambiguous; no legacy method is substituted."
        )
    result = {
        "raw_manifest_json": snapshot.read_manifest_bytes().decode("utf-8"),
        "id": project["id"],
        "run_id": snapshot.run_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "availability": "available",
        "collection_status": manifest["status"],
        "started_at": manifest["started_at"],
        "finished_at": manifest["finished_at"],
        "input_verification": manifest.get("input_verification", "unverified"),
        "source_digest": manifest["source"]["digest"],
        "source_inventory_complete": manifest["source"]["inventory_complete"],
        "subject_kind": manifest["source"]["kind"],
        "source_limitations": manifest["source"]["limitations"],
        "scope_digest": digest_json(
            sorted(row["path"] for row in manifest["source"]["files"])
        ),
        "contexts": manifest["contexts"],
        "health": health,
        "limitations": list(
            dict.fromkeys(
                [*manifest["limitations"], *manifest["source"]["limitations"], *reasons]
            )
        ),
    }
    if len(canonical_json_bytes(result)) > MAX_PROJECT_BYTES:
        raise ContractError(
            "Project projection exceeds the finite 1 MiB limit; use a smaller explicit snapshot"
        )
    return result


def _goal(goal: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    wrapper = project.get("health")
    health = wrapper["document"] if wrapper else None
    value = None
    if project["availability"] != "available" or health is None:
        reasons.append("Selected measured project result is unavailable.")
    else:
        if (
            project["input_verification"] != "verified"
            or project["collection_status"] != "completed"
        ):
            reasons.append(
                "Stored source binding/collection is unverified or incomplete."
            )
        if project["scope_digest"] != goal["scope_digest"]:
            reasons.append(
                "Goal file scope differs from the selected source inventory."
            )
        if digest_json(health["scorer"]) != goal["scorer_digest"]:
            reasons.append("Goal scorer/profile/calibration identity differs.")
        if set(health["required_context_ids"]) != set(goal["required_context_ids"]):
            reasons.append("Goal required contexts differ.")
        if (
            health["aggregate"]["availability"] != "scored"
            or health["aggregate"]["overall"] is None
        ):
            reasons.append("Full required-context measured health is unavailable.")
        if not reasons:
            value = health["aggregate"]["overall"]
    return {
        **{
            key: goal[key]
            for key in (
                "id",
                "project_id",
                "minimum_health",
                "scope_digest",
                "scorer_digest",
                "required_context_ids",
            )
        },
        "outcome": (
            "unknown"
            if reasons
            else "observed_met" if value >= goal["minimum_health"] else "observed_unmet"
        ),
        "value": value,
        "minimum_health": goal["minimum_health"],
        "reasons": reasons,
        "current_source_verified": False,
        "interpretation": "Historical scoped observation only; no current-source policy acceptance.",
    }


def build_portfolio(config: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Read selected historical pins independently; never average incompatible scores."""
    config = deepcopy(config)
    validate_config(config)
    now = _now(now)
    projects = []
    project_payload_bytes = 0
    for selected in sorted(config["projects"], key=lambda row: row["id"]):
        try:
            row = _project(selected, cutoff=now)
            size = len(canonical_json_bytes(row))
            if project_payload_bytes + size > MAX_PROJECT_PAYLOAD_BYTES:
                raise ContractError(
                    "Finite portfolio project-payload budget exceeded; select a smaller explicit project group"
                )
            project_payload_bytes += size
            projects.append(row)
        except (CppulseError, OSError, UnicodeError, RecursionError) as error:
            projects.append(
                {
                    "id": selected["id"],
                    "run_id": selected["run_id"],
                    "manifest_sha256": selected["manifest_sha256"],
                    "availability": "unavailable",
                    "health": None,
                    "limitations": [str(error)],
                }
            )
    by_id = {row["id"]: row for row in projects}
    teams: dict[str, list[str]] = defaultdict(list)
    for row in config["team_history"]:
        if _utc(row["effective_from"]) <= now and (
            row["effective_until"] is None or now < _utc(row["effective_until"])
        ):
            teams[row["team_id"]].append(row["project_id"])
    report = {
        "version": "1.0.0",
        "id": config["id"],
        "configuration_digest": digest_json(config),
        "generated_at": now.isoformat(),
        "selection": "historical-pinned",
        "current_source_verified": False,
        "status": (
            "partial"
            if any(row["availability"] != "available" for row in projects)
            else "complete"
        ),
        "aggregate_health": None,
        "projects": projects,
        "goals": [_goal(goal, by_id[goal["project_id"]]) for goal in config["goals"]],
        "team_history": deepcopy(config["team_history"]),
        "teams": [
            {"team_id": team, "project_ids": sorted(ids)}
            for team, ids in sorted(teams.items())
        ],
        "limitations": [
            "Project scores are never averaged; scorer/context/source scope remains separate.",
            "Pinned runs are historical observations, not fresh source verification or project authorization beyond these roots.",
            "Team assignments are dated caller declarations, not inferred expertise or authenticated identity.",
            "External issue/task/branch/cost/notification providers and organization access control remain unqualified.",
        ],
    }
    validate_report(report, expected_config=config)
    if len(canonical_json_bytes(report)) > MAX_REPORT_BYTES:
        raise ContractError("Portfolio report exceeds finite 4 MiB output")
    return report


def validate_report(
    report: dict[str, Any], *, expected_config: dict[str, Any] | None = None
) -> None:
    """Check offline original-byte consistency and optional trusted request binding.

    Without expected_config this verifies internal consistency, not a producer's
    authenticity or agreement with a separately selected caller configuration.
    """
    _validate("report", report)
    projects = {row["id"]: row for row in report["projects"]}
    if len(projects) != len(report["projects"]):
        raise ContractError("Duplicate report project identity")
    selected_projects = {}
    if expected_config is not None:
        _validate("config", expected_config)
        selected_projects = {row["id"]: row for row in expected_config["projects"]}
        if (
            report["configuration_digest"] != digest_json(expected_config)
            or report["id"] != expected_config["id"]
            or set(projects) != set(selected_projects)
            or report["team_history"] != expected_config["team_history"]
        ):
            raise ContractError(
                "Portfolio differs from the caller-selected configuration"
            )
        for project_id, selected in selected_projects.items():
            if any(
                projects[project_id][key] != selected[key]
                for key in ("run_id", "manifest_sha256")
            ):
                raise ContractError(
                    "Project run pins differ from the caller-selected configuration"
                )
        goals = {row["id"]: row for row in report["goals"]}
        if len(goals) != len(report["goals"]) or set(goals) != {
            row["id"] for row in expected_config["goals"]
        }:
            raise ContractError(
                "Portfolio goal inventory differs from caller configuration"
            )
        for goal in expected_config["goals"]:
            if any(goals[goal["id"]].get(key) != value for key, value in goal.items()):
                raise ContractError(
                    "Historical goal prerequisites differ from caller configuration"
                )
    for project in projects.values():
        manifest = None
        if project["availability"] == "available":
            raw_manifest = project["raw_manifest_json"].encode("utf-8")
            if hashlib.sha256(raw_manifest).hexdigest() != project["manifest_sha256"]:
                raise ContractError(
                    "Original portfolio manifest bytes differ from their selected hash"
                )
            manifest = json.loads(raw_manifest)
            validate("run_manifest", manifest)
            expected = {
                "run_id": manifest["run_id"],
                "collection_status": manifest["status"],
                "started_at": manifest["started_at"],
                "finished_at": manifest["finished_at"],
                "input_verification": manifest.get("input_verification", "unverified"),
                "source_digest": manifest["source"]["digest"],
                "source_inventory_complete": manifest["source"]["inventory_complete"],
                "subject_kind": manifest["source"]["kind"],
                "source_limitations": manifest["source"]["limitations"],
                "scope_digest": digest_json(
                    sorted(row["path"] for row in manifest["source"]["files"])
                ),
                "contexts": manifest["contexts"],
            }
            if not set(
                manifest["limitations"] + manifest["source"]["limitations"]
            ) <= set(project["limitations"]):
                raise ContractError(
                    "Portfolio omitted original selected scope limitations"
                )
            if any(project[key] != value for key, value in expected.items()):
                raise ContractError(
                    "Portfolio projection differs from its pinned original manifest"
                )
            identifiers = []
            for context in project["contexts"]:
                validate("context", context)
                identifiers.append(context["id"])
            if len(identifiers) != len(set(identifiers)):
                raise ContractError("Duplicate portfolio project context identity")
            if project["id"] in selected_projects:
                selected = selected_projects[project["id"]]
                candidates = [
                    entry
                    for entry in manifest["artifacts"]
                    if entry.get("contract")
                    == {"kind": "maintenance_health", "version": "2.0.0"}
                ]
                if "health_artifact_id" in selected:
                    candidates = [
                        entry
                        for entry in candidates
                        if entry["id"] == selected["health_artifact_id"]
                    ]
                    if len(candidates) != 1:
                        raise ContractError(
                            "Selected health artifact is absent from original manifest"
                        )
                expected_id = candidates[0]["id"] if len(candidates) == 1 else None
                actual_id = (
                    project["health"]["artifact_id"] if project["health"] else None
                )
                if expected_id != actual_id:
                    raise ContractError(
                        "Health selection differs from caller configuration and manifest cardinality"
                    )
        if project["availability"] == "available" and _utc(
            project["finished_at"]
        ) > _utc(report["generated_at"]):
            raise ContractError(
                "Selected project facts postdate the portfolio observation cutoff"
            )
        if project.get("health") is not None:
            if manifest is None:
                raise ContractError(
                    "Unavailable project cannot claim selected measured health"
                )
            health = project["health"]
            raw_health = health["raw_json"].encode("utf-8")
            entries = [
                entry
                for entry in manifest["artifacts"]
                if entry["id"] == health["artifact_id"]
                and entry.get("contract")
                == {"kind": "maintenance_health", "version": "2.0.0"}
            ]
            if (
                len(entries) != 1
                or entries[0]["sha256"] != health["sha256"]
                or hashlib.sha256(raw_health).hexdigest() != health["sha256"]
                or len(raw_health) != entries[0]["size_bytes"]
                or json.loads(raw_health) != health["document"]
            ):
                raise ContractError(
                    "Portfolio health differs from the original manifest-bound artifact bytes"
                )
            validate("maintenance_health", project["health"]["document"])
            if health["document"]["aggregate"]["availability"] == "scored" and not set(
                health["document"]["required_context_ids"]
            ) <= {row["id"] for row in project["contexts"]}:
                raise ContractError(
                    "Scored portfolio health requires its selected manifest context inventory"
                )
            if project["health"]["scorer_digest"] != digest_json(
                project["health"]["document"]["scorer"]
            ):
                raise ContractError(
                    "Project scorer identity differs from its stored method"
                )
            if project["health"]["document"]["source_digest"] != project.get(
                "source_digest"
            ):
                raise ContractError("Project health source identity differs")
    for goal in report["goals"]:
        if goal["project_id"] not in projects or goal != _goal(
            goal, projects[goal["project_id"]]
        ):
            raise ContractError(
                "Stored historical goal contradicts its exact selected project"
            )
    teams: dict[str, list[str]] = defaultdict(list)
    for assignment in report["team_history"]:
        if assignment["project_id"] not in projects:
            raise ContractError("Team declaration references an unselected project")
        if _utc(assignment["effective_from"]) <= _utc(report["generated_at"]) and (
            assignment["effective_until"] is None
            or _utc(report["generated_at"]) < _utc(assignment["effective_until"])
        ):
            teams[assignment["team_id"]].append(assignment["project_id"])
    expected_teams = [
        {"team_id": team, "project_ids": sorted(ids)}
        for team, ids in sorted(teams.items())
    ]
    if expected_teams != report["teams"]:
        raise ContractError(
            "Stored team assignment differs from its declared effective intervals"
        )
    expected_status = (
        "partial"
        if any(row["availability"] != "available" for row in projects.values())
        else "complete"
    )
    if report["status"] != expected_status:
        raise ContractError(
            "Portfolio readability status contradicts project availability"
        )


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    absolute = path.absolute()
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _read_at(descriptor: int, name: str) -> bytes:
    selected = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor
    )
    with os.fdopen(selected, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise IntegrityError("Portfolio delivery state must be regular files")
        value = stream.read(MAX_REPORT_BYTES + 1)
    if len(value) > MAX_REPORT_BYTES:
        raise IntegrityError("Portfolio delivery file exceeds its byte budget")
    return value


def _replace_at(descriptor: int, name: str, content: bytes) -> None:
    if len(content) > MAX_REPORT_BYTES:
        raise ContractError("Local delivery journal exceeds finite 4 MiB limit")
    temporary = ".portfolio-" + uuid4().hex
    file = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=descriptor,
    )
    try:
        with os.fdopen(file, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
        os.fsync(descriptor)
    finally:
        try:
            os.unlink(temporary, dir_fd=descriptor)
        except FileNotFoundError:
            pass


def _publish_bytes(descriptor: int, name: str, content: bytes) -> None:
    try:
        existing = _read_at(descriptor, name)
    except FileNotFoundError:
        temporary = ".report-" + uuid4().hex
        file = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=descriptor,
        )
        try:
            with os.fdopen(file, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(
                temporary,
                name,
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
                follow_symlinks=False,
            )
            os.fsync(descriptor)
        finally:
            os.unlink(temporary, dir_fd=descriptor)
    else:
        if existing != content:
            raise IntegrityError(
                "Existing idempotent report differs from pinned scheduled bytes"
            )


def _publish_report(descriptor: int, name: str, content: bytes) -> None:
    """Publish one report after its attempt has been journaled."""
    _publish_bytes(descriptor, name, content)


def _timezone(name: str) -> tuple[ZoneInfo, str]:
    """Interpret the exact installed TZif bytes whose identity is journal-bound."""
    ZoneInfo(name)  # Validate relative IANA keys before looking up provider data.
    raw = None
    for directory in TZPATH:
        try:
            with (Path(directory) / name).open("rb") as stream:
                raw = stream.read(1024 * 1024 + 1)
            break
        except FileNotFoundError:
            continue
    if raw is None:
        try:
            with (
                resources.files("tzdata")
                .joinpath("zoneinfo", *name.split("/"))
                .open("rb") as stream
            ):
                raw = stream.read(1024 * 1024 + 1)
        except (ModuleNotFoundError, FileNotFoundError) as error:
            raise ContractError(
                "Unable to retain the installed timezone data identity"
            ) from error
    if len(raw) > 1024 * 1024:
        raise ContractError("Timezone provider data exceeds finite 1 MiB limit")
    return (
        ZoneInfo.from_file(io.BytesIO(raw), key=name),
        hashlib.sha256(raw).hexdigest(),
    )


def _occurrences(
    schedule: dict[str, Any], now: datetime, *, zone: ZoneInfo | None = None
) -> list[datetime]:
    if zone is None:
        zone, _ = _timezone(schedule["timezone"])
    local = now.astimezone(zone)
    start = date.fromisoformat(schedule["start_date"])
    results = []
    for ago in reversed(range(schedule["lookback_days"])):
        day = local.date() - timedelta(days=ago)
        if day < start:
            continue
        wall = datetime.combine(day, time(schedule["hour"], schedule["minute"]))
        intended = wall.replace(tzinfo=zone, fold=0).astimezone(timezone.utc)
        if intended.astimezone(zone).replace(tzinfo=None) != wall:
            continue
        if intended <= now:
            results.append(intended)
    return results


def schedule_tick(
    config: dict[str, Any], *, output_root: Path, now: datetime
) -> dict[str, Any]:
    """Run one explicit finite local delivery tick, with atomic journal and retries.

    The output directory must already exist. Jobs are pinned to config+occurrence;
    succeeded delivery is distinct from a complete report or policy acceptance.
    """
    config = deepcopy(config)
    validate_config(config)
    now = _now(now)
    digest = digest_json(config)
    outcomes = []
    selected_output = _absolute(str(output_root))
    for project in config["projects"]:
        selected_store = _absolute(project["store"])
        if selected_output.is_relative_to(
            selected_store
        ) or selected_store.is_relative_to(selected_output):
            raise ContractError(
                "Local delivery output must not overlap a selected immutable project store"
            )
    with _directory(selected_output) as descriptor:
        lock = os.open(
            ".portfolio.lock",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=descriptor,
        )
        os.close(lock)
        try:
            try:
                state = json.loads(_read_at(descriptor, "schedule-state.json"))
            except FileNotFoundError:
                state = {"version": "1.0.0", "jobs": [], "timezone_bindings": {}}
            _validate("state", state)
            known_reports = {"report-" + row["id"] + ".json" for row in state["jobs"]}
            retained_reports = {
                name
                for name in os.listdir(descriptor)
                if name.startswith("report-") and name.endswith(".json")
            }
            if retained_reports - known_reports:
                raise ContractError(
                    "Retained local reports are missing from their delivery journal; restore the journal before retrying"
                )
            for key, binding in state["timezone_bindings"].items():
                if key != digest_json(
                    {
                        "configuration_digest": binding["configuration_digest"],
                        "timezone": binding["timezone"],
                    }
                ):
                    raise ContractError("Timezone journal binding identity differs")
            schedules = {row["id"]: row for row in config["schedules"]}
            for row in state["jobs"]:
                if row["configuration_digest"] != digest:
                    continue
                selected = schedules.get(row["schedule_id"])
                if selected is None:
                    raise ContractError(
                        "Journal job references an unconfigured schedule"
                    )
                binding_key = digest_json(
                    {"configuration_digest": digest, "timezone": selected["timezone"]}
                )
                if binding_key not in state["timezone_bindings"]:
                    raise ContractError(
                        "Existing jobs require their retained timezone identity"
                    )
            zones = {}
            for schedule in config["schedules"]:
                zone_name = schedule["timezone"]
                zone, zone_hash = _timezone(zone_name)
                zones[schedule["id"]] = zone
                key = digest_json(
                    {"configuration_digest": digest, "timezone": zone_name}
                )
                known = state["timezone_bindings"].get(key)
                observed = {
                    "configuration_digest": digest,
                    "timezone": zone_name,
                    "sha256": zone_hash,
                }
                if known is not None and known != observed:
                    raise ContractError(
                        "Timezone provider bytes changed; approve a new configuration generation before further delivery"
                    )
                state["timezone_bindings"][key] = observed
            for row in state["jobs"]:
                if (
                    row["intended_at"] != _utc(row["intended_at"]).isoformat()
                    or row["next_retry_at"] != _utc(row["next_retry_at"]).isoformat()
                ):
                    raise ContractError(
                        "Delivery journal times must use canonical UTC identities"
                    )
                expected = digest_json(
                    {
                        "configuration_digest": row["configuration_digest"],
                        "schedule_id": row["schedule_id"],
                        "intended_at": row["intended_at"],
                    }
                )
                if row["id"] != expected:
                    raise ContractError("Local delivery journal job binding differs")
            jobs = {row["id"]: row for row in state["jobs"]}
            if len(jobs) != len(state["jobs"]):
                raise ContractError("Duplicate local delivery job identity")
            # Retain each approved generation so later goals/team changes cannot
            # erase the inputs behind historical job/configuration identities.
            _publish_bytes(
                descriptor,
                "configuration-" + digest + ".json",
                canonical_json_bytes(config),
            )
            for schedule in sorted(config["schedules"], key=lambda row: row["id"]):
                if not schedule["enabled"]:
                    continue
                due = set(_occurrences(schedule, now, zone=zones[schedule["id"]]))
                # Catch-up bounds admission, not recorded retry work whose
                # original local calendar day has rolled over.
                due.update(
                    _utc(row["intended_at"])
                    for row in state["jobs"]
                    if row["configuration_digest"] == digest
                    and row["schedule_id"] == schedule["id"]
                    and row["status"] in {"pending", "failed"}
                    and _utc(row["intended_at"]) <= now
                )
                for intended in sorted(due):
                    key = digest_json(
                        {
                            "configuration_digest": digest,
                            "schedule_id": schedule["id"],
                            "intended_at": intended.isoformat(),
                        }
                    )
                    previous = jobs.get(key)
                    if previous and previous["status"] == "succeeded":
                        try:
                            retained = _read_at(descriptor, "report-" + key + ".json")
                            if (
                                hashlib.sha256(retained).hexdigest()
                                != previous["report_sha256"]
                            ):
                                raise IntegrityError(
                                    "Delivered report differs from its recorded hash"
                                )
                            retained_report = json.loads(retained)
                            validate_report(retained_report, expected_config=config)
                            if retained_report["generated_at"] != intended.isoformat():
                                raise ContractError(
                                    "Delivered report clock differs from its scheduled occurrence"
                                )
                            continue
                        except (CppulseError, OSError, ValueError):
                            # Revalidate/recover a missing file; never silently retain
                            # success for a changed delivery or overwrite different bytes.
                            previous["status"] = "failed"
                            previous["next_retry_at"] = now.isoformat()
                    if previous and (
                        previous["status"] == "exhausted"
                        or _utc(previous["next_retry_at"]) > now
                    ):
                        continue
                    if previous and previous["attempts"] >= schedule["max_attempts"]:
                        previous.update(
                            status="exhausted",
                            error="Retry budget exhausted after interrupted or invalidated delivery",
                        )
                        _validate("state", state)
                        _replace_at(
                            descriptor,
                            "schedule-state.json",
                            canonical_json_bytes(state),
                        )
                        outcomes.append(dict(previous))
                        continue
                    attempts = previous["attempts"] + 1 if previous else 1
                    job = {
                        "id": key,
                        "schedule_id": schedule["id"],
                        "configuration_digest": digest,
                        "intended_at": intended.isoformat(),
                        "attempts": attempts,
                        "status": "pending",
                        "next_retry_at": (
                            now + timedelta(seconds=schedule["retry_seconds"])
                        ).isoformat(),
                        "report_sha256": None,
                        "report_status": None,
                        "error": None,
                    }
                    jobs[key] = job
                    state["jobs"] = sorted(jobs.values(), key=lambda row: row["id"])
                    _validate("state", state)
                    _replace_at(
                        descriptor, "schedule-state.json", canonical_json_bytes(state)
                    )
                    try:
                        report = build_portfolio(config, now=intended)
                        content = canonical_json_bytes(report)
                        _publish_report(descriptor, "report-" + key + ".json", content)
                        job.update(
                            status="succeeded",
                            report_sha256=hashlib.sha256(content).hexdigest(),
                            report_status=report["status"],
                        )
                    except (CppulseError, OSError) as error:
                        job.update(
                            status=(
                                "exhausted"
                                if attempts >= schedule["max_attempts"]
                                else "failed"
                            ),
                            error=str(error)[:2000],
                        )
                    _validate("state", state)
                    _replace_at(
                        descriptor, "schedule-state.json", canonical_json_bytes(state)
                    )
                    outcomes.append(dict(job))
        finally:
            os.unlink(".portfolio.lock", dir_fd=descriptor)
    active_jobs = [
        row for row in jobs.values() if row["configuration_digest"] == digest
    ]
    retry_times = [
        _utc(row["next_retry_at"])
        for row in active_jobs
        if row["status"] in {"pending", "failed"}
    ]
    return {
        "active_job_counts": {
            status: sum(row["status"] == status for row in active_jobs)
            for status in ("pending", "failed", "exhausted", "succeeded")
        },
        "next_retry_at": min(retry_times).isoformat() if retry_times else None,
        "configuration_digest": digest,
        "attempted_at": now.isoformat(),
        "outcomes": outcomes,
        "delivery_kind": "local-files-only",
        "policy_acceptance": "not_assessed",
    }
