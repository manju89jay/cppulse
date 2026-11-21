# cppulse Architectural Decisions Log

> Current scope and maintenance authority: [production-scope-authority.md](plans/production-scope-authority.md). The user accepted the full187-item production endpoint; old MVP/proposal labels are historical. Acceptance and runtime qualification remain separate. All prior decision bodies/IDs are preserved.


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


## PROD-20261114-01: Execute the full reconciled production scope
- **Context**: The full 118 requirements and 60 tasks were audited against delivered code; the earlier S0–S7 boundary did not satisfy the later full-product instruction.
- **Decision**: The latest user authorization starts full autonomous implementation with all P0–P14 phases retained. Keep a separate execution ledger, current-byte check evidence and independent acceptance review. Existing draft plans remain historical inputs. No new commits, pushes, deployment, publication or messages are authorized.
- **Why**: Delivery must be assessed against the complete product goal, not a convenient subset or aggregate test count.
- **Tradeoffs**: Unavailable platforms, standards review and human usefulness remain open blockers; they cannot be replaced by source inspection or invented tests.
- **Interview angle**: “I kept a requirement open until observable acceptance and current source-bound evidence supported it.”

## PROD-20261114-02: Reconcile C++17 style and configurable library limits
- **Context**: Historical style prescribed span/expected beyond C++17 and a fixed 500 KiB skip that conflicts with amalgamated-library support.
- **Decision**: Preserve the C++17 implementation, checked containers/results and explicit failure boundaries. Adopt a positive configurable max_file_bytes with a 16 MiB default and visible skip reasons. Synchronize only genuinely shared concurrent state.
- **Why**: Standards and resource limits must describe actual supported code and cannot silently exclude the primary library use case.
- **Tradeoffs**: The byte limit is not a memory or whole-program safety guarantee. Per-worker memory isolation and tested platform combinations remain separate requirements.
- **Interview angle**: “A configured large header can be analyzed; an exceeded limit remains an explicit incomplete result.”

## PROD-20261114-03: Preserve snapshot decision provenance
- **Context**: Uploaded D28/D29 describe review restrictions and research capture; current D28/D29 describe different later changes.
- **Decision**: Preserve current entries unchanged. Refer to the uploaded entries as SNAPSHOT-20261114-D28 and SNAPSHOT-20261114-D29, retaining the separately audited source paths and hashes rather than overwriting either history. Subsequent user Git authorization applies only to the recorded historical save/push.
- **Why**: Reused IDs cannot establish one continuous decision history or override current instructions.
- **Tradeoffs**: Historical references require their provenance label, not an ambiguous bare D number.
- **Interview angle**: “I reconciled contradictory records without rewriting evidence.”

## PROD-20261114-04: Qualify installed editor bytes against one closed backend wheelhouse
- **Context**: The VSIX was built, but `test:host` referenced a missing runner. Backend installation selected an older same-version cppulse wheel from a second directory and failed the current hash lock.
- **Decision**: Add an isolated real-host runner that installs the actual VSIX and invokes a separately installed CLI. Prepare verification backends using a single wheelhouse with exactly one cppulse wheel and its actual SHA-256; retain hash checking. Record display/socket failures as environment blockers, with no editor-host acceptance.
- **Why**: Compiled sources and client unit tests cannot establish behavior of installed extension bytes. Weakening lock verification would hide the wrong-package selection.
- **Tradeoffs**: The current native fixture uses the earlier named dev2 native candidate. Linux display startup is blocked in this command environment; full P2/P8, other platforms and production-native qualification remain unfinished. Unit/syntax checks do not establish host acceptance.
- **Interview angle**: “A reproducible installation selects one exact artifact; a packaged extension still needs a real-host test.”

## PROD-20261116-01: Preserve exact native measurement and runtime capabilities
- **Context**: Fresh Cloud tests reproduced CR-only LOC errors and omitted unresolved includes. The container's default libclang 18 lacked the binary-opcode API required by the implementation.
- **Decision**: Count physical/code lines with the exercised Clang semantics (CR/LF breaks, CRLF one break, LFCR two), retain unresolved inclusion facts, configure-check the required libclang API, and select LLVM/libclang 19 in the analyzer container.
- **Why**: Producer measurements and dependency gaps must be real before consumers can score or reuse facts.
- **Tradeoffs**: The exercised host is GCC14/libclang19.1.7; the Ubuntu container is a separate version lane. Include observations alone do not establish closed dependencies for positive cache reuse.
- **Interview angle**: “I tested raw outputs and compiler coordinates before trusting derived scores.”

## PROD-20261116-02: Make Git tooling optional for installed static analysis
- **Context**: The core distribution required GitPython and eagerly imported its miner even for a source directory with no history. This contradicted the required absent-Git workflow.
- **Decision**: Move GitPython to the git extra (also installed for development tests) and put the miner behind an optional-tool boundary. Missing Git/GitPython produces validated unavailable-history metadata, no file history rows, and no invented ownership/ranking evidence. Available-miner operational failures remain failures.
- **Why**: Static analysis must work without a Git executable or GitPython while preserving missing-data meaning.
- **Tradeoffs**: Existing component development requirements retain GitPython. Core numerical/presentation dependencies are unchanged; ML/PDF/web remain optional.
- **Interview angle**: “An unavailable history stage is explicit data rather than a reason to lose static findings.”

## PROD-20261116-03: Bind declared reviews to exact artifact bytes
- **Context**: Local artifact IDs can name changed generated bytes under the same source digest; a review bound only to source and ID could wrongly pass.
- **Decision**: Policy profile 1.2 positive reviews require reviewed_artifact_sha256 bindings for every policy-required artifact, matching the current manifest. Legacy review metadata remains readable but unknown. Reject unreachable reviewer quorums.
- **Why**: A source identity and caller label do not show which report was reviewed.
- **Tradeoffs**: Old unstamped claims need a new scoped review record. Digests do not authenticate a reviewer or establish independent human review.
- **Interview angle**: “I distinguish the identity of reviewed bytes from the label attached to them.”

## PROD-20261116-04: Expose measured scoring and bounded read clients explicitly
- **Context**: Missing measured consumer modules blocked collection. A helper-only scorer would not provide the requested public journey; a read client must not silently execute recipes or recompute gates.
- **Decision**: Preserve the historical scorer and expose versioned measured health through explicit required contexts and immutable derived runs. Add read-only MCP stdio tools with snapshot/request/response bounds and a pinned, authenticated optional work-unit catalog route. Keep incomplete scale/cache obligations open.
- **Why**: Every interface must retain the same measured facts, score prerequisites, identities and missing scope.
- **Tradeoffs**: Finite MCP snapshot reads are a bounded preview, not indexed large-project qualification. Private cache/index primitives do not establish public incremental equivalence or benchmark acceptance.
- **Interview angle**: “A new client reads the same result and cannot manufacture a newer passing assessment.”

## PROD-20261116-05: Keep incremental primitives conservative and catalog reads finite
- **Context**: Missing work-unit runtime prevented baseline collection. Native parse contexts, receipts and dependency observations have distinct identities; observed include edges do not establish a closed content manifest. A row-count limit alone did not bound catalog response bytes, and a reader must not create a catalog while serving a request.
- **Decision**: Add a private finite work-unit protocol with isolated native processes, exact retained input/executable/argv/TU bindings, resource capability observations, bounded submission and cancellation, and checked checkpoints that preserve original receipts. Reject positive reuse when dependency closure is unknown. Keep extraction keys separate from assessment keys and retain cache origins without issuing new native/runtime receipts. Index immutable, schema-checked work-unit summaries transactionally in SQLite; serve the optional configured catalog through readonly opens and run/query/row/byte-bound pages.
- **Why**: An interrupted worker, changed input or stale cache cannot become a clean new execution. API reads stay finite and do not mutate the selected evidence store.
- **Tradeoffs**: The cache/index protocol remains private. Native dependency closure, integrated clean/cached/resumed equivalence, full findings/history indexes, budget-derived pool sizing, crash recovery beyond explicit fresh work roots, other-platform resource qualification and representative scale benchmarks remain open. Digest checks identify bytes and do not authenticate producers. The optional summary API does not close the complete P5 plan.
- **Interview angle**: “I retained an original receipt on resume and refused a cache hit when I could not identify every dependency.”

## PROD-20261116-06: Bound candidate MCP and skill claims to exercised installed bytes
- **Context**: A real normalized native run retains about 15 MiB including compiler resources, exceeding the first finite 8 MiB MCP preview budget. Text-skill preparation and released-command validation are separate obligations.
- **Decision**: Keep bounded manifest/artifact reads with a 32 MiB snapshot budget and explicit run/hash pins, page/chunk/request/response bounds. Package a deterministic text-only candidate skill using installed public commands. Record separate actual MCP-client and clean-agent candidate transcripts.
- **Why**: A finite client should handle the actual small native fixture while retaining a real resource boundary, consistent underlying values and no implicit execution.
- **Tradeoffs**: This does not qualify indexed large-project MCP queries or the released-command AC-16 condition; no publication is authorized. Hashes bind retained bytes but do not authenticate producers.
- **Interview angle**: “I verified the installed client on real stored outputs and kept candidate preflight separate from release acceptance.”

## PROD-20261116-07: Freeze and exercise the original six-project corpus without substituting samples
- **Context**: Historical examples were not revision-pinned and included inconsistent totals. The full plan retains fmt, grpc, json, leveldb, poco and protobuf; utfcpp is supplemental.
- **Decision**: Add a versioned schema/lock and explicit fetch/run verifier. Preserve exact revisions, actual retained history counts, per-source hashes, measured outputs and missing compilation-context limits. Sampled and full tracked-source native runs have separate evidence.
- **Why**: A valid raw report from a ten-file sample cannot establish full configured-project analysis or detector accuracy.
- **Tradeoffs**: Fallback/shallow-history limits remain visible. Actual resource observations are not benchmark budgets, upstream-suite results or calibration evidence.
- **Interview angle**: “I expanded the corpus while preserving exactly what was and was not exercised.”

## PROD-20261116-08: Keep behavioral and temporal claims in separate finite channels
- **Context**: Historical co-change, authorship and predictive validation answer different questions. Alias/trailer handling, future labels and feature availability can otherwise leak incorrect attribution or future information into a result.
- **Decision**: Emit optional versioned behavioral facts with explicit cutoff, attribution, exclusions and exact denominators while preserving legacy Git metrics. Use a separate finite temporal-evaluation input/report with train-only fitting, chronological/project holdouts, probability-only Brier/reliability measures and explicit unavailable cases.
- **Why**: A historical ownership proxy is not expertise; a controlled model fixture is not empirical future-defect validation.
- **Tradeoffs**: Full streamed/incremental and symbol history remain open. The pinned fmt history has no confirmed future labels and therefore remains not_evaluable; no labels or accuracy were invented to fill that gap.
- **Interview angle**: “I preserve the availability time and meaning of a signal before evaluating it.”

