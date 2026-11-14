# cppulse staged implementation and review plan

> Scope update, 2026-11-14: the user now requires completion planning for the
> FULL production specification without narrowing. The earlier S0–S7 execution
> limit below is historical and is superseded by
> [the full production completion plan](cppulse-production-completion-plan.md).
> All M0–M9 tasks remain tracked; later releases are not a stopping boundary.

Date: 2026-11-13. Status: Core S0-S7 authorized for autonomous execution; later stages remain roadmap items.

The subsequent autonomous-execution instruction replaces manual blocking reviews for the core track with technical self-reviews and retained review packets. Genuine access blockers and external publication decisions remain separate.

cppulse currently has a tested native analysis demonstration. The next goal is an installable local tool that can tell a C++ maintainer or consumer which declared configurations have usable verification evidence, which checks failed, and what remains unverified. The roadmap preserves the existing analysis product, delivers a small collection-and-assessment workflow early, and accounts for the broader maintenance, integration and organization backlog separately.

This planning pass reviewed the retained verification records and current source. It did not rerun the application suites or implement new product functionality. The execution evidence below belongs to the completed stabilization run.

## 1. Current state

### Source and delivery state

| Item | Current state |
|---|---|
| Repository | manju89jay/cppulse |
| Working branch | codex/job-application-demo-20261113 |
| HEAD and starting checkpoint | b89dce9d22b37ef44843a68eb3373c525b4b8e94 |
| Stabilization changes | Present in the cloud working tree, uncommitted |
| Main inspected during stabilization | 82120d26b51f99b64068f9d66f6e000fcaee97c2; not a claim about today's remote head |
| Verified environment | Linux x86-64; GCC 14.2, libclang 19.1.7, CMake 3.31.6, Python 3.12.14, Node 24.22.1, Chromium headless 156 |
| Distribution | Source-checkout workflow; no verified portable installed release |
| Docker | Definitions corrected, but no Docker executable/socket was available for execution |
| Remote state | No stabilization commits, pushes, ref updates, GitHub writes, deployment or publication |

Detailed evidence: [stabilization handoff](../../review/HANDOFF.md), [demo verification](../portfolio/demo-verification.md), and the retained files under review/logs/ and output/demo/.

### Implemented functionality and its limits

| Capability | Implemented and demonstrated | Remaining work |
|---|---|---|
| Native C++ analysis | C++17/libclang analyzer, closed CRTP/variant rule set, 22 built-in checks, JSON findings | Representative precision/false-positive cases; scope, headers, variants and unsupported syntax; no complete memory-safety or standards-compliance claim |
| Build configuration | JSON/simple YAML, exclusions, rule switches/thresholds, compilation-database support and fallback parsing | Consistent effective configuration and full argument/context validation; tested distinction between exact, inferred and fallback contexts |
| File identities and counts | Repository-relative findings, legacy static/Git path join fixes, physical LOC correction | Renames/deletions, external inputs, separators/case collisions, symlinks, generated/vendor scope and baseline multiplicity |
| Analysis completeness | Per-file parse status, compile-context label, diagnostic error count and enabled-rule list | General execution evidence, full rule-execution facts, every required header/configuration and sound score prerequisites |
| Git mining | Churn, frequency, age, contributors, single-contributor alerts, SZZ-like labels; shallow-boundary helper | Optional no-Git journey, current versus historical file universe, rename/merge semantics, contributor identity, bounded/reusable history traversal |
| Health and hotspots | Version-labeled weighted findings per merged file; null health for empty features; zero-score hotspots omitted | Materially incomplete scope and history-only files must not inflate health; actual complexity metrics and reviewed scoring method |
| Risk model | XGBoost and conditional CV code, heuristic fallback; truthful method/profile/feature metadata in demo | Real predictive utility, temporal validation/calibration, single-class/insufficient-class cases and explicit not-evaluated metrics |
| Refactoring roadmap | Working category suggestions and heuristic effort/impact ordering | Precise evidence links, measured metrics and user validation; no measured ROI |
| Reports and API | Four JSON outputs, aggregate JSON report, readable seven-section PDF, validated API/PDF inputs | Dependency-light HTML/JSON distribution; immutable run reads; context/evidence/policy views; broader error-state tests |
| Dashboard | Actual API envelope/nested-score/factor/date integration; local CSS; finding-page aggregation | Bounded server-side search/filter/history queries rather than loading every page; evidence gaps and context drill-down |
| CLI | analyze/report/watch; caller-relative path fixes, source-root override, profile precedence, JSON/PDF dispatch, subprocess logs | Installed discovery without entering source component directories; argv-based process execution; friendly commands and stable exits |
| Local engineering | Shared checks, synthetic fixture, regression cases, artifact and browser verification | Clean-machine/installed-artifact checks, cross-platform runner, locked release dependencies, package/version manifests, extension tooling |
| Containers | Schema build contexts, output binds, analyzer arguments/runtime dependencies, PDF one-shot and producer exit waiting corrected in source | Build and execute containers; failure/repeated-run tests; general verification for arbitrary input repositories |
| Historical showcases | Internal-total audit documented | Regenerate or retire inconsistent examples; they are not current benchmark evidence |
| Assurance product | Draft evidence/policy/assessment schemas and proposed design | No general collector, pure evaluator, evidence freshness system, consumer comparison or policy release workflow exists yet |

