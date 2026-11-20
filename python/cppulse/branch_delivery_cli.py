"""Local-only branch command adapter; no provider or shared CLI dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from cppulse.branch_delivery import (
    analyze_branch_delivery,
    collect_branch_graph,
    validate_config,
    validate_report,
)
from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes

MAX_CONFIG_BYTES = 512 * 1024


def _read_config(path: Path) -> tuple[bytes, dict[str, Any]]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CONFIG_BYTES:
            raise ContractError("Configuration must be a regular file within 512 KiB")
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ContractError("Configuration exceeds 512 KiB")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in values:
            if key in result:
                raise ContractError("Duplicate JSON configuration key: " + key)
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ContractError("Non-finite JSON configuration value: " + value)

    document = json.loads(
        raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant
    )
    validate_config(document)
    return raw, document


def _write(directory: Path, name: str, value: bytes) -> None:
    descriptor = os.open(
        directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _new_output(output: Path, repo: Path, config: Path) -> Path:
    output = Path(os.path.abspath(output))
    # Reject symlink ancestors, including otherwise harmless aliases: a retained
    # result must name the actual explicit destination, not redirect through one.
    for parent in [output, *output.parents]:
        if parent.is_symlink():
            raise ContractError("Output path contains a symbolic link")
    resolved_repo = repo.resolve(strict=True)
    if output == resolved_repo or resolved_repo in output.parents:
        raise ContractError("Output must be outside the source repository")
    metadata = resolved_repo / ".git"
    protected = [resolved_repo]
    if metadata.is_file():
        descriptor = os.open(metadata, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            data = stream.read(4097)
        if len(data) > 4096 or not data.startswith(b"gitdir: "):
            raise ContractError("Linked worktree metadata is unsupported or oversized")
        metadata = (resolved_repo / data[8:].decode("utf-8").strip()).resolve()
    if metadata.exists():
        protected.append(metadata.resolve())
        common = metadata / "commondir"
        if common.exists():
            descriptor = os.open(common, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                data = stream.read(4097)
            if len(data) > 4096:
                raise ContractError("Git common directory reference exceeds bound")
            protected.append((metadata / data.decode("utf-8").strip()).resolve())
    if any(output == path or path in output.parents for path in protected):
        raise ContractError("Output overlaps source or Git metadata")
    if output == config.resolve(strict=True) or output in config.resolve().parents:
        raise ContractError("Output conflicts with configuration input")
    output.mkdir(mode=0o700)  # Exclusive; never clean or replace prior evidence.
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture bounded local Git branch facts; caller delivery claims remain unverified"
    )
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = None
    try:
        raw, config = _read_config(args.config)
        output = _new_output(args.output, args.repo, args.config)
        _write(output, "config.original.json", raw)
        _write(output, "config.json", canonical_json_bytes(config))
        capture = collect_branch_graph(args.repo, config)
        _write(output, "capture.json", canonical_json_bytes(capture))
        report = analyze_branch_delivery(config, capture)
        validate_report(report, config=config, capture=capture)
        _write(output, "report.json", canonical_json_bytes(report))
        cancelled = any(row["status"] == "cancelled" for row in capture["commands"])
        status = 130 if cancelled else 0 if report["graph_status"] == "available" else 3
        artifacts = {}
        for name in (
            "config.original.json",
            "config.json",
            "capture.json",
            "report.json",
        ):
            content = (output / name).read_bytes()
            artifacts[name] = {
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        receipt = {
            "version": "1.0.0",
            "exit_code": status,
            "graph_status": report["graph_status"],
            "meaning": "local graph availability only; no provider delivery or policy approval",
            "artifacts": artifacts,
        }
        _write(output, "outcome.json", canonical_json_bytes(receipt))
        print(
            json.dumps(
                {
                    "output": str(output),
                    "exit_code": status,
                    "graph_status": report["graph_status"],
                }
            )
        )
        return status
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        status = 2
        diagnostic = {
            "exit_code": status,
            "error": type(error).__name__,
            "message": str(error)[:2000],
        }
    except KeyboardInterrupt:
        status = 130
        diagnostic = {
            "exit_code": status,
            "error": "cancelled",
            "message": "Interrupted; existing evidence was retained",
        }
    if output is not None:
        try:
            _write(output, "error.json", canonical_json_bytes(diagnostic))
        except OSError as retention_error:
            diagnostic["retention_error"] = str(retention_error)[:1000]
    print(json.dumps(diagnostic), file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
