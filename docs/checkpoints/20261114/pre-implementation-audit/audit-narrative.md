# cppulse: product, delivery and production-specification reconciliation

Read-only review, 14 November 2026. This is an audit and correction proposal, not implementation approval or a new completion claim.

## Finding

cppulse has a substantially strengthened local prototype and a working, narrowly qualified evidence/policy core. It does **not** yet implement the complete production specification. The cloud work built useful packaging, result-integrity and orchestration machinery, but did not deliver the rich maintenance analysis, scale, editor integration, platform qualification or user validation needed to satisfy the full goal. Some delivered behavior is also defective.

The original demo-only assignment was explicit. Later instructions broadened the goal to everything planned. Treating the assistant's S0–S7 implementation boundary as the user's complete production goal was a scope-handling failure. The newer completion plan acknowledges that boundary; a plan does not implement its missing features.

## Audit basis and boundaries

- Current branch: `codex/cppulse-local-core-20261114`; exact HEAD `15492dbfcbc6b20d938e42e760486da4181035f6`.
- Original starting branch/checkpoint: `codex/job-application-demo-20261113`, `b89dce9d22b37ef44843a68eb3373c525b4b8e94`.
- Read the uploaded TASK_SPEC/AGENTS/CLAUDE first, then discovery/landscape, complete production requirements/design/tasks, decisions, architecture and applicable styles. Inspected actual current implementation, tests and generated records rather than relying on document claims.
- The uploaded ZIP contains 49 Markdown snapshots. Decoded folder paths were extracted outside the repository. Snapshots were never copied over current files. The instructions, research and production specification match current files after line-ending normalization; several architecture/decision/README/example files differ.
- All 118 numbered requirements/scenarios, 60 M0–M9 tasks and eight additional design/environment/validation obligations are retained in the accompanying checklist, with an additional explicit Docker/Compose execution row. M8/M9 remain the specification's optional/expansion groups, not silently deleted scope and not prerequisites for the first useful release.
- No project code/documentation edits, Git reference changes, commits, pushes, deployment or publication were made during this review. Pre-existing uncommitted planning edits were preserved. Targeted probes and audit artifacts are outside the repository; test tools may update ordinary ignored build/test state.
- Status means: **verified** = the stated requirement has actual supporting evidence within its stated scope; **implemented but unverified** = implementation exists without applicable execution evidence; **partial** = only a subset works or is delivered; **missing** = capability/evidence is absent; **conflicting** = current behavior or documents contradict the target. A passing unit suite or source file alone does not establish production functionality.

## The original product and developer value

The broad product is a free, inspectable, locally usable C++ maintenance and verification tool. It should help an application or library developer answer: what should we fix, why does it matter, which supported configurations were actually checked, and what is still unknown before releasing or adopting this code?

It combines four deliberately separate results: explainable maintenance health; experimental change-risk prioritization; verification-evidence completeness; and acceptance under a selected versioned policy. Meaningful maintenance analysis calls for measured complexity, size, duplication, dependencies, change coupling, ownership and trends with concrete links to code. Existing compilers, analyzers, CTest, coverage and sanitizers remain the producers of many verification facts.

The later focused discovery proposes an initial audience of compiled-library/header-only maintainers and their consumers. A library might support Linux/GCC/C++17 with exceptions disabled and Windows/MSVC/C++20. Tests for the first configuration cannot establish the second. cppulse should connect selected checks to the actual distributed header/package, compiler/flags/macros and consumer workloads, show failures and missing variants, and help adopters identify additional local tests. A sample instantiation never establishes every possible template use.

The discovery's nlohmann/json `JSON_THROW(error)` to `throw error` example is explicitly hypothetical. It explains why actual `-fno-exceptions` compilation and the exact distributed artifact matter; it is not an observed upstream defect or a test performed on nlohmann/json in this session.

The landscape is a dated research inventory, not a current market benchmark. Similar aggregation, health and verification capabilities already exist. Free private use, inspectable methods and this combined workflow are adoption hypotheses. No maintainer study or comparative experiment supplied here establishes demand, superiority or usefulness. No score establishes certification, ASIL, medical classification or universal production readiness.

## Scope and delivery chronology

