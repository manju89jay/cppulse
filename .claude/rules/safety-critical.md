---
paths:
  - analyzer-core/**/*
---

# Safety-Critical Coding Rules for analyzer-core

These rules reflect the safety-critical domain that cppulse is designed to
analyze. analyzer-core must itself embody the standards it enforces.

## Memory Safety
- Zero raw pointer ownership — all ownership via smart pointers
- No manual memory management anywhere in the analysis pipeline
- Buffer access via `std::span` or range-checked containers

## Concurrency Safety
- No global mutable state — all shared state explicitly synchronized
- Thread-safe result aggregation in FileAnalyzer (std::mutex on findings vector)
- No data races — validate with ThreadSanitizer (`-fsanitize=thread`) before merge

## Error Paths
- Every libclang API call result must be checked
- `clang_parseTranslationUnit` failure → log error, return empty findings (not crash)
- File not found → log warning, skip file, continue analysis

## Robustness
- Never crash on malformed input — analyzer-core must handle any C++ file gracefully
- Template-heavy files, macro-only files, empty files: all must return cleanly
- Large files (>500KB): skip with a warning rather than OOM

## No Dynamic Exceptions Across Boundaries
- All public API functions are `noexcept` or return `std::expected`
- No exceptions propagate out of libclang callback functions

## MISRA-Adjacent Naming
- No single-letter variable names outside loop indices
- No abbreviated names that require domain knowledge to decode
- All constants are `constexpr` with descriptive names
