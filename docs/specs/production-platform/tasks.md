# cppulse Production Platform Implementation Plan

Status: Proposed backlog; no task below is marked implemented by this document
Specification version: 1.0
Date: 2026-11-04

Requirements: [requirements.md](requirements.md)
Design: [design.md](design.md)

## 1. Delivery order and release boundaries

| Order | Milestone | Depends on | Deliverable | Relative scope |
|---:|---|---|---|---|
| M0 | Consolidate and establish trustworthy contracts/results | Inspected baseline | One verified baseline, correct identities/scores/statuses, versioned contracts | Medium |
| M1 | Repeatable development and release candidates | M0 | Shared local verification, package/install tests, candidate artifacts | Medium |
| M2 | Bounded and incremental analysis | M0, M1 | Worker isolation, dependency-aware cache, history/catalog foundation, benchmark budgets | Large |
| M3 | Friendly installed CLI and build checks | M1, M2 | Init/doctor/check/explain, baselines, CMake integration, SARIF, reliable exits | Medium |
| M4 | Maintainability measurements and trends | M0-M3 | Function metrics, duplication, measured hotspots, snapshots, explanations | Large |
| M5 | Library evidence and configurable assurance | M3, M4 | Context matrix, evidence adapters, policy engine, general and domain starter packs | Large |
| M6 | Deeper behavioral analysis | M2, M4 | Coupling, ownership, offboarding, component and function history | Large |
| M7 | Developer/agent integrations and distribution | M3; M5/M6 for their exposed features | MCP, VS Code, updated free skill, reusable consumer integrations | Medium |
| M8 | Organization and portfolio features | M4-M7 | Goals, teams, portfolio, scheduled reports, delivery/cost adapters | Large |
| M9 | Advanced optional capabilities | Relevant preceding capabilities | Validated fixes/PR repair, API/ABI/fuzzing adapters, extra languages, identity/hosting | Very large |

Relative scope describes engineering breadth, not a calendar commitment.
Release version numbers are assigned after baseline/version inventory, not
inferred from the version strings currently used by individual components.

- Release A: M0-M3, dependable existing analysis with installation and build gates.
- Release B: M4-M5, measured maintenance health and consumer/policy assessment.
- Release C: M6-M7, broader Git intelligence and developer integrations.
- Expansion releases: selected M8/M9 features justified by demand.

A basic free agent skill can ship after M3 using released health/build
workflows; full evidence/policy instructions follow the corresponding release.
Do not wait for every enterprise feature before releasing useful software.

## 2. Mandatory sequence inside every milestone

1. Define/update schemas and semantic contracts; run contract tests.
2. Implement data producers; run their component checks.
3. Implement consumers/scoring/evaluation; run their component checks.
4. Implement report/API/dashboard presentation as affected; run its checks.
5. Implement public orchestration and integration commands; run CLI/build checks.
6. Run end-to-end, installed-artifact, compatibility, and applicable performance tests.

Keep independent tasks within the milestone small and reviewable, but do not
start dependent components before the preceding phase passes. This is the
TASK_SPEC.md build order applied to the revised scope.

Required component commands remain:

~~~text
analyzer-core: cmake -B build
               cmake --build build
               ctest --test-dir build --output-on-failure
cli:           cmake -B build
               cmake --build build
               ctest --test-dir build --output-on-failure
Python:        pytest -v --cov=src tests/
dashboard:     npm ci
               npm test
               npm run build
integration:   local Docker Compose and installed-package scenarios
~~~

For Python package migration, preserve these component commands or document
their compatible replacement explicitly. Existing test framework coverage
targets in TASK_SPEC.md remain minimums; percentage coverage alone is not
proof of correct analysis.

## 3. M0 Consolidation and correct results

| Task | Work | Acceptance evidence |
|---|---|---|
| M0-01 | Inventory current worktree, origin/main 82120d2, health-score-v2 history, and preliminary drafts. Preserve unrelated files and existing working code. | Recorded baseline and merge/reuse plan; no duplicate implementation of existing fixes |
| M0-02 | Define canonical identities, manifest/status envelopes, configuration/version compatibility, scorer availability, and model metadata schemas. Reconcile draft contracts. | Draft-07 and semantic validation; legacy fixture compatibility |
| M0-03 | Add regressions for absolute/relative paths, separators, basename collisions, empty/partial scope, missing context, profile propagation, and incorrect model labels. | Reproductions demonstrate the pre-fix behavior |
| M0-04 | Correct producers, configuration propagation, per-file parse outcomes, rule execution facts, generated/vendor scope, and no-Git handling. Reuse newer branch fixes. | Producer output validates; valid partial facts survive failed units |
| M0-05 | Correct feature joins, score prerequisites, actual complexity availability, heuristic metadata, label provenance, and false clean-state handling. | Consistent equations; no fabricated complexity/probabilities/perfect missing-data score |
| M0-06 | Update reports and CLI output to expose partial/unknown state; fix existing advertised command/format behavior and baseline matching. | CLI and rendered results agree; no silently ignored format/profile options |
| M0-07 | Verify all existing components and regenerate a small pinned example before refreshing larger examples. | Tests, schema results, semantic score verification, and documented remaining limitations |

