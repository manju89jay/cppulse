# Reviewer-fix integration and fresh Cloud verification

This record preserves the original reviewer-fix intake and its observations.
See the [current branch policy and checkpoint](../CODEX_CLOUD_HANDOFF.md) for
present publication status.

This three-task batch from the 20 November 2026 audience review was exercised
in a fresh Linux x86_64 Cloud workspace. All 187 canonical definitions remain
unchanged across 118 requirements, 60 M0–M9 tasks, nine obligations and P0–P14.
The ledger remains at 38 verified, 96 open, 51 active and 2 blocked. Those
38 rows retain historical acceptance and still need a genuine affected-evidence
refresh for changed source. HUMAN-USEFULNESS and ENV-MATRIX remain blocked.

## Histories and deliberate integration

The source base is master `d1e598028aec76f6455a7ed45602945274b72f8d`, tree
`2629467e843a46aabc976fb1c118f74cc0267e67`, identical to the previously tested
Cloud baseline `e5b6db6da16b8f567c0fb21aa00f1d17739a4938`. The second proposed
merge parent is
main `82120d26b51f99b64068f9d66f6e000fcaee97c2`; merge base is
`3945825be8dcff2e3cb0fa2ec11174854a09c85e`. At intake, main was default. The proposed
integration branch is `codex/reviewer-fixes-20261120`. Receiving-host verification
uses a detached checkout of the pinned master with the exact handoff applied.

A no-commit manual merge carrier preserves both histories without materializing
96MB of historical generated main-side data under an exhausted disk budget.
That carrier initially used the tested tree; every main-only path is explicitly
classified in the owned integration manifest before qualification. The final
proposed tree must be independently checked, not accepted as a wholesale choice
of one side. The source handoff records its exact tree/index and file bodies.

| Main-side intent | Resolution |
| --- | --- |
| Shallow Git boundary recovery | Keep the already identical canonical `cppulse.git_miner.commit_utils` and tested compatibility wrappers/regression; no duplicate legacy implementation |
| Missing WeasyPrint native libraries | Keep existing canonical public RuntimeError/503 behavior and wrapper; no PDF readiness claim |
| lodash4.18.1 update | Registry version, tarball and integrity matched main. The tested dashboard graph retains Tailwind dependencies; locked install, tests and production build ran on the receiving host |
| PDF link, stale output, UTF8, module invocations | Conditional actual PDF link, stale-PDF removal after new JSON production, canonical installed module calls, UTF8 output. Architecture's invalid0x97 byte converted without corrupting valid UTF8 |
| ADR007 density scores/checker/CI | Preserve formula/checker/results in pinned historical main history and label ADR007 historical. Current measured-context prerequisites/empty unknowns and shared CI checks remain; never apply legacy empty100 arithmetic to current results |
| Native profile flag | Explicit legacy `--profile` overrides the validated scoring-profile field before analysis and warns that the native component performs no scoring or implicit detector filtering. Enable detectors through explicit per-rule configuration; actual scoring uses the public pipeline. Config errors remain errors even with an override. Omission preserves tested discovery/defaults |
| Generated paths | Retain main's heuristic classification, but list the files and explicit native exclusion reasons instead of silently removing declarations from inventory |
| Large generated datasets/cards | Keep immutable main-side Git blobs reachable, label tested-side working examples historical, and retain the independently audited historical LevelDB demo. No corpus regeneration |

## Three bounded fixes

1. **PR-07 / UX-01 / FR-UX-04 support:** explicit ref/prerequisite/status docs and
   [a real finite C++ request/policy example](../../examples/first-trial/README.md).
   Outside the checkout, the installed console ran collect, check and HTML
   report successfully on three actual CTest cases. Missing tests and stale
   source each produced an explicit exit 3. Broader UX acceptance remains open.
2. **FR-CTX-03 / UX-02/03 / M5-05 / AC-08 support:** `.c++` is accepted consistently
   by native discovery, strict file selection and bounded Python selection.
   Missing/unsupported/unsafe database entries remain explicit unassessed gaps;
   no nonexistent source hashes, parse results or receipts are invented. Original
   argv/directory/defines/language/includes and conservative unknowns remain.
   Publication rediscovery uses the same database. R08 exercised all three
   original KJ filenames and compilation contexts on the installed candidate.
