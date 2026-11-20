# Public bounded orchestration continuation — 16 November 2026

This is a source-bound implementation slice on the existing uncommitted branch.
It is **not completion of P5/M2**, the production platform, or release acceptance.
All numbered requirements and expansion work remain in the root delivery ledger.

## Public behavior

`cppulse analyze --execution bounded` now runs isolated finite native work units,
then the existing Git/prediction/report consumers, and publishes a fresh immutable
run. It does not use the legacy archive-import operation to imply execution
provenance. The separately validated execution configuration carries requested
jobs, per-unit wall/CPU/address-space/output bounds and explicit retained work
state. Default legacy mode remains available and reports
`execution_mode=legacy, worker_limits_applied=false`.

The engine discovers all native-supported regular C++ files, retaining exclusions
and large-file skips as scope rows. It preserves native first-command selection
and header interpolation by retaining the actual full compilation database. It
does not predict libclang's transformed arguments in Python or silently fall back
when a selected database was not used. Shared working compilation databases are
hardlinked, and published input bytes are deduplicated with explicit role maps.
Native inputs/outputs and checked source copies stay outside the source root;
actual worker cwd is the source root so observed parse-context identities do not
contain a per-attempt work-directory nonce. All output/control paths are absolute.

A global finite source snapshot and separate file/parent-directory observations
are checked before/after native execution and again before publication. Native
TU primary/include buffer identities are checked against selected source and
current dependencies. Observed include dependencies enter the observed context;
raw compilation declarations and actual invocation contexts remain separate.
Changes to source, namespaces, configuration database, builtin resources or the
selected analyzer cannot become a completed current binding. Missing legacy
include-buffer identities and hidden/PCH/module/overlay/response contexts remain
unqualified; raw facts are retained rather than silently discarded.

Each actual native result retains its original ID, argv, timestamps, source,
context and output/log artifact IDs. Request/result/checkpoint and summary hashes
are linked. Post-execution metadata edits are quarantined; the exact canonical
original is retained only after its frozen digest is verified. A rejected corrupt
checkpoint is diagnostic material, not an original execution receipt. Invalid
consumer JSON is preserved untyped on failure, without promoting it into a
validated risk document or losing preceding native facts. Unpublished diagnostics
and work state remain available when publication itself cannot complete.

Manual SIGINT drains workers, publishes cancelled producer facts, stops downstream
consumers and reaches CLI exit 130. Deadline cancellation remains distinguishable
from manual interruption. Independent native failures do not erase accepted
facts from other units, and unattempted/rejected scope remains visible.

Every bounded publication, including partial/cancelled attempts, derives an
immutable-run-pinned SQLite work-unit catalog. It records native outcomes,
parse status, primary file and the snapshot's input/execution qualification.
The optional API uses `CPPULSE_WORK_UNIT_CATALOG=<store>/work-units.sqlite`,
requires a run ID plus manifest SHA, applies the existing API-key dependency,
and reads bounded, query-pinned pages without writing or creating a missing
catalog. Catalog reconstruction reads only checked immutable publication bytes;
source and worker directories may have been removed. The catalog is not an
execution or assessment authority.

## Important corrections from actual independent counterexamples

- The full-root environment's inherited builtin resource directory changed native
  arguments without being bound in the first private slice. Resources are now
  explicitly selected, content/inventory-bound, passed as argv, and protected
  from later inherited overrides. See the earlier `scale.md` record.
- A temporary header macro change restored before final content hashing changed
  actual cyclomatic complexity while the original source digest remained equal.
  The meaningful red is retained under
  `work/repairs-bounded-review/coherence-red2.log`. Separate filesystem
  observations and actual native include-buffer identities now constrain this
  case; neither is mislabeled as a complete file-manager query graph.
- A predictor writing malformed partial JSON before raising originally blocked
  failure publication. The producer receipts and the exact malformed consumer
  bytes are now retained in a partial run.
- Changed result IDs, reasons and timestamps, including a missing coordinator
  summary boundary, cannot be registered as the original receipt. Private
  checkpoint pins, previous summary pins, deterministic receipt checks and the
  final accepted-result collector all enforce this boundary.
- `__has_include` can change AST facts while `includes=[]` and all selected source
  bytes remain identical. Both ordinary and line-spliced builtin forms have
  actual clean-versus-resumed regressions. **Public unknown-closure units always
  run fresh.** The textual recognizer only restricts qualification; its absence
  cannot justify reuse. Original checkpoints remain retained as history.

## Exact source and test ownership

Main sources:

