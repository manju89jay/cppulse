# Independent optional-history and public-interface review — 16 November 2026

Reviewed `history_boundary.py`, dependency-extra changes, pipeline import
boundary, maintenance CLI dispatch/capabilities, focused tests and
`scripts/verify_installed.py`. Reviewer did not change those implementation files.

Fresh command:

```sh
PYTHONPATH=python .venv/bin/python -m pytest -q tests/test_optional_history.py tests/test_maintenance_cli.py tests/test_installed_cli.py
```

**10 passed**, 14 third-party pandas/matplotlib parsing deprecation warnings.
The history boundary checks executable and optional package availability before
importing the miner, retains unavailable metadata and empty history rows, and
preserves operational failures of an available miner. GitPython moved to a git
extra and remains in dev for component tests. Numeric/dataframe dependencies
remain core: this change does not claim complete minimization of that footprint.

Read back actual installed-final strict no-Git artifacts. Git metadata says
history unavailable with both executable and GitPython missing; ranked file rows
are empty; clean.cpp and intentional.cpp each remain unranked with missing_history
reasons. The installed verifier retains scope via ranked/unranked disjoint union,
keeps intentional findings and clean counterexamples, checks original summary
arithmetic and loader/report/optional-runtime behavior outside source imports.
Its hand-calculated weighted health formula is explicitly historical
attempted-file scoring, not acceptance of the new measured context scorer.

Two findings sent to root:

1. Maintenance CLI initially returned 0 and only new run/hash pins even when a
   required context made measured aggregate health unavailable. Requested clear
   availability/overall output and incomplete exit 3 (or explicit documented
   publication-only semantics) plus a real incomplete-context CLI regression.
   Keep the resolution associated with its later source/test evidence.
2. The strict no-Git verifier should explicitly assert unavailable history,
   empty ranking and missing_history reasons, in addition to scope union.
   The observed current candidate already meets those invariants; making them
   executable prevents a future fabricated ranking from passing this lane.

Actual final installed MCP and clean-agent skill checks are documented separately.
No OS/compiler/platform, complete P1/P3/P8/P9 acceptance or release claim follows
from these focused checks. Current source changes after this review require
rechecking their affected behaviors and exact candidate bytes.

Follow-up source inspection confirmed both requested changes: maintenance CLI now
emits the retained aggregate, scorer and consumer-assurance fields and returns 3
when overall is null. A real normalized fixture with missing-consumer required
context verifies that behavior. Strict installed verifier now asserts unavailable
history, no ranked files and missing_history reasons. Recheck exact candidate
bytes after incorporating these changes.

Measured dashboard review found another actionable contract mismatch: the new
component used `symbol_id` while analysis_metrics v2 requires `symbol`; its test
also invented availability `measured` instead of schema `available`. This hides
actual function identities and prevents filtering by real symbols. Sent to root
for correction with contract-real fixtures. Stored numeric values were copied
without score recalculation. The HTML template already uses the actual symbol
field and copies context LOC/category values. Requested those denominators and
context/aggregate limitations in dashboard presentation as well.
