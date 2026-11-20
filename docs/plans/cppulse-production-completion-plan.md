# cppulse: full production-specification completion plan

Prepared: 2026-11-14. Status: full-scope plan for review, not an implementation or release claim.

## 1. Authority, scope and the completed push

This plan responds to the instruction to push the saved changes first, then plan
completion of the full production specification without drift or narrowing.
It supersedes the S0–S7 stopping boundary in the earlier staged plan. S0–S7 is
historical delivered work, not the endpoint of this program.

Authoritative inputs, preserved unchanged:

- docs/specs/production-platform/requirements.md, specification 1.0.
- docs/specs/production-platform/tasks.md, all M0–M9 tasks.
- docs/specs/production-platform/design.md, including unnumbered obligations.
- TASK_SPEC.md and AGENTS.md operating/build-order rules, subject to the user's
  later instructions.

The traceability inventory contains **118 numbered requirements/journeys/
acceptance items and all 60 milestone tasks**, plus nine separately identified
design/environment obligations, including explicit Docker/Compose qualification. Every item must remain assigned and visible.
The original classification of advanced features as optional or expansion work
is preserved; it does not remove them from this completion plan.

Release A, B, C and expansion releases are delivery checkpoints within the
program. Delivering an early useful release does not close the remaining scope.
Dropping, substituting or deferring an item requires an explicit recorded user
decision. Lack of access produces an open blocker, not a smaller specification.

The existing work was uploaded before preparing this plan:

- Repository: https://github.com/manju89jay/cppulse
- Branch: codex/cppulse-local-core-20261114
- Remote tip: 15492dbfcbc6b20d938e42e760486da4181035f6
- Thirty focused commits, authored and committed as Manjunath Jayaramaiah,
  with no co-author trailers.
- The Git CLI lacked write credentials. The connected GitHub account recreated
  the same thirty changes using current server timestamps. Every uploaded tree,
  message, identity and parent sequence was verified after fetching the branch.
- Original local tip 576c5c4eed9a3ce2069a529fe9dfa27f4809bb1f is retained on
  codex/cppulse-local-core-20261114-original and in the original Git bundle.
  Commit hashes differ between these histories; source trees are identical.
- The starting job-application branch remains at b89dce9d22b37ef44843a68eb3373c525b4b8e94.

## 2. Honest starting state

The current deliverable is a verified Linux local preview, version 0.2.0.dev2.
It is not the completed production platform or a published binary release.

| Existing capability | Reuse and remaining qualification |
| --- | --- |
| Native analyzer and CLI | Preserve the 22 existing rules, corrected identities, parse/context facts and explicit missing scope; extend representative language, accuracy and platform coverage. |
| Installed local package | Reuse the wheel/native archive, canonical namespace, optional runtime separation and outside-checkout proof. Complete the promised support matrix and release tooling. |
| Evidence and policy | Reuse explicit recipes, typed observations, immutable runs, supported test/coverage/sanitizer adapters and six evaluator predicates. Add missing metric/review controls and wider qualification. |
| Baselines and SARIF | Reuse per-occurrence comparisons and conservative line/rename handling. Symbol/token identities, dependency-aware incremental work and scale remain unfinished. |
| Reports/API/dashboard | Reuse one checked snapshot and matching reports. Basic legacy page/filter support exists; indexed history and bounded snapshot queries remain unfinished. |
| Local integrations | Reuse CMake, hook and workflow adapters. Docker/Compose and advertised hosted execution still need actual proof. |
| Measured intelligence | Existing scores/history/ranking are limited and experimental. Complete the specified metrics, density/context scorer, trends, behavioral analysis and model evaluation. |
| IDE/agent clients | VS Code, MCP and the clean-session portable skill have not been implemented. |
| Organization/advanced features | M8 and M9 remain open work with provider, language, repair and hosting decisions to specify. |

The saved implementation passed fifteen shared checks, 2,499 tests and the
dashboard production build. The earlier installed proof verifies its exact
candidate bytes. These are evidence for that subset, not a percentage of
production completion. Do not rewrite old candidate hashes, dates or tests to
label them as new release evidence.

## 3. Delivery phases and reviews

Every package inside every phase follows:
contracts → producers → consumers → presentation → orchestration → integration.
Affected component checks pass before dependent work. Independent packages may
run concurrently after their contract gates; one owner controls Git integration.

