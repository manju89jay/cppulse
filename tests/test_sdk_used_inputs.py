"""Synthetic SDK capture boundaries; these fixtures do not attest execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cppulse.identities import canonical_json_bytes, snapshot_inputs
from cppulse.run_store import RunStore
from cppulse.sdk_inputs import retain_used_sdk_inputs


def fixture(tmp_path: Path):
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    header = sdk / "stddef.h"
    data = b"typedef unsigned long size_t;\n"
    header.write_bytes(data)
    resource = {
        "version": "1.0.0",
        "root": str(sdk),
        "source": snapshot_inputs(sdk, ["stddef.h"]),
    }
    work = tmp_path / "worker"
    work.mkdir()
    resource_bytes = canonical_json_bytes(resource)
    (work / "resources.json").write_bytes(resource_bytes)
    identity = {
        "method": "libclang-tu-buffer-sha256-v1",
        "status": "available",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }
    report = {
        "metadata": {
            "analysis": {
                "native_metrics": {
                    "files": [
                        {
                            "includes": [
                                {"target": str(header), "content_identity": identity}
                            ]
                        }
                    ]
                }
            }
        }
    }
    report_path = work / "output/findings.json"
    report_path.parent.mkdir()
    raw = json.dumps(report, indent=2).encode()
    report_path.write_bytes(raw)
    request = {
        "unit_id": "unit-a",
        "work_root": str(work),
        "inputs": {
            "resource_manifest": {
                "path": "resources.json",
                "sha256": hashlib.sha256(resource_bytes).hexdigest(),
            }
        },
        "limits": {"max_artifact_bytes": 1024 * 1024},
    }
    result = {
        "outcome": "complete",
        "artifacts": [
            {
                "path": "output/findings.json",
                "id": "report-a",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        ],
    }
    execution = SimpleNamespace(
        results=[(request, result)], source={"digest": "a" * 64}
    )
    return execution, header, data, report_path


def test_captures_only_actual_used_sdk_bytes_and_deduplicates(tmp_path: Path) -> None:
    execution, header, data, _ = fixture(tmp_path)
    (header.parent / "unused.h").write_bytes(b"unused")
    request, result = execution.results[0]
    peer = {**request, "unit_id": "unit-b"}
    execution.results.append((peer, result))
    with RunStore(tmp_path / "store").begin() as stage:
        captured = retain_used_sdk_inputs(stage, execution)
        assert captured["captured_bytes"] == len(data)
        first, second = [unit["entries"][0] for unit in captured["units"]]
        assert first == second
        assert first["status"] == "available"
        descriptor = next(
            row for row in stage.artifacts if row["id"] == first["artifact_id"]
        )
        assert (stage.path / descriptor["path"]).read_bytes() == data
        assert (
            len([row for row in stage.artifacts if row["id"].startswith("sdk-buffer-")])
            == 1
        )


@pytest.mark.parametrize("change", ["bytes", "symlink", "fifo"])
def test_changed_or_unsafe_sdk_buffer_is_unknown_without_invented_bytes(
    tmp_path: Path, change: str
) -> None:
    execution, header, _, _ = fixture(tmp_path)
    if change == "bytes":
        header.write_bytes(b"different bytes")
    else:
        header.unlink()
        if change == "symlink":
            target = tmp_path / "external.h"
            target.write_bytes(b"outside")
            header.symlink_to(target)
        else:
            import os

            os.mkfifo(header)
    with RunStore(tmp_path / "store").begin() as stage:
        captured = retain_used_sdk_inputs(stage, execution)
        entry = captured["units"][0]["entries"][0]
        assert entry["status"] in {"unavailable", "mismatched"}
        assert entry["artifact_id"] is None
        assert captured["captured_bytes"] == 0


def test_changed_raw_report_refuses_sdk_capture(tmp_path: Path) -> None:
    from cppulse.errors import IntegrityError

    execution, _, _, path = fixture(tmp_path)
    path.write_bytes(path.read_bytes() + b" ")
    with RunStore(tmp_path / "store").begin() as stage:
        with pytest.raises(IntegrityError, match="report changed"):
            retain_used_sdk_inputs(stage, execution)


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"null",
        b'{"metadata":null}',
        b'{"metadata":{"analysis":{"native_metrics":{"files":[null,{"includes":[null,{"target":17}]}]}}}}',
    ],
)
def test_malformed_consumer_output_never_blocks_original_publication(
    tmp_path: Path, raw: bytes
) -> None:
    execution, _, _, path = fixture(tmp_path)
    path.write_bytes(raw)
    execution.results[0][1]["artifacts"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
    with RunStore(tmp_path / "store").begin() as stage:
        captured = retain_used_sdk_inputs(stage, execution)
        assert captured["captured_bytes"] == 0
        assert not any(row["id"].startswith("sdk-buffer-") for row in stage.artifacts)


def test_checked_sdk_reader_indexes_once_and_shares_identical_header_bytes(
    tmp_path: Path,
) -> None:
    from cppulse.sdk_inputs import load_used_sdk_proof, read_used_sdk_buffers

    execution, _, _, report_path = fixture(tmp_path)
    request, result = execution.results[0]
    request["source_digest"] = execution.source["digest"]
    peer = {**request, "unit_id": "unit-b"}
    execution.results.append((peer, result))
    resource_bytes = (Path(request["work_root"]) / "resources.json").read_bytes()
    report = json.loads(report_path.read_bytes())
    with RunStore(tmp_path / "store").begin() as stage:
        retain_used_sdk_inputs(stage, execution)

        class Retained:
            manifest = {"artifacts": stage.artifacts}
            reads: dict[str, int] = {}

            def read_bytes(self, identifier: str) -> bytes:
                self.reads[identifier] = self.reads.get(identifier, 0) + 1
                descriptor = next(
                    row for row in self.manifest["artifacts"] if row["id"] == identifier
                )
                return (stage.path / descriptor["path"]).read_bytes()

        snapshot = Retained()
        proof = load_used_sdk_proof(snapshot)
        observed = [
            read_used_sdk_buffers(
                snapshot,
                unit_id=row["unit_id"],
                request=row,
                result=result,
                resource_manifest_bytes=resource_bytes,
                report=report,
                proof=proof,
            )
            for row in (request, peer)
        ]
        assert len(observed[0]) == len(observed[1]) == 1
        assert next(iter(observed[0].values())) is next(iter(observed[1].values()))
        assert all(count == 1 for count in snapshot.reads.values())
        assert len(snapshot.reads) == 2


def test_legacy_opaque_sdk_inventory_never_becomes_checked_bytes() -> None:
    from cppulse.sdk_inputs import read_used_sdk_buffers

    class Legacy:
        manifest = {"artifacts": [{"id": "sdk-used-inputs", "size_bytes": 1}]}

        def read_bytes(self, identifier: str) -> bytes:
            raise AssertionError(
                "Opaque legacy proof must not be interpreted as current proof"
            )

    assert (
        read_used_sdk_buffers(
            Legacy(),
            unit_id="unit-a",
            request={},
            result={},
            resource_manifest_bytes=None,
            report=None,
        )
        == {}
    )