3. **FR-ANA-03 / M4-05 / PR-07 support:** three prototype-2 detector repairs, with
   22 stable IDs and registry format2.0.0. No broader original row closes here.

| Rule | Reviewed source behavior | Required positive/negative qualification |
| --- | --- | --- |
| CPP-MOD-002 | Direct literal unqualified angle operand plus compiler-classified system include; qualified/quoted/project shadows are excluded | Real string.h/stdio.h positives; kj/string.h, local/quoted/macro/transitive controls. Explicit custom `-isystem` roots remain a compiler-trust boundary, not independent standard-library attestation |
| CPP-MOD-006 | Conservative fixed-array scalar accumulation subset; no pointer/bound or general semantic-equivalence claim | Positive original/rewrite compile and execute; reject argv/extra-index use/nonunit stride/index mutation/wrong bound/aliases/volatile/calls |
| CPP-MOD-001 | Canonical void-result/alias casts exempt; traversal still sees nested nonvoid casts | Intentional void negatives, genuine numeric/pointer and nested cast positives. External clang-tidy AllowCastToVoid=false behavior is unchanged |

The finite regression sample is in
`analyzer-core/tests/fixtures/modernization_precision_regressions.cpp` and
`test_rule_regressions.cpp`; before/after array rewrites are separate fixtures.
The original R04/fmt, R05/json and R08/KJ observations remain pinned historical
counterexamples. The receiving-host replays below are new observations tied to
selected upstream files, host paths and the installed candidate. Original
research, wheel/native bytes and timeout failures remain in their own records.

## Fresh Cloud results

The first build of the exact v2 handoff reached CTest and passed 173 of 175
cases. A literal `.c++` exclusion was interpreted as a regular expression, and
libclang exposed element volatility on the canonical array type. Both cases
were repaired. Another native control showed that dropping the qualification
from an array name could change the result of the suggested range-for rewrite.
The revised advice refers to the same array without inventing an identifier.
The original failures and the original source tree remain in the run records.

On Linux x86_64, GCC 14.2, libclang 19.1.7 and CMake/CTest 3.31.6, the repaired
code passed 175 native tests and both executable rewrite controls. The scoped
Python tests passed 308 cases, the Git miner passed 2 and the report engine passed
30. The locked dashboard passed 64 tests and built fresh assets. Its test for the
four health cards asserts the existing “Complexity finding health” label.
The installed console discovered the native prefix and passed the first trial.
The wheel and installed dashboard matched the fresh asset inventory.

| Receiving-host replay | Retained native outcomes |
| --- | --- |
| R04/fmt, compiled | `format.cc` and `main.cc` analyzed |
| R04/fmt, header-only | `main.cc` analyzed, `format.cc` explicitly excluded |
| R05/json | Both consumer macro contexts analyzed |
| R08/Cap'n Proto KJ | `array-test.c++`, `array.c++` and `consumer.cpp` analyzed, 11 headers explicitly excluded |

The eight selected translation-unit executions had zero parse errors. The
recorded range-for, intentional void cast and project-header counterexamples
had no matching finding at the original locations. All four public analyses
returned exit 3 with partial status because the retained evidence did not
establish preprocessor/time/query dependency closure. These finite observations
leave upstream readiness and broader analysis accuracy open. The historical
LevelDB showcase retains its original revision, binary and counts.

## Remaining delivery evidence

The originating workspace refused a zero-output estimate before build launch.
The fresh Cloud host admitted the above jobs with the same 4 GiB reserve and
64 MiB margin. The originating strict exit 2 reported stale CI source evidence.
On the receiving host, `python scripts/verify_delivery.py --require-complete`
returned exit 2 at the missing `work/coverage-t123/current38-source-proof.json`.
The historical exit 3 applies to the earlier source and proof only.

The original 38 criteria require their genuine source bindings, reviews,
captures and execution evidence. The handoff inventories these files and carries
only selected bodies. A current acceptance record requires the actual missing
materials and fresh affected checks, or a full rerun of the original affected
criteria. Scoped results above leave the ledger unchanged. The original research
harness's descendant cleanup remains a prerequisite for any future performance
comparison. This batch records no performance comparison.

Exit 3 from the strict verifier means current evidence is valid and full scope
remains incomplete. Exit 0 is required for full production completion. The
integration commit and push remain conditional on valid current evidence.
