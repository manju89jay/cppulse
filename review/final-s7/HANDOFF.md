# cppulse final S0–S7 handoff

Technical implementation and review are complete for the declared native local prototype journeys. At verification time, project edits were uncommitted and no project commits, pushes, ref updates, GitHub writes, merges, deployments, publication or messages had occurred. The user subsequently authorized local checkpoint commits on `codex/cppulse-local-core-20261114`; that does not rebuild or relabel the recorded candidate. No push or publication is part of this checkpoint. Temporary synthetic Git fixtures remain local and are excluded from the review archive.

## Revision and candidate

- Branch: `codex/job-application-demo-20261113`.
- Starting/current HEAD: `b89dce9d22b37ef44843a68eb3373c525b4b8e94`.
- Candidate: `/workspace/scratch/b3d4e6fff494/cppulse/output/candidates/s7-preview/cppulse-0.2.0.dev2-linux-x86_64-candidate`.
- Version: `0.2.0.dev2`; working-tree digest `e41d5d3788e5f640bd32845bf985df0f619eda8155ead264ffbb71a6fa8982a1`.
- Python wheel SHA-256: `55cf080eda016d9e3af784c59ccd9b18b07863cbcac077ea5564fb4966338026`.
- Native archive SHA-256: `16517d0c46d47f60f2c2ab80109093871f7172120df4c06621adf9f43bf6921b`.
- Source restored, every ref unchanged, and frozen source still matches the candidate: `review/autonomous/s7-final-source-verification.json`. Candidate locks, SBOM, dependency notices, file inventory and SHA256SUMS are included. This is an unpublished candidate, not a portable production release.

## Planned, achieved and remaining

| Scope | Verified result | Remaining boundary |
| --- | --- | --- |
| Existing prototype | Analyzer/CLI, Git mining, truthful ranking/scope, report dispatch and current API/dashboard stabilized; fresh four-artifact pipeline and PDF pass. | Ranking and rules remain experimental. |
| S2–S3 local core | Versioned contracts/run storage, installed namespace/resources, offline core closure and relocatable native prefix exercised. | Host libclang/LLVM/compiler/runtime remain required. |
| S4–S7 public workflows | Explicit collection, facts/policy assessment, current checks, finding baselines/SARIF, scoped coverage/sanitizers and consumer evidence; same pinned presentation across JSON/HTML/PDF/API/UI. | S6 producer qualification remains its recorded finite dialects; not every S6 matrix was rerun installed. |
| Integration | Actual opt-in CMake, local wrapper, hook framework tests and installed browser/serve checks. | Docker/Compose and hosted Action not executed; Docker absent. |
| Future stages | S8 maintainability/trends; S9 incremental caching/scale; S10 history/model validation; S11 MCP/IDE/platform distribution. | Not implemented in this core increment; VS Code extension remains an idea. |
| Expansion tracks | E1 domain/process mappings; E2 organization workflows; E3 reviewed repair; E4 additional compatibility/provenance/languages; E5 enterprise/hosting. | Future separately scoped work; human usefulness evaluation has only a prepared protocol. |

Detailed stage reviews: `review/autonomous/S1-REVIEW.md` through `S7-REVIEW.md`; current checklist and decisions are retained. Historical examples retain their original data and explicit inconsistent-total notices.

## Actual verification

**All 15 shared checks passed; 2,499 tests and the dashboard production build.** Counts below are unique within that complete run. Focused/independent gates overlap and are not added.

| Suite | Passed |
| --- | ---: |
| Root contracts/workflows | 2,040 |
| Analyzer CTest | 84 |
| CLI CTest | 20 |
| Git miner pytest | 90 |
| Predictor pytest | 98 |
| Report engine pytest | 116 |
| Dashboard tests | 51 |

Exact command vectors, working directories, exit codes and logs: `review/autonomous/logs/s7-final-shared/check-results.json`; readable command inventory: `CHECK-COMMANDS.md`. Each Python component runs `pytest -v --cov=src tests/` with canonical-package coverage added so compatibility shims do not hide implementation coverage. Native configure/build/CTest, formatting, generated checks and production dashboard build are recorded. The corrected legacy browser verifier was separately rerun after its obsolete case-sensitive label assertion failed; product content was already present.

Fresh installed proof: `/workspace/scratch/b3d4e6fff494/s7-installed-final`.
- Fresh core installs offline while the original checkout path is hidden, then runs without optional ML/PDF/web or Node. Optional PDF/web dependency/project-wheel installation occurs before hiding; all optional runtime exercises occur with source hidden. Exact site-packages origins, nineteen core/fifty web distributions and all 117 packaged file bytes were independently checked.
- All eleven top-level driver commands pass. Public native outcomes are passed/failed/insufficient evidence; current source/binary mutation returns 3. Installed finding workflow runs all twenty-four expected commands (17 exit0, 2 exit1, 5 exit3).
- Four fresh browser cases use the same three CLI/report pins plus the latest incomplete gap. Nine additional historical browser cases validate retained-store presentation, not new C++ consumer runs. All thirteen have no browser errors; product server runs without Node. Actual `cppulse serve` independently serves bundled assets/API/PDF.
- Seventy-four fresh snapshots verify contracts and all artifact hashes. Fourteen distinct retained native reports verify schemas, internal category/severity totals and relative paths. All three fresh PDFs (32 pages) pass extracted-text/bounds checks, complete rendering and visual review.
- Independent review: `installed/independent-proof-review.md` in the archive, or the same file under the external proof path. Supplemental snapshot/PDF verifiers are review harnesses, not new product features.

