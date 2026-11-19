# Bounded original-unit normalization and full declared scope

This continuation implements a finite P5→M4 integration slice, not completion of
M2, M4, P5, or the full production specification. All changes remain uncommitted.

`work_unit_analysis.py` replays immutable publication material, without opening
original source/work directories or executing a producer. It verifies the full
plan/source scope, summary pins, original request/result bytes, original receipt,
invocation identity and input/output role pins. Per-unit selected source,
configuration, compilation database and resource hash inventory remain separate
roles. It does not fabricate `execution_facts`, recipes, receipts, successful
parse attempts, or cache reuse.

Public v2 `analysis_scope` retains every selected unit, including unstarted,
rejected, excluded and failed files. Genuine per-unit `analysis_inventory`,
`observations` and `analysis_metrics` documents refer to original receipts through
`work_unit_analysis_binding`. Global declared analysis grouping is an inferred
context distinct from each actual invocation and native-observed parse context.
The contract kernel checks these links separately from the existing standalone
recipe/`execution_facts` route.

Duplication is computed once across the complete declared token-stream scope;
missing streams remain unavailable. Each unit receives those global counts,
preventing per-unit comparisons from inventing a zero for duplicate peers.
The maintenance producer and kernel use the separate full declared scope;
missing execution or measurement cannot turn a successful subset into a score.
The measured scorer remains `analyzed-kloc-context-v4`. Fallback parse context
stays unqualified even with `--allow-inferred-parse`; that option applies only to
actual inferred recorded compilation commands with verified TU buffers.

Bounded publication derives typed analysis and conservative measured health after
the raw publication transaction closes, then rebuilds the catalog for the final
returned run. Nested publication originally caused a real lock conflict; the
meaningful red is retained in `work/bridge-public-first.log`. The derive now runs
outside the original staged-run context. All original artifact bytes and receipt
identities remain retained through derived publications.

An independent pure-kernel review found that consistently repinning a changed
receipt argv could leave the old invocation context accepted. The kernel now
requires exact retained invocation argv, cwd, compiler and observed provenance.
The independent durable counterexample is in
`tests/test_work_unit_analysis_review.py`; the repaired initial two-test gate is
`work/bridge-review-argv-fixed.log` (2 passed, 20.40 seconds).

The initial actual producer/publication gate passed 14 tests in 26.37 seconds:
`work/bridge-public-third.log`. This includes a real recorded one-TU compilation
database with measured health 100, fallback health remaining null, two genuine
native receipts, immutable replay after original source/work locations disappear,
full-scope absent-unit representation and changed-link rejection. The preceding
broader gate passed all 20 existing bounded-pipeline tests, with one incorrect new
fallback-score expectation rejected; that expectation was corrected to preserve
existing fallback semantics and a separate actual recorded-command positive was
added. No acceptance requirement was reduced.

Additional finite memory guards cap unique retained input bytes and total raw
report bytes at 256 MiB each, with control metadata capped at 64 MiB. Shared
compilation database, registry and resource inventory byte strings are deduplicated
by retained artifact identity rather than copied per unit. These guards do not
establish an end-to-end coordinator memory bound: typed JSON validation,
compatibility predictor/report consumers and full representative scale budgets
remain unfinished.

SDK hash inventories alone do not constitute retained header bytes. Until actual
used SDK bytes are retained and checked against original TU buffer identities,
external include contexts remain unverified and health remains null. A separate
root-owned used-SDK-byte extension is in progress; this checkpoint does not claim
it has passed. Qualified warm reuse also remains unfinished: unknown-closure
public units continue to execute fresh.

Fresh current combined tests, source/artifact pins, SDK extension qualification,
installed artifacts, API/dashboard/MCP/editor agreement and the full acceptance
ledger must be checked after the combined source stabilizes. Historical counts
above apply only to their named commands and source epochs.

## Actual used SDK byte continuation

