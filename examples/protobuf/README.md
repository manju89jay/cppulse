# cppulse Report: Protocol Buffers

> Analyzed 2026-06-14 · 362,823 LOC · 1,078 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

Protocol Buffers (protobuf) is Google's language-neutral, platform-neutral extensible mechanism for serializing structured data. Originally developed at Google to replace ad hoc XML formats, it is now the backbone of gRPC and countless internal Google systems, as well as a widely adopted standard across the industry.
cppulse scores it at 47.2/100 — reflecting strong memory safety (86.6), complexity (0.0), modernization (0.0).

---

## Health Score

<p>
  <img src="../../assets/protobuf/health-gauge.svg" alt="Health Score: 47.2/100" width="280" />
  <img src="../../assets/protobuf/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **86.6** | 243 | explicit `delete` (107), Raw `new` (82), C-style array params (54) |
| Complexity | **0.0** | 26,098 | long functions (24764), high cyclomatic complexity (809), too many params (525) |
| Modernization | **0.0** | 80,424 | C-style casts (50286), raw string literal (15298), NULL vs nullptr (6647) |

**Total: 106,765 findings across 15 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `src/google/protobuf/compiler/command_line_interface.cc` | 99.1% | Critical | Multiple minor findings |
| `python/google/protobuf/pyext/message.cc` | 99.0% | Critical | Multiple minor findings |
| `conformance/binary_json_conformance_suite.cc` | 99.0% | Critical | Multiple minor findings |
| `python/google/protobuf/pyext/descriptor.cc` | 99.0% | Critical | Multiple minor findings |
| `src/google/protobuf/compiler/cpp/helpers.cc` | 99.0% | Critical | Multiple minor findings |
| `src/google/protobuf/descriptor.h` | 99.0% | Critical | Multiple minor findings |
| `src/google/protobuf/generated_message_tctable_lite.cc` | 99.0% | Critical | Multiple minor findings |
| `src/google/protobuf/generated_message_reflection.cc` | 98.9% | Critical | Multiple minor findings |
| `src/google/protobuf/repeated_field_unittest.cc` | 98.9% | Critical | Multiple minor findings |
| `src/google/protobuf/map.h` | 98.9% | Critical | Multiple minor findings |

**207 files** flagged Critical · **159 files** flagged High · **140 files** flagged Medium · **984 files** flagged Low risk (of 1490 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `conformance/failure_list_trie_node_test.cc` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 2 | `src/google/protobuf/varint_shuffle.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 3 | `src/google/protobuf/unredacted_debug_format_for_test.cc` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 4 | `src/google/protobuf/compiler/cpp/tracker.cc` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 5 | `src/google/protobuf/json/internal/parser_traits.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 6 | `upb/mini_descriptor/link.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 7 | `upb/io/tokenizer.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 8 | `upb/reflection/message.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 9 | `upb_generator/minitable/names.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 10 | `conformance/failure_list_trie_node.cc` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |

**Total: 1175 roadmap items · ~162370 estimated hours**

## Downloads

- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
