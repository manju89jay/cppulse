# S7 technical review — native local candidate accepted

Historical verification record: this candidate proof preceded the user's
authorization to create local checkpoint commits. Original hashes/ref inventories
below describe that earlier worktree. The new local branch and its fresh shared
checks are documented in `../checkpoint-20261114/summary.json`; the candidate
was not rebuilt or published as part of saving the commits.

The public local workflow and presentation source passes its complete native
check boundary. The exact dev2 candidate also passes the fresh installed proof
recorded below, including source-hidden runtime exercises and coherent pins.
Technical self-review and seeded fixtures are separate from human usefulness
evaluation. All project changes remain uncommitted and unpublished.

## Revision and exercised environment

- HEAD: `b89dce9d22b37ef44843a68eb3373c525b4b8e94`, branch
  `codex/job-application-demo-20261113`, plus the current uncommitted diff.
  `s7-refs.txt` and `s7-shared-summary.json` record unchanged refs.
- Source version: `0.2.0.dev2`. Earlier actual public-demo evidence explicitly
  records its dev1 source runtime; it is not relabeled as an installed dev2 run.
- Linux x86-64, Python 3.12.14, glibc 2.41, GCC 14.2, libclang 19, CMake/CTest
  3.31.6 and Node 24, using the recorded `review/environment.sh` setup. These
  finite compiler/runtime dialects do not qualify other platforms or versions.
- Docker executable/socket unavailable. Compose, container execution and a
  hosted GitHub Action are **not run / not passed**. No project commits, ref
  updates, remote writes, deployment, publication or messaging occurred.

## Implemented and source-verified boundaries

The public Python CLI now exposes explicit `collect`, `assess`, policy/finding
`check`, baseline creation, consumer `compare`, historical `explain`, evidence
reports and read-only SARIF export. Requests select finite inputs, explicit
commands and built-in versioned normalizers. Loading metadata performs no
implicit build. Machine stdout is separate from captured tool logs. A completed
capture is distinct from a policy or finding-regression pass: current check
exits are 0 passed, 1 failed, 3 insufficient/stale, 2 invalid and 130 cancelled.

Current checks reverify source and every finite recorded generated output before
evaluation and publication. Reassessment follows exact unassessed facts-base
lineage rather than copying an old active assessment. Stale/unverified inputs
retain a partial current attempt without an old green gate; historical pins
remain readable. Imported reports remain unauthenticated foreign claims.

JSON, HTML, optional PDF, API and dashboard consume one checked `snapshot_view`.
Stored control states, scores and numeric display tokens are retained rather
than recalculated in presentation. Typed observations preserve occurrences and
producer/context identity. Coverage, sanitizer outcomes, consumer compatibility,
local-test gaps, collection status and experimental maintenance scores remain
separate. API requests resolve one current attempt or exact run/hash; raw and
report downloads use the same pin, optional API-key boundary and checked bytes.
Dashboard assets are packaged, with no checkout/Node fallback at runtime.

Finding baselines add the explicit `native-line-anchor-1` strategy from retained
source bytes while preserving historical `native-1` facts. Occurrences are
multisets; unique exact lines can survive line insertions. Compatibility requires
exact relevant detector/configuration/registry/tool/observed-context facts.
Explicit one-to-one renames do not waive changed contexts. Expiring scoped
suppression affects only the finding check's unsuppressed-new count; raw findings,
policy results and unknown coverage remain visible. SARIF preserves every
occurrence, canonical URIs, Unicode positions and partial warnings. Annotated
exports require the exact retained typed comparison and its checked raw roles.

Opt-in CMake targets and local hook/action adapters call the same engine. CMake
target dependencies impose build ordering, not evidence applicability; the
check stays outside the default build unless explicitly enabled. Local Bash and
pre-commit checks do not imply Docker or GitHub runner execution. Maintainer and
consumer evaluation tasks are prepared; no user study or outreach was run.

## Evidence and results