### Recorded verification results

| Check | Result from stabilization |
|---|---|
| Root schema/structure tests | 16 passed |
| Analyzer CMake/CTest | 62 passed |
| CLI CMake/CTest | 17 passed |
| Git miner pytest | 78 passed; 91% Python coverage |
| Predictor pytest | 76 passed; 91% Python coverage |
| Report-engine pytest | 77 passed; 94% Python coverage; no skips |
| Dashboard tests/build | 33 tests passed; production build passed |
| Combined test count | 359; not a measure of product completeness or detection accuracy |
| Native demonstration | Two synthetic files, 11 physical lines, five findings only in intentional.cpp, health 95.5, one positive hotspot, heuristic ranking |
| Artifact verification | Four schemas, internal counts, file identities and PDF content validated; seven PDF pages rendered and reviewed |
| Real web integration | Built dashboard, six data routes through preview proxy, PDF download and all navigation sections passed |
| Docker/Compose | Blocked and unverified |
| Installed artifact / Windows / macOS | Not established |

The small demo does not exercise a representative standard-library/include setup, real consumer matrix or broad compilation database. It proves the integrated path for that fixture.

### Remaining issues to investigate before calling the foundation dependable

1. The integration scripts assert fixed demo filenames/counts. The Compose script accepts a repository override but still invokes the synthetic-demo verifier. Separate general pipeline validation from fixture-specific assertions.
2. Git history includes historical/deleted paths while the current scorer divides by merged feature rows. Define the eligible current analysis scope before refining scores.
3. A 50-or-more-file input can reach XGBoost without adequate label classes. Insufficient CV may currently appear as numeric zero metrics. Add failing reproductions and explicit fallback/not-evaluated behavior before claiming robustness.
4. Null health and heuristic metadata were introduced into a schema still labeled 1.0.0. Determine which formats have actually been distributed and choose tested versioning/migration rules.
5. Existing evidence drafts permit only passed/failed records, while the product needs skipped, unsupported, cancelled and operational-error facts. Assessment draft gate names also differ from design prose. Reconcile these before implementing consumers.
6. Existing per-file scoring and the older proposed KLOC-based formula differ. Retain the current formula until a separate method/version review approves a change; never silently import a new scorer.

These are source-level follow-up risks and design gaps, not claims that all those failure cases were reproduced in this planning pass.

## 2. Intended outcomes

| Outcome | User-visible completion test |
|---|---|
| Dependable existing analysis | Install an artifact, analyze a real C++ project outside the source checkout and understand findings, scope and missing information |
| Maintainer evidence workflow | Declare supported configurations, explicitly collect builds/tests, assess a selected policy and explain every failure or gap |
| Consumer evidence workflow | Compare supplied upstream evidence with the application's actual library artifact/configuration and identify additional local checks |
| Measured maintenance intelligence | Inspect real complexity/history measures, comparable trends and evidence-linked priorities with documented limitations |
| Free local developer tool | MIT-licensed local core for public, private and commercial projects; third-party licenses retained; offline after installation without a cppulse account; optional PDF, dashboard, ML and integrations do not burden the headless core |
| Broader product | Add selected organization, repair, compatibility, domain and hosting features only after their own scope and usefulness reviews |

Code health, experimental change-risk ranking, evidence completeness and satisfaction of a selected policy remain separate results. A policy result concerns declared evidence and scope; it is not product certification, ASIL assignment, a medical software class or tool qualification.

## 3. How stages and reviews work

### Execution rules

- The initial request produced this plan; the subsequent user instruction authorizes autonomous execution of the core S0-S7 track.
- Reversible implementation, fixtures and local verification proceed autonomously. Finish the technical review packet and resolve correctness failures before dependent next-stage work; user reviews can be asynchronous. Do not claim human/product validation from a technical self-review.
- Stage acceptance does not authorize project commits, pushes, branch/ref updates, GitHub writes, publication, deployment or contacting people. The current restrictions remain until explicitly changed.
- Retain working code and unrelated drafts. Use the existing C++17 architecture and component boundaries; preserve current public commands with compatibility wrappers where needed.
- Every implementation increment follows contracts -> producers -> consumers -> presentation -> orchestration -> integration. Component checks pass before dependent work.
- Use shared local checks and Compose where available. Existing automation may call these same checks; do not introduce a new external CI service.
- A blocked required environment remains a blocker for that supported workflow. It may be explicitly deferred and left unadvertised; an unrun check never becomes a pass.

### Review packet at every gate

| Review material | Required content |
|---|---|
| Scope and behavior | Stage acceptance checklist; before/after example; requirements covered and explicitly deferred |
| Changes | Bounded uncommitted diff, design decisions, dependency and compatibility impact |
| Tests | Exact commands/environment; passed, failed, skipped and blocked checks; regressions and negative cases |
| Artifacts | Actual JSON/logs/package/report/screenshots or performance data appropriate to the stage |
| Limits | Supported inputs/platforms; remaining defects; unavailable evidence and impact on claims |
| Decision | Accept and proceed, request correction/retest, or defer a named capability with a scope update |