1. **Initial cloud assignment:** stabilize the current six-component prototype for a reproducible job-application demo; build/test the analyzer, C++ CLI, three Python components and dashboard, validate contracts and full native output, attempt Docker only if usable. It expressly excluded building the new collect/assess/evidence-policy MVP and broad production backlog. Initially no project commits/pushes were authorized.
2. **Later direction:** the user asked to implement everything planned in reviewable stages and authorized autonomous execution; VS Code was raised as an integration idea. This broadened the execution goal. It did not explicitly authorize a permanent stop at S7.
3. **Actual cloud implementation:** identity/parse/profile/metadata/format fixes; namespaced Python packaging; immutable run stores and current-attempt handling; explicit finite collection recipes; bounded adapters and policy predicates; library consumer comparison; baselines/suppressions/SARIF; snapshot-backed reports/API/dashboard; CMake/pre-commit helpers; local checks and candidate/install proofs. Existing 22 native rules, Git mining, ranking paths and report/dashboard were preserved, not all newly created here.
4. **What was left out:** measured maintenance metrics/trends, the specified density scorer, robust incremental analysis and scale qualification, deeper Git intelligence, validated statistical prediction, VS Code/MCP/skill qualification, full release/platform/container qualification and M8/M9 expansions.
5. **Git authorization changed later:** the user explicitly requested a new branch, small commits under their identity and then a push. Thirty focused changes were saved and the published branch is the revision above. Those historical operations were authorized. Current review forbids new commits/pushes. The local original commit sequence and API-replayed sequence have equal trees but different commit IDs; existing delivery records retain that distinction.

## What the execution evidence actually proves

The retained full shared check record reports 15 successful checks and 2,499 tests: root 2,040; analyzer 84; C++ CLI 20; Git miner 90; predictor 98; report engine 116; dashboard 51; dashboard production build passed. Python commands include component `pytest -v --cov=src tests/` plus coverage of the migrated canonical namespace. This is a retained checkpoint run, not a newly run GitHub CI result. Its implementation revision and subsequent exact-tree replay are recorded, and it does not qualify all production requirements.

A later fresh run used the current pushed source revision against pinned fmt 10.2.1 and utfcpp 4.0.5 plus a tiny authored consumer. It built fmt and the consumer against both libraries and ran the one selected consumer CTest, regenerated all four legacy documents and PDFs, and checked schemas, totals and paths. It did not run full upstream test suites, real-history behavioral evaluation, six-project qualification or a production application.

| Actual fresh case | Scope/result | What it does not prove |
|---|---|---|
| fmt `e69e5f977d458f2650bb346dadf2ad30c5320281` | 16 attempted files, 15 analyzed/1 partial, 0 findings, full health null; upstream tests disabled | Zero defects, complete header/module support or upstream test success |
| utfcpp `6be08bbea14ffa0a5c594257fb6285a054395cd7` | 7 selected headers, 6 analyzed/1 partial, 29 rule observations, full health null; all selected contexts inferred | Confirmed defects, C++20 support or exhaustive template verification |
| Authored consumer | One 14-line TU, exact compilation context, one CTest passed, 2 rule observations, stored heuristic health 99 | Production application quality; one observation is the confirmed `auto` false positive |

All these source checkouts had shallow history. No meaningful coupling/ownership/prediction evaluation follows from them. The legacy utfcpp API/dashboard browser run passed the exercised routes/navigation/PDF download with no browser errors. It used the legacy-flat compatibility view, not the new immutable policy workflow. The three PDFs contain text on all 23 pages; page count and successful rendering are not analytical usefulness.

Separate retained S4/S6/S7 evidence exercises real CMake/CTest outcomes, selected coverage/sanitizer/GNU diagnostic cases, package-bound library consumer cases, and installed CLI/report/API/dashboard flows. This review revalidated 36 retained snapshot manifests and 3,103 referenced artifacts using current readers. That verifies retained bytes and semantic contracts, not recollection, historical source freshness, producer authenticity or cross-platform support.

The `0.2.0.dev2` source-hidden installed candidate is a real earlier proof. It predates the final formatted/source commit sequence and was not rebuilt as the exact current branch artifact. Host compiler/libclang/runtime requirements remain. Docker/Compose was unavailable; its source-level fixes are unexecuted. Windows, macOS, Python 3.11 and a full GCC/Clang matrix remain unqualified.

This review ran bounded current-source suites for policy/evidence, run storage/execution/tooling/compatibility, findings/native contracts, predictor behavior, Git current-scope cases and selected native CTests. Their individual logs/commands are included. Counts overlap existing suites and must not be added to 2,499 as a product-quality score. Independent defect probes deliberately record failing product expectations and were not added to or used to weaken repository tests.

## Confirmed defects and incompatible delivered behavior

These are present in the delivered branch and should be corrected before adding dependent features. The first two detector defects are unchanged from the starting checkpoint; the cloud work failed to discover/fix them, rather than introducing their algorithms.