| Executed boundary | Observed result | Useful retained path |
| --- | --- | --- |
| Final shared source runner | All **15 checks**, **2,499 tests** and dashboard production build passed | `review/autonomous/logs/s7-final-shared/check-results.json`; `review/autonomous/s7-shared-summary.json` |
| Public C++ evidence journey | Actual clean / intentional finding / missing XML produce **passed / failed / insufficient**, exits **0 / 1 / 3**; JSON/HTML/nonempty readable PDF for each | `output/public-evidence-demo/batches/91a6aa6908ca4f729d14aed202175968/summary.json`; `review/autonomous/logs/s7-public-evidence-readonly-final.log` |
| Actual finding-regression journey | **24 public CLI commands**, exits 17×0, 2×1, 5×3; **43 snapshots** verified; **10 native reports** validated | `output/findings-demo/batches/cfe93927ff6a4666bdd9cc487e164ff1/summary.json`; `review/autonomous/logs/s7-actual-native-findings-audit.json`; `s7-native-findings-snapshots-verified.json`; `s7-native-findings-report-validation.json` under the same logs directory |
| Actual source API/browser journey | Nine selected policy/consumer cases; pinned view/raw/PDF requests, no browser errors, server PATH without Node; explicitly **source** package mode | `review/autonomous/artifacts/s7-web-source-actual/verification.json`; `review/autonomous/logs/s7-web-source-actual.log` |
| Finding/SARIF producer related gate | **289 passed**, findings 87% and SARIF 90% coverage; independent original annotation counterexamples closed | `review/autonomous/logs/s7-finding-producer-related-final.log`; `s7-sarif-retained-independent-final.log` |
| Local CMake/hook integration | **31 passed**; source public demo also exercises the actual explicit CMake check and stale source/output exits | `review/autonomous/logs/s7-local-integrations-gate.log`; public evidence summary above |
| Original prototype demo after current health fix | Four schemas/internal totals/paths verified; **5 findings**, 2 files, health **95.5**, heuristic ranking; readable **7-page, 56,283-byte PDF** | `output/s7-legacy-demo/`; `review/autonomous/logs/s7-fresh-legacy-demo.log` |
| Original prototype actual API/dashboard | Built dashboard, exact summary/finding rows, six compatibility routes plus one view through Vite proxy, PDF and navigation pass | `review/autonomous/logs/s7-legacy-web-fixed.log` |
| Claims audit and qualifications | Historical architecture/ADR/example claims qualified with original bodies preserved; old S3 exit proposal explicitly superseded | `review/autonomous/S7-CLAIMS-AUDIT.md` |

The unique final shared count is root **2,040**, analyzer **84**, C++ CLI **20**,
Git miner **90**, predictor **98**, report engine **116**, dashboard **51**:
**2,499 tests**. Final component namespace coverage is approximately Git 90.6%,
predictor 89.0%, report 94.0%, recorded in the shared coverage JSONs. The runner
includes configure/build/CTest, component `pytest -v --cov=src` plus canonical
namespace coverage, root tests, Black/Ruff/generated checks and npm test/build.
Focused gates overlap this shared run and **must not be added** to its total.
Counts are functional regression evidence, not product completeness or accuracy.

Reproduction uses the shared runner's default non-Docker sections; exact child
argv/cwd/log/status records are in `check-results.json`:

```bash
source review/environment.sh
.venv/bin/python scripts/check_local.py --output-dir review/logs
bash scripts/demo.sh "$PWD/output/new-legacy-demo"
PYTHONPATH=python .venv/bin/python scripts/demo_evidence.py \
  --analyzer analyzer-core/build/cppulse-analyzer \
  --resource-dir "$CPPULSE_CLANG_RESOURCE_DIR" \
  --fixture demo/policy-fixture --output output/review-evidence-demo \
  --scenario all --formats json,html,pdf
PYTHONPATH=python .venv/bin/python scripts/demo_findings.py
```