Technical acceptance and product usefulness are separate reviews. Passing unit tests cannot demonstrate adoption value; a useful-looking demo cannot replace correct failure handling.

### Roadmap and dependencies

| Stage | Deliverable | Depends on | Review decision |
|---|---|---|---|
| S0 | Accepted baseline and agreed core journeys | Current work | Preserve and accept the stabilization baseline and staged scope |
| S1 | Real-input correctness and container proof | S0 | Is the existing analysis dependable for the declared initial inputs? |
| S2 | Versioned contracts, identities and coherent run storage | S1 | Are semantics, migrations and failure states sound enough for producers? |
| S3 | Installed local core and development/release tooling | S2 | Can another developer install and use the actual artifact? |
| S4 | Explicit, bounded build/test collection | S2, S3 | Does recorded evidence accurately describe what executed? |
| S5 | Pure policy assessment | S4 | Do controls, scores and gates handle failure and uncertainty correctly? |
| S6 | Library/consumer matrix and verification adapters | S5 | Does evidence apply to the actual library and consumer configuration? |
| S7 | Unified user workflows and first evidence-capable candidate | S6 | Can a maintainer and consumer make the intended decision? |
| S8 | Measured maintenance metrics and trends | S2, S3; reuse S7 views | Are metrics accurate, comparable and actionable? |
| S9 | Incremental execution and large-repository validation | S2, S4; affected features | Do warm/incremental results equal clean runs within measured budgets? |
| S10 | Deeper Git intelligence and model evaluation | S8; S9 for large histories | Are behavioral signals and model claims supported? |
| S11 | IDE/MCP integrations and free distribution | Installed/reviewed workflows; S7 for evidence features | Do integrations expose the same verified product behavior? |
| E1-E5 | Reviewed expansion tracks | Relevant core stages and demand review | Is each expansion valuable, specified and independently verifiable? |

S8-S10 are not blanket prerequisites for the first small evidence-capable candidate. Basic bounded execution, partial-result preservation and atomic publication are early requirements; aggressive caching, richer metrics and 100K-file optimization come later. Read-only integrations or a basic free skill can expose already verified analysis earlier, without advertising future commands.

## 4. Detailed implementation stages

### S0 Review the existing baseline and choose the first supported journeys

**Work:** Review the current patch, source snapshot and retained artifacts. Reproduce the native synthetic demo when execution resumes. Agree Linux x86-64 as the initial candidate target and explicitly list tested compiler/libclang/Python combinations; qualify Windows and macOS separately. Confirm library maintainers as the first product-validation audience and consumers as the second. Inventory versions and distributed interfaces before assuming a breaking change is safe. Repair stale planning references without overwriting historical context.

**Deliverables:** Baseline inventory, capability/status ledger, supported-environment draft, selected compiled-library/header-only/application examples, accepted backlog order and a decision log entry explaining the reordered milestones.

**Acceptance:** The retained diff and all new files are accounted for; the initial demo reproduces or differences are explained; existing test records remain identifiable; supported versus proposed claims are explicit. No source or Git history is discarded.

**Review R0:** Review the actual patch/demo and agree the first release boundary. Confirm that later organization/AI/hosting tracks remain visible but do not block the local core. Approval of the roadmap is distinct from permission to publish or commit.

### S1 Close remaining correctness and real-input delivery gaps

**Work packages:**

1. Define the current eligible source universe independently of Git history. Test absent Git, shallow history, deleted/renamed files, exclusions, generated/vendor/test sources and missing context. History-only rows must not silently improve health. Static findings survive unavailable history.
2. Test normalized paths, separators, duplicate basenames, case-sensitive/case-folded paths, symlinks and authorized external dependencies. Define a small fingerprint contract/compatibility review before changing producers and preserve repeated occurrences for later baselines; finalize public fingerprint semantics in S2. Label unvalidated numeric detector confidence as a heuristic indicator rather than calibrated certainty.
3. Improve discovery and context facts: supported header/source extensions, compilation-database file/directory inputs, working-directory/forced-include semantics, exact/inferred/fallback arguments, partial/unsupported/oversized files and rule availability. A fallback parse is not proof of a consumer build.
4. Reproduce model failure modes around empty inputs, one label class, sparse positive classes, unavailable SHAP and training/prediction failure. Record label provenance and explicit not-evaluated metrics. Keep ranking experimental.
5. Split general output/API verification from the fixed synthetic expectations. Execute one pinned compiled library, one header-only library and a small consuming application with recorded commands and flags. Review true findings, clean counterexamples, partial parses and totals.
6. On a Docker-capable host, build images and run Compose. Exercise first/repeated runs, a real Git input, intentional producer failure, successful one-shot exits, output visibility, API readiness and dashboard proxy/PDF. Resolve source/runtime defects found there.
7. Regenerate one truthful real example first. Expand the historical showcase only after independent totals and scope checks pass; clearly retire examples that cannot be reproduced.

