#!/usr/bin/env python3
"""Validate pipeline JSON outputs against their schemas."""

import json
import sys
from pathlib import Path

CHECKS = [
    ("docs/schemas/findings.schema.json", "output/findings.json"),
    ("docs/schemas/git_metrics.schema.json", "output/git_metrics.json"),
    ("docs/schemas/risk_scores.schema.json", "output/risk_scores.json"),
    ("docs/schemas/roadmap.schema.json", "output/roadmap.json"),
]


def main() -> int:
    import jsonschema

    failed = False
    for schema_path, data_path in CHECKS:
        try:
            with open(schema_path) as s, open(data_path) as d:
                jsonschema.validate(json.load(d), json.load(s))
            print(f"PASS: {data_path}")
        except jsonschema.ValidationError as e:
            print(f"FAIL: {data_path} — {e.message}")
            failed = True
        except FileNotFoundError as e:
            print(f"SKIP: {e.filename} not found")
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
