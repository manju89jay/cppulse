# cppulse Production Platform Requirements

Status: Proposed specification for review
Specification version: 1.0
Date: 2026-11-04

cppulse will be a free, locally usable C++ analysis and evidence-assessment
tool for applications, compiled libraries, and header-only libraries. It will
provide explainable maintenance assessments and evaluate configurable adoption
policies. Scalability, installation, compatibility, and automated maintenance
are release requirements throughout the program.

This is a proposal, not a statement that the capabilities below are implemented.
The implementation backlog is in [tasks.md](tasks.md); technical behavior and
examples are in [design.md](design.md).

## 1. Scope and operating constraints

### Product requirements

| ID | Requirement |
|---|---|
| PR-01 | The local core shall remain MIT-licensed and usable on public, private, and commercial projects without a cppulse account or subscription. Third-party dependencies retain their own licenses. |
| PR-02 | One public CLI shall provide consistent local analysis, policy checks, reports, and build integration. Dashboard, IDE, and agent interfaces shall consume the same results. |
| PR-03 | Static checks, Git history, test results, coverage, and runtime-tool evidence shall be combined through documented contracts, retaining each producer's provenance and limitations. |
| PR-04 | Code health, change-risk ranking, evidence completeness, and satisfaction of a selected policy shall remain distinct results. |
| PR-05 | Standards and organization requirements shall be supplied through versioned policy packs. Standards names and editions shall not be compiled into the evaluator. |
| PR-06 | The first supported language is C++. Additional languages, managed hosting, enterprise identity, and automatic semantic refactoring are expansion work. |
| PR-07 | Every advertised feature shall identify its supported inputs, maturity, and constraints. Unsupported checks, missing evidence, and incomplete scans shall be visible. |

### Repository constraints

Preserve working code and extend the existing CMake projects and rule engine.
Keep the hello_libclang utility. Use C++17, RAII, smart pointers, and spdlog;
follow the repository's C++ and Python style rules. Maintain architectural
decisions with Context, Decision, Why, Tradeoffs, and Interview angle.

Implement every milestone in the TASK_SPEC.md order: schemas, data producers,
consumers, presentation, orchestration, integration. Each affected component
must pass its checks before dependent component work starts.

Automation must run locally through scripts and Docker Compose. Existing CI
configuration can invoke the same scripts; no new external CI service is
required by this plan. The current TASK_SPEC.md remains the historical MVP
specification and its operating rules remain applicable. This proposal does
not modify docs/PRODUCT_VISION.md.

### Explicit limits

A passed policy is an assessment of the declared evidence and scope. It does
not assign ASIL, establish a medical software safety class, certify a product,
qualify cppulse as a safety tool, or establish suitability for every consumer.
Safety classifications are supplied by the responsible project, not inferred
from syntax or a health number.

Runtime sanitizers and established analyzers remain independent tools.
cppulse shall import and contextualize their results. A successful process
exit or an empty log alone shall not establish that sanitizer instrumentation
was enabled or that relevant paths were exercised.

ISO 26262 and IEC 62304 starter packs shall state their editions, coverage,
unassessed obligations, and review status. They shall not reproduce licensed
standard text or claim complete compliance. Exact clause mappings require
review against the relevant authorized edition.

## 2. Inspected baseline

The working branch is feature/full-mvp at 3945825, with earlier uncommitted
coverage and assurance-schema drafts. The locally recorded origin/main at
82120d2 contains newer work. These are local observations, not a fresh fetch
or evidence that a release has been published.