| Phase | Deliverable and dependencies | Review/exit gate |
| --- | --- | --- |
| P0 | Freeze full scope, evidence baseline, decisions and execution environments. | R0: every source item mapped, no omissions or hidden scope substitutions; blockers have owners. |
| P1 | Finish foundation, developer tooling, friendly CLI, generators and real container workflow. Depends on P0. | R1: documented commands and generator paths execute; Docker pipeline and failure/repeated-run cases actually pass. |
| P2 | Initial actual VS Code extension. Depends on installed core/client contracts, not completion of every later feature. | R2: installed VSIX in a real extension host; diagnostics, navigation, explicit commands, stale/cancel cases and shared-result agreement pass. This is an early slice, not full M7 completion. |
| P3 | Measured metrics, specified scorer, trends and six-project corpus. Depends on foundation contracts. | R3: independent measurements/score calculations, context prerequisites, compatible trends and reviewed real cases agree. |
| P4 | Complete evidence/policy capabilities and reviewed domain starter mappings. Depends on typed metric producers where needed. | R4: complete evaluator semantics, real producer/consumer matrices and reviewed edition-bound packs; unresolved reviews remain blocked. |
| P5 | Bounded execution, dependency cache, resumability, indexed history and scalable queries. Depends on stable fact identities. | R5: clean/cached/resumed semantic equality and crash/resource/query invariants pass before speed claims. |
| P6 | Rich Git, ownership, coupling and architectural/symbol history. Depends on P3/P5 identities and history storage. | R6: controlled histories and real projects reproduce the defined metrics without hidden attribution assumptions. |
| P7 | Optional risk-model evaluation and calibration. Depends on frozen history/metric features and labels. | R7: actual chronological/project holdouts, baselines and calibration report; poor results remain visible rather than fabricated probabilities. |
| P8 | Complete VS Code, MCP, portable skill and reusable integration distribution. Extends P2 after producer/query gates. | R8: same pinned result through every client, actual MCP and clean-agent execution; later product features exposed consistently. |
| P9 | Full platform, scale, installation, compatibility and core-release qualification. Depends on the relevant P1–P8 features. | R9: actual named-host/artifact matrix, 1K/10K/100K workloads, all release scenarios, real developer tasks and exact candidate proof. |
| P10 | Organization/portfolio/delivery/provider features, all M8 tasks. Depends on qualified metrics/history/query contracts. | R10: real multi-project/provider scenarios, identity changes, scheduling and delivery outcomes; estimates remain distinct from observations. |
| P11 | Deterministic fixes and bounded semantic/AI repair, M9-01/02. Depends on explicit transformation and behavior contracts. | R11: reviewable/idempotent patches and language-specific behavior checks; no automatic commit/PR approval is inferred. |
| P12 | API/ABI, fuzzing, dependency/process evidence and additional languages, M9-03/04. | R12: actual supported-tool/version/language clean/failure/unsupported matrices; schemas alone are insufficient. |
| P13 | Enterprise identity and optional managed hosting, M9-05. Depends on an approved provider/access/operating design. | R13: real access/isolation/storage/backup/upgrade tests and cost/ownership review; deployment is a separate authorized action. |
| P14 | Whole-program acceptance and separately authorized release/submission actions. | R14: every retained item has its required evidence or an explicit user-approved scope decision; exact artifacts and listing claims agree. Preparing an archive is not publication. |

P2 can proceed while independent P3/P4 work continues. P5 must pass before
large-input claims or final scalable client acceptance. External blockers in one
track do not halt unrelated work, but cannot be erased from the completion ledger.

## 4. Concrete work and acceptance by phase

### P0: scope, decisions and environments

1. Preserve source hashes and the complete requirement/task inventory. Bind each
   item to delivery phases, remaining work, evidence and a review gate.
2. Inventory actual Linux/Docker, Windows MinGW, Windows MSVC and macOS access.
   Distinguish compiler, libclang, Python, CMake, editor and optional runtime
   versions. Provision only through authorized environment/infrastructure paths.
3. Resolve the decision register below before dependent implementation. Open
   provider/language choices remain explicit work, not permission to omit them.
4. Agree metric definitions, corpus/sample review, usefulness tasks and benchmark
   methodology before choosing results or promotion thresholds.

Evidence: frozen inventory, access checks, dependency/support matrix, decisions,
complete traceability and the current implemented/partial/not-started baseline.

### P1: finish the engineering and container foundation

1. Close remaining M0 correctness/scope cases across the declared language and
   platform inputs; audit newer upstream changes before reuse, without blind merging.
