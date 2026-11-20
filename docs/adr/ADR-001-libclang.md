# ADR-001: Use libclang for C++ Static Analysis

> **Historical decision record — its universal capability claims are unverified.** The original rationale and metadata below are preserved. Choosing libclang does not establish that cppulse handles every C++ edge case, supports a new standard without implementation work, or detects every defect. Actual verification includes partial/unsupported parse contexts and finite selected inputs; Docker and other platforms require their own execution evidence. See the [current prototype scope](../../README.md), [native normalization limits](../development/analysis-normalization.md) and [current workflow guide](../development/public-cli.md). No detector-accuracy, certification or safety guarantee is implied by this ADR.

**Date:** 2026-03-04
**Status:** Accepted
**Deciders:** Manjunath Jayaramaiah

---

## Context
cppulse needs to parse and analyze C++17 source code to detect 22 categories of
technical debt patterns. The core question is: do we write a custom parser, or
use an existing library?

Writing a custom C++ parser is a multi-year project. C++ is one of the most
complex languages to parse correctly — templates, macros, preprocessor directives,
and overloaded operators all create ambiguity that requires full compiler front-end
understanding.

## Decision
Use **libclang** — the stable C interface to the Clang compiler's AST.

## Consequences

### Positive
- Correctness: libclang handles every C++ edge case (templates, macros, SFINAE)
  because it uses the same parser as the Clang compiler
- Maintainability: Clang updates automatically add support for new standards
  (C++20, C++23) without changes to our code
- Speed: libclang is pre-compiled and battle-tested on millions of projects
- API stability: the C interface (not C++) is explicitly maintained for stability
- Industry standard: used by clangd, clang-tidy, and most major C++ IDEs

### Negative
- Dependency on LLVM/Clang toolchain at build time
- libclang API is verbose — traversal requires callback functions
- Performance is lower than a direct Clang plugin (acceptable for batch analysis)

### Neutral
- Requires libclang-dev to be installed (handled via Docker)

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Custom regex-based parser | Would fail on macros, templates, and multi-line constructs. Not viable for production C++. |
| Tree-sitter C++ grammar | Faster, but produces a syntax tree not a semantic AST. Cannot resolve types or follow includes. |
| Clang plugin (not libclang) | More powerful but not stable across Clang versions. Would break on every LLVM update. |
| Cppcheck API | Cppcheck is a linter, not a full parser. Insufficient for AST-level analysis. |
