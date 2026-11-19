"""Independent staged ownership and final validation controls."""

from pathlib import Path

import pytest

from cppulse.errors import IntegrityError, PublicationConflict
from cppulse.run_store import RunStore
from test_contracts_v2 import source_document
from test_run_store_v2 import publish
from test_staged_read_projection import manifest


def test_projection_refuses_replaced_writer_lock(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    with store.begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        view = stage.project(manifest(stage))
        lock = store.root / ".publication.lock"
        original = lock.read_bytes()
        lock.write_bytes(b'{"run_id":"different-owner"}')
        try:
            with pytest.raises(PublicationConflict, match="ownership"):
                view.read_bytes("source")
            with pytest.raises(PublicationConflict, match="ownership"):
                view.verify()
        finally:
            lock.write_bytes(original)


def test_final_publish_checks_appended_bytes_and_preserves_previous_pointers(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "store")
    baseline = publish(store, "baseline")
    pointers = {name: (store.root / name).read_bytes() for name in ("heads.json",)}
    with store.begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        view = stage.project(manifest(stage))
        stage.write_json(
            "second.json", source_document(), contract="source", artifact_id="second"
        )
        view.verify()
        (stage.path / "second.json").write_bytes(b"changed after checked prefix")
        with pytest.raises(IntegrityError):
            stage.publish(manifest(stage))
        assert stage.path.is_dir()
        assert (
            stage.path / "second.json"
        ).read_bytes() == b"changed after checked prefix"
        assert not (store.root / "runs/candidate").exists()
    for name, raw in pointers.items():
        assert (store.root / name).read_bytes() == raw
    baseline.verify()


def test_final_publish_refuses_lost_writer_lock_before_any_visibility(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "store")
    publish(store, "baseline")
    pointers = {name: (store.root / name).read_bytes() for name in ("heads.json",)}
    with store.begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        stage.project(manifest(stage))
        lock = store.root / ".publication.lock"
        original = lock.read_bytes()
        lock.write_bytes(b'{"run_id":"different-owner"}')
        try:
            with pytest.raises(PublicationConflict):
                stage.publish(manifest(stage))
            assert not (store.root / "runs/candidate").exists()
            for name, raw in pointers.items():
                assert (store.root / name).read_bytes() == raw
        finally:
            lock.write_bytes(original)


def test_checked_projection_requires_stage_factory_not_caller_metadata(
    tmp_path: Path,
) -> None:
    from cppulse.errors import ContractError
    from cppulse.run_store import StagedReadProjection

    with RunStore(tmp_path / "store").begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        forged = manifest(stage)
        forged["input_verification"] = "verified"
        # The supported factory performs validation and qualifies source only
        # through its explicit callback; a constructor cannot skip that gate.
        with pytest.raises((TypeError, PublicationConflict, ContractError)):
            StagedReadProjection(stage, forged)
        checked = stage.project(manifest(stage))
        assert checked.manifest["input_verification"] == "unverified"
