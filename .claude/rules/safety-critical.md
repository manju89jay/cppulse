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
- Use range-checked containers or explicit validated bounds under C++17. `std::span` requires C++20 and is not required by the implementation standard.

## Concurrency Safety
- No global mutable state — all shared state explicitly synchronized
- A FileAnalyzer instance visits translation units sequentially. Synchronize concurrently accessed results if that changes. Prefer isolated worker results and owner-only aggregation; a mutex is not required for state accessed by a single owner.
- No data races — validate with ThreadSanitizer (`-fsanitize=thread`) before merge

## Error Paths
- Every libclang API call result must be checked
- `clang_parseTranslationUnit` failure → log error, return empty findings (not crash)
- File not found → log warning, skip file, continue analysis

## Robustness
- Never crash on malformed input — analyzer-core must handle any C++ file gracefully
- Template-heavy files, macro-only files, empty files: all must return cleanly
- Use a configurable file-byte budget rather than a fixed 500 KiB exclusion. Record skipped files and reasons as incomplete scope. Input-byte limits do not establish process memory bounds; worker memory limits require separate implementation and verification.

## No Dynamic Exceptions Across Boundaries
- Catch failures at executable boundaries and use C++17 result types. Apply `noexcept` only where the implementation can satisfy it, rather than converting recoverable errors into termination.
- No exceptions propagate out of libclang callback functions

## MISRA-Adjacent Naming
- No single-letter variable names outside loop indices
- No abbreviated names that require domain knowledge to decode
- All constants are `constexpr` with descriptive names