2. Add one documented cross-platform development facade for doctor, changed/full
   verification, new rule/adapter/policy, benchmark, package and release dry-run.
   Reuse CTest, pytest, dashboard tools and shared local scripts.
3. Complete registry-driven native registration/integration generation, meaningful
   extension fixtures and promotion/version rules. A generated stub is unfinished.
4. Finish concise human-default CLI output and deliberate machine formats,
   compatibility aliases, config precedence, cancellation and actionable errors.
5. Complete install/CPack/container packaging paths, locked updates, generated
   documentation, changelog and release-note preparation; reuse existing CI only.
   Resolve the specified optional Git/risk dependency boundary: qualify static
   analysis with neither a Git repository nor a Git executable/GitPython present,
   and isolate optional heavy history/model dependencies where promised.
6. Run actual Compose with synthetic and real inputs, host binds and named-volume
   extraction, one-shot success, producer failure, missing/corrupt output, repeated
   runs, shutdown and API/dashboard/PDF interaction. Record Docker as blocked
   until a usable runtime executes these cases.

Evidence: real commands, before/after regressions, installed generator example,
container logs/output extraction and no reliance on a successful one-shot
service remaining alive.

### P2: ship a reviewable VS Code preview

1. Define the shared client capability/version, result-selection and execution
   contracts. Use public CLI/SARIF/snapshot interfaces, not internal imports or
   an editor-specific scorer.
2. Build an extension manifest/project and actual VSIX. Display per-occurrence
   findings in Problems, navigate to file/line, select a retained run and show
   scope, gate, gaps, report and original-evidence links.
3. Add explicit user commands for doctor/analyze/collect/check/report and request
   selection, progress and cancellation. Opening/reading a project executes no
   recipe and silently refreshes no historical assessment.
4. Test a fresh real extension host with the installed analyzer/CLI and actual
   clean/finding/missing-evidence fixtures. Cover equal basenames, spaces/quotes,
   UTF-8 and non-BMP coordinates, unsaved/stale source, delayed responses,
   incompatible versions and absent optional runtimes.
5. Qualify the preview's finite tested workload; retain indexed-query and full
   platform obligations for P5/P8/P9. Do not mark all M7 complete from this preview.

Evidence: installable VSIX, extension-host transcript/screenshots and matching
CLI/API/editor pins and values. Native UTF-8 bytes, SARIF column kind and editor
character units require tested conversion. Marketplace submission is separate.

### P3: real metrics, design-compliant scoring, trends and corpus

1. Version function/file LOC, length, cyclomatic complexity, nesting, parameters,
   duplication and validated cohesion/compound-smell observations. Define
   template/macro/context counting and unavailable metrics explicitly.
   Define stable symbol/normalized-token/occurrence identities and a versioned
   baseline migration with overload/template/macro and collision cases. Preserve
   the existing native and exact-line strategies rather than silently claiming
   that their rename/token behavior has become more general.
2. Implement the design's analyzed-KLOC density/caps/weights and per-required-
   context health; present the worst fully evaluated required context and make
   full-scope health unavailable when required context is missing.
3. Preserve the current attempted-file-v2 method as a versioned historical method.
   Add an explicit scorer/compatibility decision and migration; do not silently
   relabel old results or continue incompatible trends.
4. Compute measured hotspots and precise roadmap fact links; retain estimates
   as estimates. Add history, function drill-down, critical-code markers,
   comparisons and debt goals with scope/method-version compatibility.
5. Pin and freshly analyze the six ORIGINAL examples with real history:
   fmt, grpc, json, leveldb, poco and protobuf. Keep utfcpp as an additional
   consumer example. Preserve historical inconsistent examples as historical;
   do not reuse their totals or substitute another six without approval.
6. Maintain positive/clean/boundary and relevant template/macro/multi-context
   fixtures per rule/metric, with independent hand-counted samples and actual
   false-positive/missed-case review across the corpus.

Evidence: raw contexts/measurements, independent score calculations, explicit
old/new method comparison, real pinned output and published review methodology.

### P4: finish policies, evidence and domain packs

1. Add typed numeric-metric thresholds and reviewed-evidence/attestation controls
   after their producers/contracts. Preserve the four outcomes, separate exact
   score numerators/denominators, gate precedence and scoped expiring deviations.
2. Broaden and qualify the declared producer/version/context matrix; retain exact
   coverage kinds, test states, sanitizer instrumentation/runtime scope, external
   namespaces and incomplete/mismatched-source handling.
