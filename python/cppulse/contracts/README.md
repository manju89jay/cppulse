# Packaged contracts

The shared validators load local draft-07 schema resources with no network
retrieval. The primary analysis/evidence foundation uses version 2.0.0.
Original risk v1 and the unreleased prototype-v1 channel have separate explicit
readers; current producers are not silently promoted into a new contract.

Verification contracts additionally describe distinct coverage counts, emitted
sanitizer instrumentation and runtime/test bindings, namespaced imported compiler
diagnostics, selected distributed library bytes, consumer declarations/actual
use/applicability, and bounded local transfer directories. They use the existing
source/context/artifact identities without introducing another primary subject
into a run. A schema is not qualification of every producer or platform.

Policy evaluator_profile is absent for the original 1.0.0 behavior. Explicit
1.1.0 adds typed minimum_coverage and sanitizer_outcome parameters. Explicit
1.2.0 additionally evaluates numeric metric thresholds per file/job and current
scoped declared reviews. Reviews require exact required-artifact SHA-256 bindings
for a positive result; older review records without hashes remain readable and
evaluate unknown. Configured reviewer IDs are not authenticated identities.
Earlier profiles retain their original capability boundary. An assessment
identifies the same evaluator profile and links typed verification/metrics
through control fact_ids.

The public workflow boundary additionally uses collection_request,
workflow_result, check_result and assessment_lineage. Requests select finite
built-in normalizers and explicit recipe roles; validation runs no commands.
Results distinguish capture completion, policy failure, insufficient evidence,
invalid input and cancellation. Reassessment pins the original unassessed facts
base and selected parent instead of reusing an earlier gate. snapshot_view binds
one immutable presentation to original manifest/artifact bytes and exact numeric
display strings. New finding_baseline/finding_comparison/finding_suppressions and
their explicit request schemas leave original baseline v2 and native-1 archives
unchanged. Contract gates remain separate from public runtime acceptance.

## Native installation metadata

`native_install` deliberately has its own version 1.0.0 and is installation
metadata, not evidence of successful analysis or platform qualification.
`load_schema("native_install")` selects this version; `validate("native_install",
document)` validates structure and relative-path semantics.

The object contains `version`, `tool_version`, `target` (`platform`, `machine`,
optional `libc` and `libc_version`), `analyzer`, `resource_dir`, `library_dirs`,
`host_requirements`, and `limitations`. `analyzer_sha256` is optional; its absence
must not be described as verified binary integrity. Each host requirement has
`name`, `constraint` and `purpose` strings. Requirements are descriptive data,
not commands to run automatically.

Analyzer, resource and library paths are canonical forward-slash paths relative
to the installation prefix. Absolute paths, backslashes, dot aliases and parent
traversal are rejected. A directory may be `.` to name the prefix itself; an
analyzer executable may not. Physical file/symlink containment, target matching,
resource availability and optional binary digest checks belong to installed
runtime discovery/doctor, not this pure JSON validator. Declaring a target does
not prove that target was tested.

Native installation metadata does not change the source/context/artifact or
run-manifest v2 identity projections.