**Acceptance:** Current scenarios AC-02/03/07 are exercised; the three real input types complete with honest scope; no-Git static operation remains useful; the general verifier handles an arbitrary supported input; Docker passes or remains an explicit deferred support item. A clean file is not a positive hotspot. Model failures cannot fabricate a successful trained result.

**Review R1:** Review the real findings and missed/false-positive cases, producer counts, failure logs and container results. Decide which inputs/platforms can be advertised. Docker absence does not prevent independent native work, but does prevent accepting Docker support.

### S2 Define versioned contracts, identities and coherent run storage

**Work packages:**

1. Reconcile existing findings/Git/risk/roadmap contracts and the draft evidence/policy/assessment files. Decide draft-versus-released compatibility. Use a new major contract for nonrepresentable semantic changes; provide a legacy reader/export or an actionable migration error, without invented scores/model names.
2. Define run manifest, source/subject, build contexts, normalized observations, measured metrics, recipe receipts, evidence, policy, assessment, baseline and registry contracts. Validate semantic constraints beyond JSON shape.
3. Separate identities: file/symbol, source-content manifest, actual distributed artifact, context, extraction/tool/rule versions, scorer, policy, run and baseline. Include dirty/untracked in-scope contents, relevant generated/dependency inputs and explicit unavailable fingerprints. Detect mutation during collection.
4. Agree execution states separately from control outcomes. An execution can pass, fail, error, time out, be cancelled, be skipped or remain unattempted; a control evaluates to passed, failed, unknown or justified not_applicable. Stale evidence is unusable for current assessment, not automatically a code defect.
5. Introduce staging plus immutable run directories and a validated manifest. Publish a completed or explicitly partial snapshot atomically. API/report readers resolve one run; interrupted writes cannot expose mixed files or stale success.
6. Define configuration precedence, effective configuration and version checks. Policies remain data. Record the CLI error/exit taxonomy before implementing public collection and assessment commands.

**Acceptance:** Contract and semantic tests cover duplicate IDs, references/cycles, invalid weights, unsupported formats/evaluators, basename/fingerprint collisions, dirty source, context/tool/policy mismatch, source mutation, interrupted publication and reader races. Reject invalid input rather than interpreting it as a clean document. Retain valid independent facts.

**Review R2:** Review sample manifests, evidence/assessment truth tables, old/new compatibility examples and exit examples before dependent producers. Resolve the current 1.0.0 schema ambiguity and gate-name mismatch. Hashes establish identity/integrity, not producer authenticity.

### S3 Deliver an installed local core and maintainable development workflow

**Work packages:**

1. Introduce namespaced Python packages with shared contracts/configuration; preserve current component entry points during migration. Extend existing CMake install/package targets and ship schemas, registries and resource paths with the installed tool.
2. Resolve native/Python components through installed metadata, not a compiled-in checkout path or component-directory changes. Use argument-vector subprocess APIs with tested platform behavior rather than shell-interpreted user strings.
3. Split core, development and optional ML/PDF/API/dashboard dependencies. Core text/JSON/HTML analysis must work without browser, Node, WeasyPrint or XGBoost runtime installation. Lock the supported release dependency matrix and test offline runtime after setup.
4. Add doctor, init and effective-config inspection; preserve analyze/report/watch behavior and add safe local diagnostic bundles with redaction defaults. Never upload a diagnostic bundle implicitly.
5. Extend the shared local runner to formatting, compatibility, installed-artifact smoke tests and machine-readable results. Keep CTest, component pytest coverage and dashboard checks usable.
6. Add a shared rule registry and reviewed rule/adapter/policy generators plus generated documentation/config checks. A generated scaffold is not a completed detector or adapter. Define experimental-to-stable promotion and preview/stable candidate channels; pinned policy/scorer versions and organization requirements must not change silently with new defaults.
7. Prepare local candidate packaging: component/contract versions, changelog, checksums, notices/SBOM, compatibility table and upgrade/rollback procedure. Verify the actual artifact with the source checkout unavailable. Automate preparation of locked dependency updates, compatibility/generated-doc checks and release notes; preparation does not authorize automatic updates or publication.

**Acceptance:** AC-01/13 and applicable AC-14 pass. Install in a fresh environment; invoke from an empty working directory; run headless analysis with optional features absent; unknown versions give actionable errors. Linux support is demonstrated; Windows/MinGW, MSVC and macOS graduate independently through installed-artifact tests. A cross-compiled binary alone is insufficient.

**Review R3:** Review the install transcript, candidate artifact, dependency footprint and support matrix. Select the minimum package for first users. A basic analysis candidate can be prepared here; its publication is a separate action.

### S4 Implement explicit and bounded collection producers

**Initial slice:** One selected CMake configure/build/CTest recipe, one context, structured execution receipts and one test-result adapter. Multi-context scheduling follows the tested single-context path within this stage.

**Work packages:**

