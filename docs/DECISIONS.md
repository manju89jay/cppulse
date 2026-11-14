# cppulse Architectural Decisions Log

> This document explains the WHY behind every significant design choice.
> Read this before any interview — it's your defense guide.

## How to Read This

Each decision follows: **Context** (what problem), **Decision** (what we chose),
**Why** (the real reason), **Tradeoffs** (what we gave up), **Standard Reference**
(if applicable).

---

## D1: libclang over custom parser / Tree-sitter / Clang plugin
- **Context**: Need to parse C++17 for 22 detection rules
- **Decision**: libclang C API
- **Why**: Full semantic AST (resolves types, follows includes), stable ABI across LLVM versions, same parser as Clang compiler
- **Tradeoffs**: Verbose callback-based API, slightly slower than Clang plugin
- **Reference**: ADR-001

## D2: CRTP rule engine over virtual dispatch
- **Context**: 22 rules need polymorphic dispatch during AST walk
- **Decision**: Curiously Recurring Template Pattern
- **Why**: Zero-overhead — no vtable lookup in the hot loop (AST visitor callback runs per-cursor). Rules are statically known.
- **Tradeoffs**: Cannot add rules at runtime, all rules compiled in. Acceptable for v1.0.
- **Interview angle**: "I chose CRTP because the rule set is closed and known at compile time. If rules needed to be loaded dynamically (plugins), I'd switch to virtual dispatch."

## D3: std::variant rule container over type-erasure
- **Context**: Need to store heterogeneous CRTP rule objects in a single container
- **Decision**: std::variant<Rule1, Rule2, ...>
- **Why**: Cache-friendly (no heap allocation), type-safe, compiler-checked exhaustive visitation
- **Tradeoffs**: Closed set; adding a rule requires modifying the variant typedef
- **Interview angle**: "variant gives me value semantics, cache locality, and exhaustive std::visit. For an open plugin system, I'd use std::unique_ptr<RuleInterface>."

## D4: XGBoost over neural networks / logistic regression
- **Context**: Bug prediction from 12 tabular features
- **Decision**: XGBoost gradient-boosted trees
- **Why**: Best performer on tabular data (Kamei et al. 2013), interpretable via SHAP, trains in seconds on CPU
- **Tradeoffs**: Requires enough labeled training data (SZZ needs 50+ commits)
- **Reference**: ADR-002
- **Verification note**: The original comparative rationale is not a measured cppulse result. The current work has not established that XGBoost outperforms other methods or that its ranking is calibrated defect probability. Historical source examples cannot supply that evidence.

## D5: SZZ algorithm — simplified keyword-based approach
- **Context**: Need to label bug-introducing commits for ML training
- **Decision**: Keyword matching ("fix", "bug", "patch") + git blame
- **Why**: Works without issue tracker integration. Original SZZ (Śliwerski et al. 2005) is well-cited.
- **Tradeoffs**: Higher false positive rate than issue-tracker linked SZZ. Honest limitation.
- **Interview angle**: "I chose keyword-based SZZ for zero-dependency operation. In production, I'd integrate with Jira/GitHub Issues for higher precision."

## D6: JSON files over REST for pipeline communication
- **Context**: 6 components need to pass data
- **Decision**: JSON files in shared ./output/ directory
- **Why**: Debuggable (inspect files directly), pipeline can run step-by-step, no network complexity
- **Tradeoffs**: Not real-time, requires shared filesystem. For microservices, I'd use gRPC.
- **Reference**: ADR-004

## D7: Health score weighted penalty system
- **Context**: Need a single 0-100 health score
- **Decision**: Default profile: memory_safety×3, complexity×1.5, modernization×1. Safety-critical profile adds misra×2.5.
- **Why**: Safety-critical findings weighted highest. MISRA only included when explicitly opted in via `--profile safety-critical` (see D13).
- **Tradeoffs**: These are heuristic category weights. Empirical calibration and superiority over other formulas have not been established by the retained verification.

## D8: 15 default rules + 7 opt-in MISRA — standard-grounded where possible
- **Context**: Which rules to implement?
- **Decision**: Default profile: 3 memory safety, 9 modernization, 3 complexity (15 rules). Safety-critical profile adds 7 MISRA rules (22 total).
- **Why**: Memory rules map to common CVE patterns. Modernization rules are empirical best practices from clang-tidy modernize-* checks. MISRA rules are opt-in because they target safety-critical embedded (see D13).
- **Tradeoffs**: Not exhaustive. 15 default rules cover the three main debt categories for general-purpose C++. MISRA opt-in adds a fourth for safety-critical projects.
- **Interview angle**: "I picked 15 default rules covering three debt categories for general C++, plus 7 opt-in MISRA rules for safety-critical work. MISRA is opt-in because real-world testing showed it produces false signals on general-purpose code (see D13)."
- **Verification note**: This is historical design wording. All22 detectors are registered unless disabled; the profile changes scoring/roadmap selection. Named coding-standard associations are limited design references, not a verified standards-conformance mapping or compliance claim. Fresh detector accuracy has not been measured.

