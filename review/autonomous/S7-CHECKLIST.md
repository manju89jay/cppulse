# R7 technical review checklist

Prepared on 2026-11-14 from the retained S7 source gates and actual local runs.
This review document is excluded from candidate source hashing. It does not
approve publication or change project refs. All paths below are repository
relative unless stated otherwise.

**Current state:** S7 technical acceptance is complete for the exercised Linux/
POSIX scope. The final shared run passed15 checks and2,499 tests plus the dashboard
production build. The exact dev2 candidate passed fresh offline core installation
with the checkout hidden, installed public workflow/finding checks, and separate
PDF/web runtime proof. Checkout restoration, unchanged refs and source-to-candidate
identity are verified. Exact final evidence is indexed below and in
[S7 review](S7-REVIEW.md). Human usefulness review remains separately outstanding;
Docker/Compose and unavailable platforms are not marked passed.

Plan authority: `docs/plans/cppulse-staged-implementation-plan.md`, S7 work
packages and R7; acceptance wording:
`docs/specs/production-platform/requirements.md`, AC-10/12/13/14.
Listed suite counts overlap and must not be summed into a unique-test total.

## S7 work-package traceability

| Planned S7 work | Implemented behavior and actual source proof | Gate/artifact | Remaining acceptance |
| --- | --- | --- | --- |
| 1. JSON/HTML/PDF/API/dashboard show completeness, contexts, controls, separate scores, original links and gaps | One validated `snapshot_view` pins original manifest bytes, selected assessment artifact, original fact bytes and exact display strings. Rendering copies stored gate-affecting values. Browser snapshot mode obtains one consolidated response and uses pinned artifact/report links. Partial/unassessed cases stay visible. Existing legacy report mode and API-key behavior have compatibility tests. | View contracts: 70 focused / 492 related; presentation: 34 focused / 131 related; final web consumer gate: 70; dashboard: 51 tests plus production build. Installed public three-case reports/checks and four browser views use the same fresh pins, including the latest gap; historical nine-case presentation compatibility also passes. | **PASSED** for exact dev2 installed artifacts and recorded selected cases. No universal platform or producer-authenticity claim. |
| 2. Public collect/assess/explain/baseline/check with explicit exits | Public CLI uses finite validated request selectors and accepted producers. Collection completion is separate from producer/test failure and policy acceptance. Assessment requires current workspace/source/output checks; repeat assessment reopens the original unassessed facts base, archives prior decisions as generic exact bytes and reevaluates expiry. Invalid shapes fail before commands. Read-only explain/SARIF never execute project commands. Finding and policy checks remain distinct modes. | Public core 35; owned workflow 44; public CLI 10; finding/SARIF CLI 9; consumer-comparison workflow boundary 6. Independent quota/cancellation and lineage counterexamples pass. Fresh19-distribution core installation has optional ML/PDF/web and Node absent; clean public workflow and full24-command finding matrix pass. Separate installed web environment reproduces P/F/U. | **PASSED** for the explicit installed journeys and documented exits. Counts from different gates overlap. |
| 3. Explicit opt-in CMake target | Packaged `python/cppulse/data/Cppulse.cmake` forwards selected policy or finding request, explicit store/workspace and paired pins. Target stays outside `ALL`, respects selected target dependencies and rejects recursive/ambiguous build configurations. | 15 CMake tests; 31 combined local integration tests. Fresh installed public workflow confirms default build creates no evidence run, opt-in target calls the public CLI, and replaced binary gives underlying `STALE_OUTPUT`/3 (CMake propagates a build-command failure, exit2). | **PASSED** for packaged helper and actual selected fixture; no recursive hidden collection. |
| 4. Baselines, scope, suppressions, SARIF and local hooks | Old `native-1` identities remain unchanged; new `native-line-anchor-1` hashes exact retained source-line bytes with explicit scope, multiplicity and context compatibility. Scoped expiring suppressions retain raw occurrences and cannot waive unknown scope. Full relevant scope is recollected; no dependency-aware incremental/cache claim. Hooks/action wrapper call the same local check, pass no changed-filename shortcut, and perform no implicit Git checkout, comment or network write. | Finding contracts 68 focused / 283 related; pure producer independent 17 and related 289; SARIF independent 19 plus closed-comparison corrective 4; official SARIF validation. Fresh installed core repeats all24 expected finding commands. Actual installed local action wrapper is included in the three-case web workflow. Supplemental checks cover74 snapshots and14 distinct native reports. | **PASSED** for local documented baseline/export/hook behavior. Hosted GitHub and Docker action execution remain unclaimed. |
| 5. Complete installed-package/Compose/API/dashboard journey; exact artifacts/checksums/notices/rollback | Matching dev2 wheel/native archive and local closure/notices/checksums are prepared. Core installs offline while hidden; separate PDF/web wheel is installed before hiding and its runtime proof executes hidden. Fresh reports/API/dashboard agree on the same selected runs and partial gaps. Candidate/source guards and upgrade/rollback instructions remain explicit. | `s7-shared-summary.json`, `s7-final-source-verification.json`; external hidden proof, installed command ledger, core/web package inventories, four fresh browser cases, nine historical compatibility views and PDF QA. | **PASSED** for the exercised native installed journey and source/ref closure. **UNEXECUTED:** Docker/Compose; native execution is not Compose qualification. Rollback instructions do not establish every version/platform transition. |
| 6. Prepare maintainer/consumer evaluation tasks | `docs/verification/evaluation-tasks.md` defines baseline observation, installation/decision/evidence-traceability tasks, missing-local-test and package/configuration comparisons, and a review record. | Preparation exists; no participant was contacted and no human result is recorded. | **OUTSTANDING HUMAN REVIEW:** observe real authorized tasks and then agree measurable usefulness criteria. Technical tests do not prove usefulness/adoption. |