1. Implement explicitly selected recipes with argv, working directory, declared inputs/outputs and allowed environment metadata. Merely reading a repository, analyzing sources or loading a policy must not run project commands or network tasks.
2. Capture tool/version, actual command, source/context/artifact identity, start/end status, logs and structured test counts. Distinguish execution-derived facts, imported claims and human attestations.
3. Use bounded worker processes, timeout/cancellation handling, crash isolation and supported resource limits. A failed build skips its dependent tests with a reason; independent contexts continue. Preserve completed facts and atomically publish partial runs.
4. Bind results to actual exercised binaries/headers/packages. Verify relevant inputs before and after execution; mutation produces a retry against a stable snapshot or an explicit incomplete result.
5. Add version-declared CTest/JUnit import. Unknown or malformed formats remain unavailable; process exit zero, zero tests and all-skipped tests are not sufficient proof of verification.
6. Validate recipe cycles, missing executables/inputs, unsafe output destinations and unsupported options. Keep logs/source/secret exposure bounded; collection is trusted user-selected execution, not a sandbox for arbitrary hostile repositories.

**Acceptance:** Deliberately fail compilation, fail a test, remove a report, supply malformed/empty output, crash/time out/cancel a worker, mutate an input and interrupt publication. Each yields the expected receipt/partial manifest and preserves independent valid results. Collection completion and observed check failure remain distinct; final gate decisions belong to assessment.

**Review R4:** Review raw logs beside normalized receipts for clean, failed and incomplete runs. Verify that the recorded evidence describes execution faithfully. Public command exposure waits for the corresponding consumers and integration checks.

### S5 Implement the pure policy assessment engine

**Work packages:**

1. Implement a pure evaluator that consumes validated persisted facts/evidence and versioned policy data. It launches no tools, imports no executable policy plugins implicitly and has no renderer-specific scoring logic.
2. Start with finding limits, minimum analysis scope, required test outcomes and required contexts. Add numeric/coverage and reviewed-evidence controls only when the corresponding typed facts are supported. Reject unsupported control kinds.
3. Implement passed/failed/unknown/not_applicable controls with reasons and evidence links. Required unknown evidence blocks acceptance; missing scope cannot be treated as not_applicable merely to pass a gate.
4. Retain raw weighted numerators/denominators and compute the proposed policy-specific readiness, completeness and observed-satisfaction separately. Zero denominators produce null; gates use unrounded values. Keep maintenance health and experimental ranking separate.
5. Implement precedence and scoped expiring deviations. Original failed outcomes/scores remain; deviations affect only permitted named gates and cannot turn required unknown evidence into a pass. Preserve owner/reviewer/rationale/scope/expiry and label permitted exceptions.
6. Supply a general C++/library starter policy and a custom organization example using the same evaluators. A policy-only change re-evaluates stored compatible evidence without rebuilding AST facts.

**Numerical acceptance example:** Passed weight 4, failed weight 2 and unknown weight 4 must produce readiness 40%, completeness 60% and observed satisfaction 66.67%. A required failed control still blocks acceptance. With all applicable controls unknown, observed satisfaction is null; with no applicable control/source scope, the gate is incomplete.

**Acceptance:** Truth-table/property/regression tests cover required failure plus unknown, high averages masking failure, complete but subthreshold results, empty scope, exclusions/disabled capabilities, stale/wrong evidence, invalid policies, expiry and mismatched deviations. Explicitly compute maximum_possible_readiness = 100 * (passed_weight + unknown_weight) / applicable_weight: when even that upper bound cannot meet the required threshold, the gate fails despite unknown evidence. Otherwise unresolved required evidence remains incomplete unless an existing blocking failure already determines failure. Schema and design status names agree.

**Review R5:** Review hand calculations, gate explanations and counterexamples. Also run an internal end-to-end slice using the installed package/test harness: one CMake/CTest context -> validated execution receipt -> assessment -> retained clean, failed and missing-evidence artifacts. This reviews the core behavior before adding every coverage/sanitizer adapter or public UI. Domain standard mappings are not required here; public workflow acceptance remains S7.

### S6 Complete verification adapters and maintainer/consumer applicability

**Work packages:**

1. Add LCOV and Cobertura with covered/total counts, measurement type, source/context and producer version. Keep line, branch, function, decision and MC/DC distinct; do not infer one from another or average incompatible shards.
2. Add supported-version ASan, UBSan and TSan collection/import recipes. Record actual compiler/link instrumentation and exercised consumer binaries, test scope and findings. Successful execution or an empty sanitizer log alone is insufficient.
3. Support imported external analyzer observations with producer namespaces and overlap handling; imported reports remain separate from independent confirmation. Each adapter declares formats/versions and tested unsupported cases.
4. Define the declared compiler/OS/target/standard/macros/link/dependency/test matrix. Show missing required contexts and selected template instantiations. Header-only checks include requested self-containment tests without claiming exhaustive template coverage.
5. Exercise a compiled library, header-only library and consuming application. Compile/test the actual distributed package or amalgamated header, not an unrelated source tree with an attached artifact hash. Seed and label a no-exceptions regression using the actual compiler flag.
6. Implement consumer comparison for explicitly supplied upstream evidence: artifact/source match, context applicability, trust/origin labels and missing local integration checks. Matching upstream evidence does not replace application tests. Add no cppulse runtime dependency to the library.
7. Package scoped evidence, manifests and limitations for local transfer. Integrity is verified; provenance/authentication claims require a separate trust design and cannot be inferred from hashes.