## D9: WeasyPrint for PDF generation
- **Context**: Need professional PDF reports
- **Decision**: WeasyPrint (HTML/CSS → PDF)
- **Why**: Full CSS support, Jinja2 templating, Python-native. No external LaTeX dependency.
- **Tradeoffs**: Large Docker image due to system deps (pango, cairo). Acceptable for server-side generation.

## D10: React + Recharts dashboard
- **Context**: Interactive visualization of analysis results
- **Decision**: React 18 + TypeScript + Recharts + Tailwind
- **Why**: Recharts has treemap (for hotspots), standard React stack, Tailwind for rapid styling
- **Tradeoffs**: Full SPA for what could be a static page. Justified by: interactive filtering, future trend comparison.

## D11: CLI in C++ (not Python)
- **Context**: Orchestrator for the pipeline
- **Decision**: C++17 with CLI11
- **Why**: Demonstrates full-stack C++ capability, consistent with analyzer-core. CLI11 is header-only.
- **Tradeoffs**: Python subprocess calls from C++ are less elegant than a pure-Python orchestrator.
- **Interview angle**: "I used C++ for the CLI to show I can build end-to-end in C++, not just the analysis engine."

## D12: Cold-start fallback for ML predictor
- **Context**: Repos with < 50 commits can't train XGBoost
- **Decision**: Fallback to heuristic weighted scoring (no ML)
- **Why**: Graceful degradation. Users still get useful output.
- **Tradeoffs**: Heuristic ranking works without training or optional ML dependencies. Relative accuracy against the trained model has not been established here.

## D13: MISRA rules opt-in via analysis profiles
- **Context**: After analyzing 6 real-world C++ projects, MISRA compliance scored 0.0 on 5 out of 6. protobuf scored 0/100 overall despite being Google production code.
- **Decision**: Default profile excludes MISRA rules. `--profile safety-critical` enables them with 2.5x weight.
- **Why**: MISRA C++:2023 targets safety-critical embedded systems (AUTOSAR, DO-178C, IEC 62304). General-purpose C++ projects deliberately use `goto`, unions, multiple returns, and uninitialized-then-assigned variables. Penalizing them produces false signals.
- **Tradeoffs**: Default profile only evaluates 15/22 rules. Safety-critical projects must explicitly opt in.
- **Interview angle**: "I discovered this by running cppulse on 6 real codebases. protobuf scored 0/100 because of MISRA rules — that's a false signal. Making MISRA opt-in shows I can calibrate a tool based on real-world data rather than theoretical assumptions."
- **Verification note**: The historical example totals are inconsistent and are not fresh benchmark or calibration evidence. The reproducible current behavior is an explicit scoring profile with separate detector switches; use the retained synthetic/real-input logs and their scope limits for an interview rather than presenting this original narrative as independently verified research.

## D14: Configurable assurance assessment separate from health and bug ranking
- **Context**: A library's maintenance score cannot establish suitability for a safety-related application. ISO 26262 and IEC 62304 include lifecycle evidence beyond code patterns; organizations also need their own policies.
- **Decision**: Add versioned JSON policies and evidence manifests with draft-07 validation. Controls return passed, failed, unknown, or not_applicable. Report weighted readiness, evidence completeness, and observed results separately. Missing evidence receives no readiness credit, and required unknown controls block the build gate.
- **Why**: Prevent clean-looking partial scans and low-priority style improvements from being mistaken for safety assurance. Keep weights, thresholds, standards, and applicability visible and user configurable.
- **Tradeoffs**: The scores describe satisfaction of the selected policy, not calibrated defect probabilities, ASIL, medical software classification, certification, or production approval. Starter policies are deliberately incomplete examples without licensed standard text or asserted clause mappings.
- **Interview angle**: "I made the score reproducible against a policy and a source snapshot. Unknown is a first-class result rather than an implicit pass."

## D15: Expose analysis gaps before awarding positive evidence
- **Context**: libclang may return an AST with fatal include errors; the MVP previously counted that file as analyzed. Headers often use interpolated compilation flags and templates still need consumer instantiations.
- **Decision**: Preserve partial findings and add per-file parse status, diagnostic error counts, compile context, and enabled rule IDs to findings metadata. A finding-limit control can fail on observed violations but can pass only with complete scoped parsing, database arguments, and enabled requested rules. Database arguments may be interpolated and are explicitly not proof of tested build variants.
- **Why**: An empty findings array must not manufacture confidence when analysis did not actually run. Explicit context evidence is required independently for library consumer configurations.
- **Tradeoffs**: More unknown results, including fallback scans and legacy reports without coverage metadata. No claim of exhaustive template, macro, target, or dependency coverage.
- **Interview angle**: "I separated successful parsing from obtaining a partial AST, and separated header parsing from testing its instantiations."