3. Complete compiled/header-only consumer cases, required instantiations,
   self-containment, missing variants and distributed-package applicability.
4. Supply general C++/library and custom-organization policies, then automotive
   and medical starter mappings reviewed against authorized pinned editions.
   Record coverage, unassessed obligations, reviewer and maturity. No licensed
   standard text reproduction, certification or inferred safety classification.
5. Exercise fail/unknown despite high averages, unsupported predicates, review
   expiry, modified artifacts, foreign claims, zero/skipped tests and unavailable
   coverage. A data schema or process exit cannot supply missing verification.

Evidence: independent formula examples, actual producer/consumer failures and
gaps, edition-bound review records, and the same controls across every interface.

### P5: correct incremental execution and scale infrastructure

1. Complete bounded worker isolation, configured jobs, wall/CPU/memory/output
   limits, large-file policy, cancellation and independent-unit fault retention.
2. Separate extraction and assessment caches. Key reuse on source, dependency,
   context, detector/configuration and tool identities. Unknown dependency
   identity forces conservative invalidation; newly enabled rules require facts.
3. Handle source/header/macro/flag/sysroot/generated input/dependency/tool edits,
   policy-only changes, history append, rewrite and shallow boundaries.
4. Add resumable checkpoints, bounded aggregation, reusable streamed Git records,
   indexed local run/history catalog and migrations/recovery.
5. Provide immutable-run/query-bound pagination cursors, search/filter/history
   APIs and bounded dashboard/editor/MCP queries. Preserve compatible legacy
   routes; basic current pagination is not an indexed large-project solution.

Evidence: clean/cached/resumed semantic equality before timing claims; actual
worker crash/timeout/cancel/write interruption/resource exhaustion, concurrent
read/latest races and migration tests. No stale positive may survive invalidation.

### P6: behavioral intelligence

Implement aliases, bots, pair attribution, former contributors, time windows,
rename/merge semantics; supported coupling with bulk/generated exclusions;
weighted ownership/familiarity, fragmentation, knowledge maps and offboarding
scenarios; user-defined architectural aggregation and symbol/function history.
Keep historical co-change separate from static dependencies. Reuse P5 history.

Evidence: known controlled histories plus real projects; all denominators,
identity changes, shallow/rewrite limitations and time cutoffs are inspectable.
Authorship remains a knowledge proxy, not an individual performance judgment.

### P7: evaluate the optional predictive model

Freeze label/feature provenance, availability times and cutoffs. Execute
chronological holdouts, project-generalization checks, imbalance-aware baseline
comparisons and calibration where probability claims are considered. Version
model artifacts/features and provide truthful fallback/not-evaluated behavior.
Remove or migrate misleading probability field names where necessary.

Evidence: actual reproducible evaluation report and limitations. Evaluation can
show that a model is not useful; fabricate no accuracy, improvement or calibrated
probability to satisfy a release label. Keep local core usable without ML.

### P8: complete developer and agent integration

1. Extend the initial VS Code client to all promised measured/history/consumer/
   policy features using the bounded queries and public capabilities.
2. Implement real local MCP tools for run status, health, explanations, findings,
   hotspots, policy gaps, rule/policy documentation and bounded original-artifact reads. Separate explicit
   execution capability from read-only tools; test a real MCP client.
3. Package reusable CMake, hook and Git-host templates and actual application/
   library examples. Qualify advertised hosted/container paths independently.
4. Build the versioned free text skill as one SKILL.md plus necessary text
   references, version information and license, using released commands only.
   Execute it in a clean agent session with installed artifacts, no source
   import/bootstrap and absent optional extras. Reading text installs no binary.
5. Compare one actual selected snapshot through CLI/API/JSON/HTML/PDF/dashboard/
   MCP/editor for identical underlying values, identities, gaps and evidence links.

Evidence: actual extension-host and MCP sessions, clean-agent transcript and
all ten client scenarios in the
[IDE work packages](cppulse-ide-production-work-packages.md).
AC-12 and AC-16 stay open until these actual executions exist.

### P9: platform, workload, release and usefulness qualification

1. Install and execute final artifacts on Linux x86-64 with actual GCC AND Clang/
   libclang combinations, Windows MinGW, Windows MSVC and macOS as distinct
   lanes. Include promised Python versions, analyzed C++17/C++20, native C++17,
   CMake presets/consumer minimum decision and editor/runtime versions.