**Acceptance:** AC-08/09/11 pass on actual samples. Wrong/stale source, changed artifact, unsupported producer, uninstrumented/prebuilt dependencies, zero/all-skipped tests and missing variants cannot silently pass. Linux/GCC evidence does not establish Windows/MSVC verification. Known failures and missing evidence remain distinguishable.

**Review R6:** Review the maintainer and consumer cases side by side, including one deliberately incompatible upstream context and one genuine missing local check.

### S7 Deliver coherent public workflows and review the first evidence candidate

**Work packages:**

1. Extend JSON/HTML/PDF/API/dashboard with run completeness, contexts, control outcomes, separate scores, original producer links and actionable gaps. Keep the existing report sections and optional API-key behavior; no presentation layer recomputes gate-affecting values. SSO/RBAC remains E5 work.
2. Expose installed collect and assess workflows, explain, baseline and check with reviewed exit contracts. Distinguish a finding-regression gate from an evidence-policy gate; reject unsupported policy/evidence options. Preserve analyze/report/watch compatibility and separate logs from machine output.
3. Install an explicit opt-in CMake check target, selected target dependencies and compile-context discovery. Keep it outside ALL by default, avoid recursive builds and isolate build directories/configurations. Optional normal-build enforcement must be expressly configured.
4. Add baseline and changed-scope semantics, scoped suppressions with rationale, SARIF and local pre-commit/build templates. Test finding multiplicity, line shifts, renames, duplicate basenames and dependency-sensitive changes. Until S9 proves dependency-aware invalidation, conservatively recompute the full relevant scope. A changed-file finding check cannot imply project-wide policy acceptance without complete compatible evidence for the required scope. Existing Git-host integration consumes the same engine; no remote comments or writes happen implicitly.
5. Run the complete installed-package/Compose/API/dashboard journey and repair reproducible examples. Retain exact candidate artifacts, verification manifest, versions/notices/checksums and upgrade/rollback instructions.
6. Prepare maintainer and consumer evaluation tasks: compare setup and evidence reconciliation against their existing scripts/tools, record confusing outputs, false alarms and missing use cases. Agree measurable usefulness criteria after observing the baseline. Preparing sessions does not authorize contacting people.

**Acceptance:** AC-10/12/13/14 and the applicable collection/consumer scenarios pass. One clean, one observed-failure and one missing-evidence case agree across installed CLI, JSON, HTML/PDF, API and dashboard. Canceled/staging runs cannot appear as latest success. Headless/offline core works without optional services.

**Review R7:** Technical review of the candidate plus a separate usefulness review of real maintainer/consumer tasks. Decide whether the narrow workflow merits a release, needs correction or needs a product-scope change. Public release, marketplace submission and messaging remain separate authorized actions.

### S8 Add measured maintainability and comparable trends

**Work:** Emit actual function/file LOC, length, cyclomatic complexity, nesting and parameter metrics. Add duplication, then cohesion/compound smells only with independently reviewed definitions and fixtures. Version metric availability/units, critical-code markers, baseline/suppression effects and score denominators. Replace the severity proxy only through an explicit new measured-hotspot/scorer decision. Link roadmap items to exact facts/findings; label effort/impact estimates. Add history, function drill-down, comparisons and basic debt goals; annotate or break incompatible trends.

**Acceptance:** Hand-reviewed clean/trigger, template/macro and multi-context cases agree with measured values. Independent score calculation reproduces results. Changing scope, compiler context, policy/scorer or disabled checks cannot silently improve a comparable trend. Expand toward six pinned real C++ repositories plus seeded defect/clean fixtures, publishing review samples and limitations rather than unsupported accuracy claims.

**Review R8:** Review metric definitions, false positives and whether the resulting priorities change a useful engineering decision. Approve any change from per-file to KLOC or multi-context scoring separately; never silently replace the current formula.

### S9 Add incremental execution and validate scale

**Work:** Separate extraction and assessment cache keys; use dependency-aware invalidation with conservative fallback when the graph is incomplete. Stream/checkpoint Git records and handle rewritten history. Add resumable work, bounded aggregation, indexed local history/catalog migrations, immutable-run pagination cursors and server-side search/filtering. Avoid downloading the whole project into the dashboard. Extend per-component limits to PDF/ML and report exhausted scope explicitly.

**Acceptance:** Cold, warm, source edit, shared-header edit, macro/flag/sysroot/dependency/generated-input/tool edit, policy-only and history-append runs match clean semantic results. Enabling a detector that was not previously executed requires fresh extraction; unavailable external dependency identity prevents unjustified cache reuse. Test crashes, cancellation, interrupted writes, resume and latest/history races. Measure repeated wall/CPU time where available, peak memory, completeness, work units and cache hits on a named host for approximately 1K/10K/100K-file tiers and representative histories. Set numerical release budgets from these measurements; repeated regressions require correction or a reviewed exception.

