# Native producer verification, 16 November 2026

Checkout: `/workspace/cppulse`, branch `codex/cppulse-local-core-20261114`,
base HEAD `6f8b662a89b367f8c6883298dc97950150d7ba4f`. Initially clean; remote
branch matched; implementation checkpoint `79665c4` is an ancestor. No commit
or push was made. Source and dependency hashes are in `source-dependencies.json`.

The first configure command (`cmake -S analyzer-core -B
analyzer-core/build-cloud-resume -DBUILD_TESTING=ON`) failed because CMake was
absent. The Cloud package helper was absent too. Dependencies were downloaded
and extracted locally into `work/native-deps`; CMake 4.4.5 and clang-format
19.1.7 were installed under `work/native-tools` and `work/native-format`.
System directories were not changed. Actual GCC is 14.2.0 and system libclang
is Debian 19.1.7. Headers/resources are LLVM 19.1.7. Local Debian versions and
archive hashes are retained in the dependency record. Earlier exploratory
extractions of older development archives were superseded by the versions
used in the build: spdlog 1.15.2, fmt 10.1.1, GTest 1.16.0, CLI11 2.4.1,
nlohmann/json 3.11.2.

## Reproduction

From the checkout root:

```sh
PYTHONPATH=work/native-tools work/native-tools/bin/cmake \
  -S analyzer-core -B analyzer-core/build-cloud-resume \
  -DCMAKE_PREFIX_PATH="$PWD/work/native-deps/usr" \
  -DLIBCLANG_INCLUDE_DIR="$PWD/work/native-deps/usr/lib/llvm-19/include" \
  -DLIBCLANG_LIBRARY=/usr/lib/llvm-19/lib/libclang-19.so.1 \
  -DBUILD_TESTING=ON
PYTHONPATH=work/native-tools work/native-tools/bin/cmake \
  --build analyzer-core/build-cloud-resume -j2
PYTHONPATH=work/native-tools work/native-tools/bin/ctest \
  --test-dir analyzer-core/build-cloud-resume --output-on-failure
PYTHONPATH=python python3 docs/checkpoints/20261116/native/verify_actual_metrics.py \
  --analyzer analyzer-core/build-cloud-resume/cppulse-analyzer \
  --resource-dir work/native-deps/usr/lib/llvm-19/lib/clang/19 \
  --output work/native-validation
```

Original 139 tests passed (`baseline-ctest.log`, 17.61 seconds). Three new
regressions failed before the fix (`red-regressions.log`). The first fix assumed
LFCR pairs like CRLF; actual callable/token coordinates disproved that assumption
(`intermediate-lfcr-ctest.log`). Corrected tests retain the actual LLVM behavior:
CR and LF terminate lines, CRLF pairs, LFCR is two terminators. Adjacent LFCR
repetitions can form an intervening CRLF (`\n\r\n\r` is three terminators).
The final suite has 142 CTests, including all original tests; see
`final-ctest.log` for the exact final count/result. Formatting only touched
changed regions, followed by rebuilding and re-running all checks.

`verify_actual_metrics.py` launches the executable and validates eleven actual
reports with `cppulse.contracts.validate(..., version='prototype_v1')` plus
independent totals, LOC/code LOC, callable metrics, token bounds, SHA-256,
clean/trigger findings, unresolved include, partial and truncation assertions.
Reports and process logs are under `work/native-validation`; `verification.json`
records output hashes. This closes the old failure to execute raw-output
schema validation, for these tested inputs only.

## Changed behavior and remaining scope

- Physical LOC counts CR correctly and agrees with Clang source coordinates;
  this also fixes clipped code LOC and legacy aggregate totals for CR files.
- Unresolved direct and transitive inclusion directives retain their spelling,
  source and unresolved status; no resolved path/content identity is invented.
- Existing include callback behavior remains intact for resolved edges.

This is a verified producer slice, not closure of P3/M4 or production acceptance.
Legacy aggregate `total_loc` still uses saturated `int`; raw per-file counts are
64-bit. Native tokenization still materializes the full libclang token array,
although retained records are bounded. Include edges do not establish dependency
closure/content identity. Full six-project corpus, every toolchain/platform,
scale budgets, packaged release qualification and licensed standards review
remain outside this native slice.

Independent consumer review identified duplicate observation counting, missing
observation documents being treated as clean, exclusive token-end line handling,
and trend compatibility omitting parse-context identities. These were sent to
the measured-consumer owner for regressions and fixes; consumer check results
must be recorded separately from native results.

## libclang capability follow-up

