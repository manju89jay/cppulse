# Explicit indexed MCP findings consumer

The default MCP server remains read-only with its existing tool set. When the
operator explicitly supplies `--query-cache /outside/source/store`, tools/list
also advertises `indexed_findings`. Loading, initialization and listing tools
must not create that cache. Calling this tool may create/reuse only the declared
derived query cache. It cannot publish into or move heads in the original store,
execute a project or evaluate policy. A cache inside the source store is refused.

Arguments are a closed object: canonical `run_id` and `manifest_sha256` are
required; `artifact_id` defaults to `findings`; page defaults to1, per_page to50
(maximum100); optional category, exact file and literal message text filters
are each at most4096UTF-8bytes without NUL. Page arithmetic must fit signed64bit.
The caller never selects an arbitrary cache filesystem path through a tool.
The tool's configured private limits default to the producer's standard profile;
`--query-limits` accepts a complete JSON limits object (at most4096bytes) for an
explicit supported larger profile. Duplicate/nonfinite/malformed config refuses.

Only completed original attempts may be queried, using exact explicit pins.
Metadata, selected report bytes/structure/finding semantics and separate derived
index are checked; unrelated original artifacts remain unchecked. Results carry
source/index pins, selected-artifact scope, false analysis-cache eligibility,
historical-pinned/current_source_verified=false labels and limitations.
Invalid arguments refuse before any cache action. No partial page is success.
The512KiB framed MCP response budget still applies; the tool supplies a smaller
page byte budget before serialization and returns a bounded error if necessary.

Existing normalized-observation `findings`, health and assessment tools retain
their distinct semantics and32MiB whole-snapshot preview budget. This new tool
explicitly supports the private prototype findings dialect only. It does not
claim normalized-observation/history indexes, source freshness, native reuse,
aggregate cache management, hard deadlines, all clients/platforms or P14.
