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
- **Decision**: Weighted deduction: memory_safety×3, misra×2.5, complexity×1.5, modernization×1
- **Why**: Safety-critical findings weighted highest. Mirrors MISRA severity classification.
- **Tradeoffs**: Weights are calibrated empirically, not formally derived. Documented for transparency.

## D8: 22 rules — standard-grounded where possible
- **Context**: Which rules to implement?
- **Decision**: 3 memory safety, 9 modernization, 3 complexity, 7 MISRA subset
- **Why**: Memory/MISRA rules map to MISRA C++:2023 and AUTOSAR C++14. Modernization rules are empirical best practices from clang-tidy modernize-* checks.
- **Tradeoffs**: Not exhaustive. 22 was chosen for demonstrable breadth, not completeness.
- **Interview angle**: "I picked rules that cover the four main debt categories in safety-critical C++. MISRA rules are directly traceable to the standard. Modernization rules mirror clang-tidy's modernize-* set."

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

