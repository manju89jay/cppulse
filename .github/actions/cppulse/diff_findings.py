#!/usr/bin/env python3
"""Compute the diff between base and head findings.

Prints the number of NEW findings (in head but not in base).
Uses (file_basename, rule_id) as the matching key for fuzzy comparison,
since line numbers shift between commits.

Usage:
    python3 diff_findings.py base_findings.json head_findings.json
    # Prints: 5  (number of new findings)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _finding_key(finding: dict) -> tuple[str, str]:
    """Create a fuzzy matching key for a finding."""
    file_basename = Path(finding.get("file", "")).name
    rule_id = finding.get("rule_id", "")
    return (file_basename, rule_id)


def count_new_findings(base_path: str, head_path: str) -> int:
    """Count findings present in head but not in base."""
    try:
        with open(base_path) as f:
            base = json.load(f)
        with open(head_path) as f:
            head = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0

    base_keys: dict[tuple[str, str], int] = {}
    for finding in base.get("findings", []):
        key = _finding_key(finding)
        base_keys[key] = base_keys.get(key, 0) + 1

    new_count = 0
    for finding in head.get("findings", []):
        key = _finding_key(finding)
        if base_keys.get(key, 0) > 0:
            base_keys[key] -= 1
        else:
            new_count += 1

    return new_count


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: diff_findings.py <base.json> <head.json>", file=sys.stderr)
        sys.exit(1)

    count = count_new_findings(sys.argv[1], sys.argv[2])
    print(count)