A fresh container build independently found that LLVM 18 lacks the binary-opcode
API used by semantic complexity measurements. `analyzer-core/CMakeLists.txt` now
compiles **and links** a small `clang_Cursor_getBinaryOpcode`/`CX_BO_LAnd` probe
before other dependencies/build steps. It rechecks when a caller changes the
headers/library pair in an existing build directory and emits actionable paths
and matching LLVM 19+ guidance on failure. `LibclangCapability.RejectsMissingBinaryOpcode`
configures against a deliberately pre-API header and asserts the diagnostic.
The actual LLVM 19 pair passes configure and the resulting **143/143 CTests
pass**, 64.76 seconds (`capability-{configure,build,ctest}.log`). The container
owner separately owns Docker package changes and container results.

## Original six-project corpus checkpoint

The old `scripts/showcase_projects.json` was unpinned and depth-one. A new
versioned lock (`demo/six-corpus-lock.json`) and Draft-07 schema freeze the six
original identities and actual immutable commit IDs before execution. The
runner `scripts/run_six_corpus.py` rejects substitutions, moving pins, duplicate
identities, dirty sources, unexpected revisions and insufficient retained
history. Its default selection is every tracked supported C++ path. An explicit
`--max-files` is labeled a lexically selected smoke sample, never full corpus
qualification. Sources are not edited or built in-place.

Eight tests cover lock failures, actual local Git cleanliness/revision/history,
and native-report source-hash/scope drift (`six-corpus-contract-green.log`). The
local Git test creates an isolated throwaway fixture commit only; it is not in
the cppulse Git repository or any remote. The collection-red checkpoint precedes
the new runner implementation. Black and Ruff pass on the new Python files.

Executed initial source-bound smoke:

```sh
PYTHONPATH=python .venv/bin/python scripts/run_six_corpus.py --fetch \
  --corpus work/six-corpus --output work/six-corpus-evidence \
  --analyzer analyzer-core/build-cloud-resume/cppulse-analyzer \
  --resource-dir work/native-deps/usr/lib/llvm-19/lib/clang/19 --max-files 10
```

All six actual reports passed schemas, native/source-buffer hashes, per-file
physical line counts, inventory selection, aggregate LOC and finding summary
checks. Every checkout retains **at least 100 real commits** and is explicitly shallow;
selected-file history is saved separately. fmt's ten selected files parsed
completely. All ten selected files in each of grpc/json/leveldb/poco/protobuf
were partial under the declared fallback C++17 context. This is a useful
counterexample to any claim that schemas establish configuration completeness.

Compact retained evidence, exact pins, counts, output hashes, script hashes and
limitations: `six-corpus-verification.json`. Native reports, command transcripts,
finite selections and selected real history: `work/six-corpus-evidence/`.
Actual sources: `work/six-corpus/`. Supplementary utfcpp is not substituted.
Full original-corpus build/test/accuracy/resource/context qualification remains
open; this checkpoint explicitly records a ten-file smoke selection and
bounded real history, not completion of that obligation.


The subsequent default full-selection LevelDB run verified all **131 tracked C++
files**: 13 analyzed, 118 partial, 28,280 physical LOC, 1,196 findings and 522
unresolved include edges. Exact actual counts/hashes are in
`leveldb-full-verification.json`; raw report (39 MiB) and logs are under
`work/six-corpus-full-leveldb`. The 62.58-second observation is an elapsed run
measurement on this concurrent Cloud host, not a comparative performance budget.
The retained history is 279 commits; `--depth 100` is a graph-depth bound and can
retain more than 100 commits when histories merge. Other recorded counts are
fmt 100, grpc 100, json 180, poco 100 and protobuf 126.

Full fmt default selection also passed the actual-report gates for all **67
tracked C++ files**, with 16 analyzed and 51 partial. Compact facts and exact
artifact hash are in `fmt-full-verification.json`; the 87 MiB native report and
logs remain under `work/six-corpus-full-fmt`. The declared context is fallback,
not an observed upstream build; incomplete parses remain visible. Full native
runs for the remaining four originals were then launched independently against
the same clean pinned sources, retaining separate evidence directories.

After the measured-consumer owner addressed the review findings, an independent
run of normalization, maintenance, duplication and trend tests passed **43/43**
in 9.36 seconds. Source hashes and bounded review scope are in
`independent-measured-review.json`; the actual raw-to-typed publication gate is
owned/reported separately by that consumer track.

## Latest exclusive-staging gate

The fresh `build-cloud-final` gate passes147/147 CTests and11 actual raw report
checks, including preexisting staging symlink/directory preservation. See
`staging-final-source-evidence.json`, `staging-final-ctest.log`,
`staging-actual-validation.log` and the updated independent streaming review.
Earlier142/143/146 counts above describe retained historical checkpoints.

