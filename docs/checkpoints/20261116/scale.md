# Scale runtime continuation — 16 November 2026

Base: `6f8b662a89b367f8c6883298dc97950150d7ba4f`, branch
`codex/cppulse-local-core-20261114`, Cloud checkout `/workspace/cppulse`.
No commits or pushes performed. This checkpoint is an implementation slice,
**not closure of P5/M2** or production qualification.

## Implemented

- New private `cppulse.work_units` runtime: retained schema-checked finite
  requests, explicit one-file native selection, source/work separation,
  canonical input/executable identities, native process receipt, invocation
  versus observed parse context, bounded streaming worker submission (1–32),
  independent process-failure retention and cancellation supervision.
- Native CPU/address-space/file-size guards are passed explicitly and only
  reported applied from the native capability document. Wall/log limits use
  the existing bounded process supervisor. CPU and peak memory measurements
  remain explicitly null.
- Checkpoints preserve the original native receipt and recheck request,
  selected source, executable and artifact bytes. An exclusive per-work-root
  lock prevents overlapping ownership. Corrupt checkpoints and interrupted
  output are explicit integrity failures requiring a fresh work root, not a
  fabricated successful resume.
- Native report scope, prototype schema/semantic checks, TU content hash,
  parse argv and receipt binding are checked before a complete result survives.
- New private `cppulse.work_unit_store`: checked extraction payload cache with
  dependency/context/native/registry/extraction-config identities and original
  immutable-run origin; separate assessment key; SQLite transactional catalog
  with immutable runs and bounded query-pinned keyset pages of work-unit
  summaries. Interrupted publication rolls back completely.
- Added tests for root separation, source/config/artifact tampering, parallel
  healthy/error units, exclusive ownership, changed receipts, invalid bounds,
  corrupt checkpoints, cache invalidation and disabled incomplete dependency
  reuse, receipt promotion rejection, immutable catalog pages and rollback.

The pre-existing runtime fixture omitted required `language_standard` and
`target` context fields. They are now explicitly `c++17`/null. Its combined
0.1-second timeout/log assertion was timing-dependent on Python interpreter
startup under parallel build load: one run retained zero bytes before timeout.
The test now independently retains exactly 97 of 100000 drained bytes and
checks a separate 0.1-second wall timeout; cancellation/process-group checks
remain. No acceptance assertion was removed.

## Verification

Initial collection could not import `cppulse.work_units`; the module was absent
at the base. Initial new implementation run found a real status mapping defect:
nonzero native exit `failed` needed the private outcome `process_error`; fixed.

The final focused suite (real native runtime + store + private draft contracts +
optional API) passed **79 tests, no skips**. See `scale-tests.log`. Ruff passed.
The adjacent `tests/test_execution.py` suite passed **48 tests** after fixing an
independent fixture race: publish `running.pid` by atomic temporary replacement
before the driver sends SIGINT. The actual SIGINT result and process cleanup
assertions remain. Isolated SIGINT runs passed twice after the fix. See
`scale-execution-tests.log`. These counts overlap no claimed whole-product gate.

Independent review by the editor-track agent found ancestor-symlink,
row/schema/byte-bound, bounded existing-cache reads and malformed-checkpoint
issues; all were corrected and regression tested. Its combined review suite
passed 78 tests before the subsequent stream-close lifecycle test. Closing the
stream now cancels pending workers, and KeyboardInterrupt drains cancelled
receipts. The final 79-test suite covers that addition.

The first generated compilation database had the wrong filename and silently
fell back. Self-review caught it: retain `inputs/compile_commands.json`, use the
explicit C++ language arguments with the clang driver, bind native's effective
`-working-directory` prefix, and exercise a real relative-include context. A
complete unit must report the database context, not pass from default flags.

The editor-track agent supplied the authenticated optional readonly
`/api/v1/work-units` route and API tests. It requires a configured catalog and
explicit run/hash pins, and does not initialize or write missing catalogs. This
route serves finite summaries; full findings/history indexing remains open.

```sh
CPPULSE_WORK_UNIT_NATIVE="$PWD/analyzer-core/build-cloud-resume/cppulse-analyzer" \
 .venv/bin/python -m pytest -q tests/test_work_unit_runtime.py \
 tests/test_work_unit_store.py tests/test_work_unit_draft_contracts.py \
 tests/test_work_unit_api.py --basetemp=work/scale-checkpoint-final
.venv/bin/python -m ruff check python/cppulse/work_units.py \
 python/cppulse/work_unit_store.py tests/test_work_unit_runtime.py \
 tests/test_work_unit_store.py
```