## Fresh artifacts

- Original full pipeline: `/workspace/scratch/b3d4e6fff494/cppulse/output/s7-legacy-demo`: findings.json, git_metrics.json, risk_scores.json, roadmap.json and report.pdf. Five findings, two files, health95.5, heuristic/not-evaluated model metadata; clean case zero findings; readable seven-page PDF.
- Installed public summary: `/workspace/scratch/b3d4e6fff494/s7-installed-final/public-web-evidence/latest-demo.json`.
- clean: **passed**; run `0a4f95db93b74db3830803512d1c0095`; PDF `/workspace/scratch/b3d4e6fff494/s7-installed-final/public-web-evidence/batches/f073d29c465e49208b038f87b1bdb8c4/clean/reports/evidence.pdf`; JSON/HTML alongside it.
- findings: **failed**; run `769e141725ec4c63b27fc25b06a005ad`; PDF `/workspace/scratch/b3d4e6fff494/s7-installed-final/public-web-evidence/batches/f073d29c465e49208b038f87b1bdb8c4/findings/reports/evidence.pdf`; JSON/HTML alongside it.
- missing-tests: **insufficient_evidence**; run `ed515ed333e94c80805ca66201755df2`; PDF `/workspace/scratch/b3d4e6fff494/s7-installed-final/public-web-evidence/batches/f073d29c465e49208b038f87b1bdb8c4/missing-tests/reports/evidence.pdf`; JSON/HTML alongside it.
- Finding baseline/SARIF journey: `/workspace/scratch/b3d4e6fff494/s7-installed-final/public-core-findings/latest-demo.json`.
- Snapshot/native verification: `/workspace/scratch/b3d4e6fff494/s7-installed-final/fresh-artifact-verification.json`.
- PDF QA: `/workspace/scratch/b3d4e6fff494/s7-installed-final/pdf-qa/verification.json`; fresh browser: `/workspace/scratch/b3d4e6fff494/s7-installed-final/installed-public-web/verification.json`.

## Reproduce the job-application demo

The recorded cloud workspace already contains the dependencies. From the repository root, load its recorded environment once:

```bash
source review/environment.sh
```

Then run this one demo command. It writes the selected output directory and uses clearly labeled local synthetic C++/Git inputs:

```bash
bash scripts/demo.sh output/demo-review
```

The broader public evidence journey is separately reproducible:

```bash
PYTHONPATH=python python scripts/demo_evidence.py \
  --analyzer analyzer-core/build/cppulse-analyzer \
  --resource-dir "$CPPULSE_CLANG_RESOURCE_DIR" \
  --fixture demo/policy-fixture --output output/review-evidence-demo \
  --scenario all --formats json,html,pdf
```

Reproduce the shared checks in a new log directory:

```bash
python scripts/check_local.py --output-dir review/autonomous/logs/review-rerun
```

To use the built candidate elsewhere, follow its INSTALL_UPGRADE_ROLLBACK.md and SUPPORT.md, verify SHA256SUMS, install its core wheel closure with `--no-index`, and set CPPULSE_NATIVE_PREFIX to the matching extracted native prefix. Optional PDF/web closure metadata is in the review archive; its actual 48-wheel local wheelhouse is `/workspace/scratch/b3d4e6fff494/s7-optional-wheelhouse`. Use that hash-locked closure for the recorded CPython3.12/Linux environment. Host dependencies remain required. The copied installed harnesses need no PYTHONPATH.

## Five-minute interview walkthrough

1. Open the small synthetic clean/intentional C++ fixture and state the declared scope. Run the original pipeline and explain the five finding records and four validated JSON artifacts.
2. Open the seven-page PDF and dashboard. Show that zero-risk clean code is not presented as a hotspot; health is a versioned descriptive calculation and ranking is experimental.
3. Show the installed public clean, rule-failure and missing-test-report cases. Tests can pass while a selected rule fails; an absent report remains insufficient evidence.
4. Open the pinned JSON/PDF/API result. Change a header or binary and show the new incomplete attempt rather than a recycled passing decision.
5. Show line-insertion baseline matching, known-new failure and ambiguous-anchor unknown, then the actual SARIF artifact. End with the limits below.

## Environment and limits

Actual environment: Linux x86_64/glibc2.41, GCC14.2, libclang19.1.7, CMake/CTest3.31.6, Python3.12.14, Node24.22.1 and Chromium156.0.8078.79. PDF rendering uses bundled Poppler26.05.0; the system pdftotext reports25.03.0. Exact argv/results and Python inventories: installed/environment-final.json and package manifests; initial dependency acquisition/setup is retained in review logs and environment.sh.

Docker executable/socket are absent: Compose/container execution has **not passed**. No Windows/macOS or other toolchain qualification, complete runtime closure, production/safety/certification/accuracy claim, model predictive validation, performance benchmark or human adoption evidence is made. Transfers preserve unauthenticated imported claims. Current finding demos fully recollect; no incremental analysis claim. No remote service was created or contacted for CI/publication.

## Review bundle

The patch includes tracked edits and every new non-review/non-output project source, including bundled assets and reference schemas. It is validated by applying to a Git archive of the exact baseline and comparing reconstructed bytes with the working tree. `patch-verification.json` records the result. The ZIP contains this patch, check logs, candidate, selected fresh artifacts, reports/screenshots and review records. It excludes Git metadata and temporary fixture repositories, host toolchains, optional wheel payloads and repeated large raw snapshot payloads; full evidence stores remain at the explicit workspace paths. `review-bundle-manifest.json` records each included file hash and this selection.
