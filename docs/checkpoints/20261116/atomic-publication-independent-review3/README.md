# Independent atomic publication review, current repair

Reviewed source and fixtures were unchanged before/after the exact command in
`final-check.json`: **22 passed, no skips, 51.21s**. Seven actual retained run
manifests and original request-bound native binary SHA9004df27… are pinned.
The native check reads the actual executable and agrees with every selected
original request. Review used the same existing Cloud checkout; no source was
committed or pushed.

The reviewed path uses one owned stage for original raw facts, SDK proof,
explicit staged read projection, typed normalization and health, followed by one
final publication. The projection exposes no published RunSnapshot identity,
path or manifest hash. The actual owned-child SIGKILL control pauses at the
normalization boundary; concurrent readers and post-kill readers retain the
previous complete run and both exact pointer bytes. The original expected-red
proof remains in `../atomic-publication-independent-review/`.

Independent review found two additional API-consistency defects and retained
meaningful failures before repair:

- A replaced publication-lock token was rejected by projection reads but accepted
  by final publish, allowing a writer without current lock ownership to promote
  its run. The final writer now checks its exact token around qualification and
  promotion boundaries.
- Direct construction of a projection accepted caller-invented verified metadata
  without the validating/source-checking stage factory. Construction now requires
  the supported factory path. This is an internal API invariant, not a claim of
  authentication against hostile Python code in the same interpreter.

The final gate covers both repairs, changed appended-artifact rejection, all
11 projection controls, the actual process-death visibility regression and six
actual SDK/link controls. Actual genuine CDB/builtin headers preserve verified
health100; actual unsupported stddef.h queries retain unknown/null results.
The tests do not alter the original receipt, fabricate an aggregate invocation,
waive source/SDK guards or recompute stored client scores.

Scope remains finite. Safe recovery of the dead owner's retained lock/stage,
interruption between the two individually atomic pointer-file promotions,
whole-parent memory, full configurations, qualified warm reuse and representative
large tiers remain separate acceptance work. This review does not close all
M2-01/M2-05/NFR-SCL-06 or production acceptance.

`retained-facts.json` maps selected copied contracts/manifests/barrier observations
to original retained stores. Original workspaces, receipts, logs, failed stages
and complete stores remain under the recorded work paths. `files.json` binds this
compact export. Durable tests are `tests/test_atomic_projection_review.py` and
`tests/test_bounded_atomic_publication_review.py`; the implementation owner made
all production changes.
