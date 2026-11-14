# Native finding regression demo

Run from the repository with the recorded local toolchain enabled:

```sh
source review/environment.sh
PYTHONPATH=python .venv/bin/python scripts/demo_findings.py
```

The input is a small, clearly labeled synthetic C++17 project. GCC, CMake,
CTest, libclang and the native cppulse analyzer actually execute. Collection,
baseline creation, finding checks and SARIF export use the public Python CLI.
Every capture records cleanup of its own generated build/report directories
before rebuilding; source inputs and historical runs are preserved.

The script writes `output/findings-demo/latest-demo.json`, pointing to a fresh
batch containing the exact requests, command arguments, captured streams,
immutable run/hash pins, `summary.json` and `line-shift.sarif.json`.

| Change | Finding check | Meaning |
| --- | --- | --- |
| Unchanged source | Passed, exit 0 | The selected complete native facts match the baseline. |
| Two blank lines inserted | Passed, exit 0 | The native line-sensitive fingerprint changes; the unique exact byte-line anchor matches. The compilation database stays byte-identical. |
| Selected header changed before recollection | Insufficient, exit 3 | Old observations cannot be reused for changed inputs. |
| Full cold recollection after the header change | Passed, exit 0 | New commands and facts replace reliance on the stale capture. |
| One additional unique allocation | Failed, exit 1 | One known new selected rule occurrence exceeds the explicit zero-new allowance. |
| An allocation line repeated verbatim | Insufficient, exit 3 | Both occurrences remain visible; the repeated anchor is ambiguous. |
| Allocations in `a/same.cpp` and `b/same.cpp` | Failed, exit 1 | Canonical paths preserve both findings despite equal basenames. |
| Compiler flag changed | Insufficient, exit 3 | Different observed parse contexts are not silently compared as equivalent. |
| Ordinary source rename | Insufficient, exit 3 | The database/context changes. Adding a rename map does not waive that difference. |
| Explicit single-file rename between predeclared database paths | Passed, exit 0 in the verified local batch | The actual retained parse-context digests match. The script does not rewrite arguments and would require unknown if those contexts differ. |

For a short interview walkthrough, open the baseline and shifted check results
first: one occurrence remains unchanged although its source line number moves.
Then show the known-new failure and repeated-anchor unknown result. Change the
selected header and point out the new partial attempt with exit 3, followed by
the fresh full collection. Finally open the SARIF artifact: its native UTF-8
byte column is converted using the retained source bytes to a Unicode codepoint
column and checked against the official SARIF 2.1.0 schema.

These are experimental rule observations and exact scoped comparisons, not an
accuracy, production-readiness or safety benchmark. Anchors do not normalize
whitespace, tokens, arbitrary renames or compiler configurations. This demo
performs full recollection and does not implement incremental analysis.

Fresh local verification on 2026-11-14 completed all 24 public CLI commands with
the expected exits: 17 returned 0, two returned 1 and five returned 3. The actual
native UTF-8 byte column was 30 and the SARIF codepoint column was 29. The compact
result is `review/autonomous/logs/s7-actual-native-findings-audit.json`; the full
batch is `output/findings-demo/batches/cfe93927ff6a4666bdd9cc487e164ff1/summary.json`.
These paths describe this workspace's verification, while the command above
creates a new batch rather than reusing those results.