| Capability | Existing implementation | Remaining work |
|---|---|---|
| Analysis | 22 C++ rule classes: memory patterns, modernization, complexity, and a limited MISRA-inspired subset | Accuracy corpus, parse coverage, context handling, stable identities |
| Health scoring | Overall and category scores; density normalization and reproducibility checks in newer origin/main | Consolidation, missing-data behavior, coverage-aware reporting, calibration |
| Profiles | Configuration, exclusions, thresholds; newer branch filters MISRA output | Consistent effective configuration across every entry point |
| Git analysis | Frequency, churn, age, contributor counts, single-contributor alerts, SZZ labels | Canonical paths, renamed/deleted files, streaming history, identities, coupling |
| Risk ranking | XGBoost, heuristic fallback, SHAP/gain explanations, cross-validation | Honest model metadata, temporal evaluation, calibrated probability claims |
| Roadmap | Category actions and heuristic prioritization/effort estimates | Measured metrics, precise evidence links, explicit estimate labeling |
| Presentation | FastAPI read endpoints, React dashboard, seven-section PDF | Complete package-to-dashboard integration, history, paging, partial states |
| Orchestration | analyze, report, watch; basic GitHub PR comments and regression checks | Installed execution, reliable gates, fingerprints, native incremental workflow |
| Engineering | Component tests, formatting, Dockerfiles, existing CI configurations | Unified local verification, release packaging, compatibility/performance tests |
| Assurance | Draft policy/evidence/assessment schemas and parse-coverage edits | No working assessment engine or completed evidence workflow |

The audit reproduced separate feature rows for an absolute analyzer path and
a relative Git path naming the same file. It also reproduced an empty feature
set receiving health 100. Source inspection found severity used as a complexity
proxy, heuristic outputs labeled xgboost, and PR matching by basename/rule.
Milestone M0 must add regression cases and resolve these behaviors. Existing
work in origin/main must be reviewed before rebuilding features it already has.

## 3. Users and required journeys

| ID | User journey | Required outcome |
|---|---|---|
| UX-01 | An application developer installs cppulse and runs doctor, init, analyze | Actionable analysis without needing a cppulse source checkout, browser, PDF runtime, or ML installation |
| UX-02 | A library maintainer selects a target and consumer configurations | Results distinguish tested configurations, parsing assumptions, and unassessed consumers |
| UX-03 | A header-only maintainer supplies small consumer programs | Evidence covers declared instantiations and configurations without claiming exhaustive template coverage |
| UX-04 | A developer adds a build check | One documented CMake integration and a stable exit contract; no output parser written by the user |
| UX-05 | An existing project adopts cppulse | A versioned baseline supports gating new problems while showing existing debt |
| UX-06 | An organization adds a custom policy | Existing evaluation capabilities can be configured without editing the evaluator |
| UX-07 | A contributor adds a detector or adapter | A generator and contract tests provide the normal extension path |
| UX-08 | A maintainer diagnoses a bug and prepares a release | A reproducible local workflow verifies both the fix and the final installed artifact |

## 4. Functional requirements

### 4.1 Source and build context

| ID | Requirement |
|---|---|
| FR-CTX-01 | Discover supported C++ source and header extensions, including .cpp, .cc, .cxx, .h, .hh, .hpp, .hxx, .ipp, .inl, and .tpp. Record file classification and intentional exclusions. |
| FR-CTX-02 | Use normalized repository-relative identities throughout findings, history, scores, baselines, and reports. Preserve a display path and a separate identity for authorized external dependencies. |
| FR-CTX-03 | Accept a compilation database file or directory; honor its working directory, language standard, target, defines, include paths, and forced includes. |
| FR-CTX-04 | Record whether arguments were exact, inferred/interpolated, or fallback. Inferred header arguments shall not be described as an observed consumer build. |
| FR-CTX-05 | Represent each selected compiler/target/macro/standard combination as a distinct context. Do not merge incompatible variants into a single claim of coverage. |
| FR-CTX-06 | Record each discovered file as analyzed, partial, failed, excluded, unsupported, or not attempted, with reasons and diagnostics. |
| FR-CTX-07 | Record revision when available, dirty state, source-content identity, tool versions, effective configuration, rule versions, and policy identity. Git history shall be optional for static analysis. |
| FR-CTX-08 | Detect source/context changes during a run. Affected results shall be retried against a stable snapshot or marked incomplete. |

### 4.2 Static findings and maintainability