## PROD-20261116-09: Keep execution budgets separate from native detector settings
- **Context**: The public pipeline still had one monolithic native process; bounded worker primitives alone did not satisfy public scheduling. Passing orchestrator-only fields into strict native rule configuration would mix responsibilities.
- **Decision**: Add a separately inspected execution section to public effective configuration, with explicit CLI overrides, finite jobs/time/memory/output settings and an explicit retained work directory for resume. Keep native detector/profile/exclusion settings unchanged. Preserve legacy mode until the bounded engine's producer, consumer and installed acceptance gates pass; reject bounded selection rather than silently using legacy while integration is unfinished.
- **Why**: Configured resource limits must be applied and observed, and a missing worker integration cannot masquerade as completed bounded analysis.
- **Tradeoffs**: Resume needs disjoint, explicitly retained work state; ephemeral default execution cannot promise later resume. Per-unit address-space limits are not a whole-machine memory guarantee. Full scale/cache/query acceptance remains open.
- **Interview angle**: “I made the requested execution plan inspectable before wiring it into the public workflow.”


### PROD-20261116-10 — Explicit history and measured public hotspots

Separate history controls from native detectors and execution budgets. Disabled
history must retain unavailable scope before optional Git imports; behavior
requires bounded data and explicit UTC cutoff. New hotspot reports use complete
native CC/physical LOC and identify their method/scope. Historical reports retain
their original severity-proxy values with explicit labels, avoiding silent
rebaselining. Actual arithmetic fixture and component gates are recorded in the
public integration checkpoint; full corpus/client/platform acceptance remains
open. Public isolated proposal verification requires explicit trusted-project
execution and grants only selected-test results, never source application or
equivalence.

### PROD-20261116-11 — Streaming retained material and bounded ABI scope

Context: large opaque native outputs were copied and verified as whole Python
byte arrays. P12 also lacked an actual ABI producer; native tools returned false
clean observations for stripped/corrupt DWARF fast paths.
Decision: stream opaque RunStore material with unchanged immutable namespace and
integrity checks; keep typed JSON validation explicit. Initially support only
hash/version-pinned libabigail2.6.0 and GNU readelf2.44 over Linux shared ELF full
compile-unit embedded DWARF, checking each actual root DIE. Keep source binding
unverified and raw observed exit bits explicit. Why: bounded memory and finite
validated scope must be demonstrated by real artifacts rather than broad labels.
Tradeoffs: whole typed JSON remains; this ABI slice has no CPU/address-space
sandbox or universal compatibility claim. Other formats and full P12 remain open.
Interview angle: a tool's zero exit can conceal missing debug semantics; independent
counterexamples must constrain both producer and retained-report validation.

## PROD-20261116-12: Publish bounded native work as original independent executions
- **Context**: A public worker option could not be satisfied by private scheduler tests or by importing an aggregate file as if one native process had produced it. Independent actual-native counterexamples exposed restored-header races, corrupt consumer output losing producer facts, changed checkpoint metadata being reused, and an external `__has_include` query changing clean semantics despite an empty include graph.
- **Decision**: Add an explicit bounded public analysis mode with native-compatible finite discovery, original compilation-database selection and header inference, stable observed process cwd at the source root, and absolute outputs in disjoint work roots. Preserve independent original receipts, exact result/request/checkpoint pins, source and filesystem observations, and explicit local-to-published artifact bindings in fresh immutable runs. Compare actual TU include-buffer identities to selected/current dependencies, retain unsupported context qualification visibly, quarantine changed metadata, preserve consumer-failure/cancellation facts, and derive a bounded immutable-run catalog with read-only authenticated queries and reconstruction from stored bytes.
- **Why**: Fresh analysis, missing evidence, a stored historical checkpoint and a passing policy are different claims. An aggregate export cannot create a new native invocation or hide a failed/changed unit.
- **Tradeoffs**: Unknown dependency/query closure always forces public units to run fresh; an empty include graph is not closure proof. The marker recognizer only restricts qualification and cannot enable cache reuse. Public qualified warm reuse, complete extraction/assessment caching, all build-configuration enumeration, full findings/history indexes, parent-death recovery, end-to-end consumer memory limits and representative scale budgets remain unfinished. The generic private checkpoint API retrieves historical receipts; it is not authority for fresh closed-input qualification. Legacy mode remains the default and reports that worker budgets were not applied. Source/input binding never claims target tests, policy approval or certification.
- **Interview angle**: “I kept the actual original receipt, detected a header edit even after its bytes were restored, and reran an apparently unchanged source when an unobserved filesystem query could change its AST.”

## PROD-20261116-13: Require parsed-buffer coherence for fresh measured claims

- **Context**: Matching invocation arguments cannot prove that included bytes parsed by libclang equal the retained source. Actual restored-header/VFS and filesystem-query counterexamples changed the AST while ordinary bindings still appeared valid. An inferred-context opt-in also admitted unverified buffer inputs into a numeric health result.
- **Decision**: Retain native TU-buffer SHA/size identities, classify normalization coherence independently from argument matching, and require verified coherence for fresh scorer `analyzed-kloc-context-v4` and stamped policy assessments. The inferred-parse option does not waive buffer verification. Preserve historical v3 scores and unstamped policy documents under their original semantics with visible legacy labels.
- **Why**: A fresh measured score or passing native predicate must be supported by the parsed input bytes rather than a later disk read or an argument claim.
- **Tradeoffs**: Unsupported closure mechanisms and missing retained dependencies remain unknown. This conservative qualification does not establish universal dependency closure or authorize warm-cache reuse. Historical observations remain readable without being promoted to current proof.
- **Interview angle**: The verification separates what was invoked, what Clang actually read, and what the retained evidence can support.

## PROD-20261116-14: Retain actual used SDK buffers outside project source

- **Context**: Bounded units retained the builtin SDK inventory's hashes, while measured normalization required the actual parsed bytes. Promoting those hashes to frozen project files would change source scope and overstate evidence.
- **Decision**: Retain only actual TU-observed SDK buffers in a separate typed proof. Pin exact original native-report JSON, deduplicated original SDK-inventory JSON and original work-unit request identities; verify actual TU SHA/size against retained SDK artifacts. Bound unique SDK bytes to64MiB, each file to8MiB and proof bytes to64MiB. Cache checked proof/index/content once per normalization. Preserve legacy opaque SDK inventories as unknown. Scan retained bytes for unsupported preprocessing operators after logical-line splicing.
- **Why**: A selected compiler SDK, the bytes actually parsed and immutable project source are separate identities. The proof must retain their relationship without merging them.
- **Tradeoffs**: An inactive `__has_include_next` in real stddef.h remains conservatively unknown; no dependency closure or warm-cache reuse is inferred. Full parent-memory and atomic multi-publication behavior remain open.
- **Interview angle**: An actual builtin header can qualify a measured result only when retained bytes agree with both the original SDK selection and Clang's own buffer identity.

## PROD-20261116-15: Separate finite service regression observations from ordinary repair verification

- **Context**: The actual Poco MongoDB command-reuse defect requires a live selected service and ELF relinking. The existing ordinary trusted C++17 repair profile has different protected-source and CMake/CTest semantics.
- **Decision**: Add a separate explicitly trusted finite service profile and public `verify-service-proposal` command. Retain exact before/after compilation, ELF relinking, selected protected cases, owned loopback service/image identity, individual process streams and original tool bytes. Execute sealed selected Linux tool snapshots; disclose unverified helper/runtime closure and absence of CPU/address-space/cgroup enforcement in this profile.
- **Why**: A genuine failing-before/passing-after finite observation must not silently broaden another profile or claim semantic equivalence.
- **Tradeoffs**: Current Linux ELF/service scope does not establish universal repairs, hidden-case completeness, deployment safety or platform support. Expanded P11/M9 acceptance remains open.
- **Interview angle**: The reported claim is the selected observed regression pair, with original failures and exact process receipts retained.

## PROD-20261116-16: Display exact stored measured evidence and watch its selected source scope

- **Context**: An editor must preserve stored numerical values and scorer identity, including historical methods. JavaScript floating-point formatting can lose exact retained numeric tokens, while workspace-only watchers miss explicitly selected outside or aliased roots.
- **Decision**: Parse bounded retained JSON with duplicate/depth/identity checks and preserve numeric lexemes for display. Retain scorer/config/artifact identities and explicit legacy-v3 versus buffer-checked-v4 labels. Track pending/current selected canonical and lexical roots, apply configured source/evidence byte limits, and invalidate stale views on observed selected-source changes.
- **Why**: Presentation must preserve the evidence's original semantics and freshness boundaries rather than recompute scores or assume all selected roots belong to the opened workspace.
- **Tradeoffs**: Real extension-host lifecycle and exact installed VSIX checks remain necessary after watcher changes; this decision does not declare their final acceptance.
- **Interview angle**: The UI shows the stored value and why it is qualified, and drops confidence when its selected source changes.

## PROD-20261116-17: Version atomic store heads and refuse unsupported legacy access

- **Context**: Actual owned-process SIGKILL between the two v2 pointer replacements exposed a newly completed latest attempt alongside the previous completed collection. Derived v2 mirrors cannot make two independent path replacements atomic. Separate recovery interruption tests also showed that a durable selected old-lock journal must survive interruption after unlink without touching a new writer.
- **Decision**: Introduce a versioned v3 single `heads.json` authority containing completed and attempt manifest references plus a generation. Publish both references with one atomic replacement and expose a frozen related-reference reader. Fresh empty stores use v3; historical v2 remains readable, while writing requires explicit migration or an explicit non-atomic v2 compatibility choice. Preserve exact original v2 pointer bytes and manifest/artifact identities in a checked migration plan. Persist an incomplete migration marker, install reserved-directory fences at both legacy pointer slots, then activate checked v3 heads. Resume only from the pinned original plan and revalidate its referenced runs before destructive steps and activation. Export selected v3 heads only to a separate new checked offline v2 directory. Recover only explicitly selected qualified dead local lock incarnations, retain staged bytes and durable receipts, and preserve any current different writer.
- **Why**: A generation must be one observable commit point. A format transition must either preserve the old contract or refuse unsupported readers/writers; silently stale legacy mirrors are not compatibility. Original execution/source facts do not become fresh through recovery, migration or export.
- **Tradeoffs**: Unsupported old binaries fail at directory fences and can retain an unreferenced run or stale writer lock before refusing; they are not supported v3 writers. Incomplete migration fails closed and requires explicit resume. An already-open old head descriptor may legitimately have zero links after atomic replacement, so readers accept that pinned descriptor while rejecting extra hardlinks. Actual old installed wheel readers/writers and a separate v2 export were tested, but a new installed wheel, full consumer/integration checks, representative scale, additional platforms and full P14 remain required. Process SIGKILL tests do not establish physical power-loss guarantees or protection from a malicious filesystem owner.
- **Interview angle**: “I reproduced a mixed completed epoch with a real killed publisher, made the authority one versioned replacement, and tested old binaries failing explicitly rather than reading apparently current stale files.”

