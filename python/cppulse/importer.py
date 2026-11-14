"""Archive existing flat pipeline output as an explicitly unverified v2 snapshot.

Importing old output cannot retroactively prove which source bytes were analyzed.
No builds, Git commands, shell commands or policy evaluation execute here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from cppulse import __version__
from cppulse.compatibility import read_prototype_document, read_risk_scores
from cppulse.errors import InputChanged
from cppulse.identities import digest_json, snapshot_inputs
from cppulse.run_store import RunStore


def import_pipeline(
    data: Path,
    source_root: Path,
    store_root: Path,
    *,
    kind: str = "application",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Retain four original documents and a conservative normalized risk view."""
    data, source_root = data.resolve(), source_root.resolve()
    started = datetime.now(timezone.utc).isoformat()
    documents = {}
    original_digests = {}
    for name in ["findings", "git_metrics", "risk_scores", "roadmap"]:
        content = (data / f"{name}.json").read_bytes()
        original_digests[name] = hashlib.sha256(content).hexdigest()
        document = json.loads(content)
        documents[name] = read_prototype_document(name, document)
    metadata = documents["findings"]["metadata"]
    recorded_root = Path(metadata["repo_path"])
    if not recorded_root.is_absolute() or recorded_root.resolve() != source_root:
        raise ValueError(
            "Import source root must match the producer's absolute repository path"
        )
    inventory = metadata.get("analysis", {}).get("files")
    if inventory is None:
        raise ValueError("Import requires an explicit native source inventory")
    inputs = [entry["path"] for entry in inventory if entry["status"] != "excluded"]
    subject = snapshot_inputs(source_root, inputs, kind=kind, inventory_complete=False)
    normalized = read_risk_scores(documents["risk_scores"], allow_prototype_v1=True)
    store = RunStore(store_root)
    with store.begin(run_id) as stage:
        for name in documents:
            entry = stage.copy_artifact(
                name,
                data / f"{name}.json",
                f"legacy/{name}.json",
                "application/json",
                contract=(name, "prototype_v1"),
            )
            if entry["sha256"] != original_digests[name]:
                raise InputChanged(f"Import artifact changed while copying: {name}")
        stage.write_json(
            "normalized/risk_scores.json",
            normalized,
            contract="risk_scores",
            artifact_id="normalized-risk",
        )
        for name, media_type in [
            ("report.pdf", "application/pdf"),
            ("report.html", "text/html"),
            ("report.json", "application/json"),
            ("analyzer.log", "text/plain"),
            ("effective_config.json", "application/json"),
        ]:
            if (data / name).is_file():
                stage.copy_artifact(
                    name.replace(".", "-"), data / name, name, media_type
                )
        manifest = {
            "version": "2.0.0",
            "run_id": stage.run_id,
            "status": "completed",
            "source": subject,
            "contexts": [],
            "stages": [
                {
                    "id": "archive-import",
                    "status": "passed",
                    "depends_on": [],
                    "reason": "Original producer claims retained; no analysis or compilation was rerun.",
                }
            ],
            "artifacts": stage.artifacts,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "config_digest": digest_json(
                {"operation": "archive-import", "format": "prototype_v1", "kind": kind}
            ),
            "versions": {"cppulse": __version__, "input_format": "prototype_v1"},
            "limitations": [
                "Import completed, not source analysis: source bytes were inspected after the original run and cannot establish its historical source binding.",
                "No compiler contexts are reconstructed from legacy labels.",
                "Normalized legacy health/evaluation remain unverified; importing artifacts is not a policy pass.",
            ],
        }
        snapshot = stage.publish(manifest)
    snapshot.verify()
    for name, document in documents.items():
        if snapshot.read_json(name) != document:
            raise AssertionError(f"Archive changed original {name}")
    return {
        "run_id": snapshot.run_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "store": str(store.root),
        "input_verification": snapshot.manifest["input_verification"],
        "operation": "archive-import",
        "artifact_count": len(snapshot.manifest["artifacts"]),
    }


def main() -> None:
    """Import one explicit local pipeline bundle without upgrading its claims."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument(
        "--kind",
        choices=["application", "library", "header-only"],
        default="application",
    )
    parser.add_argument("--run-id")
    args = parser.parse_args()
    print(
        json.dumps(
            import_pipeline(
                args.data, args.source, args.store, kind=args.kind, run_id=args.run_id
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
