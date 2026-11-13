# cppulse project overview

Prepared: 2026-11-13. Positioning: engineering prototype for job applications.

## Application paragraph

I developed cppulse, an open-source C++ codebase-analysis prototype combining a C++17/libclang analyzer with Python-based Git-history analysis and experimental risk ranking. It includes 22 built-in checks, a CRTP/std::variant rule engine, JSON artifact contracts, fixture-based tests, and CLI/reporting components. The project demonstrates practical experience with C++ tooling, modular architecture, testing, and native/Python integration. Prediction accuracy and production readiness remain areas for validation.

## One page overview

### Native C++ tooling

Implemented libclang AST traversal and 22 checks for memory-related patterns, modernization, complexity, and selected coding rules. Organized static rule dispatch with CRTP and std::variant.

### Component architecture

Separated native analysis, Git mining, prediction, and reporting through inspectable JSON artifacts and documented schemas. Kept component boundaries explicit for debugging and extension.

### History and experimental ranking

Extracted churn and contributor signals. Added XGBoost-based ranking with a small-dataset heuristic fallback and conditional cross-validation; treated predictive results as experimental.

### Testing and delivery groundwork

Included fixture-driven C++ tests and Python test suites, CLI orchestration, FastAPI/PDF/React components, and local Docker definitions. These provide concrete code and design decisions to discuss.

### Engineering tradeoffs

Reused a compiler front end for C++ parsing. Chose static rule dispatch with a closed rule set. Used human-readable JSON to make native/Python boundaries inspectable.

### Current maturity

Engineering prototype. Current priorities are reproducible end-to-end execution, contract consistency, and scoring validation. Configuration-specific verification evidence is a proposed next direction.

Repository: https://github.com/manju89jay/cppulse

## Before applying

- Verify one small end-to-end demonstration and record its environment and revision.
- Align README claims with current behavior; inspect historical example totals before using them as evidence.
- Describe the design, limitations, and your use of AI assistance accurately.
- Avoid claims of production readiness, certification, proven prediction accuracy, or measured business impact.

PDF generated locally at output/pdf/cppulse-project-overview.pdf.
