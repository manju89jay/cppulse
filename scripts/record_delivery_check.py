"""Execute an explicit local check and retain source-bound, immutable evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def source_files(root: Path, selections: list[str]) -> dict[str, str]:
    """Hash tracked and nonignored source files only in selected work packages."""
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=root
        )
        .decode("utf-8")
        .split("\0")
    )
    selected = [Path(name).as_posix().rstrip("/") for name in selections]
    if not selected or any(
        Path(name).is_absolute() or ".." in Path(name).parts for name in selected
    ):
        raise ValueError("Select at least one checkout-relative source file/directory")
    result: dict[str, str] = {}
    for name in sorted(set(names)):
        if not name or not any(
            name == part or name.startswith(part + "/") for part in selected
        ):
            continue
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Source binding refuses a symlink/outside path: {name}")
        if path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result:
        raise ValueError("No source files matched the requested check scope")
    return result


def record_check(
    root: Path, command: list[str], sources: list[str], evidence: Path, timeout: float
) -> dict[str, Any]:
    """Run literal argv and reject a passing claim if its source changed mid-run."""
    if not command or timeout <= 0:
        raise ValueError("A finite positive timeout and explicit command are required")
    evidence = evidence.resolve()
    if not evidence.is_relative_to((root / "review").resolve()):
        raise ValueError("Check evidence must be a new directory under review/")
    if any(path.is_symlink() for path in [evidence, *evidence.parents]):
        raise ValueError("Evidence directory cannot follow symlinks")
    before = source_files(root, sources)
    evidence.mkdir(parents=True, exist_ok=False)
    log = evidence / "output.log"
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    interrupted = False
    with log.open("xb") as stream:
        try:
            child = subprocess.run(
                command,
                cwd=root,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            exit_code = child.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
        except KeyboardInterrupt:
            exit_code = 130
            interrupted = True
        except OSError as exc:
            stream.write(str(exc).encode("utf-8", errors="replace"))
            exit_code = 2
    after = source_files(root, sources)
    stable = before == after
    status = (
        "passed"
        if exit_code == 0 and stable
        else "cancelled" if interrupted else "stale" if not stable else "failed"
    )
    result = {
        "check_id": evidence.name,
        "command": command,
        "cwd": str(root),
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.monotonic() - clock,
        "status": status,
        "exit_code": exit_code,
        "source_files": before,
        "source_stable": stable,
        "source_files_after": after if not stable else None,
        "log": str(log.relative_to(root)),
        "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        "qualification": "Only the explicit command and selected source scope were checked; this is not a whole-product or platform qualification.",
    }
    (evidence / "check.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    """Record one explicit local check; never infer completion from a plan."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        result = record_check(ROOT, command, args.source, args.evidence, args.timeout)
        print(
            json.dumps(
                {
                    key: value
                    for key, value in result.items()
                    if key not in {"source_files", "source_files_after"}
                },
                indent=2,
            )
        )
        return 3 if result["status"] == "stale" else result["exit_code"]
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
