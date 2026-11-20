# Interpreting retained and current results

A run records collection status independently of its assessment gate. Completed
collection can contain an observed build/test failure. A newer partial or
cancelled attempt must not be replaced by an older apparent success. Retained
historical views remain available but make no new source-freshness claim.

For each result retain the source digest, job and observed parse contexts,
manifest SHA-256, rule/scorer/policy versions, original artifact hashes and
reasons. Headers parsed using inferred arguments are not proof of an actual
consumer configuration. Runtime evidence applies to the selected executed
instrumented binary and workload; a supplied upstream report does not establish
consumer application verification. Checksums identify bytes, not authenticity.

Controls are passed, failed, unknown or explicitly not applicable. Unknown
required evidence blocks acceptance, and known required failures take precedence
over incomplete evidence. A high average cannot override a blocking control.
Zero tests, entirely skipped tests, missing/stale coverage, unsupported reports,
uninstrumented binaries and empty sanitizer logs do not establish success.
Self-declared reviewer IDs do not authenticate reviewers or independence.

The current CLI exit contract is:

| Exit | Meaning |
|---:|---|
| 0 | Requested operation completed; for check/assess, gate passed |
| 1 | Known check/assessment gate failure |
| 2 | Invalid input or operational failure preventing a usable requested result |
| 3 | Incomplete analysis/evidence |
| 130 | Explicit cancellation |

Analyze may report violations with successful collection; use the matching check
for enforcement. Report rendering has its own exit and does not change the
stored gate. Missing optional PDF/web/ML should not block deterministic JSON/HTML
core use. Missing native runtime blocks new native analysis, while a supported
retained historical view may still be readable.

When health is unavailable, explain the missing scope/context instead of
inventing 100. Measured complexity is distinct from severity or finding counts.
Experimental ranking is not calibrated defect probability. Trends with different
source scopes, scorer/policy versions or context prerequisites need an explicit
compatibility decision; do not silently connect incompatible points.