## D16: Local evidence integrity and a build gate, without replacing sanitizers
- **Context**: Developers want build integration as approachable as sanitizer flags while retaining their existing analysis and test tools.
- **Decision**: Add a small Python assurance package, a CMake opt-in target, artifact SHA-256 checks, and source snapshot binding. Existing pipeline JSON stays compatible. External test and review records are explicit attestations; command receipts establish execution results only.
- **Why**: Reuse mature compilers and sanitizers and concentrate cppulse on a visible, configurable evidence gap. Ship canonical schemas as package data so installed assessments do not depend on a checkout.
- **Tradeoffs**: Hashes detect changed artifacts; they do not authenticate a producer or prove an attestation. Scoped source hashes do not cover external dependencies, toolchain binaries, or hardware. A sanitizer command's zero exit status alone does not prove instrumentation or adequate exercised paths.
- **Interview angle**: "The build fails for unsatisfied policy, while the JSON still contains partial evidence and specific next actions."

## D17: Free Agensi skill as a text workflow package
- **Context**: Agensi distributes SKILL.md and text resources through MCP, not compiled cppulse binaries.
- **Decision**: Prepare a single MIT-licensed skill ZIP and a free listing description. Keep the native tool's installation and the skill's distribution distinct.
- **Why**: The skill can guide agents through evidence collection and interpretation without implying that loading a skill installs a compiler tool or performs certification.
- **Tradeoffs**: Publishing requires an authenticated creator account and marketplace review. A prepared ZIP is not a live listing.
- **Interview angle**: "I packaged the repeatable assessment workflow, while keeping the executable tool independently usable."

## Proposed decisions for the production platform specification

The entries below describe the proposed specification in
docs/specs/production-platform/. They do not mark the corresponding runtime
features as implemented or the proposal as accepted.

## D18: Consolidate existing work before expanding the platform
- **Context**: The working branch predates the locally recorded origin/main, which already contains density scoring, profile filtering, generated-source exclusions, and reproducibility work.
- **Decision**: Inventory and reuse existing changes before adding platform features; keep the current implementation drafts distinct from supported functionality.
- **Why**: Avoid duplicate implementations and conflicting score definitions.
- **Tradeoffs**: Baseline reconciliation and verification precede visible new features.
- **Interview angle**: "I treated repository history as existing engineering investment and verified it before rebuilding capabilities."

## D19: Immutable runs and an indexed history catalog
- **Context**: Independent mutable JSON reads can mix runs; large histories and reports need efficient access.
- **Decision**: Preserve JSON interchange and legacy exports while proposing immutable run snapshots, atomic latest publication, and a local SQLite history/index catalog.
- **Why**: Keep artifacts inspectable and add coherent reads, paging, checkpointing, and historical queries.
- **Tradeoffs**: Requires catalog migrations, atomic-publication tests, and a compatibility path for flat-file consumers.
- **Interview angle**: "I retained the debuggability of JSON while indexing the queries that became expensive."

## D20: Separate fact extraction from assessment caching
- **Context**: Header, compiler, and macro changes affect analysis; policy-only changes often do not require parsing again.
- **Decision**: Cache extraction by source/dependency/context/tool/rule identities and evaluation by fact/scorer/policy identities, using bounded isolated workers.
- **Why**: Obtain incremental speed without reusing stale semantic results or rerunning expensive parsing for every weight change.
- **Tradeoffs**: Dependency uncertainty requires conservative invalidation; process isolation adds scheduling and serialization costs.
- **Interview angle**: "Cache correctness was an observable invariant: a warm or incremental run must agree with clean execution."

## D21: One installed product and one locally runnable verification path
- **Context**: Checkout-relative commands, duplicated CI scripts, and heavy optional dependencies increase support and release effort.
- **Decision**: Preserve the C++ CLI and existing components, add namespaced Python packaging and optional capabilities, and wrap standard component tools with one cross-platform local developer runner.
- **Why**: Users receive a coherent install and maintainers verify the artifact users actually run, following the local Docker Compose constraint.
- **Tradeoffs**: Package migration and native-runtime installation testing require additional engineering; early releases support only verified platforms.
- **Interview angle**: "I made package installation and interface compatibility release tests, rather than assuming source-tree tests were sufficient."

## D22: Version scoring, policies, and comparison identities explicitly
- **Context**: Changed rules, formulas, configuration, or fingerprints can make historical scores and baselines incomparable.
- **Decision**: Pin these identities in manifests and require explicit migration or visibly interrupted comparisons; keep health, experimental risk, completeness, and policy readiness separate.
- **Why**: Make upgrades explainable and prevent a tool update from silently changing an organization's acceptance criteria.
- **Tradeoffs**: More metadata and migration work; visually continuous trends may need an explicit break.
- **Interview angle**: "I treated metric meaning as an API contract instead of silently recalculating yesterday's baseline."

