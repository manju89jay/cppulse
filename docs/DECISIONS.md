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
- **Tradeoffs**: Weights are calibrated empirically, not formally derived. Documented for transparency.

## D8: 15 default rules + 7 opt-in MISRA — standard-grounded where possible
- **Context**: Which rules to implement?
- **Decision**: Default profile: 3 memory safety, 9 modernization, 3 complexity (15 rules). Safety-critical profile adds 7 MISRA rules (22 total).
- **Why**: Memory rules map to common CVE patterns. Modernization rules are empirical best practices from clang-tidy modernize-* checks. MISRA rules are opt-in because they target safety-critical embedded (see D13).
- **Tradeoffs**: Not exhaustive. 15 default rules cover the three main debt categories for general-purpose C++. MISRA opt-in adds a fourth for safety-critical projects.
- **Interview angle**: "I picked 15 default rules covering three debt categories for general C++, plus 7 opt-in MISRA rules for safety-critical work. MISRA is opt-in because real-world testing showed it produces false signals on general-purpose code (see D13)."

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
- **Tradeoffs**: Heuristic is less accurate than ML prediction.

## D13: MISRA rules opt-in via analysis profiles
- **Context**: After analyzing 6 real-world C++ projects, MISRA compliance scored 0.0 on 5 out of 6. protobuf scored 0/100 overall despite being Google production code.
- **Decision**: Default profile excludes MISRA rules. `--profile safety-critical` enables them with 2.5x weight.
- **Why**: MISRA C++:2023 targets safety-critical embedded systems (AUTOSAR, DO-178C, IEC 62304). General-purpose C++ projects deliberately use `goto`, unions, multiple returns, and uninitialized-then-assigned variables. Penalizing them produces false signals.
- **Tradeoffs**: Default profile only evaluates 15/22 rules. Safety-critical projects must explicitly opt in.
- **Interview angle**: "I discovered this by running cppulse on 6 real codebases. protobuf scored 0/100 because of MISRA rules — that's a false signal. Making MISRA opt-in shows I can calibrate a tool based on real-world data rather than theoretical assumptions."

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
