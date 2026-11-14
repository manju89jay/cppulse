# S0 and S1 native technical checkpoint

Baseline HEAD remains b89dce9d22b37ef44843a68eb3373c525b4b8e94.
Project refs compared byte-for-byte with start-refs.txt: unchanged.
All changes remain uncommitted, including earlier stabilization work.

## Executed checks

| Suite | Result |
|---|---|
| Root | 27 passed |
| Analyzer CTest | 77 passed |
| CLI CTest | 20 passed |
| Git miner | 90 passed, 91% coverage |
| Predictor | 95 passed, 92% coverage |
| Report engine | 80 passed, 94% coverage |
| Dashboard | 37 passed; production build passed |
| Total | 426 passed |

Invocations: source review/environment.sh; bash scripts/check_local.sh;
bash scripts/demo.sh; python3 scripts/run_real_corpus.py;
python3 scripts/verify_web_demo.py --data output/corpus/consumer
--evidence review/autonomous/consumer-web.

Before-fix reproductions cover native contexts/argument barriers, resource
lookup, relative CLI paths, scope/scoring, model/backend failures, history
lineage/no-Git and partial-state presentation. Logs are retained in logs/.

## Real inputs and claims

Pinned fmt e69e5f977d458f2650bb346dadf2ad30c5320281 builds as a static library.
Pinned utfcpp 6be08bbea14ffa0a5c594257fb6285a054395cd7 is used header-only.
The selected application links both and passes its UTF-8/formatting CTest.
These are not full upstream test-suite passes or accuracy benchmarks.

| Analysis | Attempted files | Findings | Parse state | Full-scope health |
|---|---:|---:|---|---|
| fmt selected inventory | 16 | 0 | 15 analyzed, optional module TU partial | unavailable |
| utfcpp selected inventory | 7 | 29 | 6 analyzed, C++20 header partial under C++17 | unavailable |
| consuming application | 1 | 2 | exact database command; completely parsed | scored for selected scope |

All three cases pass general JSON/schema/count/identity/PDF validation.
API responses and built dashboard browser checks pass on actual consumer data.
Raw parse context, partial facts and limitations remain available. The two
remaining variant gaps are not hidden by exclusions or diagnostic suppression.

Docker is blocked: no executable or socket, no environment-change tool.
Windows/macOS, all build variants, predictive accuracy and broad detector
accuracy remain unverified. Symlink entries are excluded conservatively;
per-link exclusion receipts are not yet implemented. Merge history is marked
partial and follows a first-parent delta model. Current schema-v1 extensions
are prototype behavior pending explicit S2 compatibility reconciliation.

## Disposition

Native-qualified checkpoint accepted for progression into S2 contracts.
Docker and additional-context support remain deferred/unadvertised rather
than marked passed. Independent code review can still reopen a correctness
issue; human usefulness validation has not occurred. No project or release
publication action is authorized by this technical acceptance.

Independent review reopened and corrected symlink-parent traversal, heuristic
factor values and active-feature metadata, dirty pinned checkouts and a legacy
relative-root/basename ambiguity. Dedicated regressions and the aggregate
426-test run passed after those corrections.