## Configured original-corpus work in progress

`work/corpus-configured/` contains out-of-source upstream CMake builds; original
immutable source pins and at least100 real commits remain in `work/six-corpus/`.
Required dependency submodules are initialized only at their original gitlink
commits, with download/checkout transcripts retained. No cppulse commit, push
or remote mutation occurs. Actual compilation databases are retained unchanged
by the analyzer. Repeated target configurations are **not** equivalent to one
file being analyzed once; selected-file native reports do not qualify every
database entry or header-only consumer.

- fmt actual full test build and20/20 CTests pass. Its44 database entries cover
  28 unique source files. Bounded native analysis of those28 files is running.
- LevelDB original library andleveldbutil build pass. Its39 database files all
  parse completely; native schema/source hashes/LOC/totals pass, without unresolved
  includes or token truncation. `work/corpus-configured-evidence/leveldb/manifest.json`
  records exact commands/caps/native/database/report identities. Upstream tests
  are running separately. The initial test build fails in pinned googletest under
  GCC14 `-Werror=maybe-uninitialized`; that failure is retained. A separately
  recorded configuration uses `-Wno-error=maybe-uninitialized` while retaining
  the diagnostic and all tests. This configuration does not qualify the default
  warning-as-error configuration.
- JSON `test-algorithms_cpp11` builds andits2 CTests pass. The explicitly selected
  two-TU native pilot is2/2 analyzed, with no unresolved/truncated facts and passing
  schema/semantic gates. It does not cover all85 database entries/73 files or
  every declared language standard. `json-configured-verification.json` pins it.
- protobuf's initial configure fails for missing required googletest; after
  restoring pinned googletest/Abseil, actual full build is running.
- grpc's initial configure fails for missing pinned dependencies. After restore,
  its default BoringSSL build fails on GCC14 `_Generic` in C++ (log retained).
  A separate recorded supported configuration selects installed OpenSSL using
  `-DgRPC_SSL_PROVIDER=package`; its full build is running. The BoringSSL/GCC14
  failure remains open.
- Poco default configuration with `-DENABLE_TESTS=ON` succeeds; actual build is
  running under an1800-second wall budget. Unavailable optional platform/database
  dependencies remain explicit CMake observations, not tested configurations.

A source-first hand-count pilot freezes two LevelDB functions and rationales in
`leveldb-hand-count-protocol.json`; comparison matches all8 CC/nesting/parameter/
length checks in `leveldb-hand-count-comparison.json`, including two expanded
fall-through do-while macros. This pilot is not corpus-wide accuracy, precision
or recall. Source-bound rule accuracy sampling, unsupported syntax review, full
consumer/platform/dependency matrix and resource qualification remain open for
DESIGN-SIX-CORPUS, M4-02, M4-05, FR-ANA-02 andAC-08.

### Subsequent configured results

The fmt bounded native checkpoint completed:28/28 selected unique database files
analyzed,24,475 physical LOC,334 findings, no unresolved includes or truncated
tokens. Schema and source/hash/LOC/totals assertions pass in274.17seconds.
`fmt-configured-verification.json` also hashes the successful20-test upstream
logs. Its44 compilation-database entries remain broader than28 per-file parses.

LevelDB's explicitly recorded GCC14 warning-policy configuration now builds and
passes30/30 upstream CTests in249.54seconds. The original warning-as-error build
failure stays retained; this does not promote that failed configuration. Exact
configuration, commands, logs and database identities accompany the separate39-TU
native checkpoint in `leveldb-configured-verification.json`.

The JSON fixture in `consumer-fixtures/json/` is a supplemental real header-only
consumer of the pinned original JSON headers. Separate actual CMake/build/CTest
executions for C++11,14,17 and20 all pass. Each corresponding real native database
parse is complete, and all16 independently source-counted CC/nesting/parameter/
length assertions pass. `json-header-consumer-verification.json` records commands,
source/report/database/native hashes and observed arguments; source-first counts
are in `json-header-consumer-hand-count.json`. The four Linux/GCC14 contexts do
not qualify other toolchains/platforms, every JSON test or template instantiation.

An additional source-first fmt Linux `convert_rwcount` pilot matches all four
manual metric counts (`fmt-hand-count-{protocol,comparison}.json`). The source
protocol explicitly distinguishes its inactive Windows conditional branch.