**Review R9:** Review correctness equivalence before speed. Publish supported limits and measured results; do not trade away scope or reuse stale facts to meet a timing target. Large-tier support remains unadvertised until those runs execute.

### S10 Add behavioral intelligence and evaluate optional risk models

**Work:** Introduce contributor aliases, bots, pair attribution, former contributors, time windows and rename/merge semantics. Add coupling with minimum support and bulk/generated-commit filters; then weighted ownership/familiarity, knowledge maps, fragmentation, offboarding scenarios and component/architecture aggregation. Add symbol/function history before function-level coupling. Distinguish historical co-change from static include/call dependencies. Reuse indexed history rather than recomputing it for every view.

Evaluate optional predictive models using explicit label provenance, chronological cutoffs/holdouts and project-level generalization checks, imbalance-aware baselines and calibration where probability claims are considered. Do not use future history to evaluate future-defect prediction. Record not-evaluated metrics and distribution limits.

**Acceptance:** Controlled histories cover bots/aliases/bulk edits/merges/renames, empty/shallow history, turnover and known coupling. No double-counting or undefined denominators. Explanations agree with source facts. A model must demonstrate value over simple baselines before promotion; inconclusive evaluation retains experimental ranking or leads to disabling the claim, not manufacturing a favorable score.

**Review R10:** Review known-history outcomes and the model evaluation report. Decide which signals are useful enough to ship. Authorship remains a knowledge proxy, not proof of expertise or a basis for individual performance judgments.

### S11 Add developer integrations and prepare free distribution

**Work:** Add read-first MCP interfaces and initial VS Code diagnostics using persisted public contracts. Share CLI/API status, evidence and scoring logic. Add capability boundaries for explicitly requested execution; reading results must not modify a repository or launch tools. Package reusable build/pre-commit/Git-host templates and consumer examples. Prepare a free text-based skill using released commands only; distinguish loading instructions from installing native software.

Create platform candidate artifacts, container versions as supported, notices/dependency inventory, support matrix, migration/rollback guide and a clean-session skill test. A basic analysis-only skill may be prepared after S3; evidence instructions follow S7. Windows/MinGW, MSVC and macOS each require a real installed-artifact run before support claims. Run a feedback loop on installation and interpretation, not just download counts.

**Acceptance:** AC-12/16 pass; MCP/IDE/API/CLI values agree for one immutable run. Unknown capabilities/versions fail clearly. A fresh agent can follow the skill with only documented commands. No account/subscription is required for the local core; runtime remains offline after dependencies/packs are installed.

**Review R11:** Review the actual candidate, clean-agent transcript and listing text. Preparing a ZIP is not marketplace submission, and verified packaging is not publication. Decide which integration/platform to release based on useful demand.

## 5. Expansion stages retained from the broader plan

Every expansion starts with a small sub-specification and a scope/usefulness review. It then follows the same contracts-to-integration sequence and review packet. These are planned options, not prerequisites for the useful free local evidence workflow.

| Track | Detailed work still planned | Preconditions and acceptance | Review |
|---|---|---|---|
| E1 Domain starter policies | Automotive/medical starter mappings, required process/review evidence, edition/version metadata, custom organization examples and explicit unassessed obligations | S5-S7; reviewed mappings against authorized editions; general evaluator remains domain-neutral; do not reproduce licensed text or claim certification/tool qualification | Review each mapping, scope and evidence obligations before making it an available pack |
| E2 Organization and portfolio workflows | Team ownership/alignment/history and fragmentation; multi-repository portfolios and goals; scheduled reports; branch/merge/delivery analytics; issue-tracker adapters; cost/ROI estimates; additional report/notification channels | S8-S10 as needed; provider/access/data contracts; correct team/branch/time-window semantics; missing-data states; observed costs distinct from estimates; explicit scope and delivery configuration | Validate a real organizational decision before each provider/view; execution schedules or messages require separate user instructions |
| E3 Reviewable fixes and AI-assisted repair | Narrow deterministic dry-run patches first; later semantic refactoring, agent-driven repair and PR preparation | Accurate source/context/fingerprint contracts; precise edit scope, idempotence, compile/test and behavior-validation cases; no weakening controls or undisclosed edits; semantic work gets a language-specific validation design | Review patch and behavioral evidence; creating commits/PRs or sending changes remains separately authorized |
| E4 Additional evidence and languages | API/ABI compatibility, fuzzing, dependency/provenance and traceability adapters; reviewed process artifacts; additional analyzed languages | Supported-tool/version/platform sub-specs and representative clean/failure/unsupported fixtures; preserve scope/producer attribution; language-specific metrics/calibration and packaging | Approve each adapter/language independently; a schema or generic command wrapper is not completion |
| E5 Enterprise identity and optional hosting | SSO/RBAC, project/tenant access, managed deployment, storage/retention, secrets and operating-cost model | Threat/access/ownership/backup/deletion/upgrade design and tests; explicit hosting demand; local account-free product remains usable independently; deployment and external API costs stated | Separate product/security/cost review before implementation; deployment/publication is a distinct action |

