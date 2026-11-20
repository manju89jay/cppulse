# Independent parsed-input qualification review

The independent post-fix selected gate passed **69 tests**, no skips, 11.58s,
with the exact source hashes unchanged before/after (`current-check.json`).
This gate covers synthetic unsupported closure variants, current policy marker,
inferred opt-in, measured health and opaque streaming controls. It is a selected
review observation, not full production acceptance or end-to-end memory proof.

An actual Clang19 C++23 `#embed` counterexample changed a static assertion from
passing to a parse error when only an embedded binary byte changed. Both native
reports retained identical primary-source SHA and **empty includes[]**. The
normalizer had classified this unsupported closure as verified. `embed-red.log`
retains the meaningful failing control. The parent fixed conservative preprocessing
`embed` recognition before the 69-test passing gate. No embedded dependency closure
or warm-cache qualification is claimed.

A second actual invalid `-std` probe failed TU creation and emitted a native
measurement row with null source-buffer digest and empty includes. The pure
binding helper nevertheless returned matched (`direct-failed-red.log`). The parent repaired this by requiring an observed analyzed/partial TU before
buffer coherence can qualify. The full normalizer regression preserves a readable
failed row and unavailable metrics; no failed-AST buffer qualification is accepted.

All changes remain uncommitted. The full 187-item delivery verifier remains
incomplete; original scope and meaningful failures are preserved.

The final independent gate passed **83 tests**, no skips, 16.77s, with reviewed
source hashes unchanged (`final-check.json`). The durable 16-regression set is
`tests/test_native_include_binding_review.py`; both meaningful prior reds remain
retained. Ruff, Black and scoped diff checks passed. This closes these two
identified defects within the finite current profile, not full-plan acceptance.
