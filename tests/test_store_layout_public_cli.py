"""Public migration/export preserve selected snapshots and refuse in-place export."""
import json
from pathlib import Path
import pytest
from cppulse.cli import main
from cppulse.run_store import RunStore
from test_run_store_v2 import publish


def test_public_upgrade_export_preserves_both_heads(tmp_path: Path, capsys) -> None:
    store = RunStore(tmp_path / "store", format_version="2.0.0")
    publish(store, "completed")
    publish(store, "partial", status="partial")
    pins = [
        store.resolve_latest().manifest_sha256,
        store.resolve_latest_attempt().manifest_sha256,
    ]
    assert main(["store-layout", "upgrade", "--store", str(store.root)]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == "3.0.0"
    destination = tmp_path / "legacy"
    assert (
        main(
            [
                "store-layout",
                "export-v2",
                "--store",
                str(store.root),
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["scope"] == "explicit_offline_v2_snapshot"
    exported = RunStore.open_existing(destination)
    assert exported.format_version == "2.0.0"
    assert [
        exported.resolve_latest().manifest_sha256,
        exported.resolve_latest_attempt().manifest_sha256,
    ] == pins
    assert (
        main(
            [
                "store-layout",
                "export-v2",
                "--store",
                str(store.root),
                "--destination",
                str(store.root),
            ]
        )
        == 2
    )
    capsys.readouterr()
    assert store.resolve_latest().manifest_sha256 == pins[0]


@pytest.mark.parametrize("flag", ["--expected-lock-sha256", "--expected-lock-token"])
def test_inspect_partial_pin_refuses_before_open(tmp_path: Path, flag: str) -> None:
    absent = tmp_path / "absent"
    assert (
        main(["store-recovery", "inspect", "--store", str(absent), flag, "a" * 64]) == 2
    )
    assert not absent.exists()


def test_capabilities_advertise_explicit_store_boundary(capsys) -> None:
    assert main(["capabilities"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert "store-layout" in value["commands"]
    assert value["store_formats"]["default_write"] == "3.0.0"
    assert value["store_formats"]["legacy_write"] == "explicit_2.0.0_non_atomic"
