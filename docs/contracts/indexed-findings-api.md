# Manifest-bound indexed findings HTTP contract

`GET /api/v1/findings` retains its page/per_page/category response fields and
legacy flat-file compatibility. Stored runs use a private, transactional SQLite
query index instead of parsing the whole findings report or opening every run
artifact. `file` is an exact path filter; `text` is a literal message substring.
Rows retain their original order and duplicate occurrences. Page size is at most
200, filters at most 4096 UTF-8 bytes, and the serialized page at most 4 MiB.

Authentication precedes store inspection and cache creation. An explicit
`run_id`/`manifest_sha256` must be a complete canonical pair. Otherwise one
checked latest-attempt head is selected (v3 atomic heads or legacy v2 pointer).
Incomplete attempts return 409 before index creation; a broken or unsupported
store returns 503 and cannot fall back to flat exports. A request stays bound to
its selected manifest even if the current head changes. Malformed pins/filters
return 422. Invalid configuration, source/cache corruption or exhausted index
budgets return 503 with no successful partial page.

The response adds original source pins/status/input-verification claim, derived
index pins, limitations, `read_scope=selected_artifact_only`, and
`analysis_cache_eligible=false`. Only selected report bytes, whole JSON structure
and finding item semantics are checked. Other artifact bytes and ignored
metadata semantics remain unverified. No RunSnapshot represents unchecked
original artifacts; the derived index has its own verified RunSnapshot. Query
reuse never means native analysis reuse or verified original source freshness.

The first stored-run request may construct the index within the private request
contract's finite budgets. The cache defaults to `DATA_DIR/.query-index`;
operators may choose a separate writable `CPPULSE_FINDINGS_CACHE_DIR` when the
source store is read-only. `CPPULSE_FINDINGS_INDEX_LIMITS`, when set, is a complete
JSON limits object under the private request schema, at most 4096 UTF-8 bytes.
It replaces defaults; it does not relax schema maxima. The supported larger
ignored-array-element profile explicitly sets `max_item_bytes=33554432`; it must
also specify max_index_bytes, max_rows, sqlite_cache_kib and wall_seconds.
Cache contention refuses instead of returning an unfinished index. Wall checks
are cooperative; general store verification/fsync has no deadline callback.
Whole-process hard deadlines, aggregate retained-cache eviction, full Git
history indexing, all scale tiers and installed/client agreement remain separate
acceptance work. Flat legacy files retain their existing in-memory behavior and
do not acquire manifest/source verification through this endpoint.