Covers PR-01..07, FR-CTX-01..08, FR-ANA-01/03/04/06..08,
FR-GIT-01/08, FR-POL-07, and AC-02/03/07/13.

## 4. M1 Development and releases

| Task | Work | Acceptance evidence |
|---|---|---|
| M1-01 | Define verification-result and package-version manifests; freeze the initially supported dependency/platform matrix. | One documented source of versions and compatibility expectations |
| M1-02 | Add the cross-platform local development runner around existing CTest/pytest/dashboard tools. | Full run invokes every required suite and returns machine-readable failures |
| M1-03 | Consolidate common Python contracts/configuration with compatibility entry points. Separate development and optional runtime dependencies. | Existing component commands and isolated installs both pass |
| M1-04 | Extend CMake with install targets, package core artifacts, and build the Python distribution and optional components. | Analyze from an empty working directory using only installed artifacts |
| M1-05 | Complete integration fixtures: actual outputs, volume extraction, PDF generation, API queries, and browser-level dashboard checks. | Integration fails when any promised output or consumer is broken |
| M1-06 | Generate candidate versions, changelog, checksums, notices, dependency inventory, support matrix, and verification manifest. | A retained candidate can be reproduced and installed; dry-run publication changes no external state |
| M1-07 | Add rule/adapter generators and generated-documentation checks; make existing CI call shared local commands. | A generated extension passes registry/contract checks only after meaningful fixture implementation |

Covers NFR-MNT-01..09, REL-01..10, AC-01/12/13/14.

## 5. M2 Scale and incremental execution

| Task | Work | Acceptance evidence |
|---|---|---|
| M2-01 | Define work-unit/dependency/cache identities, checkpoints, and committed snapshot semantics. | Contract fixtures cover crashes, incomplete graphs, and stale/latest races |
| M2-02 | Introduce bounded analyzer workers, per-unit time/resource limits, cancellation, and explicit large-file policy. | Limits respected; a crashing parser does not erase other results |
| M2-03 | Implement dependency-aware facts caching and separate assessment caching. | Clean versus cached results agree for source/header/flag/tool/policy edits |
| M2-04 | Stream reusable Git records, handle history rewrite/shallow cases, and checkpoint incremental mining. | Complete and resumed history metrics agree on controlled histories |
| M2-05 | Publish immutable runs atomically and add indexed history/catalog queries and bounded result aggregation. | Readers never mix runs; interruption recovery and catalog migration pass |
| M2-06 | Add stable pagination to the API and efficient dashboard access for large findings sets. | Bounded page size and one-run cursor consistency |
| M2-07 | Benchmark 1K/10K/100K-file tiers and representative histories on a named host. Set measured release budgets. | Published cold/warm/edit timing, memory, completeness, and comparison results |

Covers NFR-SCL-01..10, FR-GIT-02, FR-UX-08, AC-04/05/06.

## 6. M3 User workflow and first public release

| Task | Work | Acceptance evidence |
|---|---|---|
| M3-01 | Define CLI/config/exit contracts and baseline fingerprints. | Compatible invocation fixtures and actionable invalid-input cases |
| M3-02 | Specify and implement core health/finding-regression gate predicates before exposing check. General evidence-policy packs remain M5 work. | No dependency on the later assurance engine; unsupported policy/evidence options are rejected clearly |
| M3-03 | Implement init, doctor, effective configuration, explain, check, baseline, and local bug-report commands. Preserve analyze/report/watch. | Clean-machine and outside-checkout journeys; JSON/log separation |
| M3-04 | Install the CMake helper and implement explicit check targets, target/dependency selection, and optional normal-build checks. | A sample application and library use the installed package without custom output parsing |
| M3-05 | Add changed-scope checks and SARIF exports; repair the existing PR comparison/action as a consumer of the same engine. | Rename, repeated finding, basename collision, branch, and partial-analysis tests |
| M3-06 | Publish concise quickstarts, troubleshooting, upgrade/rollback instructions, and a supported-environment table. | Every example is exercised by package integration tests |
| M3-07 | Prepare Release A and a free skill/listing containing released commands only; test the skill in a clean agent session. | Verified install artifacts; validated text ZIP; listing describes actual scope; submission status recorded separately |