These commands create fresh outputs rather than asserting that retained mutable
`latest-demo.json` pointers identify a new run. Use the exact batch paths above
for this review. Installed execution must instead use the selected installed
interpreter/package and its recorded analyzer/resource paths, without source
`PYTHONPATH`; the completed fresh installed proof is recorded below.

## Concrete defects closed before source acceptance

- Metadata-limit overflow and cancellation after capture could advance derived
  work incorrectly. Corrective probes now produce partial/cancelled latest
  attempts with explicit errors and no positive transform promotion:
  `logs/s7-independent-collect-corrections-green.json`.
- Reassessment could borrow new producer facts or upgrade unverified history
  merely because today's files match. Exact lineage and source/output checks
  reject those cases and expose a fresh unassessed gap:
  `logs/s7-independent-assessment-boundaries-green.json` and
  `logs/s7-compare-workflow-boundary-tests.log`.
- Snapshot-view guards now preserve exact large numeric values and distinguish
  source/run/context mismatch, missing jobs and justified nonapplicability. Raw
  media/download pins and PDF origins are checked; missing data does not fall
  back to an older positive or unrelated flat file. Reproductions and corrective
  gates are retained as `logs/s7-snapshot-view-*.log`, `s7-raw-media-header-red.log`
  and `s7-pdf-base-tests.log`.
- Finding contracts previously permitted an unrelated/identity rename to relax
  fingerprint equality, or fallback observations to count as known unchanged.
  They now require an applicable nonidentity mapping and credible current scope.
  The producer reconstructs original source anchors rather than trusting a
  self-consistent forged baseline. See `logs/s7-finding-rename-reproduction.log`,
  `s7-finding-contract-independent-probes.log` and the 289-test final gate.
- SARIF initially accepted unchecked caller classifications or suppressions from
  a different parse context/rule version. Before/after regressions now require
  credible unique current anchors, exact suppression scope and a retained typed
  comparison. Original independent probes reject, and valid retained annotations
  still satisfy the unchanged official OASIS schema:
  `logs/s7-sarif-independent-reproduction.log`,
  `s7-sarif-independent-corrective.log`,
  `s7-sarif-retained-comparison-red.log`,
  `s7-sarif-retained-independent-final.log`.
- The built legacy dashboard initially needed repair to its actual flat-data
  adapter/rendering journey. The original failure/diagnosis and corrected real
  browser run remain separate in `logs/s7-legacy-web.log`,
  `s7-legacy-web-diagnosis.log` and `s7-legacy-web-fixed.log`. Fresh prototype
  health metadata now names `weighted-findings-per-attempted-file-v2`.

Actual finding integration demonstrates unchanged/line-shift pass, known unique
new finding fail, repeated-line ambiguity, separate equal basenames, stale
header rejection before full recollection, changed-flag context unknown,
ordinary database-changing rename unknown and a compatible predeclared-path
rename pass. Actual UTF-8 native byte column **30** becomes SARIF Unicode
codepoint column **29**. These are clearly synthetic C++ cases executed through
real tools, not allegations about an upstream project's defects.

## Limits and remaining stages

The accepted S6 coverage/sanitizer/consumer/transfer scope remains as recorded in
`S6-REVIEW.md`; S7 does not widen its qualified producer dialects, infer missing
metrics or authenticate imported producers. Complete selected local checks do
not establish all headers/runtime dependencies, every memory access/path,
project-wide accuracy, safety, compliance or production readiness. Ranking and
effort/impact estimates remain experimental. Historical examples are preserved
with explicit inconsistent-total/nonbenchmark notices. No human usefulness
claim follows from technical self-review or prepared evaluation tasks.

The staged plan keeps these separate follow-ups; this review implements none of
them or expands their scope:

| Remaining stage/track | Work still planned |
| --- | --- |
| S8 | Independently defined/measured maintainability metrics, comparable trends and scorer decisions, richer drill-down and reviewed real corpus expansion. |
| S9 | Dependency-aware incremental caching/invalidation, resume/indexing/pagination/search and measured cold/warm correctness/scale at named workload tiers. Current finding demos recollect the full relevant scope. |
| S10 | Richer controlled-history ownership/coupling/bot/alias semantics; chronological held-out model evaluation, baselines and calibration before predictive claims. |
| S11 | Read-first MCP/IDE integration, free distribution guidance/skill and independently exercised platform candidates. Existing local templates are a subset, not completion. |
| E1 | Reviewed domain/standards starter mappings and process obligations; no certification or licensed-text reproduction. |
| E2 | Organization/portfolio/scheduled/issue-tracker/ROI workflows with explicit provider/data/notification reviews. |
| E3 | Narrow reviewable fixes, then separately validated semantic/AI-assisted repair; no implicit commit or PR authorization. |
| E4 | Additional API/ABI, fuzzing, provenance/process evidence and languages, each with supported-version producer and integration proofs. |
| E5 | Enterprise identity, optional hosting and operating/access/storage/retention design; deployment requires separate authorization. |

## Fresh dev2 installed acceptance — PASSED

The exact unpublished candidate is accepted for the declared native local
prototype journeys. [Installed summary](installed-s7/summary.json) records the
complete paths and limits. The candidate is
`output/candidates/s7-preview/cppulse-0.2.0.dev2-linux-x86_64-candidate`.

- Wheel SHA-256: `55cf080eda016d9e3af784c59ccd9b18b07863cbcac077ea5564fb4966338026`.
- Native archive SHA-256: `16517d0c46d47f60f2c2ab80109093871f7172120df4c06621adf9f43bf6921b`.
- All eleven top-level driver commands return zero. The fresh core installs
  offline while the original checkout path is absent. Optional PDF/web wheels
  and project wheel install before hiding; their actual runtime checks happen
  while hidden. Exact site-packages origins and dependency inventories are
  retained. Core has nineteen distributions including pip, with no optional
  ML/PDF/web or Node. The fifty-distribution web environment has no ML,
  browser-testing packages or Node runtime requirement.
- Installed core repeats the public clean CMake/freshness journey and all
  twenty-four actual finding CLI commands with the expected exits: seventeen
  zero, two one and five three. Full installed web collection produces one
  passed, one failed and one insufficient-evidence gate, with local CMake and
  the actual Bash adapter over the public engine.
- Four fresh installed browser cases use those same three check/report pins
  and the latest stale-output gap; all nine additional historical browser cases
  render retained-store compatibility only. Every browser case has zero browser
  errors, pinned raw/report downloads, and no Node on the product server PATH.
  A separate actual `cppulse serve` smoke verifies bundled assets/API/PDF.
- All seventy-four fresh snapshots and fourteen distinct retained native reports
  verify their contracts, hashes, internal totals and relative paths. All three
  fresh PDFs, thirty-two pages, pass text/bounds checks, full rendering and visual
  review. Full records are outside the checkout under
  `/workspace/scratch/b3d4e6fff494/s7-installed-final`.
- The checkout is restored. HEAD, branch and all refs match the original record;
  the complete frozen candidate source state still matches the working tree.
  See `s7-final-source-verification.json`. No project commit or external write
  occurred. Packaging and review are not publication.

The original legacy harness failed on an obsolete case-sensitive label. Actual
content was present; the corrected harness also adds exact totals/all-record and
navigation checks, and passes. Original failed and corrected logs are retained.
An initial final-ref comparison used different output column ordering; repeating
with the baseline's exact `for-each-ref` format verifies identical refs. Neither
was concealed or treated as a product pass before correction.

Docker/Compose and a hosted Action remain **unexecuted**. Host compiler headers,
libclang/LLVM and system runtime/PDF/browser libraries are not a complete
redistributable closure. Other platforms, large-workload performance, detector
accuracy, safety, predictive validity and human usefulness remain unqualified.
The S6 producer matrices were source-verified separately; this installed proof
repeats the selected native/public journeys, not every S6 matrix. S8-S11/E1-E5
remain the future work listed above.
