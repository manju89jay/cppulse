# cppulse project overview

Updated: 2026-11-14. Current source version: **0.2.0.dev2**.
Positioning: an AI-assisted engineering prototype for job applications.

## Application paragraph

I am building cppulse with AI-assisted implementation and verification: a local
C++ analysis and engineering-evidence prototype combining a C++17/libclang
analyzer, Python Git-history analysis, experimental ranking, explicit build/test
collection and scoped policy checks. Its CLI, immutable JSON artifacts, reports,
FastAPI API and React dashboard make findings, failed checks and missing evidence
inspectable. The project demonstrates compiler tooling, native/Python integration,
contract design, testing and careful interpretation of verification results.
Ranking accuracy, production readiness and safety or certification claims remain
unproven; I describe my contributions and AI assistance explicitly.

## What is implemented

| Area | Current behavior |
| --- | --- |
| Native C++ analysis | 22 experimental checks for memory-related patterns, modernization, complexity and selected coding rules; libclang parsing with CRTP/`std::variant` dispatch and explicit parse/rule-consideration status |
| History and ranking | Current-file Git churn/contributor signals, explicit unavailable/partial history, profile-aware score/model metadata and optional ML with a heuristic fallback |
| Evidence collection | Explicit finite source inventory, contexts and argv recipe; retained command/output identities, bounded capture, cancellation and selected native/test/coverage/sanitizer/import normalization |
| Policy and findings | Current-time assessment/reassessment, distinct passed/failed/insufficient-evidence gates, scoped finding baselines/regression checks and checked SARIF export |
| Provenance and reuse | Hash-bound immutable local snapshots, separate latest-attempt gaps, bounded transfer and upstream/local consumer comparison with imported claims kept separate from local proof |
| Presentation | Historical explain and JSON/HTML/PDF evidence reports; API/dashboard views of the same retained facts and assessment, including missing or incomplete material |
| Local integration | Shared local checks, optional explicit CMake/hook/action-wrapper checks and a packaged dashboard served by the optional Python web API; Node is a build dependency, not a dashboard runtime requirement |

`collect` executes only the explicit recipe. Assessment, checking, comparison and
rendering add no hidden build or test commands. A completed collection is not a
policy pass. Current checks verify the selected source and every recorded finite
generated output before publication; a replaced binary cannot inherit its old
tests. Reassessment recomputes expiry while retaining original facts and exact
historical decisions. Historical reports remain historical and perform no fresh
source check.

Finding baselines select files, jobs and rules explicitly. Ambiguous line anchors,
changed contexts and incomplete analysis remain unknown. A finding-regression
pass is separate from an evidence-policy pass. Compatible imported consumer
evidence does not replace application tests or authenticate an upstream producer.

## Fresh verified source behavior

The S7 shared local run passed **all 15 checks and 2,499 tests**, plus the dashboard
production build. These are executed regression checks, not a completeness or
accuracy metric:

| Suite | Passed |
| --- | ---: |
| Root contracts, workflows and integration regressions | 2,040 |
| Analyzer CTest | 84 |
| CLI CTest | 20 |
| Git miner | 90 |
| Predictor | 98 |
| Report engine | 116 |
| Dashboard | 51 |

Exact commands, exits and logs are recorded in
[the S7 shared results](../../review/autonomous/logs/s7-final-shared/check-results.json).

The fresh legacy demo in `output/s7-legacy-demo/` produced five findings across
two files, no findings in its clean file, a 95.5 descriptive health score and a
readable seven-page PDF. That explicitly synthetic input uses the heuristic
model. Health uses weighted findings per attempted current file
(`weighted-findings-per-attempted-file-v2`), not KLOC; full-scope health is
unavailable for absent scope or partial parsing. Health and ranking do not supply
the evidence-policy gate.

The public CLI's actual C++ demo separately demonstrates one passed, one failed
and one insufficient-evidence policy case. Its result is
[the current public-evidence summary](../../output/public-evidence-demo/latest-demo.json),
with 22 verified snapshots recorded by
[the read-only artifact audit](../../review/autonomous/logs/s7-public-evidence-artifact-audit.log).
It also exercises stale source/output checks and preserves the earlier pinned
historical result instead of showing it as current green evidence.

The actual native finding workflow retained 24 command records and 43 checked
snapshots, covering baseline/new/unchanged/unknown behavior and SARIF. See
[the finding audit](../../review/autonomous/logs/s7-actual-native-findings-audit.json)
and [snapshot verification](../../review/autonomous/logs/s7-native-findings-snapshots-verified.json).
These are labeled synthetic C++ scenarios executed by real native tools, not a
benchmark against representative production defects. The actual API/browser
source check passed nine selected views, including failed, partial and missing
local-check cases; evidence is in
[the web verification log](../../review/autonomous/logs/s7-web-source-actual.log).

## Reproduce and explain

After the README setup, run `bash scripts/demo.sh` for the original four-document
analysis/report demo. Use the [public command guide](../development/public-cli.md)
for collection, assessment, policy/finding checks, comparison, evidence reports
and SARIF. The [demo walkthrough](demo-verification.md) and
[policy walkthrough](../../review/autonomous/POLICY-DEMO.md) provide interview
context; earlier checkpoint details in them must be read with their recorded
revision and artifact pins.

The starting checkpoint is `b89dce9d22b37ef44843a68eb3373c525b4b8e94` on
`codex/job-application-demo-20261113`. Current stabilization and staged additions
are saved on the local review branch `codex/cppulse-local-core-20261114`. Source test success does not establish the final
installed dev2 candidate: exact installed-wheel/native-prefix acceptance is
recorded separately in [S7 review](../../review/autonomous/S7-REVIEW.md) when completed. No final
dev2 installed proof is asserted here.

## Maturity and boundaries

S7 public workflows and presentation are implemented and source-verified. The
qualified cloud environment is Linux x86_64, Python 3.12.14, glibc 2.41, GCC 14.2
and libclang 19. Python 3.11 is in the declared package range but is not qualified
by this host's execution. Docker/Compose was unavailable; its definitions are not
an observed Compose pass. Windows/macOS, other compiler combinations and broad
production workloads remain unqualified.

Pinned fmt 10.2.1 and utfcpp 4.0.5 plus a small consuming application provide
selected real-input evidence. They are not full upstream test-suite results or
a detector-accuracy benchmark. Optional module/C++20 cases, unsupported sanitizer
runtime cases and incomplete dependency/context proof remain visible limitations.
The finite identities do not establish the complete host dependency closure or
producer authenticity. MISRA-labeled checks are selected patterns, not a
compliance assessment.

Earlier S1–S6 reviews and the frozen dev1 installation remain useful historical
evidence for their exact artifacts. They are not proof for current dev2 bytes.
Historical example totals have inconsistencies and must not be reused as
benchmark, accuracy, production or safety claims. Preserve draft context and
explain authored decisions, reviewed changes and AI assistance honestly.

Repository: https://github.com/manju89jay/cppulse