## Explicit remaining acceptance gaps

The native producer now retains unresolved include observations, but include
observations still do not establish dependency content closure.
**Scheduler cross-run fact reuse stays disabled.** Unknown dependencies produce no cache key/hit. Positive checkpoint
resume with a nonempty native include graph is rejected conservatively; no
runtime/test/sanitizer evidence is transferred to a changed source. The cache
primitive requires an independently complete dependency manifest; its synthetic
closed-identity tests do not qualify actual native dependency discovery.

The catalog indexes work-unit summaries, not the full findings/history model.
Public CLI/pipeline/cache integration, findings/history API/dashboard/editor/MCP
indexed queries, complete assessment cache storage, dependency closure discovery, resource-budget-derived pool sizing,
checkpoint crash recovery without a fresh work root, catalog migrations beyond
v1, current/latest publication races, streamed Git/history reuse and the required
real workload benchmark tiers remain open. Generic store shape/identity tests
are not six-project or million-line scale qualification. No speed, memory-budget
or production-ready claims are made.

## Source identities for this slice

- `python/cppulse/work_units.py`: `d5b62c347a500310de9ab79762e1b3e17097a9cbd21cc15d8ce437b00805e17d`
- `python/cppulse/work_unit_store.py`: `66c1ef205962ba31ca3fd9bc2f72738dadf0ea8d317c4b8211716c78944dba10`
- `tests/test_work_unit_runtime.py`: `44dae8b833864330e34779f15db42100679aa1ac0be24cdeec3cc9bd23740a2e`
- `tests/test_work_unit_store.py`: `a1e2808c97c97e41f114f51da37c95997a9f053ab3b9a1beafe1a01c2ffad05f`
- `tests/test_execution.py`: `30b3919bbe97fc14912acdce303ff06cae4844125718a2de1f2bee6c71833a3d`

## Root-suite environment reconciliation

The first full-root run failed five native work-unit assertions even though the
isolated 79-test slice passed. Retained pytest-72 temporary material had already
been removed by pytest retention. A fresh one-test reproduction isolated the
cause: `work/cloud-resume/environment.sh` exports `CPPULSE_CLANG_RESOURCE_DIR`.
The native CLI consumes it and appends `-resource-dir=...` to observed parse
arguments, but the work-unit request had not bound that inherited override.
The retained result reason was **Native parse arguments differ from requested
context**. This was a real missing environment-input binding, not stale source
imports or evidence that invalid output should be accepted.

The fix captures an explicit finite builtin selection during preparation,
retains a new private `resource_inputs` document (absolute external root plus
validated source snapshot), binds the native resource argument in both request
context and literal execution argv, and rechecks the entire selected builtin
inventory/content before execution, after execution and on resume. The private
document deliberately does not reuse public resource_manifest v2, whose root
semantics are workspace-relative. Later inherited overrides are masked for the
child; the original explicit selection wins. Three regressions cover retained
resource selection despite environment changes, changed builtin bytes, and a
later unselected override. On this host the actual selected tree is 241 files,
approximately 14 MiB; this is an input observation, not a performance claim.

Reproduction/final root-environment command:

```sh
. work/cloud-resume/environment.sh
python -m pytest -q tests/test_work_unit_runtime.py tests/test_work_unit_store.py \
 tests/test_work_unit_draft_contracts.py tests/test_work_unit_api.py \
 --basetemp=work/scale-root-env-final2
```

Results: **82 passed, no skips, in 30.34 seconds**.
`scale-root-environment-tests.log` records the final root-env test run.
The earlier 79-test checks remain historical for their pre-resource-fix source.

Updated affected-source hashes:
- `python/cppulse/work_units.py`: `0582b7c6a900846a59c4f56609930ae746768519ae9f2ad5e3f125d8a8299757`
- `python/cppulse/contracts/schemas/work_units_private/resource_inputs.schema.json`: `b34a852292130829f8591a02452032fa535b6d8382f7ca998faa7dac1e4b777c`
- `tests/test_work_unit_runtime.py`: `4c290e92e7d54c999a03faa62c4aae71a2b828ce8e7429e3c4aa2a4daa7660b2`
