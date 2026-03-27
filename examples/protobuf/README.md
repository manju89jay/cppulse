# cppulse Report: Protocol Buffers

> Analyzed 2026-03-27 · 400,000 LOC · 1,085 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

Protocol Buffers (protobuf) is Google's language-neutral, platform-neutral
extensible mechanism for serializing structured data. Originally developed at
Google to replace ad hoc XML formats, it is now the backbone of gRPC and
countless internal Google systems, as well as a widely adopted standard across
the industry. At 400K lines and 1,085 analyzed files, protobuf is a large,
mature codebase — and its cppulse score of 0.0/100 is the starkest result in
this benchmark set. The zero score is driven entirely by a catastrophic MISRA
compliance failure: 354 findings of uninitialized variables and multiple returns
across the analyzed file sample, plus a zero modernization score reflecting
legacy typedef-heavy style. Memory safety and complexity are actually respectable
at 95.0 and 80.9 respectively.

---

## Health Score

<p>
  <img src="../../assets/protobuf/health-gauge.svg" alt="Health Score: 0.0/100" width="280" />
  <img src="../../assets/protobuf/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **95.0** | 13 | C-style array params (11), raw `new` (1), explicit `delete` (1) |
| Complexity | **80.9** | 37 | Long functions (18), high cyclomatic complexity (10), excess params (9) |
| Modernization | **0.0** | 96 | NULL vs nullptr (51), deprecated C headers (12), `auto` opportunities (12) |
| MISRA Compliance | **0.0** | 354 | Uninitialized variables (301), multiple returns (45), `goto` (5) |

**Total: 500 findings across 16 of 22 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `python/google/protobuf/pyext/unknown_field_set.cc` | 99.9% | Critical | MISRA violations (27), memory issues (1) |
| `rust/cpp_kernel/map.cc` | 99.9% | Critical | MISRA violations (3), memory issues (1) |
| `rust/test/cpp/interop/test_utils.cc` | 99.9% | Critical | MISRA violations (5), memory issues (2) |
| `src/google/protobuf/compiler/cpp/copy_unittest.cc` | 99.9% | Critical | MISRA violations (12), memory issues (1) |
| `src/google/protobuf/compiler/cpp/tools/analyze_profile_proto_main.cc` | 99.9% | Critical | MISRA violations (5), memory issues (1) |
| `src/google/protobuf/compiler/csharp/csharp_bootstrap_unittest.cc` | 99.9% | Critical | MISRA violations (7), memory issues (1) |
| `src/google/protobuf/compiler/main.cc` | 99.9% | Critical | MISRA violations (12), memory issues (2) |
| `src/google/protobuf/field_with_arena_test.cc` | 99.9% | Critical | MISRA violations (6), memory issues (2) |
| `src/google/protobuf/json/internal/zero_copy_buffered_stream.h` | 99.9% | Critical | MISRA violations (3), memory issues (1) |
| `src/google/protobuf/preserve_unknown_enum_test.cc` | 99.9% | Critical | MISRA violations (47), memory issues (1) |

**541 files** flagged Critical · **140 files** flagged Low risk (of 681 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `conformance/binary_json_conformance_suite.cc` | Reduce cyclomatic complexity | complexity | 42h | 24.0 |
| 2 | `conformance/naming_test.cc` | Address MISRA C++ compliance violations | misra | 30h | 24.0 |
| 3 | `conformance/test_manager_test.cc` | Address MISRA C++ compliance violations | misra | 14h | 24.0 |
| 4 | `bazel/private/file_concat/main.cc` | Replace raw pointers with smart pointers | memory_safety | 4h | 16.0 |
| 5 | `bazel/private/file_concat/main.cc` | Address MISRA C++ compliance violations | misra | 2h | 16.0 |
| 6 | `bazel/tests/proto_descriptor_set_test.cc` | Address MISRA C++ compliance violations | misra | 8h | 16.0 |
| 7 | `benchmarks/benchmark.cc` | Modernize C++ code: apply C++11/14/17 idioms | modernization | 8h | 16.0 |
| 8 | `benchmarks/benchmark.cc` | Address MISRA C++ compliance violations | misra | 42h | 16.0 |
| 9 | `conformance/binary_json_conformance_suite.cc` | Replace raw pointers with smart pointers | memory_safety | 4h | 16.0 |
| 10 | `conformance/binary_json_conformance_suite.cc` | Modernize C++ code: apply C++11/14/17 idioms | modernization | 24h | 16.0 |

**Total: 1,261 roadmap items · ~114,639 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