Covers UX-01/04/05/08, FR-UX-01..06/09/11/12, REL-06..11,
AC-01/03/06/13/14/16.

## 7. M4 Maintainability metrics and trends

| Task | Work | Acceptance evidence |
|---|---|---|
| M4-01 | Define versioned function/file metrics, snapshot comparison, and duplication observations. | Units, denominators, availability, and comparison compatibility are explicit |
| M4-02 | Emit actual complexity/nesting/length/parameter metrics, then validated duplication and cohesion metrics. | Positive/negative and macro/template fixtures; counts match hand-reviewed cases |
| M4-03 | Calibrate and explain a maintenance profile; compute measured hotspots and precise roadmap evidence links. | Same facts give same scores; no claim of empirical probability or financial ROI without supporting validation |
| M4-04 | Add history, trends, function drill-down, critical-code markers, and basic debt goals. | Version/context changes break or annotate trends rather than silently continuing them |
| M4-05 | Expand and review the pinned corpus and resource measurements. | Accuracy sample, false positives, unsupported syntax, and baseline results published |

Covers FR-ANA-02/04..07, FR-GIT-07, FR-UX-07, AC-12/15.

## 8. M5 Evidence and configurable library assurance

| Task | Work | Acceptance evidence |
|---|---|---|
| M5-01 | Finalize context-matrix, evidence, policy-pack, assessment, and deviation schemas plus adapter/evaluator contracts. | Semantic validation includes provenance, duplicate IDs, cycles, stale/mismatched evidence, and unsupported evaluators |
| M5-02 | Produce selected consumer/context inventories and CTest/JUnit, LCOV/Cobertura adapters with execution scope. | Missing/zero/skipped tests and denominator/context mismatches never pass silently |
| M5-03 | Add ASan/UBSan/TSan collection/import adapters for explicitly supported tool/platform versions. | Instrumented failing/clean samples, uninstrumented runs, empty logs, wrong contexts, and stale artifacts are distinguished |
| M5-04 | Implement the pure policy evaluator, four control outcomes, three scores, gate precedence, and bounded deviations. | Hand-calculated examples and invariants pass; averages cannot override blocking failures/unknowns |
| M5-05 | Add compiled-library and header-only examples with selected consumer/instantiation matrices. | Missing consumer variants are visible and required variants block acceptance |
| M5-06 | Render assessment/evidence/gaps in JSON/HTML/PDF/API/dashboard and add collect/assess workflows to installed CLI/CMake. | Interface agreement and complete package scenarios pass |
| M5-07 | Ship general and custom-library policies, then reviewed automotive/medical starter mappings with explicit coverage statements. | Edition pinning, unsupported obligations, and mapping maturity are visible; no certification claim |
| M5-08 | Prepare Release B and update the skill to expose only released evidence/policy workflows. | AC-08..12 and AC-16 pass; policy and software versions are recorded together |

Covers PR-03..05, UX-02/03/06, FR-EVD-01..10, FR-POL-01..10,
FR-UX-07, AC-05/08..12/15/16.

## 9. M6 Behavioral intelligence

| Task | Work | Acceptance evidence |
|---|---|---|
| M6-01 | Define contributor identity, rename history, coupling support, and component/symbol history contracts. | Synthetic histories specify aliases, bots, bulk commits, merges, and renames |
| M6-02 | Produce weighted ownership, familiarity, coupling, and fragmentation metrics from shared history. | No double counting or undefined denominator on shallow/empty history |
| M6-03 | Evaluate offboarding scenarios, architectural hotspots, and function-level historical priorities. | Outcomes match known synthetic histories and disclose knowledge-proxy limitations |
| M6-04 | Add maps, trends, explanations, and comparison support to reports/API/dashboard. | Underlying metrics agree with CLI; large-view queries stay within benchmark budgets |
| M6-05 | Evaluate optional risk models with temporal cutoffs and calibration. | Publish evaluation methodology; unvalidated ranking remains labeled experimental |

Covers FR-GIT-03..08, UX-05, AC-07/12/15.

## 10. M7 Integrations and distribution

| Task | Work | Acceptance evidence |
|---|---|---|
| M7-01 | Specify read-first MCP/IDE contracts and execution capability boundaries. | Client fixtures cannot obtain inconsistent scoring or hidden analysis assumptions |
| M7-02 | Implement run/health/findings/hotspot/policy-gap MCP tools and initial VS Code diagnostics. | Compare results with CLI and installed API fixtures |
| M7-03 | Package reusable local build/pre-commit integration and existing Git-host workflow templates. | Consumer examples execute shared commands rather than duplicate logic |
| M7-04 | Validate and submit the expanded free skill and release integration artifacts. | Marketplace review/publication recorded separately from ZIP preparation; text delivery does not claim native installation |