The three additional configured original-source pilots now pass: grpc
`gpr_strdup`, protobuf `VersionString` andPoco's two-parameter `Environment::get`
are fully parsed using their actual generated compilation database arguments.
All12 source-first CC/nesting/parameter/length checks match; original selected
translation units were compiled into actual object files. The full upstream
builds remain in progress separately. `configured-three-hand-count-protocol.json`
freezes source hashes/counts/rationales; `configured-three-hand-count-comparison.json`
records exact commands, contexts, report/database/native hashes and comparisons.
This is three named pilot functions, not an accuracy estimate or full corpus pass.

## Current corpus-derived correction and parallel test gate

Actual source review of the retained fmt report disproved CPP-CX-002 results for
exported functions such as `GetWithoutMatchers`: the old rule mixed the visibility
attribute's spelling line1022 in an included header with function bodies near
line12848 in the main file. Valid JSON and matching totals did not detect these
false lengths. The90-row deterministic source-bound review queue under
`work/corpus-accuracy/frozen-queue.json` remains a pending review artifact anddoes
not establish accuracy. The older334-finding fmt report remains preserved.

`ExportMacroExtentMatchesMeasuredLengthAndFindingLocation` fails before the fix
for both a one-line exported function andan actual88-line exported function.
The corrected rule uses expansion coordinates, validates same-file andmonotonic
line bounds, andmatches the already-correct raw metric definition. The root
coordinator independently inspected this change andreported no material defect.
The affected28-file fmt configured native report is being rerun into a new
`work/corpus-configured-evidence/fmt-expanded-location/` directory; no older
artifact was overwritten.

A separate actual Release `ctest -j2` exposed cross-case contamination through
the old shared `/tmp/cppulse_coverage_test`. All native test fixtures/outputwriter
cases now exclusively create owned directories with process/clock/counter
identities. Existing paths are never removed to establish ownership, andall
original assertions remain. The old147 cases pass in parallel after this fix.

The current full native suite now has**148/148 passing CTests at-j2**,44.77seconds,
and11 actual raw report/schema/semantic checks pass. New regression red/build/
parallel/actual logs andentire native source inventory are retained in
`export-location-current-evidence.json` and`native-export-location-*.log`.
The coordinator's independent helper/rule inspection found no material defect.
Earlier139/142/143/146/147 counts andtheir binaries are historical checkpoints.
All acceptance gaps andthe complete production goal remain intact.

## Current TU include-buffer identities and coherence

An independent bounded-path review found a real restored-header counterexample:
BRANCH0 was frozen, actual libclang parsed BRANCH1, anddisk bytes returned to0
before global content checks. The actual native include inventory now carries
additive `content_identity` facts using `libclang-tu-buffer-sha256-v1`: explicit
available SHA-256/size from `clang_getFileContents(TU,includedFile)`, ornull and
unavailable. It never substitutes fresh filesystem reads. Per-TU file caching
avoids hashing the same included buffer repeatedly. Unresolved includes remain
explicitly unavailable. The optional schema field preserves readable legacy
path-only reports; absence cannot establish parsed dependency bytes. These facts
do not establish a complete dependency or compiler/runtime closure.

The meaningful restored-header regression fails before the producer fix and
passes after it:17-byte and131,089-byte headers retain the actual parsed hashes
after their disk bytes are restored; a genuinely empty buffer retains SHA-256
of empty bytes andsize0. Unresolved include identities remain null/unavailable.
The source/schema guard checkpoint now passes**149/149 CTests at-j2**,11 actual
native reports and74 Python native/metrics contract tests. The final149 suite
runs in55.50seconds. `include-buffer-current-evidence.json` records current
source/binary/log hashes andcommands; red artifacts remain alongside it.

Independent actual collect/normalize/persist controls now show: clean declared
header CC1 matches; transient declared header CC2 invalidates the actual input
binding; transient undeclared header CC2 remains unverified after normalization.
All three retain the same frozen source digest. A stronger actual Clang VFS
control retains honest equal before/after declared-file facts andverified raw
execution binding while the TU buffer differs: the normalizer marks its context
mismatched andits derived snapshot partial. Actual commands, original receipt/
manifest pins, source hashes andchecks are retained in
`../normalizer-coherence-independent-native-review.json`; no receipt/report/stat
facts were manufactured. The initial invalid harness plan is also preserved.

The macro-extent correction's28-file fmt rerun passes with311 findings instead
of334 at identical24,475LOC andanalyzed scope. The olderreport remains retained
as concrete red corpus evidence; no exclusions, suppression or scoring settings
were changed. This report used the preceding ac80052f detector binary. Current
include-buffer producer reruns forfmt andLevelDB are separate work in progress.