- `python/cppulse/analysis_execution.py`
- `python/cppulse/work_units.py`
- `python/cppulse/pipeline.py`
- `python/cppulse/work_unit_store.py`
- narrow opaque sidecar retention in `python/cppulse/importer.py`
- packaged private work-unit plan/summary/bindings/source-observation/checkpoint
  schemas under `python/cppulse/contracts/schemas/work_units_private/`

Public execution/history config and CLI flags are root-owned. Actual TU buffer
production and additive raw-schema support are native-owner work. Independent
coherence regressions are owned by the repairs reviewer.

Representative fresh commands (the native candidate is an immutable copied
Linux qualification slice, not all-platform acceptance):

```sh
. work/cloud-resume/environment.sh
export CPPULSE_ANALYZER=/workspace/cppulse/work/native-include-buffer-candidate/9004df27f73a73901e3c231834628c24009ffded1730e598754acd6e7c7a6373/cppulse-analyzer
export CPPULSE_WORK_UNIT_NATIVE="$CPPULSE_ANALYZER"
export MPLCONFIGDIR="$PWD/work/mpl-cache"
python -m pytest -q tests/test_analysis_execution_contracts.py \
 tests/test_analysis_execution.py tests/test_bounded_pipeline.py \
 tests/test_bounded_input_coherence.py tests/test_work_unit_runtime.py \
 tests/test_work_unit_store.py tests/test_work_unit_api.py
```

Earlier gates are historical for their precise source, and overlapping counts
must not be added:

| Evidence | Actual result | Scope boundary |
|---|---:|---|
| `work/engine-runtime.log` | 12 passed | Initial contracts/native aggregate equality/CDB inference, before later review fixes |
| `work/bounded-final-byteproof.log` | 36 passed | Initial actual TU-proof public/native slice; subsequent metadata/resume fixes supersede it |
| `work/bounded-cli-sigint.log` | 1 passed | Real first native completion, actual second-process cancellation, CLI 130, no consumers |
| `work/bounded-index-all-gate.log` | 6 passed | Normal/failed/cancelled catalog derivation and malformed CDB validation |
| `work/bounded-catalog-rebuild.log` | 29 passed | Immutable-only rebuild plus store/API gates |
| `work/bounded-unknown-closure-correct.log` | 3 passed | Actual negative-query fresh equality, conservative public restart and historical private checkpoint retention |

The final independent broad gate passed **140 tests, no skips, in 138.43 seconds**.
`review/cloud-20261116-bounded-independent-repairs-current/check.json` pins the
selected source/schema/test hashes, exact command, log hash and
`source_stable=true`. Its `output.log` contains the actual result. It includes the
real CLI signal case, ten actual coherence cases, two opaque-history archive
cases, API/catalog/rebuild, and source/resource/receipt/checkpoint regressions.
This qualifies the finite scheduling/publication slice only. Source changes during earlier gates and deliberately retained
meaningful reds are not relabeled as passing candidate qualification.

## Retained open scope

- M2-01: complete closed dependency/query identities, crash/current/latest races
  and fully qualified committed checkpoint semantics remain open.
- M2-02 / NFR-SCL-01/02: supported-host native worker bounds and independent fault
  retention are exercised slices; aggregate host budgeting, coordinator abrupt
  death/orphan recovery, other platforms and representative large workloads
  remain unqualified.
- M2-03 / NFR-SCL-03/04: public qualified warm resume, production extraction cache
  and assessment cache remain unfinished. No actual producer currently supplies
  a closed dependency/query manifest, so all public units rerun. Private
  synthetic closed-key tests are not native closure qualification.
- M2-04: richer shared/incremental Git records are separate owner work; opaque
  sidecar retention does not establish their runtime provenance or correctness.
- M2-05/06 / NFR-SCL-05: this is a work-unit summary index, not the complete
  findings/history index or efficient dashboard/MCP query model. Full migrations,
  recovery and cross-publication races remain open. Opaque RunStore material now
  streams in separate root work, but typed aggregate JSON validation and
  predictor/report compatibility consumers still load whole documents. Do not
  claim an end-to-end parent-memory bound from worker tests.
- M2-07 / NFR-SCL-08: reference 1K/10K/100K tiers, cold/warm/edit/history cases,
  CPU/peak-memory instrumentation and measured release budgets remain open.
- FR-CTX-05: native-compatible first-command selection is preserved; every extra
  compiler/target/macro/standard combination is not automatically enumerated.
- Explicit library/header-only project-kind classification and all supported
  platform/installed artifact qualification remain in the complete root plan.

No commit, push, deployment, publication or external message was performed.