| ID | Requirement |
|---|---|
| FR-ANA-01 | Preserve existing rules, correcting detection limitations through regression fixtures rather than replacing the engine wholesale. Experimental checks shall be distinguishable from stable checks. |
| FR-ANA-02 | Emit measured function/file metrics: analyzed LOC, function length, cyclomatic complexity, nesting depth, parameter count, and duplication. Add cohesion and compound smells when validated. |
| FR-ANA-03 | Every finding shall include namespaced rule identity, tool/version, location, context, severity, explanation, and a stable comparison fingerprint. Numeric confidence shall not be presented as calibrated certainty without validation. |
| FR-ANA-04 | Never substitute severity or finding count for an advertised complexity measurement. Missing measurements remain unavailable. |
| FR-ANA-05 | Support declared source/generated/vendor/test exclusions, baseline handling, and scoped suppressions with rationale. Do not silently improve scores by hiding disabled checks or exclusions. |
| FR-ANA-06 | Produce a deterministic health calculation with a published formula and version. Report observed scope and analysis completeness beside it. |
| FR-ANA-07 | An empty, failed, or materially incomplete required analysis shall not receive an unqualified health 100. Full-scope health is unavailable until its prerequisites are met. |
| FR-ANA-08 | Apply the same effective profile and rule configuration in CLI, Docker, build targets, API consumers, and agent workflows. |
| FR-ANA-09 | Support normalized findings from external analyzers through adapters. Keep imported diagnostic identifiers and distinguish overlapping findings from independent confirmation. |

### 4.3 Git and behavioral analysis

| ID | Requirement |
|---|---|
| FR-GIT-01 | Preserve existing metrics while handling absent history, shallow boundaries, deleted files, renames, merges, and configured time windows explicitly. |
| FR-GIT-02 | Stream and reuse history processing; avoid repeated complete history materialization for each metric. Record truncation or bounds as limitations. |
| FR-GIT-03 | Support contributor aliases, bot exclusion, former contributors, and configured pair-programming attribution. Authorship is a knowledge proxy, not proof of expertise. |
| FR-GIT-04 | Add file-level change coupling with minimum support and configurable exclusions for bulk/generated commits. Add function-level coupling after symbol history exists. |
| FR-GIT-05 | Add weighted ownership, knowledge maps, offboarding simulation, and fragmentation at author/team levels. |
| FR-GIT-06 | Aggregate hotspots and coupling by user-defined architectural component. Label historical co-change separately from static include/call dependencies. |
| FR-GIT-07 | Persist comparable snapshots for health, complexity, hotspots, ownership, and goals. Mark gaps and method-version changes. |
| FR-GIT-08 | Preserve SZZ as an imperfect label source. Record label provenance and analysis cutoff; do not use future information to validate future-defect prediction. |

### 4.4 Verification evidence and library assessment

| ID | Requirement |
|---|---|
| FR-EVD-01 | Import CTest/JUnit results and coverage reports, initially LCOV and Cobertura. Preserve test counts, failed/skipped cases, covered/total counts, measurement type, and context. |
| FR-EVD-02 | Import ASan, UBSan, and TSan evidence using versioned adapters and explicitly selected collection recipes. Record supported platform, invocation, instrumentation evidence, executed test scope, and outcomes. |
| FR-EVD-03 | An empty report, zero tests, entirely skipped tests, process success alone, or unsupported parsing shall not imply successful verification. |
| FR-EVD-04 | Bind evidence to the declared source/context and producer version. Verify artifact integrity and detect missing, modified, stale, or mismatched evidence. Hashes do not authenticate the producer. |
| FR-EVD-05 | Distinguish execution-derived facts, imported producer claims, and human attestations. Report reviewers, rationale, expiry, and scope where supplied. |
| FR-EVD-06 | Allow a declared matrix of library consumers: compiler, OS/target, standard, macros, dependency configuration, linking mode, and required tests. |
| FR-EVD-07 | Header-only checks shall include declared consumer instantiations and header self-containment where requested. Passing a sample shall not imply all template types or macros were exercised. |
| FR-EVD-08 | Scope runtime evidence to the consumer binary and actual instrumentation. A prebuilt uninstrumented library requires an explicit limitation. |
| FR-EVD-09 | Keep line, branch, function, decision, and MC/DC coverage distinct. Do not infer MC/DC from branch coverage. |
| FR-EVD-10 | Provide extension points for fuzzing, API/ABI compatibility, dependency provenance, requirements traceability, and reviewed process artifacts. These are not initial complete implementations. |

### 4.5 Configurable policies and assessment