2. Qualify loader/runtime dependencies, path/case/separator collisions, optional
   absence, offline operation, outside-checkout use, clean install, upgrade,
   rollback, previous supported schemas/config/baselines and migration failures.
   Include static-only installation without GitPython or a visible Git binary,
   not merely analysis of a directory without a .git folder.
3. Run approximately 1K, 10K and 100K-file tiers and representative histories on
   named hosts. Include cold/warm/source/shared-header/context/dependency/tool/
   policy/history edits; repeat measurements, not one favorable sample.
4. Record wall/CPU time, peak memory, completeness, work units/cache hits and
   environment. Set numerical regression budgets from measured baselines
   BEFORE treating the optimized candidate as acceptable; investigate repeated
   breaches. Include PDF/ML and query costs rather than measuring AST time alone.
5. Execute AC-01–16 and the declared support matrix against exact installed
   artifacts. Complete real maintainer/consumer installation and interpretation
   tasks with consent and actual outcomes; prepared tasks are not user validation.
6. Assemble Release A/B/C candidate packets from qualified completed features.
   Earlier release checkpoints do not complete P10–P14 or remove those tasks.
   This phase qualifies candidate execution; AC-16's released-command closure
   and actual submission/publication states remain open until P14.

Evidence: actual host/artifact logs, semantic equivalence, repeated workload
results, compatibility matrix and real task review. Missing hosts/runtime or
participants remain open blockers; cross-compilation and mocks are insufficient.

### P10: all organization and portfolio work

Specify provider/data contracts, then implement all M8 tasks: team alignment and
fragmentation, multi-repository portfolio/goals/scheduled reports, branch/delivery
analytics with task linkage, issue-tracker cost/ROI views, and report/notification
integrations. Preserve per-project access, method/version and missing-data scope.
Keep observed costs/outcomes separate from estimates. Define retry/idempotence,
time zones, permissions and delivery results before external effects.

Evidence: controlled team changes, real multi-repository aggregation, provider
contract plus actual configured integration, scheduling/retry and report results.
Sending messages or changing external trackers requires explicit authorization;
unit mocks or dry-run outputs cannot be labeled successful real delivery.

### P11: controlled fixes and semantic repair

Define supported transformations/languages and acceptance first. Implement narrow
deterministic dry-run patches with source pins, precise edits, idempotence,
clean counterexamples and compile/test verification. Then implement the bounded
semantic/AI-assisted repair and PR-preparation workflows with behavior evidence,
failure/recovery and clear unverified cases.

Evidence: reviewable diffs, actual before/after language-specific behavior tests,
ABI/performance checks where relevant and rollback/no-op cases. AI suggestions
are not proof of semantic equivalence. Commits, PRs and external model use/costs
are explicit configured actions; preserve offline local analysis independently.

### P12: additional evidence and languages

Specify and implement actual supported API/ABI, fuzzing and dependency/provenance/
requirements/process adapters. Preserve producer versions, execution scope,
unsupported cases and authentication/claim distinctions. Select and approve the
additional language set, then deliver its producer, metrics/rules, contracts,
calibration, installation and complete interface integration.

Evidence: real clean/failure/unsupported tool and language cases, not only
generic wrappers/schemas. Do not infer ABI compatibility, security or language
coverage from an unrelated C++ test. Undefined language/tool selection remains
an open decision with no automatic deletion of M9-03/04.

### P13: enterprise identity and hosting

Complete the provider/runtime and operating-cost sub-specification, then
implement SSO/RBAC and project/tenant authorization over every API/download/
catalog path, identity lifecycle, storage/retention, secret handling, backup/
restore, deletion, upgrades/rollback and operational diagnostics.

Evidence: actual identity/provider and multi-tenant allow/deny/isolation tests,
storage/restore/migration results and an owned operating-cost/access review.
Keep the local account-free product independent. Deployment and operating spend
require separate authorization after a concrete tested candidate exists.

### P14: close the whole specification and release honestly

Reconcile every inventory item with accepted evidence. No unresolved required
item becomes complete merely because a phase demo works or a test total grows.
Retain original optionality and all explicitly approved scope decisions.

Repeat applicable full checks, installed scenarios, compatibility and measured
budgets on the EXACT final artifacts; retain hashes, source/version/config,
SBOM/notices, changelog, support/maturity table and upgrade/rollback guidance.
Prepare VSIX/MCP/skill/binary/container release and marketplace materials.