## Acceptance criteria

| Criterion | Evidence already executed | Status and exact boundary |
| --- | --- | --- |
| **AC-10:** a required failed or unknown control cannot pass merely because an average is high | `tests/test_policy_gate_properties.py::test_required_failed_and_unknown_cannot_be_hidden_by_other_controls` exercises required failure/unknown across other control states and thresholds 0/50/100. Exact Fraction arithmetic preserves threshold meaning. Fresh installed public evidence cases produce passed / failed / insufficient gates; repeat checks do not reuse expired historical decisions. | **PASSED** for source properties and installed selected scenarios. Finding regression remains a separate result. |
| **AC-12:** one run has identical status, scores, identities and evidence links across interfaces | `snapshot_view` closes raw manifest/artifact SHA/size and exact assessment display strings. The fresh installed CLI/JSON/HTML/PDF and four browser views select the same three check pins plus latest gap. Pinned raw downloads and API/PDF links retain identity; old nine-case installed views add compatibility proof without rerunning their producers. | **PASSED** for these coherent installed interfaces. MCP/IDE are S11, not delivered by S7. |
| **AC-13:** previous supported config/schema/baseline works or gives an actionable migration error | Explicit `prototype_v1` reader, frozen old risk interpretation and downgrade refusal preserve prior claims. Unsupported majors fail explicitly. Existing v2 baseline/`native-1` records remain readable; new anchors use a separate version. Fresh installed legacy analysis, public baseline/SARIF and older nine-case snapshot presentation pass. Invalid/incompatible facts remain rejected or unknown. | **PASSED** for documented formats and exercised previous-data paths. No universal backward/forward compatibility or exhaustive upgrade/rollback qualification. |
| **AC-14:** packaged HTML/PDF/API/dashboard gives meaningful outputs and correct partial/error states | Package-resource tests cover optional absence, partial/unassessed states, escaping and exact selectors. Fresh installed core19-distribution and separate web50-distribution environments preserve optional separation; packaged dashboard runtime has no Node. Three fresh PDFs total32 pages, all rendered and visually reviewed. Four fresh and nine historical installed browser cases pass from unrelated cwd. | **PASSED** for the exact dev2 candidate and recorded environments. Host PDF/browser/native dependencies remain explicit. |

## Actual command and artifact ledger

