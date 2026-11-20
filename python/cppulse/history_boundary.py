"""Keep optional Git tooling outside the static-analysis import boundary."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

from cppulse.contracts import validate
from cppulse.errors import ContractError


def mine_optional_history(
    repo: Path, output: Path, *, options: dict[str, Any] | None = None
) -> int:
    """Mine history when installed, otherwise retain explicit unavailable scope.

    Operational failures from an available miner remain failures. Missing tooling
    never creates file-level history rows, ownership claims or ranking evidence.
    """
    disabled = options is not None and options.get("enabled") is False
    missing = []
    if not disabled and shutil.which("git") is None:
        missing.append("Git executable")
    if not disabled and importlib.util.find_spec("git") is None:
        missing.append("GitPython")
    if not disabled and not missing:
        from cppulse.git_miner.main import run

        if options is None:
            return run(repo, output)
        kwargs: dict[str, Any] = {
            "szz_max_fix_commits": options["szz_max_fix_commits"],
            "history_options": {
                key: options[key]
                for key in (
                    "max_commits",
                    "max_record_bytes",
                    "max_cache_bytes",
                    "timeout_seconds",
                )
            },
        }
        if options["cache_dir"] is not None:
            kwargs["history_options"]["cache_dir"] = options["cache_dir"]
        if options["behavior_config"] is not None:
            kwargs.update(
                behavior_config=Path(options["behavior_config"]),
                behavior_cutoff=options["behavior_cutoff"],
            )
        return run(repo, output, **kwargs)
    if any(
        (output / name).exists() or (output / name).is_symlink()
        for name in ("git_history.json", "git_behavior.json")
    ):
        raise ContractError(
            "History output contains retained rich sidecars; select a fresh output "
            "directory rather than mix unavailable history with prior results"
        )
    document = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": str(repo.resolve()),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "commit_range": "unavailable",
            "total_commits": 0,
            "history_status": "unavailable",
            "limitations": [
                (
                    "History explicitly disabled by invocation or project configuration."
                    if disabled
                    else "Optional history tooling unavailable: "
                    + ", ".join(missing)
                    + ". Install cppulse[git] and a Git executable to enable history; "
                    "static analysis remains available."
                )
            ],
        },
        "file_metrics": [],
        "knowledge_silos": [],
    }
    validate("git_metrics", document, version="prototype_v1")
    output.mkdir(parents=True, exist_ok=True)
    (output / "git_metrics.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    return 0
