# Native metrics resume checkpoint

Frozen immediately on root stop request. No commits, pushes, refs, GitHub writes or publication. Known foreground sessions 16685 (build), 81174 (rebuild/test), and 57955 (CTest/sample) completed before freeze; no owned process remains running.

## Changed files

- New `analyzer-core/src/metrics.h`, `metrics.cpp`: live TU source buffer SHA-256, physical/code LOC, source-spelled bounded token inventory, function definitions with USR/fallback/location/length/semantic CC/nesting/parameters, actual resolved inclusion callback edges.
- `analyzer-core/src/analysis_coverage.h`: per-file optional JSON measurements and effective max token records.
- `analyzer-core/src/analyzer.cpp`: include metrics, remove fresh-filesystem LOC helper; extract from live TU in analyze_file; RAII clang index/TU cleanup; legacy total_loc integer currently saturates. Scale agent independently owns constructor/run selection and inserted max_token_records run initialization.
- `analyzer-core/src/config.h`, `config.cpp`: native max_token_records default100000, strict integer positive <=INT64MAX.
- `analyzer-core/src/output_writer.cpp`: additive metadata.analysis.native_metrics serialization.
- `analyzer-core/src/rules/complexity/cyclomatic_complexity.h/.cpp`: public measure_cyclomatic_complexity shared with detector; lambda own body measured separately.
- New `analyzer-core/tests/test_native_metrics.cpp`: child owner added20 actual-source tests. Child stopped on request; any final delta is in child response.

## Executed checks and retained proof

- `source review/environment.sh; pytest -q tests/test_maintenance_metrics_contract.py` ->64 passed (current contract gate before extraction edits).
- Child baseline16 runtime tests failed meaningfully before producer/writer existed: `review/production-20261114/p3-native-resume/native-metrics-tests-red.log`.
- Isolated `cmake -S analyzer-core -B analyzer-core/build-p3-native-resume -DBUILD_TESTING=ON` and `cmake --build analyzer-core/build-p3-native-resume -j2` succeeded; logs configure.log/build.log.
- Initial producer runtime17/20 failed JSON array initializer issue; retained native-metrics-tests-initial.log. Fixed functions/edges member initializers to assignment initialization, rebuilt (build-after-initial.log).
- `analyzer-core/build-p3-native-resume/cppulse-analyzer-tests --gtest_filter=NativeMetricsFixture.*` ->20 passed, native-metrics-tests-initial2.log. Nine proposed handcounts, lambda capture/body, USR overloads, SHA byte changes, bounds/defaults, includes, skipped/excluded, multiline literal measured.
- `ctest --test-dir analyzer-core/build-p3-native-resume --output-on-failure` ->139/139 passed, ctest-green.log. Includes concurrently added scale native tests.
- Follow-on retained actual report/schema validation script did NOT execute native sampling: Python import failed at `from cppulse.contracts import validate` with ModuleNotFoundError before fixture creation or subprocess. Need `PYTHONPATH=python` for plain python invocation (pytest adds path). No raw observed-output report exists from that command; no producer gate communicated as fully schema-validated.

## Current correctness issues / remaining work

1. Independent reviewer found CR-only source `int value() {\r    return 1;\r}\r` parses cleanly but physical_loc1/code_loc1 complete=true while function_length3/token coordinates cover3 lines. metrics.cpp counts only LF; fix physical-line counting aligned with clang CR/LF/CRLF (check LFCR pairing too). No fix implemented before freeze. Child was asked to add/capture CR regressions, then immediately stopped by root; inspect child final and file before resuming.
2. Actual clang_getInclusions callback records resolved includes only; unresolved missing.hpp produces no unresolved edge yet. Plan add actual InclusionDirective main-file traversal with clang_getIncludedFile null and spelling, rather than inventing a resolved path.
3. Legacy total_loc is int and currently saturates; per-file raw actual LOC remains uint64. Consider widening public total_loc/writer types instead of saturation before large-run acceptance.
4. No full raw native report/schema+semantic validation executed yet, despite20 native tests green. Perform with current source and ensure source SHA optional fields accepted.
5. SHA implementation standard SHA256 verified against two independent Python hashlib fixture digests; additional boundary-length known vectors useful before acceptance (not yet executed). Empty buffer handling uses actual TU file handle; no fresh filesystem read.
6. Token retention cap does not cap libclang tokenization memory: full CXToken array exists during extraction; visible records bounded and observed total retained. Resource qualification remains scale owner work.
7. No README/DECISIONS edits by this owner. Definitions/method choices need root documentation review. All118requirements/60tasks/9obligations remain open scope;139 checks do not mean production acceptance.

## Agreed contracts and coordination

- `metadata.analysis.native_metrics`, version1.0.0, metric_version cppulse-metrics-1, max_token_records declared globally and each stream record_limit.
- Partial parse retains lexical LOC/function facts availability partial; measurement_complete=false, function_count=null. Skipped/excluded/failed unavailable cells null, arrays empty and reasons.
- Token truncation complete=false/availability partial, total_tokens actual observed, retained_tokens and records bounded, explicit reason; AST completeness remains separate.
- Function source extent inclusive lines, template prefix retained; semantic CC shares corrected helper. Lambda body separate; capture initializers attributed to enclosing scope. Else-if nested method.
- identity_kind usr or source-location-fallback. Raw functions kind enum current schema accepted values.
- Python metrics agent /root/python_metrics_resume added optional native source_content_sha256 string64lowerhex|null to both raw schemas; normalizer must bind observed hash to frozen source manifest and preserve partial unavailability.
- Python normalizer/scorer consumer implementation was waiting for full native gate; notified20 native tests green, NOT final full gate. Planned duplication algorithm separate version cppulse-exact-duplicates-30-v1 exact kind+spelling windows >=30tokens; native token inventory itself claims no duplication.

## Resume commands / environment

```
cd /workspace/scratch/b3d4e6fff494/cppulse
source review/environment.sh
export PYTHONPATH=python
cmake --build analyzer-core/build-p3-native-resume -j2
analyzer-core/build-p3-native-resume/cppulse-analyzer-tests --gtest_filter=NativeMetricsFixture.*
ctest --test-dir analyzer-core/build-p3-native-resume --output-on-failure
pytest -q tests/test_maintenance_metrics_contract.py
```

Environment uses toolchain `/workspace/scratch/b3d4e6fff494/toolchain/usr`, libclang actual19.1.7 under lib/llvm-19; LD_LIBRARY_PATH toolchain/usr/lib/x86_64-linux-gnu. Formatter `../git-checkpoint-20261114/format-tool/clang_format/data/bin/clang-format`. Existing CMake glob picks metrics.cpp/test file automatically. Avoid canonical build dir race. No handoff hashes newly captured after stop.
