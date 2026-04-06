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