## D23: Automate extension and candidate preparation with behavior checks
- **Context**: More detectors, evidence formats, and integrations otherwise multiply boilerplate, documentation drift, and manual releases.
- **Decision**: Propose a shared rule registry, extension generators, generated reference material, regression-first fixes, and locally prepared release candidates with verification manifests.
- **Why**: Make routine contribution and release work repeatable while keeping detector validity and semantic changes reviewable.
- **Tradeoffs**: Generators and contracts need maintenance; scaffolding and passing mechanical checks do not prove analysis quality or certification.
- **Interview angle**: "I automated repeated mechanics and kept observable behavior and compatibility as the acceptance boundary."

## Documentation decisions

## D24: Keep the tool landscape as a repository reference
- **Context**: The user requested a durable copy of the tool comparison before narrowing cppulse's goal.
- **Decision**: Save the categorized tables, availability notes, official sources, and research date in docs/research/cpp-analysis-tool-landscape.md, and link it from README.md. Keep goal selection pending.
- **Why**: Make the comparison easy to find from the repository and reusable in later planning discussions.
- **Tradeoffs**: Product capabilities and licensing are a dated snapshot; the linked sources need review when making a selection.
- **Interview angle**: "I preserved the research separately from feature commitments so the comparison could guide scope without silently becoming the roadmap."

## D25: Consolidate product discovery separately from feature commitments
- **Context**: The user requested a document covering the research gathered so far, present capabilities, and what could make cppulse useful to current C++ developers.
- **Decision**: Add docs/research/cppulse-product-discovery.md and link it from the README and tool landscape. Record source-inspection limits, proposed differentiation, the maintainer/consumer example, and validation questions; retain the earlier platform specification as a separate proposal.
- **Why**: Provide one reusable reference without confusing existing source, uncommitted drafts, hypothetical diagnoses, and possible future functionality.
- **Tradeoffs**: Source observations and competitor capabilities are dated; a discovery summary cannot establish runtime correctness, user demand, qualification, or accepted implementation scope.
- **Interview angle**: "I made the proposed value concrete while preserving the evidence boundary between research, code presence, validated behavior, and release claims."

## D26: Present cppulse as an engineering prototype in application materials
- **Context**: The user requested an honest project assessment, application paragraph, and one-page PDF.
- **Decision**: Prepare a source-grounded portfolio overview with implemented engineering work, explicit prototype maturity, and proposed work kept separate.
- **Why**: Demonstrate C++ tooling and architecture without using unverified benchmarks or production/safety claims.
- **Tradeoffs**: A concise overview omits implementation details; a verified demo and claim reconciliation are still needed before relying on repository marketing.
- **Interview angle**: "I can explain the implementation, tradeoffs, limitations, and how development tools assisted the work."

## D27: Delegate prototype stabilization using an isolated cloud checkpoint
- **Context**: The user selected a cloud task to make the current project build, pass checks, and provide a job-application demonstration.
- **Decision**: Prepare a separate codex/job-application-demo-20261113 checkpoint branch from the current source and selected uncommitted project work. Include existing draft code, tests, and project documentation as context; exclude local employer-specific REVIEW.md and generated outputs. Delegate stabilization and a reproducible demo, while keeping the proposed evidence-policy MVP outside this task.
- **Why**: Give the cloud task a reviewable source snapshot and explicit acceptance criteria without losing local work or silently expanding the goal.
- **Tradeoffs**: The checkpoint preserves unvalidated drafts and requires independent build/test verification. Cloud Linux checks cannot establish Windows support, and Docker availability must be checked before claiming Compose integration passes.
- **Interview angle**: "I scoped the delegated task around reproducible evidence and a demonstrable prototype rather than treating a research proposal as implemented functionality."

## D28: Stabilize the existing prototype without expanding its product scope
- **Context**: The job-application task requires executed evidence from the current checkpoint, preserving draft work and prohibiting further project commits or remote writes.
- **Decision**: Retain the current pipeline and per-file scoring formula; normalize analyzer finding identities to repository-relative POSIX paths and adapt legacy absolute producer paths at the feature boundary. Keep API envelopes and adapt the dashboard. Empty feature sets have null health, heuristic runs identify themselves, and profile/model/formula metadata is explicit. Preserve legacy hotspot field names but label their severity proxy honestly.
- **Why**: Prevent split static/history signals, dashboard runtime shape failures and misleading perfect/ML results. Keep behavior changes reviewable without importing the unrelated scoring rewrite on main.
- **Tradeoffs**: Ranking remains uncalibrated, schemas gain nullable no-data scores, and the CLI remains checkout based with an explicit root override. Defaults exclude MISRA only from scoring/ranking/roadmap; detector switches remain independent. Native equivalent passed; Docker source fixes remain unexecuted because Docker is unavailable.
- **Interview angle**: "I verified contracts and real consumer behavior, distinguished missing data from clean input, and kept claims within the evidence."

