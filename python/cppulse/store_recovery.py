"""Explicit qualified local dead-writer recovery; staged facts are never reused."""

from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any
from uuid import uuid4

from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.store_coordination import (
    local_process_identity,
    process_incarnation,
    publication_guard,
    validate_store_document,
)

MAX_LOCK_BYTES = 16384
LOCAL_FILESYSTEMS = frozenset({"ext4", "xfs", "btrfs", "tmpfs", "overlay"})


def _strict_json(raw: bytes) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise ContractError("Duplicate writer-lock JSON key")
            result[key] = value
        return result

    try:
        result = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ContractError("Nonfinite writer-lock JSON")
            ),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("Writer-lock JSON is invalid") from exc
    if not isinstance(result, dict):
        raise ContractError("Writer-lock JSON must be an object")
    return result


def _filesystem(root: Path) -> dict[str, Any]:
    if sys.platform != "linux":
        return {
            "qualified": False,
            "type": None,
            "mountpoint": None,
            "reason": "Only the selected local Linux filesystem recovery protocol is qualified.",
        }
    try:
        with Path("/proc/self/mountinfo").open("rb") as stream:
            raw = stream.read(8 * 1024**2 + 1)
        if len(raw) > 8 * 1024**2:
            raise IntegrityError(
                "Mount inventory exceeds finite recovery observation budget"
            )
        selected = None
        for line in raw.decode("utf-8").splitlines():
            left, right = line.split(" - ", 1)
            encoded = left.split()[4]
            mount = re.sub(
                r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), encoded
            )
            try:
                root.relative_to(mount)
            except ValueError:
                continue
            if selected is None or len(mount) > len(selected[0]):
                selected = (mount, right.split()[0])
        if selected is None:
            raise IntegrityError("Selected store has no observed filesystem mount")
        mount, kind = selected
        qualified = kind in LOCAL_FILESYSTEMS
        return {
            "qualified": qualified,
            "type": kind,
            "mountpoint": mount,
            "reason": (
                "Cooperative local filesystem locking only; remote/shared filesystems are unsupported."
                if qualified
                else "Selected filesystem is outside the qualified local allowlist."
            ),
        }
    except (OSError, ValueError, IndexError, UnicodeError, IntegrityError) as exc:
        return {
            "qualified": False,
            "type": None,
            "mountpoint": None,
            "reason": str(exc),
        }