| ID | Requirement |
|---|---|
| FR-POL-01 | A policy pack shall declare identity, version, applicable scope/kinds/contexts, standards/editions if any, control definitions, weights, gates, and required evidence. |
| FR-POL-02 | Controls shall evaluate to passed, failed, unknown, or not_applicable. Applicability and exclusions require explicit machine-readable reasons. |
| FR-POL-03 | Initial evaluators shall support finding limits, numeric metric thresholds, minimum analysis coverage, test outcomes, minimum coverage, required context coverage, and reviewed evidence requirements. |
| FR-POL-04 | Publish readiness, evidence completeness, and observed-control satisfaction separately using the equations in design.md. Unknown controls receive no readiness credit. |
| FR-POL-05 | Required unknown controls block policy acceptance. Known blocking failures remain failures even when other evidence is unavailable. |
| FR-POL-06 | Deviations shall preserve the original result and score, be scoped and expiring, and only affect gates explicitly permitting them. Unknown required evidence cannot be converted into a pass by a deviation. |
| FR-POL-07 | Policy and rules configuration shall be validated on loading. Unsupported control types, unresolved references, duplicate IDs, invalid weights, and cycles shall be actionable errors. |
| FR-POL-08 | Supply general C++/library starter policies first, then explicitly incomplete automotive and medical starter packs with reviewed mappings. Custom organization policies require no domain-specific code when supported evaluators suffice. |
| FR-POL-09 | Policy changes shall not silently rebaseline a historical trend. Record versions and show comparisons only where definitions and scope are compatible. |
| FR-POL-10 | Policy files are data. Merely loading a policy shall not execute build, test, network, or shell commands. |

### 4.6 CLI, build, reports, and developer integrations

| ID | Requirement |
|---|---|
| FR-UX-01 | Preserve analyze, report, and watch compatibility; add init, doctor, check, explain, and explicit evidence-collection workflows. |
| FR-UX-02 | Provide concise text by default; structured JSON and SARIF where applicable; documented exits; logs separate from machine output; clear progress and cancellation. |
| FR-UX-03 | The CLI shall run from an arbitrary working directory. Discover installed components without checkout-relative cd commands or shell-interpreted user arguments. |
| FR-UX-04 | Configuration shall have documented precedence and an inspectable effective form. Conflicting discoveries and unsupported options shall not be silently ignored. |
| FR-UX-05 | CMake integration shall offer an explicit check target, compile context discovery, selected target dependencies, and optional ordinary-build enforcement. No new compiler sanitizer flag is claimed. |
| FR-UX-06 | Support changed-file/baseline checks with dependency-aware invalidation. Renames and same-basename files must not hide new findings. |
| FR-UX-07 | Reports shall show run completeness, analyzed scope, policy/scorer versions, findings, hotspots, evidence gaps, knowledge limitations, and actionable next work. Retain the existing seven PDF sections and add assessment material. |
| FR-UX-08 | Provide paginated findings and history APIs, searchable/filtered views, and links from summaries to original evidence. Every request resolves one committed run snapshot. |
| FR-UX-09 | Support deterministic HTML/JSON reporting without optional PDF or web dependencies. Installation of PDF/dashboard/ML shall be optional. |
| FR-UX-10 | Add read-first MCP capabilities, an initial VS Code integration, and a portable skill using the same public contracts. IDE/MCP results shall agree with the CLI. |
| FR-UX-11 | A local bug-report bundle shall exclude source excerpts, credentials, tokens, and unrestricted environment dumps by default. Upload is a separate explicit action. |
| FR-UX-12 | Offline runtime operation shall be supported after dependencies and packs have been installed. No account is required for core analysis. |

## 5. Scalability and reliability requirements