| Finding | Actual evidence | Correction acceptance |
|---|---|---|
| CPP-MOD-005 suggests `auto` on an existing `const auto` declaration | Fresh authored consumer finding at main.cpp:12; rule checks resolved type spelling rather than written declaration | Clean `auto`/`decltype(auto)` cases stay clean; an actually verbose explicit iterator remains detectable |
| CPP-CX-001 double-counts nested logical expressions and skips an ordinary uninstantiated function-template definition | Fresh bounded probe: `if(a&&b&&c)` reports 5 under the documented counting method's expected 4; equivalent template has no finding | Hand-reviewed operator/macro/template cases; no double traversal; version semantic detector change |
| Incomplete file receives numeric low-risk label | utfcpp cpp20.h has 20 parse errors but a stored 0.0/LOW rank | Per-file/context applicability and unknown status; no low-risk presentation based on absent analysis |
| Public `analyze` reports partial health but exits 0 | Fresh missing-include probe, expected documented partial exit 3 | All entry points return consistent 0/1/2/3/130 semantics; usable partial facts remain |
| Ambiguous config discovery silently picks one file | Fresh `.cppulserc.json` plus `.cppulserc.yml` probe picks YAML without an error | Reject ambiguity or require explicit selection; preserve documented precedence |
| Fixed 500-KiB native file limit obstructs common amalgamated/header-only inputs | Analyzer constant and explicit skipped-file branch; dedicated bounded probe retained | Configurable bounded limits, visible incomplete scope and successful above-limit real header fixture under an adequate budget |
| Scorer and hotspots diverge from complete design | Actual score model is weighted findings per attempted file; complexity_score is severity/3 | Explicit version/migration decision and agreed design implementation; actual analyzed-KLOC metrics and measured hotspots, no proxy as measurement |
| Report can imply stronger knowledge/risk conclusions than available history supports | Legacy report says no silos detected and shows LOW ranks despite shallow/partial limitations | Unknown/insufficient-history states in each affected section; measured versus heuristic estimates visibly separated |

## Document conflicts requiring explicit reconciliation

- The November 4 full platform proposal and November 11 focused discovery have different breadth. Discovery explicitly does not supersede the full proposal; this audit preserves both. The full M0–M9 checklist governs comparison, while the focused library workflow remains a value hypothesis to test.
- Historical TASK_SPEC specifies a raw weighted-finding deduction for overall health and per-file category scales. The delivered overall calculation divides weighted findings by file count; the production design instead specifies analyzed-KLOC density/caps/weights and worst-required-context semantics. Current disclosure of its method is good but is not implementation of that design.
- The safety style requests C++20/23 conveniences such as span/expected despite a C++17 implementation rule; it also prescribes the same fixed small file cap that the production design rejects. Resolve the rules explicitly rather than pretending all can be followed simultaneously.
- Proposed CLI defaults to concise text, has explicit effective config and changed checks. Current CLI largely emits JSON and omits parts of those workflows. Actual CMake helper needs 3.21+, versus the specification's preserved 3.16 consumer minimum where feasible. Changing interfaces/minimums needs a compatibility decision.
- Snapshot D28/D29 and current D28/D29 are different decisions under reused IDs. Preserve both histories with unique provenance; do not replace the current log with the snapshot.
- Some current README/portfolio/status statements still describe older pre-proof/pre-push checkpoints and S0–S7 as the accepted endpoint. New plans/records cannot silently rewrite old evidence. Maintain one current capability ledger linking immutable historical records.
- Historical example totals and F1/benchmark/Windows/production claims are not fresh qualification. The original six are fmt, grpc, json, leveldb, poco and protobuf. utfcpp is useful additional evidence, not a replacement for that required corpus.

## Unavailable references

`docs/PRODUCT_VISION.md` and the referenced ADR-007 density-score text are absent from both the checkout and upload. Review-index links to the original handoff brief, checkpoint manifest/backup, cloud receipt, old verification JSON and portfolio PDF are also absent. The complete pre-cloud research conversation/web archive and maintainer interviews were not supplied. Their contents/acceptance cannot be invented.

`REVIEW.md`, `.claude/session-state.md` and `docs/research/cppulse-review-index.md` are available in the upload but absent in current checkout. They describe different dated stages, including historical Windows review and initial scaffolding, and are not current cloud completion evidence.

The full five-column matrix and M0–M9 task checklist follow in the HTML/CSV/JSON outputs. The correction plan retains all missing proposed features and explicitly separates them from defects above.