## PROD-20261116-18: Expose explicit store transitions and format negotiation

- **Context**: Atomic v3 heads require an explicit migration boundary; consumers must identify supported formats without executing a project. Recovery receipt inspection also needs exact original lock pins when a newer writer exists.
- **Decision**: Expose `store-layout upgrade` and `store-layout export-v2` as thin public adapters to the checked store APIs. Advertise read versions, default v3 writes, explicit non-atomic v2 writes, migration and separate export in an optional closed capability field. Permit paired exact original lock pins on read-only recovery inspection; reject incomplete pairs before opening a store. Treat v3 layout metadata as store hints so corrupt stores cannot fall back to flat report reads.
- **Why**: Operational transitions and unsupported legacy access must be discoverable and deliberate.
- **Tradeoffs**: Nine public adapter checks and25 API checks passed; fresh whole-suite and installed artifact checks remain required. Capability advertisement does not attest runtime or platform qualification.
- **Interview angle**: Migration is an explicit operation with checked retained facts, while capability negotiation remains read-only.

## PROD-20261116-19: Evidence-gated single-writer execution board

- **Context**: The full187-item program needs bounded concurrent execution, safe shared-contract ownership and current input-bound dependency gates. The user explicitly selected GPT-6.1 Sol Ultra continuation without changing endpoint, budget limits or no-commit/no-push restrictions.
- **Decision**: Maintain `docs/plans/production-execution-board.json` and its readable view, covering all187IDs and P0–P14. Lead owns shared contracts/schemas, storage/heads/recovery, pipeline/config/public dispatch, packageversions/assets, ledger integration and ALL shared environment/dependency changes. One read-only reviewer writes only its isolated review controls/evidence. Permit at most TWO code-writing tracks including lead and ONE heavyweight fullsuite/corpus/container/package job. Current second writer slot is vacant. Record starting hashes for both tracked and untracked claimed files and absent future targets; explicit handoff is required before another owner edits a claimed path.
- **Why**: Relevant passing component/interface evidence opens dependency edges; global require-complete exit3 must not halt independent ready work. Consumer work waits for changing producer interfaces. Short artifact freezes bind one coherent native/wheel/VSIX set to exact tests.
- **Tradeoffs**: READY/integrated/scoped qualification are orchestration views, not canonical acceptance states. Full3327pass baseline is preserved at its exact pre-private-timestamp-repair epoch;106current source-stable checks cover that subsequent repair. Retained-layer candidate has six independently reproduced defects and is not integrated or qualified. LaterM8/M9, platform and human obligations stay queued/blocked explicitly; no requirement weakening or publication is authorized.
- **Interview angle**: Ownership and dependency gates are concrete files, hashes and commands, rather than a shared mutable work queue or a global-green prerequisite.

## PROD-20261116-20: Retain exact selected layer bytes before runtime qualification

- **Context**: Live input inventories do not retain namespace bytes; current nanoseconds exceeded the private schema's JS-safe bound. Independent review also demonstrated that generic integral floats can authorize invalid PAX timestamp text, and post-publication pathname/content races can invalidate an apparently verified output.
- **Decision**: Keep private0.1 input/capture documents with exact signed64-bit nanoseconds and localized strict integer validation. Stream actual checked bytes into deterministic retained gzip/tar, verify the same streams and independent bounded archive semantics, bind the selected current output parent and descriptor through publication, and preserve failure witnesses without promoting uncertain results. Force cache eligibilityfalse and closureunqualified until runtime/native/non-filesystem contracts and checks pass.
- **Why**: A manifest of earlier hashes or readonly host bind cannot establish the bytes later consumed. Exact numeric and publication semantics need actual producer-to-contract and artifact controls.
- **Tradeoffs**: Current profile is Linux/procfs, private owned output, regular file/directory inputs with finite budgets; no symlink/hardlink/mount crossing support, no universal simultaneous live snapshot or physical power-loss guarantee.139source-bound checks and18independent controls verify this slice, not fullM2/P5/P14.
- **Interview angle**: The claim follows the bytes from the checked descriptor into retained archive and later independent verification, while unsupported runtime/cache claims remain explicit.


## PROD-20261116-21: Review finite runtime bytes before actual immutable-image execution

- **Context**: Historical ldd selection and passing input archives do not prove runnable runtime bytes. Independent review exposed three partial ELF mapping errors and two supervisor status publication races.
- **Decision**: Keep explicit declared runtime, checked archive-byte codec, retained project/SDK/runtime namespace, and actual image execution as separate gates. Use a pinned static supervisor to keep output tmpfs alive; publish status from its held FD and recheck parent/witness/final identities. Preserve every genuine red and repaired independent proof. New source gets source-bound checks before any candidate freeze.
- **Why**: Neither process exit nor fixture scaffolding proves that the collected bytes belong to the selected execution.
- **Tradeoffs**: Imported ldd provenance remains incomplete; lazy loading, implicit mounts, aggregate cgroups, hostile same-UID native behavior and universal cache closure remain unqualified. Capturing original absolute paths preserves CDB meaning but does not qualify arbitrary relocation.
- **Interview angle**: A review found a producer could publish somebody else's status file; the repair binds publication to the exact held descriptor before any real container observation is accepted.


## PROD-20261117-01: Collect live tmpfs output through a pinned in-container helper

- **Context**: Actual Dockerarchive collection could not expose the running tmpfs status, and ambient client proxy configuration injected undeclared environment fields. Both real failures were retained rather than presented as native success.
- **Decision**: Use an owned empty Dockerclient configuration, verify actual container properties and native/helper bytes before start, collect bounded status/USTAR through the pinned helper inside the live container, retain actual stdout/stderr and unqualified failed snapshots separately, then recheck ownership before cleanup.
- **Why**: A client exit does not prove native completion or preserve tmpfs output; actual kernel/container observations must agree with retained bytes.
- **Tradeoffs**: This finite Linux profile remains unqualified for universal runtime closure, hostPID authentication, aggregate cgroups and cache reuse. Installed kits use a dynamic helper with declared host C++ runtime; static image8 has a distinct explicitly pinned helper.
- **Interview angle**: The first real run exposed a transport assumption that mocks missed; the fix now preserves original native streams and proves parsed source/SDK bytes from an actual immutable image.

## PROD-20261117-02: Keep independent code moving against frozen source inputs

- **Context**: A complete root pass must bind one source epoch while independent provider work continues.
- **Decision**: Freeze live product/config/schema/version/assets, allow one separately owned workcopy/patch against exact recorded base hashes, run its tests with explicit module-origin assertions, review it independently, and apply only after the live freeze closes. Preserve pre-patch broad evidence and require fresh non-injected live component checks after integration.
- **Why**: Parallel work must not turn a passing suite into an unstable-source result or falsely qualify a draft.
- **Tradeoffs**: Applying a later patch makes a broad root result historical for the changed module; globalP14 remains separate. The late primary-target CMake dependency followup was recorded as a new epoch instead of borrowing the older nativekit test pass.
- **Interview angle**: The paging patch moved from six meaningful failures to58draft checks,65independent draft checks and92freshlive checks while the3646root epoch stayed byte/identity stable.

## PROD-20261117-03: Qualify one installed epoch and preserve resource interruption

- **Context**: Current helper packaging, retained runtime and paging repairs require actual installed agreement. During a correctly guarded run, Docker continued creating an owned container after its client was interrupted for disk reserve.
- **Decision**: Test one frozen native/wheel/VSIX set, use the packaged SDK, retain original client/editor/native outputs, and keep failed attempts separate from resumed proofs. Identify any late object by exact intent name, nonce, immutable image and observed state before cleanup. Preserve inactive dependency bytes reversibly, with metadata journals and separate-copy restore commands. Repair bounded late-create cleanup and interruption receipts before qualifying that lifecycle path.
- **Why**: A stopped client is not a stopped daemon operation; a successful retry does not erase a real cleanup gap. Exact artifact epochs remain useful even when later independent source patches are integrated.
- **Tradeoffs**: Current installed scope is finite Linux cases with declared host requirements and shared optional PDF/web dependencies. Native helper variants are distinct. Universal runtime closure, aggregate cgroups, full feature/platform/editor acceptance and cache reuse remain open. Full187-item acceptance is unchanged.

## PROD-20261117-04: Retain interruption receipts and distinguish late daemon completion

- **Context**: A real disk-guard cancellation killed a Docker create client before the daemon published its object; a one-shot absence probe missed the late stopped container.
- **Decision**: Retain cancelled/raw partial client evidence with unknown exit/full drain counts, durable local cleanup selectors and bounded absence-only retries. Require observed exact ownership before removal. Do not promote native output or absence on client cancellation. A second cancellation or completion outside the bounded cleanup window remains unresolved.
- **Why**: Client process supervision and daemon operation lifetimes differ. The corrected path is tested by actual SIGINT during an observed owned create client, not inferred from a clean run or mocks.
- **Tradeoffs**: Four probes, eight-second scheduling and32command caps preserve bounds; no universal daemon completion time is claimed. Exact current source passes65 owner/69 independent checks and27 independent actual evidence assertions. Full runtime/cache/platform/production scope remains open.

## PROD-20261117-05: Bind query optimization to selected report bytes

