"""A derived byte check must not confer original source verification."""

import pytest

from cppulse.errors import ContractError, InputChanged
from cppulse.run_store import RunStore
from test_contracts_v2 import manifest_document, source_document
from test_run_store_v2 import publish


def candidate(store, material_check, *, source_check=None):
    with store.begin("candidate") as stage:
        artifact = stage.write_json("source.json", source_document(), contract="source")
        manifest = manifest_document()
        manifest.update(run_id="candidate", artifacts=[artifact])
        return stage.publish(
            manifest, material_check=material_check, source_check=source_check
        )


@pytest.mark.parametrize("version", ["2.0.0", "3.0.0"])
def test_byte_material_guard_does_not_claim_original_source_verified(tmp_path, version):
    store = RunStore(tmp_path / "cache", format_version=version)
    events = []
    snapshot = candidate(store, lambda: events.append("material"))
    assert events == ["material"]
    assert snapshot.manifest["input_verification"] == "unverified"
    assert store.resolve_latest().run_id == "candidate"


@pytest.mark.parametrize("version", ["2.0.0", "3.0.0"])
@pytest.mark.parametrize("exception", [InputChanged, KeyboardInterrupt])
def test_failed_or_interrupted_material_guard_leaves_previous_heads(
    tmp_path, version, exception
):
    store = RunStore(tmp_path / "cache", format_version=version)
    old = publish(store, "old")

    def changed():
        assert not (store.root / "runs/candidate/run_manifest.json").exists()
        raise exception("selected original artifact changed")

    with pytest.raises(exception):
        candidate(store, changed)
    assert store.resolve_latest().manifest_sha256 == old.manifest_sha256
    assert store.resolve_latest_attempt().manifest_sha256 == old.manifest_sha256
    assert not (store.root / "runs/candidate").exists()
    assert (store.root / ".staging/candidate/source.json").is_file()
    assert not (store.root / ".publication.lock").exists()


@pytest.mark.parametrize("result", [False, True, 0, [], {}])
def test_non_none_material_return_is_not_a_successful_check(tmp_path, result):
    store = RunStore(tmp_path / "cache")
    old = publish(store, "old")
    with pytest.raises(ContractError, match="Material-check"):
        candidate(store, lambda: result)
    assert store.resolve_latest().manifest_sha256 == old.manifest_sha256


def test_original_source_check_remains_last_and_sole_verification_authority(tmp_path):
    store = RunStore(tmp_path / "cache")
    events = []
    snapshot = candidate(
        store,
        lambda: events.append("material"),
        source_check=lambda: events.append("source"),
    )
    assert events == ["material", "source"]
    assert snapshot.manifest["input_verification"] == "verified"