Track preparation, verification, authorization, submission, review and actual
publication separately. Tag/publish the already verified artifact rather than
rebuilding an untested release. No marketplace submission, deployment, outreach
or message is implied by the current instruction to push a Git branch.
After authorized distribution, repeat the clean-session skill journey using
the released artifact's exact bytes and documented released commands to close
AC-16; candidate preflight alone cannot close that release condition.

## 5. Decisions and access that cannot be invented

| Decision/input | Needed for | Required handling |
| --- | --- | --- |
| Actual Docker and Windows/macOS hosts; compiler/runtime versions | P1/P9 and affected integrations | Obtain usable authorized environments; record executed lanes or explicit blockers. |
| Density scorer caps/weights, context prerequisites and legacy migration | P3 | Review measured method and record versioned decision; do not silently retain a different scorer as equivalent. |
| Metric definitions, promotion thresholds, corpus and usefulness protocol | P0/P3/P9 | Freeze methodology before results; preserve the six original projects. |
| Benchmark host, workloads and measured release budgets | P5/P9 | Measure and review; retain all required tiers rather than shrinking workload to fit. |
| CMake consumer minimum and supported Python matrix | P1/P9 | Resolve current helper 3.21 versus proposed 3.16 where feasible; exercise promised combinations and document decisions. |
| Authorized standards editions and qualified mapping reviewers | P4 | No fabricated clauses or review claims; incomplete review blocks that pack's acceptance. |
| Organization/task/issue/notification providers and cost definitions | P10 | Produce approved provider/data sub-specifications; actual delivery requires authorization. |
| Supported repair transformations/model provider and behavior criteria | P11 | Bound implementation and evidence; model/API charges and PR writes remain explicit. |
| Additional language(s), ABI/fuzz/provenance tool versions | P12 | Specify concrete supported scope; keep the requirement open until delivered and validated. |
| Hosting model, IdP, access ownership, budget and retention | P13 | Review architecture/cost/access before real deployment; test implemented controls. |
| Release/marketplace accounts and publication approval | P14 | Finish reviewable artifacts first, then obtain the separate required authorization. |

## 6. Reviews, progress and anti-drift controls

- Each item has a current status, remaining work, delivery phases, evidence and
  review gate in the traceability files. Planning coverage is not completion.
- Use distinct states: not started, implementing, implemented/scoped, technically
  verified, product-reviewed, release-prepared, submitted/published, or blocked.
  A blocked/skipped requirement stays open with its owner and unblock condition.
- Each review packet contains a requirement delta, focused diff/commits, exact
  commands/results, actual artifacts, compatibility/resource impact, limitations
  and next unfinished items. Show counterexamples as well as favorable demos.
- Technical self-review and real user/product review are separate. Neither
  substitutes for the other or silently changes acceptance.
- At every phase gate and before reporting completion, compare the live source
  IDs against the frozen inventory. Any missing/unassigned item fails the review.
  Run the portable consistency check from the repository root:

  ~~~bash
  python docs/plans/verify_production_plan.py
  ~~~

  It checks planning coverage and preserved source text/hashes, not whether an
  implementation or release passed.
- Preserve draft and prior evidence context. Never relabel old output, training
  metrics, benchmark data, candidate hashes, authorship or timestamps as new proof.
- Reversible implementation proceeds autonomously within the accepted scope
  and contract gates. Ask only for genuine access or decisions; do not use a
  missing provider/host to stop independent work or discard a requirement.
- Keep commits focused and short, with the user's requested Git identity and no
  co-author trailer. Use shared local verification; no new external CI service.
  Do not force-push, merge, deploy, publish or message others without authorization.
- Report completed work and remaining production scope separately. Never use
  “production complete” to mean “the current local core increment passed.”

## 7. Traceability and next executable increment

The companion [JSON traceability](production-completion-traceability.json) and
[CSV traceability](production-completion-traceability.csv) preserve every
original requirement/task text, source line, baseline status, gap, owner phase,
evidence and acceptance gate. Source SHA-256 values bind the input specification.
Nine additional design/environment obligations are tracked separately; they
do not replace the numbered items.

The next increment is P0/P1 closure plus P2 client contracts and a real installed
VSIX, while independent P3 metric/scorer contracts are prepared. That scheduling
choice does not remove or defer the remaining P3–P14 work. Review the full plan
and decision/access register before beginning new production implementation.

This planning pass changes documentation only. No new product feature, extension,
benchmark, container qualification, external message or release is claimed.
