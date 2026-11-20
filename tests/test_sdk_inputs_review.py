"""Independent used-SDK capture degradation controls over real retained files."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cppulse.identities import canonical_json_bytes, snapshot_inputs
from cppulse.sdk_inputs import retain_used_sdk_inputs


class Stage:
    """Record only writes issued by the capture helper."""

    def __init__(self) -> None:
        self.written: dict[str, bytes] = {}

    def _put(
        self, identifier: str, path: str, content: bytes, media_type: str, contract: Any
    ) -> None:
        assert identifier not in self.written
        self.written[identifier] = content

    def write_json(
        self, path: str, document: dict[str, Any], *, contract: str, artifact_id: str
    ) -> None:
        assert artifact_id not in self.written
        self.written[artifact_id] = canonical_json_bytes(document)


@pytest.mark.parametrize(
    "payload",
    [
        b"{not JSON",
        b"null",
        b"[]",
        b'{"metadata":[]}',
        b'{"metadata":{"analysis":{"native_metrics":{"files":[null,{}]}}}}',
    ],
)
def test_invalid_raw_reports_never_abort_sdk_capture_or_manufacture_bytes(
    tmp_path: Path, payload: bytes
) -> None:
    sdk = tmp_path / "sdk"
    (sdk / "include").mkdir(parents=True)
    (sdk / "include/stddef.h").write_bytes(b"// retained SDK header\n")
    resource = {
        "version": "1.0.0",
        "root": str(sdk),
        "source": snapshot_inputs(sdk, ["include/stddef.h"], inventory_complete=True),
    }
    work = tmp_path / "work"
    (work / "output").mkdir(parents=True)
    resource_bytes = canonical_json_bytes(resource)
    (work / "resource-inputs.json").write_bytes(resource_bytes)
    (work / "output/findings.json").write_bytes(payload)
    request = {
        "unit_id": "unit-a",
        "work_root": str(work),
        "inputs": {
            "resource_manifest": {
                "path": "resource-inputs.json",
                "sha256": hashlib.sha256(resource_bytes).hexdigest(),
            }
        },
        "limits": {"max_artifact_bytes": 1024 * 1024},
    }
    result = {
        "outcome": "invalid_output",
        "artifacts": [
            {
                "id": "raw-output-a",
                "path": "output/findings.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    before = deepcopy(result)
    stage = Stage()
    document = retain_used_sdk_inputs(
        stage, SimpleNamespace(results=[(request, result)], source=resource["source"])
    )
    assert document["captured_bytes"] == 0
    assert all(
        entry["status"] != "available"
        for unit in document["units"]
        for entry in unit["entries"]
    )
    assert (work / "output/findings.json").read_bytes() == payload
    assert result == before
    assert set(stage.written) == {"sdk-used-inputs"}
