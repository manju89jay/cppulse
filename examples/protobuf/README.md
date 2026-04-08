# cppulse Report: Protocol Buffers

> Analyzed 2026-03-27 · 400,355 LOC · 1,085 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

Protocol Buffers (protobuf) is Google's language-neutral, platform-neutral extensible mechanism for serializing structured data. Originally developed at Google to replace ad hoc XML formats, it is now the backbone of gRPC and countless internal Google systems, as well as a widely adopted standard across the industry.
cppulse scores it at 93.8/100 — reflecting strong memory safety (93.7), complexity (88.1), modernization (84.5).

---

## Health Score

<p>
  <img src="../../assets/protobuf/health-gauge.svg" alt="Health Score: 93.8/100" width="280" />
  <img src="../../assets/protobuf/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **93.7** | 229 | C-style array params (11), Raw `new` (1), explicit `delete` (1) |
| Complexity | **88.1** | 1,303 | long functions (18), high cyclomatic complexity (10), too many params (9) |
| Modernization | **84.5** | 61,812 | raw string literal (51), deprecated C headers (12), unscoped `enum` (12) |

**Total: 63,344 findings across 15 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `conformance/binary_json_conformance_suite.cc` | 56.5% | Medium | Memory issues (1), Complexity findings (14) |
| `conformance/conformance_test_runner.cc` | 31.8% | Medium | Memory issues (2), Complexity findings (3) |
| `conformance/conformance_test_main.cc` | 27.7% | Low | Memory issues (2), Complexity findings (1) |
| `conformance/conformance_test.cc` | 23.0% | Low | Memory issues (1), Complexity findings (4) |
| `conformance/text_format_conformance_suite.cc` | 20.3% | Low | Memory issues (1), Complexity findings (3) |
| `conformance/binary_json_conformance_suite.h` | 14.7% | Low | Memory issues (1), Complexity findings (1) |
| `conformance/conformance_test.h` | 14.3% | Low | Memory issues (1), Complexity findings (1) |
| `conformance/text_format_conformance_suite.h` | 14.3% | Low | Memory issues (1), Complexity findings (1) |
| `bazel/private/file_concat/main.cc` | 13.2% | Low | Memory issues (1) |
| `hpb/extension.h` | 13.0% | Low | Memory issues (1) |

**2 files** flagged Medium · **29 files** flagged Low risk (of 31 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `conformance/binary_json_conformance_suite.cc` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 42h | 12.0 |
| 2 | `conformance/binary_json_conformance_suite.cc` | Modernize C++ code: apply C++11/14/17 idioms and remove deprecated constructs | modernization | 24h | 8.0 |
| 3 | `conformance/binary_json_conformance_suite.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 4h | 8.0 |
| 4 | `conformance/conformance_test_runner.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 8h | 8.0 |
| 5 | `conformance/conformance_test_runner.cc` | Modernize C++ code: apply C++11/14/17 idioms and remove deprecated constructs | modernization | 6h | 8.0 |
| 6 | `conformance/conformance_test_runner.cc` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 9h | 8.0 |
| 7 | `bazel/private/file_concat/main.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 4h | 4.0 |
| 8 | `benchmarks/benchmark.cc` | Modernize C++ code: apply C++11/14/17 idioms and remove deprecated constructs | modernization | 8h | 4.0 |
| 9 | `conformance/test_manager_test.cc` | Modernize C++ code: apply C++11/14/17 idioms and remove deprecated constructs | modernization | 12h | 4.0 |
| 10 | `conformance/binary_json_conformance_suite.h` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 4h | 4.0 |

**Total: 38 roadmap items · ~259 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