## D29: Use shared local checks, transparent synthetic history and explicit report dispatch
- **Context**: Reproducibility required dependency constraints, a valid Git input, readable PDF output and an actual dashboard/API run; no external CI or project commits were authorized.
- **Decision**: Add local check/demo/validation scripts, fixed synthetic C++ sources and temporary local-only fixture commits using current timestamps and an explicit automation identity. Resolve CLI paths before component directory changes, route JSON/PDF formats explicitly, preserve successful subprocess logs, and forward config with explicit profile precedence. Pin pydyf 0.10.0 for WeasyPrint 61.2 and build Tailwind locally instead of fetching runtime CSS from a CDN. Reuse main's shallow-history helper and tests selectively. Correct Python Docker contexts to include schemas; use host output binds and a PDF one-shot service; wait for producer exit statuses in Compose integration.
- **Why**: Reproduce actual failures, avoid misleading synthetic history, make local output visible, and avoid treating a successful one-shot exit as an integration failure. A local CSS build removes a runtime network dependency.
- **Tradeoffs**: Fixture Git IDs/timestamps vary while source contents stay fixed; native dependencies still need setup. Compose execution requires a Docker host and is explicitly not claimed here. Historical examples were audited but retained with their inconsistent totals qualified in README.
- **Interview angle**: "The demo is small and transparent. Logs, schema checks, PDF renders and browser integration show exactly what ran; unavailable checks remain visible."

## D30: Validate demo totals against independent producers
- **Context**: Cross-checking native LOC against Git-miner physical line counts exposed an unconditional extra line in the analyzer; zero-score files also appeared as hotspots. Docker source review exposed duplicated analyzer entrypoint arguments and missing shared logging libraries.
- **Decision**: Count physical lines consistently for empty, final-newline and no-final-newline files; add a regression case. Omit zero-score hotspots and assert file/LOC totals independently in demo validation. Correct Compose analyzer arguments and runtime logging dependencies; retain the explicit Docker execution limitation.
- **Why**: Matching schemas alone cannot establish internally consistent results or accurate labels.
- **Tradeoffs**: Historical counts are not regenerated; these local Docker source corrections still require container execution. Commit-message keyword labeling remains noisy; the synthetic demo message avoids inadvertently matching the substring “fix” in “fixture”.
- **Interview angle**: "Independent totals caught a real producer bug that each component's original tests missed."

## D31: Autonomous core stages with retained technical review packets
- **Context**: The user authorized autonomous execution after the staged plan and product brief, retaining the prohibition on project commits, remote writes and publication.
- **Decision**: Execute S0-S7 through technical self-reviews, preserving the checkpoint and prior worktree. Keep unavailable Docker/platform and human usefulness validation separate from executed technical checks. Use pinned fmt/utfcpp plus a selected consuming application to go beyond synthetic-only proof.
- **Why**: Routine implementation can proceed without repeated approvals while the user retains concrete diffs, logs and artifacts for review.
- **Tradeoffs**: A technical self-review does not establish product demand, unavailable-platform support or permission to publish. Target-specific incomplete input remains explicit rather than being suppressed to improve scores.
- **Interview angle**: "Real inputs exposed compilation-command and completeness issues that a synthetic happy path did not exercise."

## D32: Scope health to attempted current sources and retain unavailable results
- **Context**: Current Git records previously included historical paths and the feature union missed clean untracked sources. Sparse/single-class datasets and missing parse scope could produce misleading model/health metadata.
- **Decision**: Project Git metrics onto current tracked lineage, make no-Git history explicitly unavailable, and use the analyzer's attempted source inventory as the feature universe when supplied. Full-scope health is null for partial scope or no active detectors. Unavailable evaluation metrics are null; model/backend failures use explicit heuristic fallback. Reports retain partial findings and explain limitations.
- **Why**: Deleted/excluded/history-only rows must not improve the score, and missing analysis/evaluation cannot masquerade as a perfect result or measured zero.
- **Tradeoffs**: Legacy inputs lacking coverage have unavailable full-scope health. Merge lineage remains marked partial. This prototype-v1 compatibility transition is explicit and will be versioned/reconciled in S2 rather than advertised as a stable release contract.
- **Interview angle**: "The source inventory defines what was inspected; Git history enriches that scope but does not redefine it."