- **Context**: A retained218MB protobuf report exceeded whole-JSON resource limits. Reading one findings page through the original full RunSnapshot still materialized unrelated typed artifacts. Independent reviews exposed unsupported-store/schema acceptance and a cache whose declared size budget was checked after reading its body.
- **Decision**: Keep whole-run snapshots fully verified and add a separate bounded metadata/selected-artifact projection. Stream whole JSON structure and selected finding rows into a private transactional SQLite run, with exact source/report/request/schema pins, pre-read size checks and material-only publication guards. Expose original and derived pins, selected-artifact scope and false analysis-cache eligibility in paged HTTP responses. Authenticate before metadata/cache actions and refuse incomplete attempts before indexing. Keep resource controls and original source verification distinct.
- **Why**: A query cache may optimize retained bytes without claiming the original source is fresh, unrelated artifacts are verified, or native analysis has been reused. The failure boundary must precede oversized reads and publication of partial rows.
- **Tradeoffs**: Current profiles have cooperative wall checks and finite per-index/page memory/disk bounds; aggregate cache retention, hard deadlines, complete ignored-metadata semantics, full Git history indexes and all scale/platform/installed acceptance remain open. The historical cold driver stays failed1 after its overbroad frozen-input list included a mutable execution board; separate fresh reuse/HTTP gates bind stable runtime/source/cache inputs. Historical allocation failures and shared-coverage contamination remain explicit. Reversible fixture preservation and prospective inclusive accounting do not change product acceptance or erase failed evidence.
- **Interview angle**: The evidence separates exact row-preserving query optimization from source truth, and retains the real large-report, race and resource failures that shaped the boundary.

## PROD-20261117-06: Compare supported Git timestamps without floating-point rounding

- **Context**: Real tiny Git histories at schema-supported year9999 showed that floating POSIX seconds erase microsecond differences, selecting the wrong half-open-window commit and qualifying a delivery before its revision.
- **Decision**: Compare exact integer epoch microseconds derived from aware timestamps. Preserve fractional precision, timezone equivalence and half-open boundaries within the existing branch request/report contracts.
- **Why**: Equal counts can hide selection of the wrong commit; the regression asserts exact commit identity and delivery chronology.
- **Tradeoffs**: This finite local branch producer repair does not authenticate provider events, reconstruct historical ref tips or establish DORA metrics. Source-bound92owner/42independent checks cover the named profile; isolated coverage has its narrower30-case scope.

## PROD-20261117-07: Reserve external rule hash slots and opt in to derived MCP cache writes

- **Context**: An accepted unsafe GCC rule and a distinct literal `option-<its SHA256>` rule mapped to the same namespace. Independent implementation also needs large MCP result pages without changing the default read-only server contract.
- **Decision**: Reserve lowercase64hex hash-slot literals, hash their original spelling separately, and align the shared semantic verifier with the producer. Preserve ordinary/previous unsafe IDs. Historical ambiguous normalized literals fail current verification and require explicit re-import of retained raw reports; do not silently rewrite their identity. Advertise the new MCP `indexed_findings` tool only after an operator configures a separate cache outside the source store. Initialization/listing remain side-effect free; calls may write only that derived cache.
- **Why**: Producer and consumer must agree on non-aliasing rule identities. Explicit configuration distinguishes query optimization writes from default read-only access and source/native truth.
- **Tradeoffs**: No new schema fields or broad version compatibility are inferred. Legacy ambiguous facts need separate migration qualification. Prototype query indexing does not replace normalized-observation/history indexes or whole-run evidence verification. Actual scoped source stdio and byte checks precede a fresh installed candidate; later live patches require a new epoch.

## PROD-20261117-08: Preserve the eager-reader failure while specifying bounded native projections

- **Context**: Exact retained218MB protobuf bytes trigger MemoryError in the actual eager loader at both512MiB and1GiB virtual-address limits. Selected findings indexing alone cannot remove the separate full-report and global-token allocation paths.
- **Decision**: Retain both nonzero failures with held-FD/input/source checks and kernel metrics. Specify a separate private projection producer using literal nonoverlapping object-key selectors, bounded values/array rows, global syntax/finite-number budgets and provisional records followed by whole-byte EOF/size/SHA completion. Keep report-schema validation, source/SDK/receipt/rule binding, global duplication and typed normalization as explicit later consumer gates. Preserve all existing complete RunSnapshot and structural-parser contracts.
- **Why**: A memory failure must identify the actual loader and bytes. Structural completion cannot substitute for report semantics, source truth or a bounded end-to-end normalization pipeline.
- **Tradeoffs**: Object-key paths cannot traverse inside array elements; file-level native metrics still need a supported item cap. Diagnostic AS limits are not RSS/cgroup guarantees or reference timings. Contract-only70/70passing checks release producer work without claiming that native ingestion or full187-item acceptance is complete.

## PROD-20261117-09: Close only the three approved original requirements

- **Authorization**: Resume only FR-UX-12, FR-EVD-09 and FR-GIT-03, verification and canonical evidence updates, then stop. Retain all118 requirements,60tasks,nine obligations and P0–P14; no next batch or broad M6 acceptance follows. One product owner (lead), one read-only completed-batch reviewer, exclusive files, no commits/pushes/publication.
- **Evidence**: Reuse matching wheel6bff/native96bee with current relevant source and input/material hashes. Kernel seccomp denial and account-free installed core processing supplement the prior proxy-only offline check. A preinstalled local coverage pack genuinely passes; the native compatibility finding policy remains insufficient evidence. Installed coverage keeps5/8line,1/2branch,2/3LCOVfunction distinct; Cobertura function stays unknown, decision/MC/DC requests unsupported, import-only facts unavailable. Installed controlled histories preserve alias/bot/former/pair semantics and a visible knowledge-proxy limitation.
- **Review**: runtime_review7 accepted the exact original three criteria with3,029read-only checks;86focused component tests passed. Failed controls and harness corrections remain retained. No product change or package rebuild was necessary. Source/artifact pins and usable commands are in docs/checkpoints/20261117/three-item-closure.md and work/closure-fr3/verification.json.
- **Ledger**: Move exactly the three reviewed IDs to verified, preserving old evidence/remaining-work text as history; other184rows unchanged. Definition SHAe57e89fb7db188f1f4805b95c0bc6f2896c7ab9eef15d851723cc422a0bd2381 remains unchanged. Use the existing JSON proof protocol rather than accepting old Markdown as executable proof.
- **Outcome**: The unchanged strict verifier returns3: valid scope/evidence with118open,64active,2blocked,3verified, complete=false. The full program remains incomplete. Stop and await explicit user approval; no old autonomous queue resumes.

## PROD-20261117-10: Resume full scope through source-bound installed import closures

- **Context**: The user superseded the earlier stop-after-three limit and authorized the full187-item production endpoint. FR-EVD-01 lacked typed public imported test counts/context; FR-ANA-09 was GCC-only despite promised external adapter expansion.
- **Decision**: Retain original definitions/P0–P14 and implement bounded clang-tidy19.1.7 text/Cppcheck2.17.1 XML2 producers, shared versioned namespace validation and public import/output flows. Add imported counts/case identities to existing attributed evidence rather than fabricating an execution receipt. Expose repeated diagnostics/potential location overlap with false independent confirmation and zero confidence adjustment. Preserve supplied IDs/raw reports; document the existing GCC secondary-note derived fallback when no option exists.
- **Why**: Parsing and source identity do not authenticate producers, prove executed tests, or turn overlapping claims into independent confirmation. Zero/unsupported input must remain unavailable or skipped.
- **Tradeoffs**: Finite supported matrix, not every provider/version/format. Shared-source changes required a fresh current candidate and relevant refresh of the existing three closures. One staged wheel f294 was built; harness request/count mistakes retained and repaired without package churn. Independent review accepted five exact original criteria after2,907checks;409affected component tests pass with11explicit live-tool skips. All broaderM5/M6/platform/editor/P14scope stays open.
- **Continuation**: Canonical states5verified/116open/64active/2blocked; strict verifier3. Full authorization remains active, FR-EVD-03 dispatched, memory-ingestion prerequisite lead-owned, one heavy slot/4GiBreserve preserved. No commits/push/publication.
- **Interview angle**: Demonstrate genuine failed/skipped import counts, original tool IDs and deterministic potential-overlap output while showing why a local hash or duplicated diagnostic is not authentication or confidence.

## PROD-20261117-11: Prove false-pass guards with genuine installed controls

- **Context**: FR-EVD-03 needs current installed positive/zero/skipped/process-only/empty/unsupported outcomes. User full-task authorization supersedes the earlier batch stop.
- **Decision**: Reuse exact f294current relevant inputs, actual CTest3.31.6 compile/inventory/test flows, imported negative controls and independent purepolicy replay. Genuine clean0, unavailable3, actualfailure1; no successful verification from process0 or copied reports.
- **Why**: Both all-rejecting behavior and unsupported/empty falsepasses need meaningful controls.
- **Tradeoffs**: Finite exactcriterion only; no broaderM5orP14claim.448independent checks/1310stablepacket hashes support acceptance. Lead canonical-wrapper filename collided with a frozen aggregate; restore original exactSHA from retained data, preserve failedproofs, use unique canonical-proof.json, and normalize existing relative-path protocol without weakening checks. No originaldata remains lost.
- **Continuation**: Six acceptedartifact-profile criteria; fullprogram incomplete. Subsequent native producer edit makes globalcurrentstrict2(stalejsonProjection); lead must refresh coherent currentartifacts/evidence before current-source completion claims. Never record assumed3 or retag old logs.
- **Interview angle**: Actualpositive versus zero/skipped/process-only negatives, exact originalartifact recovery, and honest distinction between artifact acceptance and a changing source epoch.


## PROD-20261117-12: bounded native byte ingestion and unknown scopes

Keep sealed private compression, packaged JSON-schema checks and original native maintenance semantics distinct from provenance and source truth. The first actual218MB run passed schema/semantic/summary checks under512MiB AS but failed its64MiB duplication budget before a late partial peer; preserve actualexit1. A preliminary completeness declaration may avoid token indexing only when independently checked against every actual consumed frame atEOF. Contradiction, cancellation and limit failures cannot become clean or unknown success. No caps, original criteria or final verification are weakened. Qualify the repaired consumer, then one coherent installed candidate; all187 scope remains.

## PROD-20261117-13: Bound work-unit raw reports and preserve cold fixtures reversibly

