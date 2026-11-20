# Private bounded JSON projection0.1

This is the next producer boundary for large native-report ingestion. Existing
`iter_json_array` and complete RunSnapshot semantics remain unchanged. A
projection is neither normalized evidence nor a full report-schema validation.

`iter_json_projection(binary_stream, selectors, *, expected_sha256,
expected_size, limits=ProjectionLimits())` yields immutable records followed by
exactly one completion marker after whole-document structure, finite JSON
numbers, original byte length, EOF and SHA pass. Every earlier record is
provisional. Consumers must retain a transaction and withhold publication until
the completion marker and their own schema/provenance/aggregate checks pass.
The caller owns and guards the stream/file identity; parsing authenticates no
producer and verifies no original source freshness.

Selectors are frozen `ProjectionSelector(name, path, mode, required=True)`
values. Names are unique ASCII identifiers, at most64characters. Paths are
tuples of1–32literal decoded nonempty object keys, each within the existing UTF8
key budget and without NUL. They are not expressions, filesystem paths, dotted
paths or wildcard syntax. Selected paths must be distinct and cannot overlap
through ancestor relationships. Shared ancestor objects are allowed. An existing
prefix must be an object; this version cannot select through an array.

`mode="array"` streams each element, preserving order, repeated occurrences and
number/string lexemes in compact UTF8 JSON. `mode="value"` yields exactly one
bounded encoded value, including scalar/null/object/array. A required absent path
fails; an optional absent path emits no record. A present array must actually be
an array, even when optional. Completion reports present selector names and
per-selector counts in declaration order, distinguishing absent from empty.

`ProjectionLimits.json_limits` is the exact existing JsonStreamLimits dataclass:
all input bytes, ignored arrays, depth, tokens and simultaneous keys retain their
finite caps. The global selected-record cap includes value records and all
selected array elements. Value captures add a separate max_value_bytes cap
(default64KiB, maximum32MiB). Array rows retain max_item_bytes, including each
ignored nested array element. Max selectors defaults to32 (hard maximum32);
combined UTF8 name/mode/path identity bytes default16KiB (hard maximum64KiB),
with fixed additional object/tuple overhead bounded by selector/path counts.
Budgets are exact integers; booleans, floats and subclasses are refused.

All keys, ignored content and numeric tokens are structurally checked. All
numbers also retain the existing eager native loader's finite-Python-JSON
acceptance boundary: an overflowing float or a number unsupported by its bounded
Python JSON decoder is rejected, even in ignored metadata. This strengthens the
generic structural parser without changing its separate0.1contract. The new
producer may reuse its frozen private parsing primitives; that dependency must
be source-bound and requalified when those primitives change.

Records carry selector name, zero-based ordinal (null for mode=value), raw bytes
and kind=record. The completion marker carries version, base stream version,
original SHA/size, present selectors and counts, kind=complete,
read_scope=structural_projection and explicit schema_verified=false,
source_verified=false, native_executed=false, analysis_cache_eligible=false.
Errors, read growth/truncation, budget exhaustion, missing required paths or
abandoned iteration produce no completion marker. Partial output is never a
successful projection.

For native metrics, a selector for metadata/analysis/native_metrics/files
captures one file item, including its nested tokens/functions/includes. Its
per-file cap must explicitly admit or refuse that size; this interface alone
does not stream individual nested token records through that file array.
Full normalization still needs all original binding/config/registry/source/SDK
checks, complete report-schema/summary semantics, disk-backed aggregate token
and duplication processing, failure isolation, typed export, measured-policy
consumers and installed/scale qualification. No acceptance criteria are reduced.

## Optional completed-object key audit

The producer accepts `object_audit(path, keys)` as an optional callable, checked
before input I/O. On completion of each selector-trie prefix object (including
the root and present empty objects), it receives the literal decoded key path
and an ordered tuple of every member name, including ignored members. Objects
inside selected captures retain their complete raw subtree and are not prefix
audits; wholly ignored nested objects are still structurally checked but are
not separately audited. Existing parser key/depth/token/byte caps remain in force.

This permits a native semantic consumer to reject unknown closed-object fields
and distinguish absent optional objects from present empty objects without
capturing the large metrics object. No new record or completion event type is
introduced. The callback may reject an object; its exception prevents completion
and therefore transactional publication. Callback data is provisional until the
same original EOF/size/SHA completion. A callback that retains metadata owns its
retention budget. Merely receiving keys does not verify the report schema, native
semantics, source freshness, execution or cache eligibility. Every existing
completion qualification flag remains false.