## D33: Version meaning and publish coherent local snapshots
- **Context**: The unshipped prototype extended a schema still named 1.0.0, and independently mutable output files could represent different runs.
- **Decision**: Freeze the known original risk v1 shape, explicitly select prototype_v1 for the extended native pipeline, and introduce version 2 contracts. Normalize legacy observations conservatively; refuse nonrepresentable legacy exports. Use content/context identities, a validated manifest, staged immutable-by-API run directories, checked reads and atomic manifest-bound pointers. `latest` is the last completed collection; `latest_attempt` exposes newer partial/cancelled publications. A completed collection is not a policy pass.
- **Why**: Preserve existing data without inventing verification, model accuracy or complete analysis. A reader resolves one run before reading artifacts; failed publication cannot expose a mixed bundle.
- **Tradeoffs**: Initial storage is POSIX-only, uses an exclusive writer lock and reads artifacts into memory. Hashes establish integrity, not authenticity. Source verification concerns the declared finite inventory; legacy archive imports cannot retroactively establish source binding. Indexing, automatic stale-lock recovery and large-input streaming remain later work.
- **Interview angle**: "Independent review reproduced publication bugs that shape-only schema tests missed. I added cross-document and interrupted-publication regression cases."

## D34: Install canonical Python components beside a separately qualified native analyzer
- **Context**: The C++ checkout CLI embeds a project root, generic Python src packages collide, and optional PDF/ML/web dependencies burden a headless installation.
- **Decision**: Preserve the existing C++ CLI and source entry points while introducing one installed Python console dispatcher over namespaced implementations and the same C++17 analyzer. Package schemas/templates as resources. Ship a pure Python wheel plus a separate native archive with validated prefix-relative metadata, matching Clang builtins, required notices and declared host dependencies. Keep argument-vector execution and optional feature dependencies explicit.
- **Why**: Installed commands must operate outside the checkout and use the actual candidate artifacts, while existing component tests and callers keep their entry points.
- **Tradeoffs**: This refines D11 for installed orchestration; it does not replace the native analysis engine or discard the C++ CLI. The first native candidate targets only the exercised Linux environment and is not a self-contained compiler toolchain. Installation, optional-feature and relocation tests determine support rather than source presence.
- **Interview angle**: "Installation proof requires the delivered wheel and native prefix to work from an empty directory, with source-tree paths unavailable."

## D35: Resolve current attempts once and preserve failed analysis facts
- **Context**: An older completed result can remain apparently current after a component exit, missing PDF or interrupted operation. Flat files also allow mixed reads during replacement.
- **Decision**: Installed analysis retains failure logs/configuration/partial bytes before cleanup and records an incomplete attempt. Reports and each API request resolve one manifest-bound snapshot and read checked bytes. Incomplete API data returns409, corrupt stores503 and absent current PDF404; no stale flat fallback. Historical reports write derived output outside immutable runs. Flat exports remain compatibility views.
- **Why**: A new operational failure must be visible without erasing independent facts or presenting yesterday's result as current. A liveness response remains separate from project verification.
- **Tradeoffs**: Legacy flat mode remains less coherent by design. Source binding in archive-style analysis is unverified; explicit collection must inspect inputs before and after execution. Storage/publication failures can prevent retaining a failed attempt, but do not mask its original error.
- **Interview angle**: "I tested a newer incomplete attempt against valid old flat files and an old PDF; the API refused to display them as the new result."

## D36: Judge observed collection separately from process exit and pre-run intention
- **Context**: A zero exit can omit required reports, pre-run inventory can name a binary the actual run did not execute, and source/material can change before publication.
- **Decision**: Use explicit typed recipe bindings, bounded POSIX execution and separate normalization stages. Retain exact JUnit and CTest3.31.6 LastTest.log bytes, actual commands/directories and selected tool/binary identities. Preserve failed checks as usable observed failures; missing, stale, malformed or unsupported verification remains unavailable. Publish source-race facts as partial/stale without rerunning commands. Record separate snapshot and control-metadata caps.
- **Why**: A command receipt states what happened operationally; it does not alone establish valid verification of the intended artifact. Immutable snapshots preserve independent facts and make newer incomplete attempts visible.
- **Tradeoffs**: First support is narrow: trusted POSIX recipes, direct binary commands and a reviewed CTest dialect/options. Cached no-op outputs, wrappers, unknown producer versions and uncollected runtime/dependency closure cannot gain implicit verification credit. Captured bytes and metadata are bounded per file/step; memory, CPU and total disk are not sandboxed.
- **Interview angle**: "A real counterexample passed the test names while executing a different binary. I closed that gap with actual execution records and retained artifact identities."

## D37: Separate the selected collection job from the observed parse context
- **Context**: A build/test job declaration does not describe the exact arguments libclang used for a file. A raw findings report, an expired test result or an inconsistent outcome label must not silently become current verification evidence.
- **Decision**: Retain the native parser's ordered arguments, actual process working directory and libclang version. Define typed execution facts and an explicit per-file analysis inventory linked to retained report/config/registry/database inputs. Normalize checked snapshot bytes into a new derived run, preserving parent bytes and identities. Keep job IDs for selecting policy scope and observed per-file contexts for analysis provenance. Require finite selected Clang resources to be retained explicitly for a matched analysis claim. These are S5 design/implementation decisions; acceptance waits for the complete producer, evaluator and installed gates.
- **Why**: Positive zero-finding results need an explicit requested file/rule scope and usable execution binding. Missing or stale evidence remains unknown; retained observations can explain a result without being relabeled as a complete build or whole-program verification.
- **Tradeoffs**: Initial matching is deliberately narrow and rejects ambiguous/inferred/fallback compilation contexts. The finite inventory is not a whole-system dependency closure or producer authentication. Policy evaluation reads supplied facts and an explicit assessment time; it launches no project commands. Exact rational arithmetic controls gates, and deviations cannot waive unknown or incomplete results or alter raw scores.
- **Interview angle**: "I distinguish the job we requested, the parser command we observed and the requirement we evaluate. Each has a separate identity and a testable boundary."

