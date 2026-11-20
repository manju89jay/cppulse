# Shared checked Git history Cloud continuation

Implementation continues uncommitted in `/workspace/cppulse` on
`codex/cppulse-local-core-20261114`, HEAD
`6f8b662a89b367f8c6883298dc97950150d7ba4f`. The earlier behavior/policy source
checkpoints remain historical evidence, not claims about this later source.
No implementation commit, push, remote-ref update or external message occurred.

## Implemented slice and interfaces

FR-GIT-02 / M2-04 now have a shared checked raw producer and durable local
checkpoint implementation. See `docs/contracts/git-history.md` and the private
`git_history_private` schemas. `history_cache.py` spools bounded Git records,
validates/hash-checks accepted SQLite records and checkpoints, and builds a
shared disk-backed current-file rename projection. The miner, silo summaries,
SZZ, behavior and metadata consumers use that scan once per pipeline invocation.
They do not independently materialize full histories. Miner/silo date aggregation
uses scalar extrema/counts; SZZ selects commit IDs and bounds actual blame output.

`run(..., history_options={...})` accepts the agreed five cache/budget keys.
Public history settings remain separate from native extraction settings. Root
coordinator integration owns effective configuration/CLI/history boundary and
capture of the new sidecars. `git_history.json` is diagnostic history metadata,
not a fabricated execution receipt or primary native/runtime evidence contract.
Optional behavior keeps its own versioned calculation and configuration identity.
`scan_history(..., revision=fullSHA)` supports graph consumers without checking
out code or changing refs.

Warm/append views reuse only structurally valid complete raw records. Rewrites,
changed shallow boundaries and producer/extraction profiles select new views;
current filename/deletion projection is rediscovered. Alias/window/cutoff changes
recompute behavior rather than reusing a stale aggregate. Missing/corrupt raw
objects are recollected; corrupt checkpoint inventories are rebuilt. Pending
revision selection and raw transactions never become accepted records.

The cache byte budget uses actual file size and actual SQLite page size, not an
assumed 4096-byte page. Qualified DELETE journaling, actual before/after input
identities, finite per-command capture/wall limits and generation invalidation
are explicit. Larger file/history/platform budgets remain separate qualification.

## Review-found defects and preserved regressions

The independent ABI/history reviewer reproduced seven material issues and
retained the original scripts/proof JSON before owner repairs:

1. Existing 8192-byte SQLite pages bypassed a budget computed with 4096.
2. Raw scan failure triggered an unbounded fallback metadata traversal.
3. Working-tree attributes changed clean output while warm facts stayed stale.
4. Inherited Git root/index/object overrides redirected selected inventory.
5. Repository fsmonitor configuration executed project code during discovery.
6. Disabled/unavailable requests left old optional positive sidecars next to new output.
7. An inherited reference trace wrote an additional file.

Repairs validate actual cache bytes before mutating pragmas, fail raw collection
operationally without fallback output, pin commit-tree attributes and explicit
`info/attributes`, bind selected repository environment, supervise bounded
inventory and disable fsmonitor/hooks/lazy-fetch/trace effects. Incompatible old
sidecars and symlinks are preserved and refused before writes. Public
unavailable-history branches enforce the same refusal.

Original counterexamples/review inventory are under
`work/history-independent-abi/`; independent source-bound checks are under
`review/cloud-20261116-history-independent-abi-v2/` and later recorded rechecks.
Export scripts, JSON proofs and logs only: **do not export fixture `.git`
directories or synthetic Git objects/commits**.

## Executed checks

These are overlapping gates, not additive totals:

- Owner raw cache/behavior/inventory gate: **69 passed** in 36.52 seconds,
  `history-logs/owner-69.log`. It includes three **actual SIGKILL** recovery
  scenarios: after two durable accepted records, inside raw SQLite acceptance,
  and during final checkpoint publication. Each resumed result equals clean.
- Final independent source-bound gate including the deterministic timeout fixture:
  **75 passed**, no skips, exit 0 and `source_stable:true`; receipt
  `history-logs/independent-75-check.json` (original
  `review/cloud-20261116-history-independent-abi-v3/check.json`). Exact combined
  statement/branch coverage for the two reviewed history modules is **84%**;
  this differs from the extended component statement-coverage scope below.
- A later extended coverage run exposed a test-fixture race: a real fast Git
  process can exit before the first poll under a one-microsecond deadline.
  The reviewer replaced that timing assumption with an actual owned slow
  executable under a finite wall budget. The test is retained, stronger and
  independently passed. Production timeout behavior was not weakened.
- Final required extended component/coverage gate: **159 passed**, no skips,
  25.03 seconds; aggregate component statement coverage **89%**. Exact log:
  `history-logs/component-159.log`. This includes the deterministic timeout fixture.
  The earlier 158-pass/one-fixture-failure log is retained as
  `history-logs/component-timeout-fixture.log`, not a green result.

Required extended component command from `git-miner`:

```sh
../.venv/bin/python -m pytest -v --cov=src --cov=cppulse.git_miner tests/ ../tests/test_git_history_cache.py ../tests/test_git_inventory_boundary.py ../tests/test_git_behavior.py
```

The test sets cover cold/warm/append, rewritten branches, rename/current deletions,
delete/recreate baseline behavior, shallow deepening, bounds expansion, record and
checkpoint corruption, explicit info-attribute invalidation, callback mutation,
capacity exhaustion/recovery, protected cache paths, immutable revision selection,
shared producer reuse, real hooks/environment overrides, and output refusal.

## Pinned real-input proof

`git-history-evidence.json` records current source hashes, environment, canonical
producer profile/checkpoint, artifact hashes and three measured runs over real
fmt at `e69e5f977d458f2650bb346dadf2ad30c5320281`:

| Case | Recorded commits | Current C++ files | Extracted | Reused | Wall seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cold | 100 | 67 | 100 | 0 | 5.799 |
| Warm | 100 | 67 | 1 | 99 | 1.109 |
| Independent clean reference | 100 | 67 | 100 | 0 | 6.442 |

The warm retry is **intentional**: the known shallow boundary's unavailable
parent delta is not promoted to a complete cache hit. All three results remain
partial, expose that boundary, and have identical semantic Git-metric digests.
The proof checks source stability before/after. Runtime resource observations use
Linux `wait4` for the foreground Python miner and waited children; maximum RSS
is not an aggregate concurrent process-tree peak. There is one observation per
case, not a benchmark distribution, performance superiority claim or release budget.

## Remaining acceptance

This does not close whole M2/P5/P6. The required 1K/10K/100K file and growing-history
workloads, repeated resource budgets, in-flight Git parent-death cleanup, hard
aggregate process-tree resources, all supported Git/platform/version combinations,
complete cross-branch rename lineage and function/symbol history remain open.
Ordered commit IDs are still traversed for a new append/rewrite view; raw fact
extraction is incremental, not a constant-time history append guarantee.

The private cache is local derived state with content/key consistency, not
producer authentication or an organization access-control boundary. Immutable
primary report artifacts retain their own source/run pins. A flat output
directory is not a multi-reader atomic run protocol.
