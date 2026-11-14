# Typed verification and local applicability contracts

These packaged version 2.0.0 contracts extend the local evidence foundation.
Schema validation checks supplied structure, arithmetic and references. The run
store checks retained bytes; versioned producers separately parse actual reports
and prove their supported tool relationships. These contracts do not authenticate
producers, establish complete dependency closure or certify a library. Actual
producer, host and installed integration gates remain separate recorded checks.

## Coverage

coverage_facts retains origin, producer, adapter, original report artifact,
selected source/job identity, proof receipt IDs, test evidence, object/mapping
pairs and runtime profiles. Per-file source hashes may be unknown for imports;
execution-derived usable facts require the selected hashes and actual proof.

Each measurement contains kind, versioned method, covered, total and explicit
unit-group identities with their own covered/total counts. Aggregates equal the
unit sums; identities are unique within a file/kind. Group counts allow a
Cobertura line's branch aggregate without inventing individual branch identities.
Other supported methods describe individual points with total one and covered
zero or one. Count arithmetic uses the JSON number representation exactly.

| Format | Measurement | Method |
| --- | --- | --- |
| LCOV | Line | lcov-da-v1 |
| LCOV | Branch | lcov-brda-v1 |
| LCOV | Function | lcov-fnda-v1 |
| Cobertura | Line | cobertura-lines-v1 |
| Cobertura | Branch | cobertura-condition-counts-v1 |

Cobertura method line rates do not establish function-entry coverage. Decision
and MC/DC are unsupported. Zero denominators remain zero counts, not success.
Imports remain producer claims. Usable execution coverage binds selected inputs
to a compiler object and mapping, the linked binary, selected actual CTest
execution and a newly created runtime profile consumed by the report producer.
Copied step inputs can have different artifact IDs only with identical checked
bytes and the existing workspace-path lineage. Accumulated preexisting counters
are unsupported by this first slice.

Existing orchestration requires successful generated-input ancestors. A failed
CTest process retains its raw results/profile, while its dependent report step
is skipped and coverage remains unavailable. No implicit failure-tolerant edge
or weakened ancestry is introduced. Test and coverage outcomes remain distinct.

## Sanitizers

sanitizer_facts names ASan, UBSan or TSan, requested files, the actual compiler
version/hash, compile/link/inspection receipts, object proofs, runtime linkage,
selected component gaps, actual exercised binary inputs and normalized test case
IDs. Diagnostic records identify their retained raw artifact and exercised case.

The first proof method is elf-relocations-v1 on selected Linux x86-64 ELF/GCC
inputs. Retained inspection output identifies emitted data/check callsite
relocations. Initialization-only symbols, command flags, compile databases,
runtime linkage alone and empty logs are insufficient. Runtime SONAME linkage
does not establish the loaded runtime's hash or authenticity. The producer must
declare unsupported stripped, LTO, wrapper and unreviewed format cases.

The linked binary's exact bytes must be the selected CTest input, with actual
command/case association already checked by collection. Clean outcomes require
nonzero executed tests and complete selected source/component proof. A credible
diagnostic may remain failed while another component is uninstrumented; the gap
stays visible and makes the policy failure incomplete. UBSan recovery/exit zero
cannot erase a diagnostic. Runtime startup failures remain operationally
unavailable, not clean. The proof covers selected emitted operations, not every
function, statement, template instantiation or runtime path.

Stdout-only version/inventory/inspection probes can have no material outputs.
The current executor still records available material after a successful empty
output collection. These probes require passed receipts, verified unchanged
bindings and complete retained logs; not_collected is not positive proof.

## External diagnostics

external_analysis_facts initially describes imported gcc-json adapter 1.0.0
diagnostics from GNU-G++ 14.2.0. The original report, option identity, source
location, nullable byte column, occurrence ID and producer version are retained.
The gcc namespace remains distinct from native rule IDs. Unsafe option strings
use a full SHA-256 identifier while preserving the original string. Repeated
occurrences are not collapsed. An empty report has unverified scan completeness;
it cannot establish clean analysis or silently satisfy native finding_limit.
This first adapter does not claim GCC analyzer support for C++.

## Distribution subjects and consumers

distribution_subject selects original source files and exact distributed
archive/header artifacts. A distribution-only local import has no asserted
upstream source inventory and retains that limitation. consumer_matrix declares
expected configurations, tests, selected instantiations and requested header
self-containment. Missing expected contexts remain declarations, not executions.

consumer_usage binds selected distribution inputs to a direct compiler/link
receipt and fresh depfile or GNU linker-map output. Actual configuration and
target probes use the same compiler bytes. The producer parses the bounded
supported formats and ordered flags; unknown ABI-affecting switches do not
silently disappear. A hash attached to an unrelated build, an include path or a
compile database alone does not establish actual package use. Header
self-containment requires an explicit selected minimal consumer proof. ABI
strings describe observed macro identity, not a general ABI compatibility proof.

consumer_comparison preserves separate local/upstream source and manifest
identities. Foreign manifests, subject and matrix remain original generic blobs
in a separate namespace; they are never inserted as another primary source in a
local run. Configuration-compatible describes only the selected known dimensions
and actual local usage. It can coexist with missing application tests or header
checks, which stay visible. Matching upstream headers or an archive does not
replace local integration tests or unrecorded instantiations.

Actual usage must belong to the matrix's selected subject; matching compiler
settings or coincidentally equal bytes from another subject cannot establish
that proof. A distribution mismatch explicitly identifies changed package kind,
logical paths or bytes through mismatches value distribution. That value is
separate from the configuration-only matching_dimensions; a package mismatch
does not invent a compiler or other configuration difference.

## Local transfer

transfer_bundle describes a directory payload, not an executable installer or
archive extractor. A bounded file inventory names separate roots under
roots/<label>/runs/<run-id>/. Raw manifests and artifact bytes remain unchanged.
Root manifest SHA and metadata size match the inventory. File count, per-file,
total payload and control JSON limits are explicit; unsafe paths, case aliases,
special files, symlinks, duplicate entries and publication pointers are refused.
The descriptor is excluded from its own payload hash inventory and is separately
bounded before parsing. The reader checks physical inventory, bytes and original
contracts without executing retained recipes or updating latest pointers.

The imported directory is an unauthenticated claim even when every byte matches.
SHA verification establishes local transfer integrity, never authorship or trust.