## D38: Give component installations the same YAML profile semantics
- **Context**: The canonical core pins PyYAML, but the predictor component's requirements omitted it. The Docker image and native component quickstart therefore could use a line-scanning fallback that silently interpreted a valid commented or quoted safety-critical profile as default.
- **Decision**: Pin PyYAML 6.0.3 in predictor/requirements.txt, matching the core package. Let the existing Dockerfile consume the shared requirements rather than adding a separate Docker-only dependency. Add valid commented and quoted profile regressions.
- **Why**: An installation path must not change the selected scoring profile for the same valid configuration.
- **Tradeoffs**: This repairs a source-level dependency gap. The predictor suite passed 98 tests and isolated host source-layout checks passed; those checks used host Python 3.12 and do not qualify Docker's Python 3.11 image or Compose execution, which remains unavailable.
- **Interview angle**: "I traced a configuration mismatch to the installed dependency closure, then fixed its shared source so local and container setups consume the same parser."

## D39: Keep coverage measurements and policy versions explicit
- **Context**: Line, branch and function coverage measure different units. A percentage can conceal missing files or configurations, and averaging reports can invent coverage that no selected job observed.
- **Decision**: Add bounded LCOV and Cobertura normalization with original report bytes, producer versions, unit counts and explicit source/job identities. The GCC 14.2/gcovr 8.8 collection slice binds finite profile files to actual compile, link and CTest receipts. Policy evaluator profile 1.1 adds per-file, per-job coverage thresholds using exact rational counts; an omitted profile retains the four-predicate 1.0 behavior. Missing, zero-total, conflicting or incompatible measurements remain unknown. Do not infer decision coverage, MC/DC or Cobertura function coverage.
- **Why**: A positive threshold must apply to every selected measurement cell, with a traceable denominator. Compatible repeated reports may be recognized without merging unrelated shards or choosing the most favorable result.
- **Tradeoffs**: These are narrow adapters, not a general coverage system. Failed process ancestry still blocks dependent reporting; raw failed-test profiles may be retained without acquiring positive verification credit. The isolated verification-tool environment pins gcovr without adding it to the headless runtime dependencies. S6 acceptance requires the full integration review.
- **Interview angle**: "I preserve the units behind a percentage and distinguish missing evidence from a measured shortfall."

## D40: Transfer evidence without promoting foreign claims
- **Context**: Upstream and consumer evidence can have different source identities even when they concern the same distributed library. Copying a manifest or verifying its checksum cannot establish producer authenticity or current local execution.
- **Decision**: Transfer checked raw manifests and artifacts in bounded, separately named directory roots. Preserve each original source scope and label reopened evidence as imported, unauthenticated and not rechecked for source freshness. Reject unsafe paths, symlinks, unlisted payloads and overwrite races. Read-only comparison can consume foreign roots; current-source publication requires a local run and explicit current-source checks. External GNU JSON diagnostics retain their producer namespace and unverified scan completeness, including parseable empty reports.
- **Why**: Consumers need to inspect original facts without silently merging foreign source inventories, inventing independent confirmation or replacing application tests with an upstream claim.
- **Tradeoffs**: The initial format is a local directory bundle, not an archive, signature or remote trust service. It uses Linux no-replace publication and bounded in-memory payloads. Compiler-diagnostic imports support a reviewed GNU 14.2 JSON slice; they do not constitute a complete external C++ scan. S6 acceptance waits for the consumer and integration gates.
- **Interview angle**: "Integrity tells me whether retained bytes changed; applicability and trust are separate questions."

## D41: Bind sanitizer outcomes to observed instrumentation and test controls
- **Context**: A sanitizer link flag or an empty successful log does not show that selected code was instrumented, executed or reported without suppression. Independent actual tests reproduced false clean outcomes through CTest configuration changes, automatic custom files, a same-named source in another command directory and source-defined UBSan default suppressions.
- **Decision**: Limit initial support to the exercised Linux ELF/GCC 14.2/binutils 2.44/CTest 3.31.6 slice. Retain and bind selected object callsite relocations, final runtime dependencies/symbols, source bytes, direct commands, literal finite CTest definitions and explicit custom-file guards. Require supported runtime options with an empty suppression override and stderr reporting, and reject known custom sanitizer default/report hooks. Preserve a credible runtime diagnostic as failure even when a recovering test exits zero; incomplete selected instrumentation remains explicit.
- **Why**: The result must describe the selected instrumented binary and actual exercised tests, with enough retained context to reject the concrete reporting and identity substitutions found in review.
- **Tradeoffs**: This does not prove every access was instrumented, every path executed, a complete runtime dependency closure or producer authenticity. Unsupported configuration remains unavailable. The actual twelve-case matrix and all four original counterexamples pass their intended outcomes; S6 overall acceptance still waits for consumer comparison, policy and shared integration checks.
- **Interview angle**: "A recovering UBSan test passed CTest while emitting a real defect. I kept operational test success and the sanitizer outcome separate."

