# Source-stable full root integration baseline

Actual command: `.venv/bin/python -m pytest -q tests --basetemp /tmp/cppulse-post-v3-root-integration`.

Result: **3327passed,18warnings,907.70seconds,exit0**. No skipped tests reported. Exact source hashes before/after were equal; minimum free space4,642,127,872bytes; owned-process disk guard did not trigger. The wrapper's literal argv, timestamps, source hashes, resource observations and log are preserved in `post-v3-root-evidence/`. Original fixtures remain in `/tmp/cppulse-post-v3-root-integration`; do not reuse that basetemp for another run.

This includes the current public v3 migration/export/recovery/capabilities changes and the previously repaired finding/repair/policy/prototype-schema integration failures. API25 and installed8b9763 checks are separately recorded, not counted into this3327. Native149 belongs to its recorded Release source/artifact epoch.

The independent producer→contract timestamp regression was reproduced separately under work/ and was intentionally not hidden inside this passing root suite. Production private frozen-input timestamp/schema repair and its new regressions follow this baseline; this run must not be represented as a full-suite pass for later source bytes. Full P14, scale, cache qualification, unfinished M8/M9 and unavailable platform/human gates remain open.
