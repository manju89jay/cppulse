# Independent bounded-to-measured bridge review

Current selected actual-publication and adversarial controls: **12 passed**, no
skips, 31.02s (`bridge-current.log`). The SDK extension was still being edited,
so this intermediate log is not a source-stable final candidate claim.

Durable tests live in `tests/test_work_unit_analysis_review.py` and
`tests/test_sdk_inputs_review.py`. The original actual two-TU publication and
retained raw/derived snapshots remain under `work/coherence-review2/`.

Retained meaningful counterexamples and repairs:

- A public two-TU run attempted nested derivation while holding the publication
  lock. The parent moved derived publication after the outer staging context.
- A consistently repinned original-receipt graph could change runtime argv
  while inheriting the old invocation context. The bridge kernel now compares
  retained invocation argv/cwd/compiler/provenance with the original receipt
  and request. Independent argv and cwd controls pass.
- One successful unit could retain an available global-duplication zero after
  a declared peer became missing. The metric kernel now requires complete
  declared global scope, original successful units and all peer inventories
  before global duplicate counts can remain available. Missing, truncated and
  unverified-scope controls pass independently of health documents.
- The metric contract accepted duplicate source lines exceeding physical LOC.
  The parent added the per-file/context available-count invariant.

Read-only review also identified malformed native-output risks in the initial
SDK capture helper before a red reproduction was run. The parent added defensive
decoding. Five independent real-file/synthetic malformed-report controls preserve
raw output and original result bytes and capture no invented SDK buffers.

These checks establish finite local consistency, not producer authentication,
SDK dependency closure, calibrated accuracy, global memory budgets, qualified
warm reuse or full production acceptance. All changes remain uncommitted.

## Current source-bound final review gate

The final selected gate passed **87 tests**, no skips, 70.73s, with reviewed
producer/kernel/scorer/store source, every v2/private work-unit schema and test
fixtures unchanged before/after. Exact command, hashes and **18 actual immutable
run-manifest pins** are in `final-bridge-check.json`; output is in
`final-bridge-tests.log`. Black, Ruff and scoped diff checks passed.

The six actual SDK controls use genuine compilation databases and the current
native binary. `__stddef_size_t.h` obtains checked retained SDK bytes and default
scorer-v4 health100. Actual `stddef.h` retains bytes but remains unverified with
null health because its inactive `__has_include_next` query is outside the finite
profile. Altered or omitted SDK proof roles cannot retain a qualified parse.
Copied exact selected manifests/contracts/raw reports and authored fixture source
are pinned by `actual-sdk-artifacts.json`; complete original stores remain under
`work/coherence-review2/final-bridge-tmp/`.

Streaming query controls also cover CR/LF/CRLF splices across1MiB raw-read
boundaries and an operator spanning2MiB of removed continuations. Harmless normal
line continuation is qualified without waiving actual preprocessing queries.

Two preliminary actual-SDK logs are retained transparently: the first fixture
omitted a compilation database and incorrectly expected a health artifact before
explicit unknown-health publication existed. The next used a fallback context
and incorrectly expected the inferred opt-in to qualify fallback. The final
fixture uses a genuine CDB; buffer, numerical and unknown assertions were
preserved. These fixture errors are not claimed as production defects or as a
qualified SDK-marker bypass counterexample. Genuine prior invocation/global
scope/duplicate-line reds remain separate above.

This finite review does not close M4-01, full P3/P5 or any full acceptance item.
It does not establish universal preprocessing closure, qualified reuse, large-run
memory budgets, calibrated detector accuracy, other platforms or production
completion. All new changes remain uncommitted.