- **Context**: Single-report bounded readers do not fix the work-unit normalizer's retained report list and global token dictionary. The first 47 affected checks pass against native5f7 and the packaged resource directory, including SDK bindings and cross-file duplication; an early-index exception also needs explicit generator closure. Repeated retained failures and fixtures leave too little room for the generic test guard.
- **Decision**: Keep public eager replay and its byte limits unchanged. Private normalization defers report bodies, opens one checked original report at a time, validates its schema and metric semantics, and indexes global duplication after a complete peer census. Both iterator passes close explicitly on error. Lazy arrays compare literal JSON contents a row at a time for the existing SDK consistency check. Preserve original source, failed checks and wrong-tool/resource attempts; final source parity and independent review remain separate gates.
- **Why**: Removing all-unit report/token retention must preserve original source/receipt/context/rule identities, exact duplicate counts and unknown missing peers. Hash consistency never authenticates a producer or establishes SDK closure.
- **Tradeoffs**: Reports are re-read for census/index/normalization. Primary input cache, SDK proof and final typed outputs still have separate retained budgets; this is not complete large-run or worker-isolation acceptance. Changing source invalidates affected dependency gates and old whole-source installed qualification until refreshed.
- **Resource preservation**: The fmt and Poco/Data cold fixture bytes and supported metadata were fully archived, independently compared with original and restored trees, then retired under a sole resource lease. Durable indexes, archive hashes, journals and restore commands remain. Neither subtree is referenced by current canonical pins; both must be restored before their corpus use. No test or acceptance criterion is removed. Poco uses the independently reviewed archive allocation gate (4GiB reserve plus exact restoration, archive cap, metadata and 16MiB margin); generic test-wrapper limits are unchanged. grpc/src remains present and queued, with its discovery implications explicit.
- **Interview angle**: A resource workaround needs independent restoration evidence and exact failure preservation; passing bounded components is not a large-run completion claim.

## PROD-20261117-14: Disclose behavioral versus retained legacy history scope

- **Context**: FR-GIT-01's eight installed edge cases passed, but independent review rejected whole closure because only behavioral output showed the configured window. Legacy metrics retain the selected scan, not a default90-day window. Preserving values without a product-visible scope note left that distinction ambiguous.
- **Decision**: The lead adds an accurate scope limitation to emitted legacy metrics and the copied history result only when behavioral metrics are requested. Preserve metric values, available/partial/unavailable status and the shared raw cache result. Existing schema/API fields are sufficient; no new contract or version is introduced. FR-GIT-01 remains open pending independent repair review and current installed qualification; dependent FR-GIT-02 verification waits.
- **Why**: Time scopes must be visible in the emitted artifacts. An informational scope note must not invent a collection failure, a90-day default, or a filtered legacy count.
- **Tradeoffs**: A truthful note describes which filter applies; it does not rewrite legacy semantics, establish complete history under truncation, or close broaderM6. Current11criteria remain accepted for frozen686artifact; newmain source makes the globalproof stale until relevant source/artifact evidence is refreshed.
- **Verification**: Real default/7-day/2-day histories preserve legacy fields and available status; configured notes appear in both outputs and raw cache_info is unchanged. The actual missing-scope regression fails before repair; earlier date/configuration setup failures remain recorded. Source checks pass; exactsource gate is work/git-window-scope51/source-gate.json.
- **Resource**: The standard candidate52build was refused before launch by the existing generic reserve/margin guard. Preserve the refusal. No reserve or acceptance limit is reduced. Verified reversible preservation of two cold source subtrees is queued; candidate estimate will be based on measured previous identical pure-Python packaging allocation, with the64MiBgenericmargin retained.
- **Interview angle**: A passing metric test can still omit the scope needed to interpret it; independent review should block that closure and drive a small producer repair.


## PROD-20261117-15: Check integrity before declining unrepresentable SDK proof

- **Context**: Legacy used_sdk_inputs2 embeds each native report as a JSON string. Capture parsed and copied the report before considering the proof cap; larger ingestion improvements do not remove this eager boundary. An actual SDK-specific memory-limit failure has not been reproduced.
- **Decision**: Before materialization, a descriptor whose raw size already exceeds the unchanged64MiB proof cap is checked through the existing bounded SHA/size/EOF/no-follow reader, then omitted without SDK buffer writes. Preserve all representable report semantics and the existing unknown consumer path. The schema and production limits are unchanged.
- **Why**: Even an unescaped report cannot fit in that proof. Declining capture must neither conceal artifact corruption nor manufacture qualified SDK evidence. Hash equality is integrity, not producer authentication.
- **Tradeoffs**: This is only a safety guard for provably unrepresentable reports. Reports below the cap, cumulative proof allocation, embedded-proof validation and typed-material loading retain eager paths. The separately owned scalable proof/material protocol prerequisite remains active; no NFR or scale closure follows.
- **Verification**: Real native producer red control reaches the eager reader on oldsource. Final product source passes29affected SDK checks; a separately added current-test epoch passes the actual capture-to-normalize-to-publication-to-schema/readback declined case with no SDK buffers, unverified coherence and null health. Both supported and unsupported real SDK paths retain original semantics. Independent component review: work/runtime-review61/sdk61/review.json. Exact installed source refresh remains pending; the unchanged strict verifier correctly returns2 for the stale historical SDK pin until refreshed.
- **Interview angle**: A bounded rejection path still has to consume and verify the original bytes; a successful narrow repair must expose the remaining memory contract.


## PROD-20261117-16: Aggregate complete measured file priorities by declared component

- **Context**: FR-GIT-06 already emits configured component ownership and historical coupling, but measured hotspots were file-only and truncated to20 display entries. Ownership/touch totals do not substitute for measured hotspot aggregation.
- **Decision**: Add an optional component_hotspots field to explicit prototype/v2risk output. The producer consumes the existing validated behavior mapping and ALL eligible measured file priorities, including realzero, before the display cap. Each component partitions its members into measured/unavailable. Only complete available-history evidence yields a complete score; partialscope has null score and a separate observed sum. Missing evidence never becomes0. Preserve config/input digests as integrity declarations, never producer authentication.
- **Why**: Components must reflect the existing measured CC × history activity × finding-density method without inventing a new score or dropping the21stfile. Historical co-change stays separate from static include/call relationships. Behavioral lookback/exclusions do not silently rewrite the retained legacy hotspot activity scope.
- **Tradeoffs**: Component priority is a sum of heuristic file priorities, not a calibrated probability. Partial behavior history conservatively prevents a complete component score. Existing optional CLI/config paths supply the mapping; no new CLI flag or authenticated organization model is introduced. Original v1 export refuses these extra semantics; explicit prototype conversion preserves them. WholeFR-GIT-06 remains pending actual installed producer/consumer agreement and independent review. BroaderM6 and client/scale tasks remain open.
- **Verification**: Retain the original25-file/100-pair failure: reaching the pair cap truthfully makes historypartial. The repaired fixture includes both that negativecontrol and a1000-pair completecase; productlimits remain unchanged. Pure2passes33checks; prioraffected integration22checks pass at their own epoch. Independent imported-risk review additionally found tinyzero inflation via absolute tolerance and raw aggregate overflow. Both actual failures are retained; lead removes absolute tolerance and translates nonfinite/overflow sums into ContractError. Final consumer/source gate and one combined installed candidate follow before acceptance.
- **Interview angle**: A component feature needs actual measured inputs, complete membership and honest scope; UI truncation and floating-point tolerances can silently change the product meaning.


## PROD-20261117-17: Separate excluded architecture members and retain excluded duplication peers

- **Context**: Actual installed65nativeexcluded-member control exposed two genuine gaps after the full componentpositive passed. Architecture mapping includes api/b.cpp, while FeatureEngineer intentionally excludes it from attemptedranking/healthscope. Separately, work-unit globalduplication skipped its actualunavailable tokenframe, leaving3measuredpeers andfalseavailable0s despite the fourthunit's partialoutcome. The unchangedvalidator correctly rejected publication. OriginalSDK3cases/5integritycontrols/positivecomponent and bothfailures remain immutable.
- **Decision**: Add optionalexplicit component_hotspots.excluded_files. The strictcomponentpartition is ranking/unranked scope UNIONdisjointexcludedmembers, never measuredexcludedfiles. FeatureEngineer carries originalparse exclusions separately, without changing attempted/rank/healthdenominators. Keep the genuineexcluded nativeframe in the globalduplicationcensus; do not waivevalidatorconditions or supply a falsecompletehint.
- **Why**: An unmeasured architecture member must remain visible without being treated as attempted or scoredzero. Globalduplication needs everydeclaredpeer; a genuinelyunavailable peer makes allglobalcountsunknown.
- **Tradeoffs**: Historicalac3outputs remain bound to thatartifact. The repair needs onejustifiednewcandidate69, not a retroactiveoldlog/source label. Other unproven discoverygap/overallsource-scope interface concerns remain lead-owned under NFR-SCL-02/NFR-SCL-05/M2-05/AC-06; no wholememory/scale closure is claimed. The index requires its completenesshint match actualframes, so a falsehint is not a permitted workaround.
- **Verification**: Originalscope68red2fail retained. Contract/compat21pass; initialcombinedgate had75pass+1wrongtestcount (excluded emits no duplicatemetricrows, leaving2, not4). Corrected normal+injectedconsumerfailurepublication2pass with actualnative/validbundle; finalcomponent70pass. Independent10documentcontrols and exactsource review accepted at work/scope-review70/component-review.json. WholeFR-GIT-06 and canonicalcurrentevidence await actualinstalled69packet/review; no broaderM6 or NFR acceptance follows.
- **Interview angle**: Distinguishing architecture membership from attemptedmeasurement prevents denominator drift; a missing peer is a completeness fact, not a zero observation.


## PROD-20261118-18: Project checked native inputs for the legacy predictor

- **Context**: Actual installed69 legacy native JSON load fails MemoryError on the original218MB protobuf aggregate under baselineVMS+512MiB while its tiny control passes. The original producer's incomplete parse/duplication scope must remain visible.
- **Decision**: Reuse the existing schema/byte-pinned checked reader and streamed native semantic validation, materialize only legacy findings/inventory/header inputs, and hand literal CC/LOC/hash claims to the existing feature/priority calculation. Keep raw original bytes retained and all missing prerequisites unknown. Stage output files until the input's final identity guard succeeds, then use the existing per-file replacement behavior.
- **Tradeoffs**: Findings/history/features/outputs still materialize. Default96MiB projection database and SDK64MiB wire/proof caps remain unchanged. Resource admission's64MiB estimated scratch is not a product cap. Late-source failure preserves prior outputs, but there is no new atomic two-file publication promise. No wholeNFR/M2/scale/SDK authentication claim follows.
- **Verification**: OriginalMemoryError70 and actual late-publication red2 failure retained;35affected checks then14focused public/parity checks pass with exact recorded bytes. Genuine218MB memory and new installed source refresh remain gates. Reviewer77 accepted the bounded source and late-input-failure repair. Three independently verified reversible coldCMakeFiles archives provide disk headroom without deleting evidence or lowering4GiBreserve; restore each exactparent before nativebuildtree use.


## PROD-20261118-19: Separate bounded SZZ label provenance from retained-history completeness