def _read_lock(root_fd: int) -> tuple[bytes, os.stat_result] | None:
    try:
        descriptor = os.open(
            ".publication.lock",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=root_fd,
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise IntegrityError("Selected writer lock is unsafe or unreadable") from exc
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o022
        ):
            raise IntegrityError(
                "Selected writer lock is nonregular, linked, foreign-owned or writable by other users"
            )
        if before.st_size > MAX_LOCK_BYTES:
            raise IntegrityError(
                "Selected writer lock exceeds finite control byte budget"
            )
        raw = stream.read(MAX_LOCK_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > MAX_LOCK_BYTES or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise PublicationConflict("Writer lock changed during observation")
    return raw, before


def _owner(lock: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    def unknown(status: str, reason: str) -> dict[str, Any]:
        return {"status": status, "reason": reason, "observed": None}

    if lock is None:
        return unknown("unknown", "Writer-lock JSON could not be validated.")
    if lock.get("version") != "2.0.0":
        return unknown(
            "legacy",
            "Original local process incarnation was not recorded; explicit foreign/legacy recovery is unsupported.",
        )
    try:
        validate_store_document("publication_lock", lock)
    except ContractError as exc:
        return unknown("unknown", str(exc))
    original = lock["owner"]
    if original["status"] != "available" or current["status"] != "available":
        return unknown(
            "unknown", "Original or current local Linux owner identity is unavailable."
        )
    if any(
        original[key] != current[key] for key in ("boot_id", "pid_namespace", "uid")
    ):
        return unknown(
            "foreign",
            "Original boot, PID namespace or user differs from this local observer.",
        )
    try:
        observed = process_incarnation(lock["pid"])
    except FileNotFoundError:
        return unknown(
            "absent",
            "Original selected PID no longer exists in the qualified local namespace.",
        )
    except (OSError, IntegrityError) as exc:
        return unknown("unknown", str(exc))
    if observed["start_ticks"] != original["start_ticks"]:
        return {
            "status": "pid_reused",
            "reason": "The selected PID now identifies a different incarnation; no process was signalled.",
            "observed": observed,
        }
    if any(observed[key] != original[key] for key in ("pid_namespace", "uid")):
        return unknown(
            "unknown",
            "Current selected process identity is inconsistent with the original owner.",
        )
    if observed["state"] in {"Z", "X"}:
        return {
            "status": "zombie",
            "reason": "Original incarnation has exited and cannot resume execution.",
            "observed": observed,
        }
    return {
        "status": "alive",
        "reason": "Original selected writer incarnation is still present; recovery is refused.",
        "observed": observed,
    }


def _observe(root: Path, root_fd: int) -> tuple[dict[str, Any], os.stat_result | None]:
    filesystem = _filesystem(root)
    root_metadata = os.fstat(root_fd)
    if root_metadata.st_uid != os.geteuid() or root_metadata.st_mode & 0o022:
        filesystem = {
            **filesystem,
            "qualified": False,
            "reason": "Store root is foreign-owned or writable by other users; local recovery is unqualified.",
        }
    selected = _read_lock(root_fd)
    raw, metadata = selected if selected is not None else (None, None)
    lock = None
    if raw is not None:
        try:
            lock = _strict_json(raw)
        except ContractError:
            pass
    observer = local_process_identity()
    owner = (
        _owner(lock, observer)
        if raw is not None
        else {
            "status": "no_lock",
            "reason": "No current writer lock is present.",
            "observed": None,
        }
    )
    eligible = filesystem["qualified"] and owner["status"] in {
        "absent",
        "pid_reused",
        "zombie",
    }
    report = {
        "version": "1.0.0",
        "mode": "inspect",
        "status": (
            "eligible" if eligible else ("no_lock" if raw is None else "protected")
        ),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "store": str(root),
        "lock_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
        "lock_raw_hex": raw.hex() if raw is not None else None,
        "lock": lock,
        "observer_pid": os.getpid(),
        "observer_identity": observer,
        "owner_observation": owner,
        "filesystem": filesystem,
        "reason": (
            "Exact selected dead local owner may be recovered explicitly; observations do not authorize automatic fact reuse."
            if eligible
            else (
                filesystem["reason"] if not filesystem["qualified"] else owner["reason"]
            )
        ),
        "preserved_lock": None,
        "preserved_stage": None,
        "report_path": None,
        "facts_reused": False,
        "current_lock_sha256": (
            hashlib.sha256(raw).hexdigest() if raw is not None else None
        ),
        "current_lock_action": "observed_only",
        "source_journal": None,
    }
    validate_recovery_report(report)
    return report, metadata


def validate_recovery_report(report: dict[str, Any]) -> None:
    """Reject contradictory recovery claims while preserving original lock bytes."""
    validate_store_document("recovery_report", report)
    if report["lock_raw_hex"] is not None:
        raw = bytes.fromhex(report["lock_raw_hex"])
        if hashlib.sha256(raw).hexdigest() != report["lock_sha256"]:
            raise ContractError(
                "Recovery report changes the selected original lock bytes"
            )
        if report["lock"] is not None and _strict_json(raw) != report["lock"]:
            raise ContractError(
                "Recovery report parsed lock differs from original bytes"
            )
    elif report["lock_sha256"] is not None or report["lock"] is not None:
        raise ContractError("Recovery report invents a missing original lock")
    if report["filesystem"]["qualified"] and (
        report["filesystem"]["type"] not in LOCAL_FILESYSTEMS
        or report["filesystem"]["mountpoint"] is None
    ):
        raise ContractError(
            "Recovery report invents qualified local filesystem semantics"
        )
    selected, observation = report["lock"], report["owner_observation"]
    status, observed = observation["status"], observation["observed"]
    if status in {"absent", "pid_reused", "zombie", "alive"}:
        if selected is None:
            raise ContractError("Owner observation lacks its original selected lock")
        validate_store_document("publication_lock", selected)
        original, observer = selected["owner"], report["observer_identity"]
        if (
            original["status"] != "available"
            or observer["status"] != "available"
            or any(
                original[key] != observer[key]
                for key in ("boot_id", "pid_namespace", "uid")
            )
        ):
            raise ContractError(
                "Owner observation is outside the original local process namespace"
            )
        if status == "absent":
            if observed is not None:
                raise ContractError(
                    "Absent process observation must not invent an incarnation"
                )
        else:
            if observed is None or observed["pid"] != selected["pid"]:
                raise ContractError(
                    "Process observation identifies another selected PID"
                )
            reused = observed["start_ticks"] != original["start_ticks"]
            if (status == "pid_reused") != reused:
                raise ContractError(
                    "PID reuse claim differs from observed process start ticks"
                )
            if not reused and any(
                observed[key] != original[key] for key in ("pid_namespace", "uid")
            ):
                raise ContractError(
                    "Observed process identity differs from the original owner"
                )
            if not reused and (
                (status == "zombie") != (observed["state"] in {"Z", "X"})
            ):
                raise ContractError(
                    "Dead/live owner claim differs from actual observed process state"
                )
    if status == "no_lock" and report["lock_raw_hex"] is not None:
        raise ContractError("No-lock observation contains original writer bytes")
    eligible = report["filesystem"]["qualified"] and report["owner_observation"][
        "status"
    ] in {"absent", "pid_reused", "zombie"}
    root = PurePosixPath(report["store"])
    if not root.is_absolute() or ".." in root.parts or str(root) != report["store"]:
        raise ContractError(
            "Recovery report store identity is not canonical absolute POSIX"
        )
    if (
        report["status"]
        in {"eligible", "prepared", "recovered", "reconcilable", "reconciled"}
        and not eligible
    ):
        raise ContractError(
            "Recovery claim lacks a qualified dead original local owner"
        )
    state = report["status"]
    if state in {"prepared", "recovered", "reconcilable", "reconciled"}:
        if (
            report["preserved_lock"] is None
            or report["preserved_stage"] is None
            or report["preserved_lock"]["sha256"] != report["lock_sha256"]
            or report["preserved_lock"]["size_bytes"]
            != len(bytes.fromhex(report["lock_raw_hex"]))
        ):
            raise ContractError(
                "Recovery report lacks preserved diagnostics and original lock pin"
            )
        lock_path = PurePosixPath(report["preserved_lock"]["path"])
        prefix = report["lock_sha256"] + "-"
        if (
            lock_path.parent != root / ".recovery"
            or re.fullmatch(
                re.escape(prefix) + r"[a-f0-9]{32}\.lock\.json", lock_path.name
            )
            is None
            or report["preserved_stage"]["path"]
            != str(root / ".staging" / report["lock"]["run_id"])
        ):
            raise ContractError(
                "Recovery receipt escapes selected store or original stage"
            )
        stage = report["preserved_stage"]
        if stage["exists"] != (
            stage["device"] is not None and stage["inode"] is not None
        ):
            raise ContractError("Recovery receipt invents missing stage identity")
        if state == "reconcilable":
            if report["mode"] != "inspect" or report["report_path"] is not None:
                raise ContractError(
                    "Read-only reconciliation observation cannot claim a new stored report"
                )
        else:
            if report["mode"] != "recover" or report["report_path"] is None:
                raise ContractError("Recovery action lacks its stored receipt")
            path = PurePosixPath(report["report_path"])
            if (
                path.parent != root / ".recovery"
                or re.fullmatch(
                    re.escape(prefix) + r"[a-f0-9]{32}\." + state + r"\.json", path.name
                )
                is None
            ):
                raise ContractError("Recovery receipt report escapes selected scope")
            if state in {"prepared", "recovered"} and path.name != (
                lock_path.name.removesuffix(".lock.json") + "." + state + ".json"
            ):
                raise ContractError(
                    "Ordinary recovery report changes its original archive identity"
                )
        if state in {"reconcilable", "reconciled"}:
            journal = report.get("source_journal")
            if (
                journal is None
                or report.get("current_lock_sha256") == report["lock_sha256"]
            ):
                raise ContractError(
                    "Reconciliation does not identify a previous completed unlock boundary"
                )
            path = PurePosixPath(journal["path"])
            if (
                path.parent != root / ".recovery"
                or re.fullmatch(
                    re.escape(prefix) + r"[a-f0-9]{32}\.prepared\.json", path.name
                )
                is None
            ):
                raise ContractError(
                    "Reconciliation lacks selected original prepared journal"
                )
            if report.get("current_lock_action") != (
                "left_unchanged" if state == "reconciled" else "observed_only"
            ):
                raise ContractError(
                    "Reconciliation must preserve every current writer lock"
                )
        elif report.get("source_journal") is not None:
            raise ContractError(
                "Ordinary recovery cannot invent a reconciliation source"
            )
        if state == "recovered" and (
            report.get("current_lock_sha256") is not None
            or report.get("current_lock_action", "removed_selected")
            != "removed_selected"
        ):
            raise ContractError(
                "Recovered receipt must describe removal only of its selected old lock"
            )
    elif (
        any(
            report[key] is not None
            for key in ("preserved_lock", "preserved_stage", "report_path")
        )
        or report.get("source_journal") is not None
    ):
        raise ContractError("An observation cannot invent recovery artifacts")


def inspect_store_lock(store: str | Path) -> dict[str, Any]:
    """Observe a selected store without changing files or signalling processes."""
    from cppulse.run_store import _directory

    root = Path(store).absolute()
    with _directory(root) as root_fd:
        return _observe(root, root_fd)[0]


def _stage_info(root: Path, root_fd: int, run_id: str) -> dict[str, Any]:
    path = root / ".staging" / run_id
    try:
        staging_fd = os.open(
            ".staging", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        try:
            metadata = os.stat(run_id, dir_fd=staging_fd, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                raise IntegrityError(
                    "Selected abandoned stage is not an ordinary directory"
                )
        finally:
            os.close(staging_fd)
        return {
            "path": str(path),
            "exists": True,
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
            "method": "left_in_place",
            "content_inventory": "not_computed",
        }
    except FileNotFoundError:
        return {
            "path": str(path),
            "exists": False,
            "device": None,
            "inode": None,
            "method": "left_in_place",
            "content_inventory": "not_computed",
        }
    except OSError as exc:
        raise IntegrityError(
            "Selected abandoned stage path is unsafe or unavailable"
        ) from exc


def _write_at(parent: int, name: str, content: bytes) -> None:
    descriptor = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(parent)


def recover_store_lock(
    store: str | Path, *, expected_lock_sha256: str, expected_lock_token: str
) -> dict[str, Any]:
    """Quarantine only an explicitly selected dead local writer lock under flock.

    Raw lock bytes and the abandoned stage stay available. No process is killed,
    no pointer is promoted and no previous fact becomes fresh source evidence.
    """
    from cppulse.run_store import _directory

    if (
        not isinstance(expected_lock_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", expected_lock_sha256) is None
        or not isinstance(expected_lock_token, str)
        or re.fullmatch(r"[a-f0-9]{32}", expected_lock_token) is None
    ):
        raise ContractError(
            "Recovery requires the exact observed lock SHA256 and token"
        )
    root = Path(store).absolute()
    with (
        _directory(root) as root_fd,
        publication_guard(root_fd, required=True) as lease,
    ):
        report, original = _observe(root, root_fd)
        if report["lock_sha256"] != expected_lock_sha256:
            return _reconcile_prepared(
                root, root_fd, lease, report, expected_lock_sha256, expected_lock_token
            )
        if report["lock"] is None or report["lock"].get("token") != expected_lock_token:
            raise PublicationConflict(
                "Selected writer lock changed or does not match the explicit expected receipt"
            )
        if report["status"] != "eligible" or original is None:
            raise PublicationConflict(report["reason"])
        stage = _stage_info(root, root_fd, report["lock"]["run_id"])
        try:
            os.mkdir(".recovery", 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        archive_fd = os.open(
            ".recovery", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        try:
            archive_metadata = os.fstat(archive_fd)
            if (
                archive_metadata.st_uid != os.geteuid()
                or stat.S_IMODE(archive_metadata.st_mode) != 0o700
            ):
                raise IntegrityError(
                    "Recovery receipt directory is foreign-owned or has unsafe permissions"
                )
            raw = bytes.fromhex(report["lock_raw_hex"])
            suffix = expected_lock_sha256 + "-" + uuid4().hex
            name = suffix + ".lock.json"
            report.update(
                mode="recover",
                status="prepared",
                preserved_lock={
                    "path": str(root / ".recovery" / name),
                    "sha256": expected_lock_sha256,
                    "size_bytes": len(raw),
                },
                preserved_stage=stage,
                report_path=str(root / ".recovery" / (suffix + ".prepared.json")),
            )
            validate_recovery_report(report)
            lease.check()
            latest = _read_lock(root_fd)
            if (
                latest is None
                or latest[0] != raw
                or (latest[1].st_dev, latest[1].st_ino)
                != (original.st_dev, original.st_ino)
            ):
                raise PublicationConflict(
                    "Original selected writer lock changed before quarantine"
                )
            # Copy the tiny control receipt instead of linking it: any crash
            # before unlink leaves the original single-link writer lock safely
            # recoverable by the same explicit expected SHA/token operation.
            _write_at(archive_fd, name, raw)
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=archive_fd)
            with os.fdopen(descriptor, "rb") as stream:
                archived = os.fstat(stream.fileno())
                preserved = stream.read(MAX_LOCK_BYTES + 1)
            if (
                not stat.S_ISREG(archived.st_mode)
                or archived.st_nlink != 1
                or preserved != raw
            ):
                raise PublicationConflict(
                    "Preserved writer receipt bytes changed before recovery"
                )
            _write_at(
                archive_fd,
                suffix + ".prepared.json",
                (json.dumps(report, indent=2, allow_nan=False) + "\n").encode(),
            )
            lease.check()
            current = _read_lock(root_fd)
            if (
                current is None
                or current[0] != raw
                or (current[1].st_dev, current[1].st_ino)
                != (original.st_dev, original.st_ino)
            ):
                raise PublicationConflict(
                    "A changed or newly-created writer lock must never be removed"
                )
            os.unlink(".publication.lock", dir_fd=root_fd)
            os.fsync(root_fd)
            os.fsync(archive_fd)
            report.update(
                status="recovered",
                current_lock_sha256=None,
                current_lock_action="removed_selected",
                reason="Explicit selected dead local writer lock was quarantined; staged bytes preserved without fact reuse or pointer promotion.",
                report_path=str(root / ".recovery" / (suffix + ".recovered.json")),
            )
            validate_recovery_report(report)
            _write_at(
                archive_fd,
                suffix + ".recovered.json",
                (json.dumps(report, indent=2, allow_nan=False) + "\n").encode(),
            )
            return report
        finally:
            os.close(archive_fd)


def _receipt_bytes(parent: int, name: str, maximum: int = 65536) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
    )
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o022
            or metadata.st_size > maximum
        ):
            raise IntegrityError(
                "Prepared recovery receipt is unsafe or exceeds its byte budget"
            )
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise IntegrityError("Prepared recovery receipt exceeds its byte budget")
    return raw


def _prepared_receipt(
    root: Path, root_fd: int, sha: str, token: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        parent = os.open(
            ".recovery", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
    except OSError as exc:
        raise PublicationConflict(
            "No qualified prepared recovery receipt matches this selected old lock"
        ) from exc
    try:
        metadata = os.fstat(parent)
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise IntegrityError("Recovery receipt namespace is foreign or unsafe")
        names = []
        count = 0
        with os.scandir(parent) as entries:
            for entry in entries:
                count += 1
                if count > 4096:
                    raise IntegrityError(
                        "Recovery receipt inventory exceeds finite inspection budget"
                    )
                if re.fullmatch(
                    re.escape(sha) + r"-[a-f0-9]{32}\.prepared\.json", entry.name
                ):
                    names.append(entry.name)
                if len(names) > 128:
                    raise IntegrityError("Too many matching prepared recovery receipts")
        for name in sorted(names):
            raw = _receipt_bytes(parent, name)
            report = _strict_json(raw)
            validate_recovery_report(report)
            if (
                report["status"] != "prepared"
                or report["store"] != str(root)
                or report["lock_sha256"] != sha
                or report["lock"] is None
                or report["lock"].get("token") != token
            ):
                continue
            archived_path = Path(report["preserved_lock"]["path"])
            archived = _receipt_bytes(parent, archived_path.name, MAX_LOCK_BYTES)
            if archived != bytes.fromhex(report["lock_raw_hex"]):
                raise IntegrityError(
                    "Prepared recovery archive differs from selected original lock bytes"
                )
            stage = _stage_info(root, root_fd, report["lock"]["run_id"])
            if stage != report["preserved_stage"]:
                raise IntegrityError(
                    "Prepared recovery's original stage identity changed"
                )
            return report, {
                "path": str(root / ".recovery" / name),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        raise PublicationConflict(
            "No prepared receipt matches the explicit selected original lock SHA256/token"
        )
    finally:
        os.close(parent)


def _reconciliation_observation(
    root: Path, root_fd: int, current: dict[str, Any], sha: str, token: str
) -> dict[str, Any]:
    prepared, source = _prepared_receipt(root, root_fd, sha, token)
    report = deepcopy(prepared)
    observer = local_process_identity()
    owner = _owner(report["lock"], observer)
    if not current["filesystem"]["qualified"] or owner["status"] not in {
        "absent",
        "pid_reused",
        "zombie",
    }:
        raise PublicationConflict(
            "Prepared recovery is foreign, unknown or no longer locally qualified"
        )
    report.update(
        mode="inspect",
        status="reconcilable",
        observed_at=datetime.now(timezone.utc).isoformat(),
        observer_pid=os.getpid(),
        observer_identity=observer,
        owner_observation=owner,
        filesystem=current["filesystem"],
        current_lock_sha256=current["lock_sha256"],
        current_lock_action="observed_only",
        source_journal=source,
        report_path=None,
        reason="Prepared original lock archive is checked; selected old lock is no longer current. Every current writer lock remains untouched.",
    )
    validate_recovery_report(report)
    return report


def inspect_recovery_receipt(
    store: str | Path, *, expected_lock_sha256: str, expected_lock_token: str
) -> dict[str, Any]:
    """Explain a selected interrupted unlock read-only, including newer writers."""
    from cppulse.run_store import _directory

    if (
        not isinstance(expected_lock_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", expected_lock_sha256) is None
        or not isinstance(expected_lock_token, str)
        or re.fullmatch(r"[a-f0-9]{32}", expected_lock_token) is None
    ):
        raise ContractError(
            "Recovery inspection requires the exact original lock SHA256/token"
        )
    root = Path(store).absolute()
    with _directory(root) as root_fd:
        current, _ = _observe(root, root_fd)
        if current["lock_sha256"] == expected_lock_sha256:
            if (
                current["lock"] is None
                or current["lock"].get("token") != expected_lock_token
            ):
                raise PublicationConflict("Selected original writer token differs")
            return current
        return _reconciliation_observation(
            root, root_fd, current, expected_lock_sha256, expected_lock_token
        )


def _reconcile_prepared(
    root: Path, root_fd: int, lease: Any, current: dict[str, Any], sha: str, token: str
) -> dict[str, Any]:
    report = _reconciliation_observation(root, root_fd, current, sha, token)
    parent = os.open(
        ".recovery", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
    )
    try:
        lease.check()
        before = _read_lock(root_fd)
        current_sha = (
            hashlib.sha256(before[0]).hexdigest() if before is not None else None
        )
        if current_sha != current["lock_sha256"]:
            raise PublicationConflict(
                "Current writer changed during selected receipt reconciliation"
            )
        name = sha + "-" + uuid4().hex + ".reconciled.json"
        report.update(
            mode="recover",
            status="reconciled",
            current_lock_action="left_unchanged",
            report_path=str(root / ".recovery" / name),
            reason="Prepared selected old unlock was reconciled from exact retained receipt bytes. Current writer lock, source facts and reader pointers were not changed.",
        )
        validate_recovery_report(report)
        _write_at(
            parent,
            name,
            (json.dumps(report, indent=2, allow_nan=False) + "\n").encode(),
        )
        return report
    finally:
        os.close(parent)


def verify_recovery_report(report: dict[str, Any]) -> None:
    """Replay preserved local receipt bytes; no source freshness is inferred.

    Staged content is deliberately not inventoried by recovery. This verifies
    the recorded directory identity, exact lock archive and selected journal.
    """
    from cppulse.run_store import _directory

    validate_recovery_report(report)
    if report["preserved_lock"] is None:
        return
    root = Path(report["store"])
    with _directory(root) as root_fd:
        parent = os.open(
            ".recovery", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        try:
            archived = report["preserved_lock"]
            raw = _receipt_bytes(parent, Path(archived["path"]).name, MAX_LOCK_BYTES)
            if (
                raw != bytes.fromhex(report["lock_raw_hex"])
                or len(raw) != archived["size_bytes"]
            ):
                raise IntegrityError("Preserved recovery lock archive changed")
            if (
                _stage_info(root, root_fd, report["lock"]["run_id"])
                != report["preserved_stage"]
            ):
                raise IntegrityError("Preserved recovery stage identity changed")
            journal = report.get("source_journal")
            if journal is not None:
                raw_journal = _receipt_bytes(parent, Path(journal["path"]).name)
                if (
                    len(raw_journal) != journal["size_bytes"]
                    or hashlib.sha256(raw_journal).hexdigest() != journal["sha256"]
                ):
                    raise IntegrityError("Original prepared recovery journal changed")
                original = _strict_json(raw_journal)
                validate_recovery_report(original)
                if original["status"] != "prepared" or any(
                    original[key] != report[key]
                    for key in (
                        "store",
                        "lock_sha256",
                        "lock_raw_hex",
                        "lock",
                        "preserved_lock",
                        "preserved_stage",
                    )
                ):
                    raise IntegrityError(
                        "Reconciled report differs from original prepared recovery"
                    )
            if report["report_path"] is not None:
                stored = _strict_json(
                    _receipt_bytes(parent, Path(report["report_path"]).name)
                )
                if stored != report:
                    raise IntegrityError(
                        "Stored recovery report differs from selected observation"
                    )
        finally:
            os.close(parent)