Protobuf's configured full upstream build now succeeds with its original pinned
dependencies, and2/2 CTest programs pass under3GiB address-space/600-second
per-process CPU limits. The programs contain98 and2,658 GoogleTest cases;
full-test reports6 internal conditional skips. These outcomes do not qualify
skipped/conformance/fuzz/other-configuration cases. Exact records are in
`protobuf-upstream-verification.json` and`protobuf-upstream-leaf-summaries.json`.
Poco's configured full build also succeeds after a preserved1800-second bounded
first-attempt timeout andincremental bounded resume. Its actual default16-suite
test run exposes environment/fixture failures; repair work retains those failures.
Grpc's bounded incremental OpenSSL build continues separately.

## gRPC actual upstream tests, current configured continuation

The pinned original gRPC source remains tracked-clean at
`f78a54c5ad4e058734aa9b2beb9459940e4de342`. Its previous complete OpenSSL build
had `gRPC_BUILD_TESTS=OFF`; that build did not establish upstream test acceptance.
The original generated cache and compilation database were copied unchanged to
`work/grpc-upstream-tests-20261116/` before enabling tests in the existing
out-of-source build. Required googletest and benchmark were restored at the
original gitlinks `2dd1c131950043a8ad5ab0d2dda0e0970596586a` and
`344117638c8ff7e239044fd0fa7085839fc03021`. Original sources, assertions and
parameter sets were not edited.

The tests-enabled OpenSSL configure passes. The original `time_util_test`,
`channel_arguments_test` and `byte_buffer_test` programs pass 8, 5 and 10 leaf
cases respectively. The original **unfiltered `end2end_test` passes all776
cases** in the explicitly declared final environment: inherited proxy variables
are removed from this test process and `MALLOC_ARENA_MAX=2` limits glibc virtual
arenas. Across these four original programs the selected configuration executes
799 passing leaf cases, with no skipped/disabled/error cases in their XML.
This includes actual SSL/insecure/in-process RPC, cancellation, reconnect,
streaming, proxy and resource-quota scenarios.

Failures remain retained. The first RPC invocation exits1 because the upstream
helper port server was absent. After starting that original helper, the full
inherited-proxy run reports771/776 passing, including four invalid-DNS channel
failures and one proxy RPC failure. Clearing only proxies passes775/776, leaving
one proxy RPC failure in a different parameter variant. A controlled same-binary
invalid-DNS case passes without proxies. The final full arena-limited run passes
776/776 under the **same3GiB per-process address-space and600-second soft CPU
limits**, rather than raising limits or changing assertions. Actual `/proc`
observations show cumulative VmPeak613,660KiB for the final process, versus
3,046,108KiB in the earlier process; the final sampled VmHWM is31,908KiB.
This supports allocator-pressure attribution but does not establish an exclusive
cause or universal reliability for the intermittent earlier proxy RPC failure.
Limits are per process; no cgroup aggregate isolation or performance budget is
claimed. Only the exclusively owned test-helper process was stopped and reaped;
other task services were preserved.

Exact commands, exit statuses, source/binary/database/runtime hashes, original
and final XML/log hashes, failure IDs, process limits, dependency pins and all
514 original upstream metadata entries are in
[grpc-upstream-evidence/verification-current.json](grpc-upstream-evidence/verification-current.json)
and its neighboring compact records. Complete raw proofs are retained in
`work/grpc-upstream-tests-20261116/` and the independently hash-checked regular-file
archive described by
[grpc-upstream-proof-export.json](grpc-upstream-proof-export.json). No fixture Git
objects or refs are included. The upstream CMake creates **no CTest registrations**;
test inventory comes from its pinned `tools/run_tests/generated/tests.json`.
512 test targets are generated. Four executed programs do not complete that
suite or its provider/platform/sanitizer/configuration matrix.

The protobuf six internal skips are also traced to pinned source conditions:
one Arena case needs an actual ASan-instrumented lane; five varint32 parameter
lengths above five bytes are explicitly marked N/A by upstream. Skips remain
visible and unchanged. A genuine ASan build remains outstanding; merely defining
the feature macro on uninstrumented libraries would not satisfy it.

`DESIGN-SIX-CORPUS`, AC-15 and P3/P9/P14 remain incomplete. This continuation
adds real upstream evidence, not native metric accuracy, complete original-corpus
qualification or production completion. Shared disk reached3.9GiB free during
concurrent work and recovered above4GiB; no sources, dependencies, logs, artifacts
or generated objects were deleted by this corpus track. Larger full-suite and
ASan builds require a preserved, verified space-recovery plan before execution.