Covers FR-UX-10, NFR-MNT-01/03/06, AC-12/16.

## 11. M8 Organization features

Each group needs its provider/data sub-specification before implementation.

| Task | Expansion | Required acceptance |
|---|---|---|
| M8-01 | Team ownership/alignment and fragmentation views | Identity changes and team history do not produce unexplained metrics |
| M8-02 | Multi-repository portfolio, goals, scheduled reports | Explicit project access/scope; reproducible per-project and aggregate results |
| M8-03 | Branch and delivery analytics | Define branch/merge semantics, task linkage, time windows, and missing-data behavior |
| M8-04 | Issue-tracker adapters and cost/ROI views | Provider-specific contract tests; estimated and observed costs clearly separated |
| M8-05 | Additional report/notification integrations | Explicit configuration and delivery outcome; reuse persisted results |

These deliver broader CodeScene-like workflows. Their absence does not block
free private-repository analysis or the initial library-assessment release.

## 12. M9 Advanced optional work

| Task | Expansion | Prerequisite |
|---|---|---|
| M9-01 | Narrow deterministic fixes and dry-run patches | Precise source edits, idempotence, compilation/tests where relevant |
| M9-02 | Agentic semantic refactoring and PR repair | Separate language-specific behavior-validation design and reviewable changes |
| M9-03 | API/ABI compatibility, fuzzing, dependency evidence adapters | Explicit supported formats/platforms and scope; no unsupported safety claims |
| M9-04 | Additional analyzed languages | Language-specific metrics, fixtures, calibration, and documentation |
| M9-05 | SSO/RBAC and optional managed hosting | Access/data ownership/deployment sub-specification and operating-cost model |

## 13. Per-change workflow

### Coverage of requested feature groups

| Feature group | Delivery |
|---|---|
| Health, code smells, measured hotspots, refactoring priorities | Correct existing behavior in M0; richer measurements and explanations in M4 |
| Rule configuration, exclusions, baselines, and local suppressions | M0/M3; general policy packs and scoped deviations in M5 |
| Health/complexity trends, function drill-down, critical code, basic goals | M4 |
| Change coupling, architectural hotspots, historical function ranking | M6 |
| Ownership, author familiarity, knowledge islands, bus-factor simulation | M6 |
| Team alignment, fragmentation views, portfolio goals | M6 metrics; M8 organizational views |
| CLI, changed-file checks, PR regression feedback, CMake and SARIF | M3 |
| Tests, coverage, sanitizers, consumer contexts, configurable readiness | M5 |
| API, HTML, PDF, dashboard, indexed/paginated results | Existing functionality verified in M1; scale/history extensions in M2/M4/M5 |
| IDE, MCP, portable skill, consumer integration templates | Basic skill after M3; full integration in M7 |
| Portfolio, scheduled reports, issue trackers, branches, delivery/cost | M8 |
| Deterministic fixes, AI refactoring, automated PR repair | M9 after behavior-validation sub-specification |
| Local packages, optional components, self-hosting | M1/M3 |
| Enterprise identity, managed hosting, more languages | M9 |

For a bug: record the smallest reproduction, add a failing regression, fix the
cause, run affected and contract checks, verify the installed package, and
classify the release impact. For false positives, retain a clean counterexample.

For a feature: specify its behavior and contracts, generate applicable
scaffolding, implement each phase in order, exercise real input and failure
cases, update generated/reference docs, measure resource impact, and validate
the candidate. Do not close a feature merely because scaffolding compiles.

For a dependency update: prepare a locked update, run the support matrix and
artifact-install tests, inspect changed behavior, and include compatibility
notes. Avoid unrelated upgrades in a bug-fix patch.

## 14. Definition of done

A milestone is complete only when its requirements and applicable AC-01..16
scenarios have recorded evidence; component checks and integration pass;
contracts and old supported inputs remain compatible or have a migration;
packaged installation works; documentation examples execute; performance impact
is measured; and decisions/limitations are recorded.

For releases, retain the exact candidate and its verification manifest,
versions, checksums, notices, changelog, upgrade/rollback notes, and platform
support table. Publishing a candidate is separate from declaring tests passed.
Do not claim a supported OS, sanitizer, standard mapping, or library context
without corresponding evidence.

Current constraints: the earlier implementation drafts are uncommitted, no
working assurance engine exists, and Docker daemon execution was unavailable
during the audit. Documentation checks do not replace future runtime, Docker,
platform, or marketplace verification.
