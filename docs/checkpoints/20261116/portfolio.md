# Local portfolio source checkpoint — 16 November 2026

Implemented the private configuration/report/state contracts and shared local
producer in `python/cppulse/portfolio.py`. Public CLI integration is owned by the
coordinator and calls this producer; no separate scoring or scheduler is implied.

## Verified source slice

- Explicit trusted authorized roots and exact per-project run/manifest pins.
  Read-only checked stores preserve independent project facts when another pin
  is corrupt/unavailable; latest-pointer movement does not redirect selection.
- Per-project source/scope, contexts, run times, measured-health documents and
  original artifact/scorer hashes. No cross-project health average.
- Goal comparisons require exact scorer/profile/calibration, source-file scope
  and required contexts, plus completed verified historical collection and full
  measured health. Unverified/partial/missing/incompatible data remains unknown.
  Observed met/unmet is explicitly historical, never current-source acceptance.
- Dated, nonoverlapping declared project/team assignments with retained history.
- Explicit finite daily local ticks with installed TZif-byte identity binding,
  spring-forward skips, first-fold autumn selection, configured catch-up window,
  pending retries across midnight, retry exhaustion and local-only outcomes.
- Atomic directory-relative POSIX journal/report publication with writer lock,
  no overwrite of different report bytes, idempotent recovery after interrupted
  final state, corruption/lost-journal denial and existing report hash checks.
- Output directories cannot overlap selected immutable stores in either
  direction. Replay time cannot borrow a run that finished after that cutoff.

These describe a local implementation slice, not complete M8/P10 acceptance.
No provider identity, branch/task/cost/notification integration, tenant access
control, daemon installation or external delivery exists here.

## Commands/results

Contract-first suite initially failed collection because the runtime module did
not exist. Later invariant checks reproduced tampered-delivery/journal issues;
a meaningful pending-retry midnight regression failed before its scheduling fix
(`portfolio-retry-red.log`). No acceptance check was skipped or deleted.

Final source command:

```sh
PYTHONPATH=python .venv/bin/python -m pytest -v --basetemp=/workspace/cppulse/work/portfolio-pytest-final-bindings tests/test_portfolio.py
```

**34 passed in 13.93s**, retained `portfolio-tests.log`. Black, Ruff and
`git diff --check` passed. The suite uses real persisted RunStores with explicitly
synthetic controlled contracts, plus actual local artifact publication. A shared
pytest-numbering setup collision affected an earlier run before tests executed;
separate basetemp resolved it without changing acceptance behavior.

## Actual native/store/local delivery integration

`work/portfolio-actual-reviewed/verify.py` reads three actual retained stores with
explicit configured roots: native-clean, native-findings and an unverified
consumer archive. `portfolio-actual-reviewed.json` binds all selected pins, source
module/schema/test SHA-256 values and actual artifact checksums.

At actual observed UTC `2026-11-16T15:21:12.729326+00:00`:

- Native clean measured health 100: historical goal observed_met.
- Native finding measured health 45.45454545454545: observed_unmet against 100.
- Unverified consumer: unknown, no borrowed/legacy positive health.
- One actual scheduled local JSON delivery succeeded. Repeating the tick emitted
  no new outcome and preserved every output byte. No project command or network
  call was made by the producer.

Reproduce with a new output directory using the retained config and explicit
as-of clock; do not overwrite prior artifacts. The earlier `portfolio-actual.json`
is an initial draft run before the future-cutoff guard and is superseded for
current acceptance by `portfolio-actual-reviewed.json`; it is not current-source
proof and must not be relabeled.

A separate source resource observation (`portfolio-resources.json`) measured one
three-project build plus one local tick: 2.175800545 wall seconds, 2.164008465 CPU
seconds, Linux process peak RSS 30,027,776 bytes. Wall/CPU exclude imports; peak
RSS includes them. This single observation is not a benchmark, regression budget,
representative scale result or installed-artifact qualification.

## Remaining gates

Coordinator owns installed public CLI/scenarios and exact-candidate packaging.
Independent review and any resulting repairs must remain tied to their source
bytes. M8 still requires complete team/fragmentation views, real provider/project
access, branch/task/delivery semantics, issue-tracker cost distinctions, configured
external scheduling/report/notification outcomes and wider product/release/user/
platform qualification. Missing provider access/choices and external-effect
approval stay named blockers, not silently removed requirements.

## Independent review follow-up

The reviewer reproduced a standalone projection gap: contexts/hashes could be
altered while a historical goal persisted. Current projections retain exact
original manifest and health JSON bytes. The validator verifies SHA-256,
descriptor/type/size, parsed-value, context and source-limit bindings. Passing
expected_config additionally anchors project/run pins, goals, team history and
health selection to the trusted request. Both the producer and repeated-success
readback do so. Byte integrity is not producer authentication.

Independent recheck passed **36 tests** (34 source plus two then-current CLI
checks), including seven fresh report mutations, at portfolio SHA-256
`5abb6affd156ec48c8eadefffcc330fac6bf4451f9a9919ac27df40181ba3f81`.
The corresponding report is `portfolio-independent-review.md`. The separate
CLI no-op exhausted-delivery exit finding is coordinator-owned and must be
rechecked against its subsequent change; it is not closed by this source gate.

Immutable configuration-generation JSON and active-job-count/next-retry outputs
preserve prior goal/team settings and make waiting failures visible. Output
budgets mark excess project projections unavailable rather than dropping other
projects. The intermediate `portfolio-actual-final.json` also predates these
review repairs; only `portfolio-actual-reviewed.json` is current source proof.

Current-source resource observation (`portfolio-resources-reviewed.json`) measured 8.990850662999947 wall seconds, 4.744397758 CPU seconds and 31182848 Linux process peak RSS bytes for one build plus one tick. Scope/limits are unchanged: post-import wall/CPU, peak includes imports, one observation, no budget/scale/installed claim.

Coordinator CLI follow-up: independent five-case public CLI recheck passed;
`portfolio-cli-review.log` retains results. The one-event exhausted fixture
explicitly sets lookback_days=1 while preserving the count assertion. Active
failed/exhausted current-generation jobs retain exit 2 even on a no-op. Explicit
empty replay time is rejected and relative output roots use absolute lexical
normalization without symlink resolution. The earlier pending CLI finding is
closed in this source scope; exact installed candidate qualification remains
coordinator-owned.
