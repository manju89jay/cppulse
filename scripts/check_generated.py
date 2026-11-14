#!/usr/bin/env python3
"""Check or explicitly regenerate local registry documentation and config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from cppulse.tooling import check_generated, generated_files  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Check by default, or rewrite only declared generated files with --write."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="regenerate declared files"
    )
    args = parser.parse_args(argv)
    if args.write:
        rendered = generated_files()
        # Preflight all paths before changing any file; generated documents must
        # not redirect writes through a checkout symlink.
        for relative in rendered:
            output = ROOT / relative
            if any(path.is_symlink() for path in (output, *output.parents)):
                sys.stderr.write(f"Refusing symlink generated output: {relative}\n")
                return 1
        for relative, content in rendered.items():
            output = ROOT / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding="utf-8")
    mismatches = check_generated(ROOT)
    if mismatches:
        sys.stderr.write("Stale generated files:\n" + "\n".join(mismatches) + "\n")
        return 1
    print("Generated registry reference and native configuration are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