| ID | Requirement and acceptance invariant |
|---|---|
| NFR-SCL-01 | Active workers never exceed the configured jobs limit. Memory/time budgets shall constrain work on supported platforms; exhausted work is reported as incomplete. |
| NFR-SCL-02 | A worker crash, malformed report, or parser failure shall not discard completed facts from other work units. The final manifest records the failure. |
| NFR-SCL-03 | Cache reuse requires compatible source, dependency, context, detector, and tool identities. Unknown dependency relationships cause conservative invalidation. |
| NFR-SCL-04 | Cold, warm, source-edit, shared-header-edit, and policy-only runs shall be benchmarked. Warm and incremental results must be semantically identical to clean execution. |
| NFR-SCL-05 | Large runs shall stream or batch findings/history and use indexed storage for history and paging. JSON remains a documented interchange/export format. |
| NFR-SCL-06 | Checkpoints and atomic publication shall prevent mixed-run or stale-success reports. A canceled run must be distinguishable from a completed one. |
| NFR-SCL-07 | Benchmark tiers shall cover approximately 1K, 10K, and 100K files and histories of increasing length. This is a measurement plan, not a promised completion time. |
| NFR-SCL-08 | Record wall time, peak memory, CPU time where available, work units, cache hits, and environment. Freeze release budgets after M2 measurements on a named reference host. |
| NFR-SCL-09 | Repeated measured regressions beyond a documented budget require correction or a reviewed exception before release. Do not gate on one noisy measurement. |
| NFR-SCL-10 | No scalability feature may hide incomplete scope, change diagnostic meaning, or reuse invalid data to meet a speed target. |

## 6. Maintainability and compatibility requirements

| ID | Requirement |
|---|---|
| NFR-MNT-01 | Preserve component boundaries and separate analysis/evaluation from CLI, transport, rendering, and editor logic. Avoid circular imports and duplicated scoring logic. |
| NFR-MNT-02 | Introduce one namespaced Python distribution with shared contracts/configuration helpers while retaining existing component entry points during migration. |
| NFR-MNT-03 | Use one registry for rule metadata; generate registration helpers, reference documentation, example configuration, and integration metadata from it. |
| NFR-MNT-04 | Provide generators for new rules, evidence adapters, and policy packs. Generated scaffolds remain incomplete until meaningful fixtures and implementations pass. |
| NFR-MNT-05 | Lock release dependencies and document the supported compiler/libclang/Python/Node/platform matrix. Separate runtime, development, and optional dependency groups. |
| NFR-MNT-06 | Version CLI/API contracts, schemas, detectors, fingerprints, scoring formulas, and policy packs. Test compatibility and provide migrations for breaking changes. |
| NFR-MNT-07 | Experimental rules and new defaults shall have an explicit promotion process. Updates shall not silently change an organization's required policy. |
| NFR-MNT-08 | Store decisions and maintenance instructions with the code. Keep TASK_SPEC.md as the historical MVP and this specification as a proposed successor scope until accepted. |
| NFR-MNT-09 | Adapters shall declare supported producer versions and limitations. Unknown formats shall not be interpreted as clean results. |

## 7. Automation and releases

| ID | Requirement |
|---|---|
| REL-01 | One cross-platform local entry point shall run formatting checks, component tests, schema/contract checks, integration tests, package smoke tests, and selected benchmarks. |
| REL-02 | Required checks include CTest, pytest with component coverage, dashboard tests/build, schema compatibility, semantic score reproducibility, and actual installed-tool execution. |
| REL-03 | Full integration shall exercise analysis, Git metrics when available, assessment, HTML/PDF, API responses, dashboard behavior, and output extraction from Docker volumes. |
| REL-04 | A bug fix shall add a reproduction/regression test that fails before the fix. Include false-positive and neighboring behavior where relevant. |
| REL-05 | A feature shall include requirements/contracts, implementation, applicable fixtures, user documentation, compatibility classification, and measured resource impact. |
| REL-06 | Local packaging shall produce platform artifacts, a Python package, optional components, and versioned container images as supported. Test the artifact users install, not only the source tree. |
| REL-07 | Candidate generation shall assemble version/changelog, checksums, license notices, dependency inventory/SBOM, support matrix, and machine-readable verification results. |
| REL-08 | Publication is a distinct release action after candidate verification. Retain prior artifacts and an upgrade/rollback guide; no runtime forced self-update. |
| REL-09 | Automate dependency-update preparation, generated documentation checks, compatibility checks, and release-note preparation. Do not auto-weaken controls to make checks pass. |
| REL-10 | AI may prepare reproducible patches and suggested fixes. Semantic refactoring remains experimental until language-specific behavior validation exists. |
| REL-11 | Free software releases run on user/maintainer infrastructure. Managed hosting and external model/API usage have separate operating costs and are not promised as free infrastructure. |

## 8. Supported environments

The first stable artifact targets Linux x86-64 with tested GCC/Clang and
libclang combinations. Windows x86-64 and macOS artifacts graduate through
the same installed-package checks; an artifact shall not be advertised as
supported merely because cross-compilation succeeded. Existing MinGW work
is reused; MSVC compatibility is a separate tested claim.