- **Context**: The SZZ producer lacked an explicit label cutoff and disclosed neither its whole-parent-file heuristic nor precise provenance. A temporal fix filter also needs to reject later-dated origins, source-text SHA spoofing and unsafe/unbounded original object reads.
- **Decision**: Add an independent inclusiveUTC SZZ cutoff to public Gitrun/CLI. Filter fix and origin metadata before contribution; parse only genuine LF-delimited porcelain headers; memoize selected GitDB origin metadata after original raw-object type/size checks. Reject mismatched shared repository owners and preserve ambient Git isolation. Store exact method/cutoff/limits in metadata.szz, with informational notes appended after operational history classification. Actual scan/cap/blame/oversize failures still mark incomplete history.
- **Tradeoffs**: Git timestamps remain unauthenticated. Whole-parent-file candidate labels are imperfect. The label cutoff does not filter other retained feature history or qualify future predictions; risk JSON retains label_source, not every Git provenance field. Existing private temporal evaluator and production model remain separate; M6-05 calibration and empirical accuracy are unclosed.
- **Verification**: Current24root+11legacy tests, actual5installed public positive/control cases and invalidUTC1 on exact4dd953wheel, independent literal controlledDAG readback. Initial provenance-causes-partial regression, source parser/origin/boundary gaps and pre-exit stdout evidence mismatch are all retained and repaired without weakening original acceptance. Final17-ID review accepts only new FR-GIT-08; prior16 refreshed with exact historical69/74scope and current affected journeys. No wholeNFR/M2/M6/scale/editor/platform/P14 closure.


## PROD-20261118-20: Bound SDK capture using its actual stored representation

- **Context**: The genuine32-unit SDK producer admitted a279438-byte proof under a test-local279437-byte cap because its compact estimate was275364. Its own reader rejected the proof; the original exit70, bytes and receipts remain retained.
- **Decision**: Use the existing store JSON encoder for per-row wire accounting, including UTF8, indentation and separators. Reserve the wire width of the existing maximum captured-byte counter so late capture cannot enlarge an already admitted header. Keep all existing production limits, schemas, wire formatting and integrity checks.
- **Verification**: The authored serialization boundary failed1 before repair;31 affected checks now pass. Installed93 replays the exact32 genuine results without new native execution: normal proof bytes are unchanged; lowered cap keeps31 readable units. Actual installed supported/unsupported/declined, five integrity and complete/excluded component checks pass. Independent review accepts current-source refresh of20 prior original criteria, with explicit old-source relocation and no historical log retagging.
- **Limits**: This fixes wire admission, not SDK OOM or eager typed-material parsing. Full NFR-SCL/M2/AC06/platform/P14 conditions remain unclosed. Candidate93 is a local uncommitted review artifact; no publication or dependency change is authorized. See checkpoints/20261118/sdk-proof-wire-budget.md.


## PROD-20261118-21: Generate native registration and reject unsupported configuration

- **Context**: C93 public/native configuration admitted recognized threshold keys on rules that never consume them. Native construction was still a second handwritten22-rule list. Actual installed/native70 and Python6failed controls are retained.
- **Decision**: Store private native class/header/order bindings inside the existing open per-rule schema vocabulary, strip them from public v2 metadata, and generate both native types and constructor/option/default helpers. Consume these in the native engine/parser. Validate Python configuration against each selected rule's authoritative schema, with native-compatible strict integer tokens instead of numeric coercion.
- **Why**: One metadata producer now supplies real native consumers; configuration accepted by Python must survive the next native boundary. No detector implementation, rule ordering, existing defaults, thresholds, contract version or production limit is weakened.
- **Tradeoffs**: Private annotations support only the native capabilities actually implemented; unsupported schema features refuse generation. Direct native integer spelling remains strict. Python max_token_records remains an explicitly unsupported root option, not a silently ignored native setting. Source/component success is not whole FR-UX-04 or NFR-MNT-03 qualification.
- **Verification**:14 producer checks include an actual compiled consumer;101 combined Python controls passed before review. Actual C++17 production-loader43 tests pass. Review found integral9.0 mismatch; original6failed/2passed retained and repaired57pass. Independent scoped review accepted. Full native engine/current installed artifact agreement is pending resource admission. Current strict verifier actual2 names stale analyzer.cpp; old C93 strict3 cannot be retagged. See checkpoints/20261118/native-registry-configuration.md.
- **Interview angle**: Generated declarations matter when runtime consumers execute them; negative producer-to-consumer controls prevent a plausible effective configuration from becoming a silent no-op.


## PROD-20261118-22: Preserve accepted scope and distinguish analysis language from implementation language
- **Context**: Historical MVP, proposed-specification and staged release labels coexist with the user's accepted full production task.
- **Decision**: The full187 definitions and P0–P14 remain the endpoint. TASK_SPEC.md remains historical; production-spec Proposed headers record pre-acceptance publication state. C++ is the first supported analyzed language. Additional languages, managed hosting, enterprise identity and automatic semantic refactoring remain retained M9 expansion with their original acceptance, not discarded scope.
- **Evidence boundary**: Matching candidate105/native149 qualifies its actual C++17/libclang19 host profile, not all languages, platforms, M9 or full production completion.
- **Maintenance**: See [current authority and instructions](plans/production-scope-authority.md). Original criterion text and decision history remain unchanged.

## PROD-20261118-23: Close small batches against exact bytes and resolve historical instruction precedence
- **Context**: Stale proof, repeated packaging and legacy style/safety recommendations can obscure the actual accepted contract.
- **Decision**: Use closed cohesive batches of2–3 original IDs, exclusive file owners, one coherent candidate or exact matching reuse, one affected evidence refresh and one independent read-only review. Strict3 permits continued individual closure; final completion requires unchanged strict0. Preserve failures and all uncommitted work.
- **Build guidance**: Native C++17 and the actual .clang-format Google-based overrides govern this build. Do not silently introduce std::span/std::expected as C++17 standard APIs, infer sanitizer/thread-safety passes from prose, or let historical fixed-size advice supersede accepted configurable large-library analysis requirements. Actual unsupported runtime/matrix/scale criteria remain open.
- **Provenance**: Keep uploaded snapshots, live source, historical unavailable references and current execution separate. M0-01's missing82120d2/history is recorded as waiting; do not fabricate it.


## PROD-20261118-24: Gate compatibility health on retained prerequisite evidence

- **Context**: A genuine clean native run with a required detector disabled produced legacy health100. The streaming predictor deliberately removes the native measurement inventory; finding counts cannot prove complete source, measurement, rule or context coverage.
- **Decision**: Normalize the existing retained work-unit/SDK evidence first. Pass its same-source, same-profile typed maintenance availability into the single compatibility prediction before the sole final publication. Raw compatibility inputs without this prerequisite evidence retain null full-scope health. Preserve legacy score mathematics, versions, native limits and the typed scorer. Label the legacy complexity category as finding-density health; measured cyclomatic complexity remains separate and missing measurements stay unavailable.
- **Why**: One authoritative prerequisite decision prevents a smaller projected input from becoming an unqualified clean result, without executing prediction or native analysis twice.
- **Tradeoffs**: A numeric legacy score requires the existing qualified evidence. Authored normalized documents and hashes do not authenticate a producer; the managed pipeline supplies evidence from its checked owned stage. Acceptance is recorded separately by source-bound evidence, independent review and the ledger; the original red and qualification failures remain retained.
- **Verification**: Actual prerequisite63 and affected-component126 checks passed; the one frozen113 wheel passed19 installed feature checks plus privacy3, SDK5+5, license57 and public report checks. See work/metrics113/ for original failures, exact artifact pins and acceptance records. This decision is not acceptance evidence by itself.
- **Interview angle**: Preserve a useful scoring calculation while making the prerequisites for publishing its result explicit.


## PROD-20261118-25: Define shared history independently of unavailable symbol production

- **Context**: The existing weighted file metrics and shared bounded history scan lacked a checked common identity/rename/coupling/component/symbol contract. Cached commits also lacked the repository attribute used to disclose shallow parent-delta availability. Actual numeric controls already excluded the shallow boundary; the missing disclosure was a provenance defect.
- **Decision**: Add the v2 shared-history schema and semantic validator plus a thin projection of the existing HistoryScan. Preserve contributor aliases, bot/former/pair facts, rename anchors, distinct-commit coupling support and explicit denominators/exclusions. Declare actual symbol history unavailable; synthetic symbol associations exercise the contract only. Resolve shallow metadata using the scan owner repository with bounded local shallow-file reads, without object or network probing and without changing metric formulas.
- **Tradeoffs**: A contract definition does not create a symbol-history producer. FR-GIT-04 remains waiting for that producer and function-level coupling. Attribution remains a knowledge proxy; hashes identify bytes and do not authenticate Git history or prove expertise.
- **Verification**: The meaningful provenance failure and both failed integration attempts remain retained. The repaired joint source gate records 225 passed, exit 0 and stable identified source at work/history114/component-repair2/record.json. Legacy plain/optional output equality remains exact: both disclose retained-history scope and the test supplies one explicit SZZ cutoff to both invocations. Installed candidate qualification, current-prior-evidence refresh and independent whole-criterion acceptance are separate required gates before ledger closure.


## PROD-20261118-26: Preserve calculation identity during explicit maintenance replay

- **Context**: The installed public maintenance command attempted to publish a second fact with the deterministic identity already retained by the pipeline. Contract validation correctly rejected the duplicate after202 installed controls had passed. A snapshot can also retain calculations for different declared context sets.
- **Decision**: Reuse an exactly equal retained calculation after the existing verified-parent and current-material checks. Preserve its run/manifest and formula/version. Select the requested stored v4 profile, parse opt-in and required/optional context set in CLI output. Show method, denominator, scope and completeness beside health; keep the legacy per-file calculation separate from physical-KLOC v4. Document snapshot compatibility explicitly.
- **Why**: Identical calculation identity must not create duplicate facts or bypass freshness; a later calculation for another scope must not determine the requested output by list order.
- **Tradeoffs**: Reuse creates no new producer execution or timestamp claim. Hashes and controlled fixtures do not authenticate producers or qualify calibration, other platforms or full P14. Original failures, both candidate epochs and complete historical proof bodies are retained with exact recovery custody.
- **Verification**: The affected source gate records162 passed, exit0 and stable source at work/metrics117/component-repair6/record.json. Installed public replay, wrong-workspace rejection, prior36 proof refresh and independent whole-batch acceptance remain required before ledger closure; this decision alone closes no item.
- **Interview angle**: Treat score identity, scope selection and evidence freshness as separate properties without changing the scoring formula.


## PROD-20261118-27: Keep repository and proxy-label identity explicit