The first three entries are retained source proofs. Entry4 records the completed
exact installed-candidate proof; the source proofs are not substitutes for it.

1. **Actual native finding matrix**

   ```sh
   source review/environment.sh
   PYTHONPATH=python .venv/bin/python scripts/demo_findings.py
   ```

   Batch: `output/findings-demo/batches/cfe93927ff6a4666bdd9cc487e164ff1/`.
   `commands.json` retains all 24 exact public CLI argv arrays and actual/expected
   exits; individual original streams are under `commands/`. Seventeen commands
   returned 0, two returned 1 and five returned 3. `summary.json` retains raw/final
   run/hash pins and typed results; `line-shift.sarif.json` validates against the
   unchanged official OASIS SARIF 2.1.0 reference. Real UTF-8 native byte column
   30 maps to SARIF codepoint column 29.

   Audits: `review/autonomous/logs/s7-actual-native-findings-audit.json`,
   `s7-native-findings-snapshots-verified.json` (43 manifests/artifact sets), and
   `s7-native-findings-report-validation.json` (10 raw reports, explicit
   prototype reader, category/severity/total conservation and canonical paths).

   | Actual scenario | Check exit / retained conclusion |
   | --- | --- |
   | Unchanged / two blank lines inserted | 0; one anchored unchanged occurrence; the old line-sensitive native fingerprint changes and the database bytes stay identical. |
   | Header changed before recollection / full cold recollection | 3 `STALE_SOURCE` with a new partial attempt / 0 after new captured commands and facts. |
   | One additional unique allocation | 1; current 2, baseline 1, known new 1. |
   | Repeated identical allocation line | 3; both current occurrences and the historical occurrence remain unknown, not silently deduplicated. |
   | `a/same.cpp` and `b/same.cpp` | 1; two new occurrences survive independently by canonical path. |
   | Compiler flag changed | 3; exact observed parse context differs. |
   | Ordinary rename, without and with an explicit map | 3 in both; the changed database/context is not normalized away. |
   | Explicit single-file rename between predeclared stable database paths | 0; one unchanged occurrence under the same actual observed context. This does not promise arbitrary rename equivalence. |

2. **Public policy/JSON/HTML/PDF/local-CMake/action source journey**

   Executed driver: `scripts/demo_evidence.py` with explicit `--analyzer`,
   `--resource-dir`, `--fixture`, `--output` and local action entrypoint. The exact
   public subcommands and outputs are recorded in each case's
   `commands/commands.json`, not reconstructed from a README example.

   Batch: `output/public-evidence-demo/batches/91a6aa6908ca4f729d14aed202175968/`;
   `summary.json` is `verified` with gate counts 1 passed, 1 failed and 1
   insufficient. Each case retains `reports/evidence.json`, `evidence.html`,
   `evidence.pdf` and verified extracted PDF text. These are source-package runs
   (`PYTHONPATH` explicitly points to this checkout), not installed S7 proof.
   Log: `review/autonomous/logs/s7-public-evidence-demo.log`.

3. **Source API/dashboard browser journey**

   Driver: `scripts/verify_snapshot_web.py`, with explicit source package,
   snapshot verification input, consumer summary and evidence directory.
   `review/autonomous/artifacts/s7-web-source-actual/verification.json` records
   nine cases: clean, findings, partial-parse, missing-tests and five consumer
   applicability cases. Per-case view JSON, screenshots, server logs and original
   artifact downloads are retained alongside it. Source-explicit package mode is
   recorded. Log: `review/autonomous/logs/s7-web-source-actual.log`.