## 6. Minimum release scenarios and where they are proved

| Scenario from the existing specification | Planned proof |
|---|---|
| AC-01 Installed use outside checkout | S3; repeat for every supported platform/release |
| AC-02 Empty/partial/failed parsing and missing context | S1, then S2/S5 gate prerequisites |
| AC-03 Paths, separators and duplicate basenames | S1; S7 baselines; S3 platform package checks |
| AC-04 Source/header/flag/dependency invalidation | S2/S4 source stability; full cache equivalence in S9 |
| AC-05 Policy-only re-evaluation | S5; assessment cache validation in S9 |
| AC-06 Crash/timeout/cancel/interrupted writes | S2/S4 minimum safety; S9 resume/scale |
| AC-07 No Git or shallow history | S1; S10 richer-history limitations |
| AC-08 Compiled/header-only consumer matrix | Initial inputs in S1; evidence applicability in S6 |
| AC-09 Empty/zero/skipped/stale runtime evidence | S4 test receipts; S6 coverage/sanitizers |
| AC-10 Required failure/unknown versus high scores | S5, public installed workflow in S7 |
| AC-11 Disabled checks/exclusions/deviations/policy mismatch | S1/S2 scope; S5 evaluator; S6/S7 integration |
| AC-12 One result across interfaces | S7 CLI/API/report/dashboard; S11 MCP/IDE |
| AC-13 Previous contracts/config/baselines | S2 migration definitions; S3/S7 installed compatibility |
| AC-14 Installed reports/API/dashboard | S3 package resources; complete evidence flow in S7 |
| AC-15 Six pinned projects and clean/defect corpus | S8 expansion; S9/S10 workload/evaluation subsets |
| AC-16 Free skill in a fresh agent session | S11, or an analysis-only subset after S3 |

## 7. Traceability to the earlier M0-M9 backlog

This sequence reorders delivery around the newer library-evidence direction. It does not delete the older proposed backlog or label whole milestones complete based on stabilization.

| Earlier milestone | Delivered stabilization subset | Remaining placement |
|---|---|---|
| M0 Consolidation/correct results | Path joins, LOC, API shapes, CLI formats/profiles, empty health and heuristic metadata, synthetic pipeline | S0-S2; S1 includes partial/no-Git/file-universe/real-project gaps |
| M1 Development/releases | Shared local source checks, dependency records, synthetic integration | S3 and S7/S11: installed packages, optional dependencies, generators, support matrix and release manifests |
| M2 Scale/incremental | No general incremental engine or coherent snapshot store | Minimum identities/atomicity in S2, bounded execution in S4; full caching/indexing/benchmark work in S9 |
| M3 Friendly CLI/build checks | Existing analyze/report/watch stabilized | S3 init/doctor/install; S7 check/explain/baselines/CMake/SARIF; S11 distribution |
| M4 Maintainability/trends | Heuristic health/hotspots/roadmap, not rich measured metrics | S8 |
| M5 Evidence/library assurance | Draft schemas and limited parse-status facts only | S2/S4-S7 core evidence workflow; E1 domain starter packs |
| M6 Behavioral intelligence | Basic Git metrics and experimental model code | S10; shared history scale in S9 |
| M7 Integrations/distribution | Existing action source; no new verified IDE/MCP/skill distribution | S7 shared local templates; S11 |
| M8 Organization features | Not implemented by stabilization | E2 |
| M9 Advanced optional features | Not implemented by stabilization | E3-E5 |

## 8. Completion and scope management

A stage is complete only when its acceptance cases ran on the declared environment, artifacts are retained, compatibility effects are handled and user-facing examples match behavior. Blocked/skipped checks and remaining limits accompany the review. Counts of tests, files or generated scaffolds do not substitute for the intended behavior.

The first evidence-capable candidate ends at S7 with the supported small corpus and explicit scale/platform limits. S8-S11 broaden measurement, performance and integration independently. Expansion tracks follow their own reviews. Useful free software can be released before every broad-platform feature exists, but a release claim cannot exceed its executed support matrix.

Calendar estimates should be made for the next accepted stage after its access, target corpus and environment are known. The plan deliberately does not invent a completion date for the entire platform. Each review can split an oversized stage, remove an unsupported claim, or revise scope without treating incomplete work as done.

### Source documents

- [Current stabilization handoff](../../review/HANDOFF.md)
- [Current demo verification and walkthrough](../portfolio/demo-verification.md)
- [Product discovery and working direction](../research/cppulse-product-discovery.md)
- [Proposed platform requirements and AC-01 through AC-16](../specs/production-platform/requirements.md)
- [Proposed design and semantics](../specs/production-platform/design.md)
- [Original M0 through M9 implementation backlog](../specs/production-platform/tasks.md)
- [Historical MVP task specification](../../TASK_SPEC.md)
- [Architectural decisions](../DECISIONS.md)