- **Context**: Findings and Git reports with conflicting declared repositories could join under the same relative file ID. A known all-zero SZZ cohort was also treated as absent and relabelled by feature heuristics; serialized ranking omitted structured SZZ cutoff/provenance.
- **Decision**: Compare declared repository roots lexically before a nonempty history join, preserve static-only operation with empty history, and leave missing root identity unverified for ranking. Preserve raw SZZ field presence separately from convenience zeros. Eligible-only training retains observed proxy zeros; only absent observations use disclosed feature heuristics, including explicit mixed cohorts. Copy the original structured SZZ provenance and record the exact training-file provenance.
- **Why**: Unrelated history must not become a file's observed history. Known zero proxy labels must not be replaced by correlated feature-derived positives. A label cutoff does not make retained full-history features a historical holdout.
- **Tradeoffs**: Paths, hashes and declared SZZ counts do not authenticate producers or establish confirmed defects, expertise or calibrated future-defect probability. Existing interfaces and scoring formulas stay compatible; raw metadata is preserved with its limitations. Legacy test-frame defaults now explicitly mark absent SZZ observations, retaining their assertions and the contrasting observed-zero regressions.
- **Verification**: Original counterexamples retain7 identity failures and5 label/provenance failures. The affected source gate records141 passed with stable identified inputs at work/predictor118/component-repair2/record.json. Installed four-result composition, prior38 evidence refresh, independent review and unchanged strict verification remain necessary before acceptance; this decision is not closure evidence.
- **Interview angle**: Separate declared origin, observation availability, training eligibility and validation claims rather than inferring them from convenient numeric defaults.


## PROD-20261119-28: Resolve local detector packs separately from scoring and policy

- **Context**: The approved T1–T3 batch requires inspectable pack precedence, three actual clang-tidy families and agreement across retained readers. Registry2.0.0 is a format version; native detection remains22 experimental checks. Older native rule pilots remain deferred.
- **Decision**: Resolve finite local JSON packs with strict schema, ordered inheritance, per-option origins and byte hashes. Preserve legacy JSON/YAML project files and separate scoring profiles/policies. Retain original pack JSON and effective settings; pack identity participates in bounded execution selection. Explicit collector recipes must match resolved provider arguments, scope and version; commands are never rewritten or supplied by a pack. Require pack files in selected source inputs and keep diagnostic origin/import completeness unchanged.
- **Why**: A tool selection, a measured maintenance result and an acceptance gate answer different questions. Hashes identify bytes and do not authenticate a producer or turn an empty import into completed clean execution. Historical API/MCP/report readers must expose the selected configuration rather than live defaults.
- **Tradeoffs**: Only documented options/scopes are accepted. No arbitrary plugins, remote packs, new native rules, arbitrary borrowing-type coverage or calibrated confidence is claimed. Docker scripts propagate one config/profile; real image/host qualification remains a separate gate. Predictor explicit invalid configuration now fails instead of silently choosing default.
- **Verification**: InitialT1 resolver/config gate88 passed; T2 actual19.1.7 producer16 contexts and component136 passed against their frozen inputs. Final combined source/installed checks, one candidate, current proof refresh and independent batch review remain required. Original harness/cache reconstruction failures remain retained; these preliminary counts do not close parent requirements.
- **Interview angle**: Make configuration an inspectable retained input, and distinguish local execution receipts from imported diagnostic claims.

- **Legacy validation clarification**: Empty/comment-only YAML and missing profile remain valid defaults; no-config keeps no implicit discovery. Explicit missing files/unknown profiles are invalid. Supplying --profile still overrides a valid config profile but intentionally no longer bypasses config validation. Outside-CWD controls retain absolute explicit selection.

- **Review repair**: Preserve the actual native CLI: it accepts profile through JSON/YAML --config and has no --profile flag. Both container stages forward one shared config; matched single-file discovery avoids native/predictor divergence, ambiguity fails, and container CPPULSE_PROFILE instructs callers to pre-resolve via host CLI. Add actual unchanged-native execution/invalid-profile control beyond mocked argv checks. Preset baselines precede inherited explicit values; only enabled origins are set by presets. Explicit predictor profile overrides update their origin leaf. Response-file indirection is rejected for the finite explicit provider settings contract.

- **Mounted output repair**: Predictor creates an exclusive private stage inside the validated output directory, then completes both output generation/schema validation and the original-input integrity guard before publication. It rechecks the output directory and regular target leaves, closes writers, and uses one atomic `os.replace` per file. A second publication failure is an error and may leave the first file updated; this is not a pairwise transaction or crash-durability guarantee. Output symlinks/nonregular leaves are rejected and cleanup owns only the private stage. The original Docker bind-mount EXDEV failure is retained.
- **Configuration identity repair**: Project configuration settings and their content hash come from one read of the same bytes. Predictor derives its profile and retained settings from one validated read as well. Controlled live-file mutation tests distinguish the selected bytes from a later filesystem value.


## PROD-20261120-29: Integrate reviewer fixes without inheriting old score or evidence claims

- **Context**: The approved finite review exposed missing `.c++` database units, three modernization-context errors and an incomplete first trial. Main and the tested checkpoint diverged; main's historical density/empty100 scoring is incompatible with current measured-context prerequisites. The originating Cloud workspace could not admit a new native build.
- **Decision**: Prepare one deliberate two-parent integration based on same-tested-tree master plus main, retaining all main-only history and referencing large historical result blobs instead of copying96MB into the checkout. Keep canonical Git/PDF implementations, versioned unknown-preserving scoring and shared CI. Resolve native profile overrides before execution. Reconcile declared units with explicit gaps/exclusions; restrict detector repairs to proven source shapes and three rule-version bumps. Provide an authored finite C++/CTest example with genuine positive/missing/stale acceptance controls.
- **Why**: Missing declarations, contextual style hints, historical arithmetic and a failed storage admission cannot become claims of clean code, calibrated probabilities or current qualification. Source transfer must preserve exact bodies/modes/tree, not depend on an unverified commit/push.
- **Tradeoffs**: The conservative range-for subset intentionally does not suggest many valid rewrites. Compiler-marked custom system roots remain trusted for header identity. First-trial execution requires actual CTest3.31.6. All187 definitions/states/P0–P14 remain intact; PR-04/M0-05 and external human/platform obligations remain unfinished.
- **Verification**: At source handoff, the originating workspace had only mechanical static checks. Wrapper admission exit 1 at 4,332,023,808 B free prevented producer start. The portable hash-checked transfer preserved the source and historical records. Receiving-host results and their remaining acceptance requirements are recorded below and in the [batch record](development/reviewer-fixes.md).
- **Interview angle**: Preserve history and evidence identities independently from current source claims; treat unavailable prerequisites as explicit blockers rather than green results.

## PROD-20261120-30 — Qualify literal exclusions and range-for advice on the receiving host

- **Context**. The frozen v2 run built with GCC 14.2 and libclang 19.1.7. CTest 3.31.6 found that a literal `.c++` exclusion let the intended translation unit through and matched a different `.cc` file. It also found a volatile array accepted as a read-only range-for candidate. A separate native run showed that applying advice which stripped `metrics::` changed the executable result from 16 to 70 when a local `values` shadowed that name.
- **Decision**. Preserve literal plus signs when translating native exclusion globs. Check array element qualification where libclang exposes it and describe the range-for rewrite without inventing an identifier. Keep the original detection controls and exercise both an exact literal exclusion and a qualified array with shadowed names.
- **Why**. Exclusion must select the same file the user named. Range-for advice must respect the observed array binding and the rule's conservative read-only scope.
- **Tradeoffs**. Range-for advice describes the rewrite without supplying a ready-to-paste loop. The existing `.c++` discovery scope, detector IDs, format versions and original acceptance criteria still apply.
- **Verification**. The receiving Cloud run preserves the exact v2 source and its two failed native CTests. The repaired code passed all 175 CTests, and the installed first trial passed its real CTest, missing-evidence and stale-source controls. The receiving-host OSS analyses retained partial results. The README records those observed outcomes and the release gate. Because it becomes wheel metadata, the documentation revision requires its own source freeze, build and installed verification. The strict delivery evidence for the original 38 criteria remains pending.

## PROD-20261120-31 — Match dashboard notices to the resolved production dependencies

- **Context**. The installed dashboard and lockfile resolved Lodash 4.18.1, while the bundled notice identified 4.17.23. The resolved production inventory contains 44 package entries and 57 license bodies, including the upstream Victory license and the notices for its vendored components.
- **Decision**. Update the Lodash heading to 4.18.1, preserve every license body, and regenerate the bundled notice and its manifest with the dashboard asset producer. Preserve the prior source tree and its verification records under their original identity.
- **Verification**. The renewed inventory compares each lockfile entry, installed package identity, and complete license body. The previous inventory had one version mismatch. The correction requires a fresh source freeze and verification of the rebuilt wheel and installed bytes. Whole-delivery acceptance still requires the complete current proof.

## PROD-20261121-32 — Separate legacy analysis completion from health qualification

- **Context**. An installed legacy invocation from `/` passed the literal source path to the native analyzer. The analyzer used the selected compilation database, analyzed the file with zero parse errors and produced the report. The archive correctly retained unverified inputs and a null health score. The CLI used that score to classify the descriptive analysis as partial.
- **Decision**. Derive legacy completion from the retained native inventory and requested report. Require a nonempty, consistent source inventory, observed successful parses with working directories and arguments, and the required profile detectors. A selected compilation database requires observed database context for each in-scope file. Empty scope, skipped or failed units and missing required results remain partial.
- **Why**. A descriptive report can help a user inspect a successfully analyzed scope while the prerequisites for full-scope health and source verification remain unavailable.
- **Tradeoffs**. Legacy publication keeps the unverified archive and any unavailable health score. Optional Git history keeps its own availability disclosure. Bounded analysis and operational error reporting retain their existing contracts.
- **Verification**. The installed Linux replay exercised all nine original working-directory cases. The legacy invocation completed with exit 0, null health and an unverified archive. The bounded unsupported-input control still returned 3. Six additional native controls returned 3 for empty scope, a skipped file, parse errors, a missing required detector, inferred context and fallback context under an explicitly selected database. Retain the earlier failing legacy receipt with its original source and artifact identities.
- **Interview angle**. Explain how one CLI response can describe a completed native analysis and an unavailable health score. The retained inventory and report support the first claim, while source bindings and complete qualified prerequisites govern the second.

## PROD-20261121-33 — Order tied roadmap rows by file and category

