# Independent profile 1.2 review — 16 November 2026

Reviewed `python/cppulse/policy_extensions.py`, its contract semantic validator,
review hash schema changes, focused runtime/contract/presentation tests and two
packaged example policies. No policy implementation files were edited by this
reviewer.

Fresh independent command:

```sh
PYTHONPATH=python .venv/bin/python -m pytest -q tests/test_policy_extensions_contract.py tests/test_policy_extensions_runtime.py tests/test_policy_profile12_presentation.py
```

Result before reviewer feedback: **77 passed**, one third-party Starlette/AnyIO deprecation warning.
This is a focused runtime/contract/presentation gate, not production or actual
native metric-producer acceptance.

The review predicate compares selected required artifact IDs and exact SHA-256
claims to the manifest, checks current source digest, attestation origin, no
execution receipt, configured reviewer ID, selected file/job scope, past review
and recording times and unexpired expiry. Missing legacy hashes remain unknown.
Contract checks bind reviewed IDs to the evidence record's retained artifact IDs
and reject hash keys outside the reviewed set. Failed eligible decisions remain
failed despite an incomplete quorum; declared IDs are explicitly not authenticated
people. Deviation fixture correction retains an independent unresolved-control
rejection test.

Numeric evaluation uses rational values, stays per file/job, rejects conflicting
or incomplete symbol inventories for positive results and preserves decisive
partial breaches only where additional values cannot reverse them. Actual
producer/schema/installed integration and wider producer/platform matrices still
need their independent gates.

Finding sent to implementation owner: the organization example initially selected
one evidence ID while requiring two distinct reviewer IDs. Because each uniquely
identified evidence record has one reviewer, that example could never pass.
Requested two explicit evidence record IDs and a semantic impossible-quorum check
against evidence-ID count. Owner resolved this with two selected evidence IDs and semantic rejection of a
quorum greater than selected evidence records. Independent rerun after the
correction passed **79 tests**, with the same third-party warning.

Domain packs still require authorized edition-specific standards text and
qualified mapping review. These tests do not establish reviewer authenticity,
standards conformance, certification or full M5/P4 closure.
