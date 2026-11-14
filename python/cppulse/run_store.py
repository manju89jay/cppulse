"""Local immutable-by-API run snapshots with checked artifact reads.

This is local persistence, not producer authentication or protection from the
filesystem owner. POSIX no-follow directory operations prevent path/symlink
redirection; digests detect corruption against the reader's frozen manifest.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
from typing import Any, Callable, Iterator
from uuid import uuid4

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError, IntegrityError, PublicationConflict

Contract = str | tuple[str, str] | dict[str, str]
_RESERVED = {
    "run_manifest.json",
    "latest.json",
    "latest_attempt.json",
    ".publication.lock",
}
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_NO_SOURCE_CHECK = (
    "Source freshness was not checked at publication; the recorded source identity "
    "is an imported caller claim."
)


def _relative(value: str) -> str:
    """Require one canonical relative artifact identity."""
    if not isinstance(value, str):
        raise IntegrityError("Artifact path must be a canonical relative string")
    path = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
        or path.as_posix() != value
        or value == "."
    ):
        raise IntegrityError(f"Unsafe noncanonical artifact path: {value!r}")
    return value


def _run_id(value: str) -> str:
    if not isinstance(value, str) or not _RUN_ID.fullmatch(value):
        raise IntegrityError(
            "Run ID must be a canonical identifier of at most 64 characters"
        )
    return value


@contextmanager
def _directory(path: Path, *, create: bool = False) -> Iterator[int]:
    """Open every ancestor without following symlinks, optionally creating dirs."""
    absolute = path.absolute()
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            for part in absolute.parts[1:]:
                if part == "..":
                    raise IntegrityError(
                        "Directory traversal is not an output identity"
                    )
                try:
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                os.close(descriptor)
                descriptor = child
        except OSError as exc:
            raise IntegrityError(
                f"Directory is missing, unsafe or inaccessible: {path}"
            ) from exc
        yield descriptor
    finally:
        os.close(descriptor)


def _read(path: Path) -> bytes:
    """Read one regular-file descriptor once; never verify then reopen its path."""
    try:
        with _directory(path.parent) as parent:
            descriptor = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise IntegrityError(f"Expected a regular artifact file: {path}")
            return stream.read()
    except OSError as exc:
        raise IntegrityError(
            f"Artifact is missing, unsafe or unreadable: {path}"
        ) from exc


def _json_bytes(document: dict[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError(
            "Document must contain finite serializable JSON values"
        ) from exc


def _json_object(data: bytes, path: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"Invalid JSON document: {path}") from exc
    if not isinstance(value, dict):
        raise IntegrityError(f"Expected a JSON object: {path}")
    return value


def _write_new(path: Path, content: bytes) -> None:
    """Durably create a new staged file; overwrites are never an artifact update."""
    try:
        with _directory(path.parent, create=True) as parent:
            descriptor = os.open(
                path.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(parent)
    except FileExistsError as exc:
        raise PublicationConflict(f"File already exists: {path}") from exc
    except OSError as exc:
        raise IntegrityError(f"Cannot durably write artifact: {path}") from exc


def _contract(value: Contract, document: dict[str, Any]) -> dict[str, str]:
    if isinstance(value, str):
        kind, version = value, document.get("version", "2.0.0")
    elif isinstance(value, tuple) and len(value) == 2:
        kind, version = value
    elif isinstance(value, dict) and set(value) == {"kind", "version"}:
        kind, version = value["kind"], value["version"]
    else:
        raise ContractError("Contract must name a kind and optional explicit version")
    validate(kind, document, version=version)
    return {"kind": kind, "version": version}


def _validate_documents(
    manifest: dict[str, Any], documents: list[tuple[dict[str, str], dict[str, Any]]]
) -> None:
    bundle: dict[str, Any] = {"run_manifest": manifest}
    for reference, document in documents:
        validate(reference["kind"], document, version=reference["version"])
        if reference["version"] == "2.0.0":
            kind = reference["kind"]
            if kind == "run_manifest":
                raise ContractError("A run cannot contain a second run manifest")
            if kind == "policy":
                # An assessment binds one policy document. Other kinds may have
                # multiple producers; a list of policies has no such selection.
                if kind in bundle:
                    raise ContractError(
                        "A run may contain at most one policy document",
                        code="UNSUPPORTED_CARDINALITY",
                    )
                bundle[kind] = document
            else:
                bundle.setdefault(kind, []).append(document)
    validate_bundle(bundle)


@dataclass(frozen=True)
class RunSnapshot:
    """A manifest-bound reader; later latest-pointer changes cannot redirect it."""

    _root: Path
    run_id: str
    manifest_sha256: str
    _manifest: dict[str, Any]

    @property
    def path(self) -> Path:
        """Return the concrete committed run directory, never the latest pointer."""
        return self._root / "runs" / self.run_id

    @property
    def manifest(self) -> dict[str, Any]:
        """Return an independent copy of the frozen manifest."""
        return deepcopy(self._manifest)

    def _check_manifest(self) -> None:
        self.read_manifest_bytes()

    def read_manifest_bytes(self) -> bytes:
        """Return the original manifest bytes from one hardened, SHA-checked read.

        Presentation and transfer callers must retain the original JSON layout
        when exposing the manifest pin; serializing ``manifest`` is not equal
        to reading the bytes identified by ``manifest_sha256``.
        """
        content = _read(self.path / "run_manifest.json")
        if hashlib.sha256(content).hexdigest() != self.manifest_sha256:
            raise IntegrityError("Run manifest changed after snapshot resolution")
        return content

    def _entry(self, name: str) -> dict[str, Any]:
        matches = [
            entry
            for entry in self._manifest["artifacts"]
            if name in {entry["id"], entry["path"]}
        ]
        if len(matches) != 1:
            raise IntegrityError(f"Artifact reference is absent or ambiguous: {name!r}")
        return matches[0]

    def _read_entry(self, entry: dict[str, Any]) -> bytes:
        content = _read(self.path / _relative(entry["path"]))
        if (
            len(content) != entry["size_bytes"]
            or hashlib.sha256(content).hexdigest() != entry["sha256"]
        ):
            raise IntegrityError(f"Artifact integrity mismatch: {entry['path']}")
        return content

    def read_bytes(self, name: str) -> bytes:
        """Return exactly the artifact bytes whose digest was checked."""
        self._check_manifest()
        return self._read_entry(self._entry(name))

    def read_json(
        self, name: str, *, contract: Contract | None = None
    ) -> dict[str, Any]:
        """Read checked bytes and validate their declared or explicit contract."""
        entry = self._entry(name)
        document = _json_object(self.read_bytes(name), entry["path"])
        reference = entry.get("contract") if contract is None else contract
        if reference is None:
            raise ContractError(
                "Reading JSON requires an explicit or declared contract"
            )
        _contract(reference, document)
        return document

    def verify(self) -> None:
        """Verify manifest, artifact bytes, contracts and closed v2 references."""
        self._check_manifest()
        documents = []
        for entry in self._manifest["artifacts"]:
            content = self._read_entry(entry)
            if "contract" in entry:
                documents.append(
                    (entry["contract"], _json_object(content, entry["path"]))
                )
        _validate_documents(self._manifest, documents)


class RunStore:
    """A local single-publisher store. Only completed collections update latest.

    Completed means execution collection completed, not that checks/policies
    passed. Partial/cancelled runs advance latest_attempt but not latest.json.
    Unknown prior locks require explicit operator recovery; no stale lock is
    deleted automatically. This first implementation uses POSIX directory FDs.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).absolute()
        self._read_only = False
        for path in [self.root, self.root / "runs", self.root / ".staging"]:
            with _directory(path, create=True):
                pass

    @classmethod
    def open_existing(cls, root: str | Path) -> RunStore:
        """Open an existing store without creating directories or writer state.

        The root and ``runs`` ancestors must be safe existing directories. A
        retained read-only copy need not contain ``.staging``. Individual reads
        still validate the selected manifest, contract and artifact bytes.

        Args:
            root: Existing local store directory; symlink ancestors are refused.

        Returns:
            A reader whose ``begin`` method refuses publication.

        Raises:
            IntegrityError: The selected directory is missing or unsafe.
        """
        instance = cls.__new__(cls)
        instance.root = Path(root).absolute()
        with _directory(instance.root / "runs"):
            pass
        instance._read_only = True
        return instance

    def begin(self, run_id: str | None = None) -> StagedRun:
        """Acquire the writer slot and begin a context-managed staging run."""
        if self._read_only:
            raise PublicationConflict(
                "Read-only run store cannot begin publication", code="READ_ONLY_STORE"
            )
        return StagedRun(self, _run_id(uuid4().hex if run_id is None else run_id))

    def open_run(
        self, run_id: str, *, manifest_sha256: str | None = None
    ) -> RunSnapshot:
        """Open one committed manifest, optionally bound to a trusted pointer hash."""
        run_id = _run_id(run_id)
        content = _read(self.root / "runs" / run_id / "run_manifest.json")
        digest = hashlib.sha256(content).hexdigest()
        if manifest_sha256 is not None and digest != manifest_sha256:
            raise IntegrityError("Latest pointer and run manifest digests disagree")
        document = _json_object(content, "run_manifest.json")
        validate("run_manifest", document)
        if document["run_id"] != run_id:
            raise IntegrityError("Run directory and manifest identity disagree")
        snapshot = RunSnapshot(self.root, run_id, digest, deepcopy(document))
        snapshot.verify()
        return snapshot

    def _resolve_pointer(self, name: str, *, completed: bool) -> RunSnapshot:
        pointer = _json_object(_read(self.root / name), name)
        if (
            set(pointer) != {"version", "run_id", "manifest_sha256"}
            or pointer["version"] != "2.0.0"
            or not isinstance(pointer["manifest_sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", pointer["manifest_sha256"])
        ):
            raise IntegrityError("Invalid latest pointer contract")
        snapshot = self.open_run(
            pointer["run_id"], manifest_sha256=pointer["manifest_sha256"]
        )
        if completed and snapshot.manifest["status"] != "completed":
            raise IntegrityError(
                "Latest completed pointer must identify a completed collection"
            )
        return snapshot

    def resolve_latest(self) -> RunSnapshot:
        """Resolve the last completed collection, not the last passed assessment.

        A later partial/cancelled publication does not replace this pointer.
        User-facing current-attempt views should use resolve_latest_attempt.
        """
        return self._resolve_pointer("latest.json", completed=True)

    def resolve_latest_attempt(self) -> RunSnapshot:
        """Resolve the last published attempt, including partial/cancelled status.

        Unpublished staging directories are never exposed. Current-source and
        policy applicability must still be evaluated by the consuming workflow.
        """
        return self._resolve_pointer("latest_attempt.json", completed=False)

    def read_json(
        self, name: str, *, run_id: str | None = None, contract: Contract | None = None
    ) -> dict[str, Any]:
        """Convenience read; resolve once yourself for a multi-file request."""
        return (
            self.open_run(run_id) if run_id is not None else self.resolve_latest()
        ).read_json(name, contract=contract)

    def read_bytes(self, name: str, *, run_id: str | None = None) -> bytes:
        """Convenience read of one checked artifact."""
        return (
            self.open_run(run_id) if run_id is not None else self.resolve_latest()
        ).read_bytes(name)

    def verify(self, run_id: str | None = None) -> None:
        """Verify one named run or the currently resolved completed snapshot."""
        (
            self.open_run(run_id) if run_id is not None else self.resolve_latest()
        ).verify()

    def _publish_pointer(self, snapshot: RunSnapshot, name: str) -> None:
        temporary = self.root / (".latest-" + uuid4().hex + ".tmp")
        _write_new(
            temporary,
            _json_bytes(
                {
                    "version": "2.0.0",
                    "run_id": snapshot.run_id,
                    "manifest_sha256": snapshot.manifest_sha256,
                }
            ),
        )
        try:
            with _directory(self.root) as root:
                os.replace(temporary.name, name, src_dir_fd=root, dst_dir_fd=root)
                os.fsync(root)
        except OSError as exc:
            raise IntegrityError(
                f"Run retained but {name} pointer publication failed"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)


class StagedRun:
    """One exclusively owned staging directory; unpublished facts remain inspectable."""

    def __init__(self, store: RunStore, run_id: str) -> None:
        self._store = store
        self.run_id = run_id
        self.path = store.root / ".staging" / run_id
        self._artifacts: list[dict[str, Any]] = []
        self._closed = False
        self._published = False
        self._lock = _json_bytes(
            {"run_id": run_id, "token": uuid4().hex, "pid": os.getpid()}
        )
        _write_new(store.root / ".publication.lock", self._lock)
        try:
            if (
                self.path.exists()
                or self.path.is_symlink()
                or (store.root / "runs" / run_id).exists()
                or (store.root / "runs" / run_id).is_symlink()
            ):
                raise PublicationConflict(f"Run ID already exists: {run_id}")
            with _directory(self.path, create=True):
                pass
        except BaseException:
            self._release()
            raise

    def __enter__(self) -> StagedRun:
        self._writable()
        return self

    def __exit__(self, *_: Any) -> None:
        self._closed = True
        self._release()

    def _release(self) -> None:
        lock = self._store.root / ".publication.lock"
        if _read(lock) != self._lock:
            raise PublicationConflict(
                "Publication lock ownership changed; explicit recovery required"
            )
        with _directory(self._store.root) as root:
            os.unlink(".publication.lock", dir_fd=root)
            os.fsync(root)

    def _writable(self) -> None:
        if self._closed or self._published:
            raise PublicationConflict("A closed or published run cannot be modified")

    @property
    def artifacts(self) -> list[dict[str, Any]]:
        """Return an independent descriptor inventory for manifest construction."""
        return deepcopy(self._artifacts)

    def _put(
        self,
        artifact_id: str,
        destination: str,
        content: bytes,
        media_type: str,
        contract: dict[str, str] | None,
    ) -> dict[str, Any]:
        self._writable()
        destination = _relative(destination)
        if not isinstance(artifact_id, str):
            raise ContractError("Artifact ID must be a string")
        if any(
            part.casefold() in _RESERVED for part in PurePosixPath(destination).parts
        ):
            raise IntegrityError("Publication metadata names are reserved")
        for existing in self._artifacts:
            previous = existing["path"]
            if previous.casefold().startswith(
                destination.casefold() + "/"
            ) or destination.casefold().startswith(previous.casefold() + "/"):
                raise PublicationConflict("Artifact file/directory identities overlap")
            for old_part, new_part in zip(
                PurePosixPath(previous).parts, PurePosixPath(destination).parts
            ):
                if old_part.casefold() != new_part.casefold():
                    break
                if old_part != new_part:
                    raise PublicationConflict(
                        "Case-folded artifact directory aliases are not portable"
                    )
            # Readers accept either ID or path, so both belong to one namespace.
            if {existing["id"].casefold(), previous.casefold()} & {
                artifact_id.casefold(),
                destination.casefold(),
            }:
                raise PublicationConflict(
                    "Artifact ID/path collides with an existing inventory entry"
                )
        descriptor = {
            "id": artifact_id,
            "path": destination,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "media_type": media_type,
        }
        if contract is not None:
            descriptor["contract"] = contract
        validate("artifact", descriptor)
        _write_new(self.path / destination, content)
        self._artifacts.append(deepcopy(descriptor))
        return deepcopy(descriptor)

    def write_json(
        self,
        name: str,
        document: dict[str, Any],
        *,
        contract: Contract,
        artifact_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate and retain JSON; prototype formats require explicit versions."""
        reference = _contract(contract, document)
        return self._put(
            PurePosixPath(name).stem if artifact_id is None else artifact_id,
            name,
            _json_bytes(document),
            "application/json",
            reference,
        )

    def copy_artifact(
        self,
        id: str,
        source: str | Path,
        destination: str,
        media_type: str = "application/octet-stream",
        *,
        contract: Contract | None = None,
    ) -> dict[str, Any]:
        """Copy explicit regular-file bytes into the staging inventory, never link."""
        content = _read(Path(source).absolute())
        reference = (
            _contract(contract, _json_object(content, str(source)))
            if contract is not None
            else None
        )
        return self._put(id, destination, content, media_type, reference)

    def publish(
        self,
        manifest: dict[str, Any],
        *,
        make_latest: bool = True,
        source_check: Callable[[], None] | None = None,
    ) -> RunSnapshot:
        """Validate, check source if supplied, write manifest last and commit once.

        Every committed publication advances latest_attempt.json. make_latest
        additionally promotes completed collections to latest.json; it never
        makes a partial/cancelled collection the last completed one.
        """
        self._writable()
        manifest = deepcopy(manifest)
        if manifest.get("run_id") != self.run_id:
            raise IntegrityError("Manifest and staging run ID disagree")
        if manifest.get("artifacts") != self._artifacts:
            raise IntegrityError(
                "Manifest artifact inventory differs from staged inventory"
            )
        documents = []
        for entry in self._artifacts:
            content = _read(self.path / entry["path"])
            if (
                len(content) != entry["size_bytes"]
                or hashlib.sha256(content).hexdigest() != entry["sha256"]
            ):
                raise IntegrityError("Staged artifact differs from its inventory")
            if "contract" in entry:
                documents.append(
                    (entry["contract"], _json_object(content, entry["path"]))
                )
        expected = {entry["path"] for entry in self._artifacts}
        actual = set()
        for path in self.path.rglob("*"):
            if path.is_symlink():
                raise IntegrityError("Symlinks are not permitted inside a staged run")
            if path.is_file():
                actual.add(path.relative_to(self.path).as_posix())
        if actual != expected:
            raise IntegrityError(
                "Unregistered or missing files in staged artifact inventory"
            )
        manifest["input_verification"] = (
            "verified" if source_check is not None else "unverified"
        )
        if source_check is None:
            manifest["limitations"] = list(manifest.get("limitations", []))
            if _NO_SOURCE_CHECK not in manifest["limitations"]:
                manifest["limitations"].append(_NO_SOURCE_CHECK)
        _validate_documents(manifest, documents)
        content = _json_bytes(manifest)
        # Finish all validation and serialization before the final current-input
        # check. A failed or accidentally list-returning checker publishes nothing.
        if source_check is not None and source_check() is not None:
            raise ContractError(
                "Source-check callback must return None or raise",
                code="INVALID_SOURCE_CHECK",
            )
        _write_new(self.path / "run_manifest.json", content)
        destination = self._store.root / "runs" / self.run_id
        if destination.exists() or destination.is_symlink():
            raise PublicationConflict(f"Run already published: {self.run_id}")
        try:
            with (
                _directory(self.path.parent) as staging,
                _directory(destination.parent) as runs,
            ):
                os.rename(self.run_id, self.run_id, src_dir_fd=staging, dst_dir_fd=runs)
                os.fsync(staging)
                os.fsync(runs)
        except OSError as exc:
            raise IntegrityError(
                "Could not atomically publish the run directory"
            ) from exc
        self._published = True
        snapshot = self._store.open_run(self.run_id)
        self._store._publish_pointer(snapshot, "latest_attempt.json")
        if make_latest and manifest["status"] == "completed":
            self._store._publish_pointer(snapshot, "latest.json")
        return snapshot