- **Context**. Four retained predictor entry-point runs emitted the same three knowledge-silo rows with equal impact. The row order and assigned priorities varied because their input came from a Python set.
- **Decision**. Keep impact descending as the primary sort. Break exact ties by the existing file path and then category in ascending order before assigning priorities. The default profile continues to omit MISRA rows. The safety-critical profile applies the same ordering to its included rows.
- **Why**. The file and category already identify the roadmap row. Using them as tie-breakers makes priorities reproducible across hash seeds and entry points while preserving impact, weights, other row fields, and profile selection.
- **Tradeoffs**. Equal-impact rows now have an explicit lexical order. Stored reports keep their original priorities. New reports may reorder ties from older generated reports.
- **Verification**. The original four differing outputs remain in custody. Qualification is pending. Planned checks cover full roadmap output and priorities across multiple Python hash seeds, source and installed entry points, both profiles, and a higher-impact control. The separate old69 comparison retains its original input and exact parity assertions.
- **Interview angle**. Show how a stable sort can preserve nondeterminism from an unordered input. Name the existing row fields that make the ordering total within the expected output scope.

## PROD-20261121-34 — Bind master CI to current producers and explicit test scopes

- **Context**. New pull requests target `master`. A clean Actions checkout has no local edits for the formatter to discover. The health controls need an actual current analyzer, while archived differential tests need their original inputs.
- **Decision**. Pin clang-format 19.1.7, Black 24.1.1 and Ruff 0.2.1. Use the PR base and head for formatting selection alongside local changes. Keep the shared native and component checks. Register the current analyzer and selected Clang headers after native configuration, build and CTest succeed for the same source. Keep the exact historical comparisons in the complete local suite and name their exclusions in the hosted command.
- **Why**. A committed test change must reach Black and Ruff. A current analyzer must exercise all nine live health controls with its own preregistered identity. The suite also retains the two pure health cases. Archive identity remains part of each historical assertion.
- **Tradeoffs**. The hosted lane depends on real provider and evidence fixtures. Its results cover the recorded source checks. Full and historical assurance still require their separate inputs and acceptance.
- **Verification**. Exercise a real clean Git checkout with committed changes, check the workflow and its command selection, and run the live health cases with a registered build. Hosted results require an actual GitHub run.
- **Interview angle**. Explain why a source diff and a build receipt are stronger inputs for CI than a dirty-worktree check or a fixed digest from a past build.

## PROD-20261121-35 — Refuse late bounded metadata changes during publication

- **Context**. The clean CI replay changed a work-unit result after the report was generated. Bounded publication kept the original receipt but still returned a completed result. A separate late external-header mutation already raised `InputChanged` during publication.
- **Decision**. Recheck the observed work-unit metadata in the store's final publication callback. A change aborts the candidate publication. Existing failure handling can retain a separate partial attempt with the original receipt and conflicting bytes as diagnostics.
- **Why**. FR-EVD-04 requires detection of changed evidence. The same failed publication cannot supply current complete analysis or qualified health for FR-ANA-07.
- **Tradeoffs**. Publication reads the retained metadata a second time. A later diagnostic attempt can fail independently if its inputs change again. A successful run keeps its existing results and pointer behavior.
- **Verification**. Exercise the actual native pipeline with unchanged metadata, then with a late result mutation. Confirm the earlier completed pointer and original receipt remain intact, and preserve the conflicting bytes only as diagnostics. Keep the external-header test on its existing final-window failure contract.
- **Interview angle**. Explain how a final pointer update can race with an earlier integrity check, even when the archived receipt itself remains byte-identical.

## PROD-20261121-36 — Close the dashboard lock under the hosted npm version

- **Context**. GitHub Actions run 44905173898 stopped at the dashboard's locked install under Node 20.20.2 and npm 10.8.2. The lock recorded esbuild 0.21.5 for the production Vite build. It lacked the compatible optional esbuild peer and platform entries for the Vite 8 used by Vitest.
- **Decision**. Regenerate the lock with npm 10.8.2 and preserve all previously locked entries. Pin Node 20.20.2 in this hosted lane and check its bundled npm version before the locked install. Keep the shared dashboard tests and production build after `npm ci`.
- **Why**. A fresh checkout should resolve exactly the same test and build dependencies selected during qualification. Retaining both esbuild versions preserves the distinct dependency requirements of the existing Vite versions.
- **Tradeoffs**. The lock adds 27 development-only entries for esbuild 0.28.2 and its platform packages. The pin makes tool upgrades explicit for this job.
- **Verification**. The original lock failed with npm EUSAGE on the same toolchain. A fresh install with the regenerated lock passed with all 343 previous entries unchanged. All 64 dashboard tests and the production build passed. The shipped HTML, CSS, JavaScript and notices were byte-identical, including the verified 44 production dependencies and 57 license bodies. The rebuilt and installed wheel changed only the asset manifest and its RECORD entry. The hosted rerun remains pending.
- **Interview angle**. Explain how an optional test-tool peer can make a locked install fail while the versions used by the production build stay unchanged.

## PROD-20261121-37 — Trust the Actions checkout for the pinned Git provider

- **Context**. GitHub Actions run 44905173898 installed Git 2.52.0 in the Python job's container. Its first developer-facade call stopped before native configuration because Git rejected the ownership of the mounted checkout.
- **Decision**. After adding the pinned Git binary to the job path, register the canonical `GITHUB_WORKSPACE` checkout in a job-owned file under `RUNNER_TEMP`. Require a checkout marker and reject a wildcard directory entry. Select the file in later steps through `GIT_CONFIG_SYSTEM` so the entry survives a fresh HOME.
- **Why**. The workflow controls which Actions checkout it builds. The exact allowlist entry lets the selected Git inspect that checkout and preserves ownership checks for other repositories.
- **Tradeoffs**. The trust entry applies for the lifetime of this CI job. The step depends on Actions declaring an existing checkout path.
- **Verification**. Execute the actual registration step with Git 2.52.0 under its ownership-test mode. Require Git to reject all initially untrusted repositories, then accept the declared checkout from a fresh HOME while continuing to reject both a sibling and a nested repository. The hosted rerun remains pending.
- **Interview angle**. Explain why a checkout can gain trust for an ephemeral CI job without turning off Git's ownership check for other repositories.

## PROD-20261121-38 — Include canonical contract tests in component coverage

- **Context**. GitHub Actions run 44907679831 on the published checkpoint passed the public root suite. The Git miner component passed all 90 tests and measured 59.31% against its required 80% canonical threshold. Local replay matched that result and measured 69.36% for the predictor against 75%. The local report-engine replay also exposed two component fixtures that assumed an older package or store layout.
- **Decision**. Keep each original component collection and working directory. Add explicit public root contracts for behavior and history, temporal prediction and risk, and the work-unit API to their matching coverage sessions. Keep the canonical thresholds and fail a report that omits a canonical Python file. Exercise the packaged report from an archive of the current package, and corrupt the authority pointer used by each store format in the named-read test.
- **Why**. Component coverage needs to observe the canonical code its clients actually exercise. The on-disk inventory gives unexecuted files a place in the denominator. A named-read test needs to damage the authority that a current read would really open.
- **Tradeoffs**. Component gates now run a small set of repository-level tests, some of which also run in the full root suite. Each uses the same collection process and regular local fixtures. Existing historical lanes keep their current test selections.
- **Verification**. Preserve the hosted and local failing receipts. The repaired local gates measured 87.44% for Git miner, 88.98% for predictor and 93.36% for report engine, with the same canonical files and statement totals. The omitted-file, shim, threshold, optional-dependency and corrupt-pointer controls passed. The repair's hosted rerun remains pending.
- **Interview angle**. Explain the difference between a passing test process and a passing coverage gate, and why a missing module cannot improve a statement-coverage result.

## PROD-20261121-39 — Separate the public handoff from historical trials

- **Context**. The scoped Linux checkpoint merged into master while the README and handoff still described it as awaiting publication. The developer evaluations and LevelDB measurements describe different historical runs.
- **Decision**. Point readers to the merged first trial and shared developer commands. Publish a bounded summary of the ten simulations with pinned upstream links and unresolved limits. Date the LevelDB producer identities and retain the original evidence.
- **Why**. Developers need a usable entry point and the scope behind each claim. Keeping provenance visible helps them choose appropriate checks for their own build.
- **Tradeoffs**. The summary reports bounded observations and limits. It leaves human usefulness, broader environment coverage and production acceptance open.
- **Verification**. Check current and historical links, run the finite trial from the installed wheel, compare the README with its packaged metadata and run the generated metadata check.
- **Interview angle**. Explain how to preserve a useful historical measurement while updating the instructions a reader follows today.

## PROD-20261121-40 — Explain why bounded source binding is unverified

- **Context**. A completed native receipt can coexist with an unqualified include or compiler context. The bounded publication explanation previously described every unavailable check as a change.
- **Decision**. Carry checked changes and unqualified inputs separately through the bounded publication guard. Retain the underlying causes and next steps in the run manifest, which the CLI and evidence report already read.
- **Why**. A reader needs to distinguish a rerun after an edit from a missing binding that requires checking the selected inputs or context. Both findings can apply to the same attempt.
- **Tradeoffs**. The binding explanation describes the selected observed scope. An actual change still aborts guarded publication. Partial archives keep their diagnostics, and qualified health still requires its original evidence.
- **Verification**. Exercise unchanged unqualified, changed, mixed and verified-clean inputs, postflight tool and resource loss, and late publication checks. Compare the pinned manifest explanation with public JSON and HTML.
- **Interview angle**. Explain what facts justify describing an input as changed, what remains unknown, and why either condition can leave the same partial result.

## PROD-20261121-41 — Verify two finite fmt consumers

- **Context**. The first trial illustrates one authored C++ consumer. A library developer also needs to see how two ways of consuming the same release produce distinct context and evidence bindings.
- **Decision**. Build the locked fmt 10.2.1 source and select compiled and header-only distribution views. Verify actual package use and header self-containment separately from the existing finite test policy. Preserve missing matrix cases as declarations in evidence reports. Provision the public fmt source explicitly before the hosted example runs.
- **Why**. A policy can accept the two selected workload outcomes without proving package applicability. Declared requirements must remain visible when a context or its execution evidence is missing.
- **Tradeoffs**. Verification is finite and pinned to the supported GCC, GNU ld and CTest producers. The two distribution views omit broader upstream analysis and uninstantiated templates.
- **Verification**. Run both configurations, the deliberately incorrect authored expectation, the absent header-only lane and a stale-workspace check. Compare the selected source, execution, package-use and assessment pins with JSON and HTML. Keep actual hosted results separate.
- **Interview angle**. Explain which observed data proves a static archive contributed to one build and which data allows a required but unexecuted lane to remain unknown.