The root-owned SDK producer now retains only actual observed SDK include bytes,
with exact raw report JSON and original resource inventory pins in a distinct
`used_sdk_inputs` document. These bytes do not become project source files.
The normalized binding identifies the checked SDK proof when external bytes are
used. The parser-resource hash inventory by itself remains insufficient.
Normalization loads and indexes that proof once per invocation and shares a
bounded content cache across units, avoiding repeated full proof parsing.
Older untyped private SDK proof artifacts remain readable as unqualified history.

The first actual SDK gate exposed two concrete gaps, preserved in
`work/bridge-actual-sdk-first.log`: the coordinator rejected every ordinary line
continuation, including a size_t header guard, and unverified runs omitted an
explicit null health document. The streaming coordinator scanner now joins
logical continuations before detecting dynamic query markers while retaining
actual split-query and chunk-boundary regressions. Unverified typed derivations
now include a conservative v4 null calculation without promoting their input
verification or manufacturing available metric values.

The repaired actual gate passed **2 tests in 27.04 seconds**, retained in
`work/bridge-actual-sdk-second.log`:

- Actual selected builtin `__stddef_size_t.h` bytes and a recorded compilation
  command yield `buffer_coherence=verified`, matched context and measured v4
  health 100 for the clean authored primary source.
- Actual selected builtin `stddef.h` bytes remain retained, but its conservative
  `__has_include_next` restriction keeps the context unverified and health null.
  No SDK byte evidence is silently equated with a closed file-manager query graph.

A separate actual two-file duplicate-source check passed in
`work/bridge-actual-dup.log`: each file has **66 duplicate tokens**, computed across
both genuine native units rather than a per-unit zero. This does not qualify
large-scale duplication performance or detector accuracy.

The final combined source-bound gate is recorded under
`work/bridge-sourcebound/`. Its `check.json`, when complete, contains the exact
command and exit status, before/after source hashes, log digest, immutable native
binary digest and explicit remaining acceptance limitations. Consult that result
rather than treating the earlier iterative counts as final candidate validation.

## Frozen combined verification and final annotation delta

The combined gate completed **75 passed, no skips, in 483.96 seconds**, with
`source_stable=true` and the immutable native binary digest
`9004df27f73a73901e3c231834628c24009ffded1730e598754acd6e7c7a6373`.
Its exact argv and before/after hashes are in
`bounded-typed-analysis-evidence/broad-75/check.json`. Statement-plus-branch
coverage for the two new modules is **81% combined**: producer 85%, kernel 74%.
This is not an 80% per-file coverage claim and is not whole-program coverage.
The traced JSON-schema-heavy command took about eight minutes; its runtime is
verification overhead, not a production benchmark or measured release budget.

The only subsequent production change fixes type imports/annotations and uses
an explicit integer-plus-not-boolean byte-budget predicate to satisfy lint. The
current-source focused gate passed **10 tests in 32.67 seconds**, no skips,
`source_stable=true`, including both actual SDK controls, runtime resolution of
public type annotations, invalid byte budgets and malformed/nonfinite/deep JSON.
Exact current hashes are in
`bounded-typed-analysis-evidence/current-10/check.json`; Ruff passed on both new
modules and their producer test file. The retained earlier lint failures are not
relabeled as current success.

`bounded-typed-analysis-evidence/manifest.json` inventories two complete compact
immutable actual SDK snapshots, including original receipts, raw native output,
retained source/input roles, actual used SDK bytes, normalized facts and health.
They can be read without the original source/work directory. The positive clean
case records numeric health 100; the conservative query case records null and
unverified input binding. No Git fixture objects or refs are included.

The independent reviewer separately records 87 passing checks with stable source
in `work/coherence-review2/final-bridge-check.json`; these overlap the above gates
and must not be added together. Installed candidate, complete client agreement,
full dependency/query closure, warm reuse, cross-publication atomicity, large
scale and the remaining full-plan requirements remain governed by the root
ledger. In particular, raw→typed→health derivation is multiple immutable
publications: CLI/catalog pin the final run, but transient latest-pointer exposure
of an intermediate raw run is not a qualified atomic end-to-end journey.