## D42: Compare actual distributed artifacts and application evidence separately
- **Context**: A library source hash does not identify the package a consumer built against. Compatible upstream configuration also does not establish that the application's workload or requested header instantiations ran. Review reproduced same-name source substitution and usage borrowing across unrelated subjects.
- **Decision**: Retain explicit distribution subjects, declared matrices and observed consumer usage. Bind actual GCC main-source/depfile input identities, selected packaged headers, archive-member link-map use, binary and CTest execution. Compare an explicit upstream subject/matrix with the same selected local subject, keeping distribution mismatches separate from configuration dimensions. Preserve upstream raw documents in a foreign namespace; never merge their source scope into the application. Record local checks and missing evidence independently of upstream compatibility.
- **Why**: A consumer must be able to see both whether supplied evidence applies and what the application itself verified. Unknown applicability, an observed build failure and a missing local test require different explanations.
- **Tradeoffs**: The initial proof supports reviewed GNU command/depfile/map/version dialects. It is not an ABI certificate, exhaustive template test or runtime trust system. The pinned fmt 10.2.1 and utfcpp 4.0.5 examples exercise distributed packages; their entire upstream test suites are not claimed. The no-exceptions failure is deliberately seeded in a clearly synthetic header, not attributed to either upstream library.
- **Interview angle**: "The package can match upstream evidence while a required application test is still missing. I expose those as separate results."

## D43: Share public workflow engines and reject stale current material
- **Context**: Internal collection and policy APIs needed a reproducible public journey. Reusing an assessed run could preserve an expired gate, and changing a binary after a passed check could leave an old success looking current.
- **Decision**: Add strict finite public requests and thin collect/assess/check/baseline/compare dispatch over the accepted producers and pure engines. Validate all selected roles before collection commands. Reassessment reopens the exact original unassessed fact base, preserves old decision bytes as generic history and evaluates the current clock without rerunning project commands. Current derived operations check selected source and all finite observed generated-output identities before and during publication. A stale or unverified attempt retains an explicit partial gap with no active old assessment while preserving the previous completed run.
- **Why**: The CLI, opt-in CMake check and local workflow wrapper must apply one meaning and make missing or changed evidence visible. Completed capture/metadata operations, finding regression and policy acceptance have separate result fields and exits.
- **Tradeoffs**: Recipes execute explicitly selected trusted local code; this is not a hostile-code sandbox or a full dependency closure. Readonly historical explain/report remains available without a fresh-source claim. Source verification cannot retroactively upgrade unverified history. The dev2 source gate passes 15 checks and 2,499 tests; final installed-candidate acceptance is recorded separately in `review/autonomous/S7-REVIEW.md` once completed.
- **Interview angle**: "A check must reject a replaced binary even when the source and an older passing report are unchanged."

## D44: Keep finding regressions and snapshot presentation explicit
- **Context**: Line numbers move, identical diagnostics can repeat, and an HTML/PDF/dashboard view can misrepresent a result if it reads different mutable files. Baseline creation also must not silently approve or suppress existing defects.
- **Decision**: Persist explicit scoped finding baselines and multiset comparisons with retained source anchors, context/rule identities, reasoned expiring suppressions and bounded explicit rename maps. Ambiguous or incompatible identities remain unknown. Export SARIF from checked observations; baseline annotations require a retained typed comparison. Render one manifest-bound snapshot view in JSON, HTML, PDF, API and the packaged React dashboard, with exact raw artifacts and stored assessment reasons. Preserve the legacy report mode separately.
- **Why**: A developer should be able to trace the displayed gate or finding back to the same run and original bytes, and distinguish a new finding from a failed policy or missing proof.
- **Tradeoffs**: These comparisons require relevant fresh collection; no incremental analysis or automatic safe rename claim is made. The actual source workflow exercises 24 commands and 43 checked snapshots; public evidence examples demonstrate passed, failed and insufficient-evidence gates. Bundled UI runtime needs no Node server, but optional PDF/web packages and host libraries still apply. Installed dev2 and unavailable-platform qualification remain separate from source tests.
- **Interview angle**: "A shifted line can remain the same finding, but an ambiguous repeated line stays unknown instead of being matched optimistically."