4. **Exact dev2 installed/source-hidden proof**

   External root: `/workspace/scratch/b3d4e6fff494/s7-installed-final/`.
   `hidden-proof.json` records passed, original checkout restored and temporary
   hidden path absent. `commands.json` retains11 successful top-level commands:
   two pre-hide web-wheel install/check commands and nine hidden-source steps.
   Core installation itself happened while hidden; the web wheel was installed
   before hiding and its actual runtime checks ran while hidden. Individual
   public demo command ledgers retain their intended nonzero check outcomes;
   a successful outer harness is not a claim that every policy passed.

   * `core-proof/manifest.json`, `transcript.json` and
     `core-installed-packages.json`: fresh offline19-distribution core install,
     installed module origins, relocated native prefix, optional ML/PDF/web and
     Node absent, legacy analysis/HTML/JSON and actionable missing-extra errors.
   * `public-core-evidence/latest-demo.json` and
     `public-core-findings/latest-demo.json`: actual installed clean public
     journey and complete24-command finding workflow, including SARIF.
   * `web-installed-packages.json` and
     `public-web-evidence/latest-demo.json`: separate50-distribution product
     PDF/web environment, no ML/browser-test packages or Node, and fresh passed/
     failed/insufficient cases with local CMake and actual local action wrapper.
   * `fresh-public-locators.json` and
     `installed-public-web/verification.json`: four browser cases over the
     exact three fresh report/check pins plus latest partial/unverified gap
     without an active assessment. Browser tools run in a separate environment.
   * `installed-nine-case-web/verification.json`: additional historical four
     policy and five consumer views, with unchanged original run/hash/artifact
     identities; this compatibility check did not rerun their C++ producers.
   * `fresh-artifact-verification.json`:74 snapshots and14 distinct raw native
     reports checked against schemas, totals and paths. `pdf-qa/verification.json`
     records32 rendered pages across the three fresh PDFs (10/11/11); visual
     review was completed. `cli-serve-smoke/verification.json` adds an installed
     console-server smoke beyond the11-command orchestration ledger.
   * Repository `s7-final-source-verification.json`: original HEAD, branch and
     all refs unchanged; restored source matches candidate worktree digest
     `e41d5d3788e5f640bd32845bf985df0f619eda8155ead264ffbb71a6fa8982a1`.

   Exact wheel SHA-256:
   `55cf080eda016d9e3af784c59ccd9b18b07863cbcac077ea5564fb4966338026`.
   Exact native archive SHA-256:
   `16517d0c46d47f60f2c2ab80109093871f7172120df4c06621adf9f43bf6921b`.
   The candidate remains local and unpublished; all project edits stay uncommitted.

## Source gate index

Commands below name the focused suites corresponding to retained green logs;
this checklist did not rerun or combine those suites into a new final gate.
Use `source review/environment.sh` for the recorded local CMake/GCC/libclang
environment and `PYTHONPATH=python .venv/bin/pytest` for root Python suites.

| Suite / command selection | Retained green gate |
| --- | --- |
| Shared contracts, workflow/lineage/finding contract boundaries | `logs/s7-central-contract-group-gate.log`: 857 / 91% shared contract coverage. |
| `tests/test_snapshot_view_contract.py` and related contract/policy suites | `logs/s7-snapshot-view-contract-tests.log`: 70 / 95%; `s7-snapshot-view-related-tests.log`: 492. |
| Public collection, request boundary, assessment/reassessment and CLI | `logs/s7-core-workflow-tests.log`: 35; `s7-owned-workflow-tests.log`: 44; `s7-public-cli-tests.log`: 10. |
| `tests/test_finding_workflow_contracts.py` / `test_findings.py` / `test_sarif.py` | `logs/s7-finding-contracts-related-final.log`: 283; `s7-finding-producer-independent-tests.log`: 17; `s7-finding-producer-related-final.log`: 289; `s7-sarif-independent-tests.log`: 19. |
| Public baseline/check/SARIF dispatch | `logs/s7-finding-cli-tests.log`: 9; retained-comparison corrective cases `s7-sarif-retained-independent-final.log`: 4. |
| Snapshot presentation/report/API consumers | `logs/s7-presentation-tests.log`: 34; `s7-presentation-related-tests.log`: 131; `s7-web-consumers-final-focused.log`: 70. |
| Dashboard tests / production build / packaged asset inventory | `logs/s7-dashboard-final-gate.log`: 51; `s7-dashboard-bundled-build.log`; `s7-dashboard-bundled-check.log`: three inventoried files. |
| `tests/test_cmake_check_helper.py`, `test_local_hook_template.py`, `test_local_action_wrapper.py` | `logs/s7-cmake-helper-gate.log`: 15; `s7-local-hooks-gate.log`: 3; `s7-local-integrations-gate.log`: 31 combined. |
| Candidate/assets/local tooling guards | `logs/s7-candidate-assets-accepted-gate.log`: 41. Earlier `s7-candidate-assets-final-gate.log` contains a retained failed attempt and is not the accepted result. |