The analyzer implementation remains C++17. Initial validated analyzed-language
profiles target C++17 and C++20. Other standards/targets can be represented
through compilation databases but remain explicitly unvalidated until their
fixture matrix passes.

Use CMake 3.25+ for the proposed developer workflow presets while preserving
the current 3.16 consumer integration minimum where feasible. Changing build
minimums requires an explicit compatibility decision. Python remains 3.11+.
Node is required for dashboard development, not headless use. Exact dependency
versions and platform combinations are selected and frozen in M1, using
supported stable releases.

## 9. Required release scenarios

| ID | Scenario | Expected behavior |
|---|---|---|
| AC-01 | Clean install; invoke outside cppulse checkout | doctor and documented analysis commands work without source-relative paths |
| AC-02 | Empty project, parse failure, missing compilation context | Explicit unavailable/partial result; no unqualified perfect score |
| AC-03 | Absolute/relative paths; Windows separators; identical basenames | One intended file identity; independent findings remain independent |
| AC-04 | Source/header/compiler-flag/dependency changes | Correct cache invalidation and equality with clean-run results |
| AC-05 | Policy weight/gate change without detector change | Re-evaluation without unnecessary AST work; policy version recorded |
| AC-06 | Worker crash, timeout, cancellation, disk-write interruption | Valid partial facts, coherent manifest, no stale passed gate |
| AC-07 | No Git repository or shallow history | Static results remain usable; Git-based claims show the limitation |
| AC-08 | Compiled library and header-only consumer matrix | Required contexts and untested instantiations are visible |
| AC-09 | Empty sanitizer log, zero/skipped tests, stale coverage | Unknown or failed evidence as appropriate; never automatic success |
| AC-10 | Required failed or unknown control with a high aggregate score | Gate cannot pass merely because of the average |
| AC-11 | Disabled check, exclusion, deviation expiry, policy mismatch | Explicit explanation, auditable scope, correct gate behavior |
| AC-12 | Same run via CLI/API/MCP/report | Identical underlying status, scores, identities, and evidence links |
| AC-13 | Previous supported config/schema/baseline | Compatible operation or an actionable migration error |
| AC-14 | Packaged HTML/PDF/API/dashboard flow | Meaningful outputs and correct partial/error states from the installed distribution |
| AC-15 | Six pinned real C++ repositories plus defect/clean fixtures | Reproducible measurements; accuracy and limitations documented |
| AC-16 | Free skill executed in a clean agent session | Uses only documented released commands and does not claim certification or install a native executable by loading text |

## 10. Deferred expansion

Team alignment, issue-tracker cost/delivery analysis, portfolio reporting,
scheduled reports, SSO/RBAC, additional languages, API/ABI compatibility
adapters, fuzzing adapters, and automated PR repair remain explicit backlog
items. They are specified as expansion outcomes in tasks.md, not prerequisites
for the first useful release. They require detailed sub-specifications before
implementation where their provider-specific contracts are not yet defined.

## 11. Competitive and distribution basis

CodeScene already provides scores, hotspots, configurable rules, knowledge
analysis, local tools, and build/review integration. Equivalent workflow
coverage is a reasonable goal; identical scores or accuracy are not assumed.
Its community offering serves open-source projects and its private-repository
products have paid plans. cppulse's adoption hypothesis is free private use,
inspectable methodology, accessible C++ integration, and explicit
consumer/policy evidence. Validate that hypothesis with real users before
investing in every enterprise feature.

Agensi receives a free text-based workflow skill. The executable is distributed
through cppulse release artifacts. Marketplace submission and review are
separate from preparing a ZIP.

Sources checked 2026-11-04:

- [CodeScene feature and plan matrix](https://codescene.com/pricing)
- [CodeScene community edition](https://codescene.com/product/codescene-for-open-source)
- [CodeScene analysis documentation](https://codescene.io/docs/guides/index.html)
- [ISO 26262-8:2018 scope](https://www.iso.org/standard/68390.html)
- [IEC 62304 scope](https://webstore.iec.ch/en/publication/6792)
- [Agensi packaging requirements](https://www.agensi.io/docs/packaging)