Independent negative review artifacts:
`logs/s7-independent-collect-corrections-green.json` and
`logs/s7-independent-assessment-boundaries-green.json`. They verify the original
quota/cancellation reproductions, no new typed facts through reassessment, and no
upgrade of historical unverified evidence from today's matching files.

## Final acceptance and remaining claim limits

| Item | Current status / requirement to close |
| --- | --- |
| Exact final S7 candidate | **PASSED:** matching dev2 wheel/native, core closure, bundled assets, source inventory, notices and checksums retained in candidate and external proof; hashes above. |
| Fresh installed core/offline journey | **PASSED:** actual fresh install while checkout hidden; core19 distributions with optional packages/Node absent; public clean and24-command finding journeys pass. Scope remains the selected host/formats. |
| Fresh installed optional HTML/PDF/API/dashboard | **PASSED:** same fresh P/F/U report/check pins plus current gap across CLI/report/API/UI, readable/rendered PDFs; separate product and browser-tool environments. Web wheel install was pre-hide; runtime proof was hidden. |
| Complete final shared checks | **PASSED:** all15 checks and2,499 tests plus production build in `logs/s7-final-shared/check-results.json` and `s7-shared-summary.json`; no substitution from older stage totals. |
| Final source/ref identity and handoff evidence | **PASSED:** `s7-final-source-verification.json` confirms starting HEAD/branch/all refs, restored path and candidate/source-state equality. Current edits remain uncommitted; root's final handoff links exact diff/artifacts. |
| Docker/Compose | **UNEXECUTED:** unavailable in the recorded environment. Native equivalence is exercised; no Compose success claim. |
| Human usefulness / R7 product decision | **PREPARED, NOT EXECUTED:** tasks exist in `docs/verification/evaluation-tasks.md`; no outreach, participant evaluation or measurable adoption/usefulness claim. |

Actual prepared/verified paths:
`output/candidates/s7-preview/cppulse-0.2.0.dev2-linux-x86_64-candidate`,
native package directory `output/packages/s7-dev2`, and external installed proof
root `/workspace/scratch/b3d4e6fff494/s7-installed-final/`, with the exact
subdirectories and proof files listed in ledger entry4. The earlier source
actual runs used development version `0.2.0.dev1`; their historical labels remain
unchanged. The separately fresh installed runs establish the exact dev2 artifact
behavior, not a retrospective relabeling of those older source runs.

Additional explicit limits:

- Support is exercised Linux x86-64/POSIX with the recorded native toolchain;
  Windows/MinGW/MSVC/macOS are not qualified by these runs.
- Selected input/resource/package hashes establish byte identity and transfer
  integrity, not authenticity, complete host closure, loaded-runtime identity or
  complete dependency/ABI equivalence. Imports remain explicitly unauthenticated;
  they do not become current local observed assurance merely because SHA matches.
- Native rules and ranking remain experimental. An absence of selected findings
  is not a safety, certification, production-readiness or accuracy result.
- Header changes trigger current-source rejection and a full relevant cold
  recollection here. Complete dependency-aware incremental invalidation,
  hot/warm cache equivalence, runtime closure and scale budgets are not proved.
- Ordinary rename/context differences remain unknown; only the exercised stable
  predeclared-path, explicit one-to-one scoped rename is positively compared.
- No hosted action run, remote comment, GitHub write, project commit/ref update,
  deployment, publication or participant message was authorized by this checklist.
- S8 measured metrics/trends, S9 incremental/scale work, S10 richer Git/model
  evaluation, S11 IDE/MCP/free distribution, and E expansion tracks remain
  outside this S0-S7 increment. S7 AC-12 does not silently include MCP/IDE.
