# Selected-artifact derived result index (private0.1)

This is the contract stage for NFR-SCL-05, M2-05 and FR-UX-08. The transactional
producer, public paging and scale gates remain pending. A valid request alone
does not prove a feature works. The upstream bounded JSON producer is a separate
passing dependency before its consumer may start.

The request schema binds one exact run ID, original manifest SHA, selected
artifact ID/path/SHA/size, supported report dialect and finite construction/query
budgets. Paths are canonical relative UTF-8 identities, not shell commands.
Unknown fields, bool/integral-float budgets, invalid Unicode and path aliases
are rejected. The first dialect selects the top-level `findings` array in a
prototype native report. It preserves every row occurrence and original order.

`read_scope=selected_artifact_only` is mandatory. Such a view cannot be passed
as a fully verified RunSnapshot, claim all other run artifacts valid or grant
analysis/policy/cache acceptance. Parsing ignored metadata establishes structure,
not its semantic schema or execution provenance. Original report bytes remain
the authority; index records do not create new source/SDK verification.

The planned index uses SQLite with ordinal primary keys and category/file
indexes. Every selected row is validated before insertion. Data stays in one
transaction until complete JSON/EOF/SHA/size verification succeeds; interrupted,
malformed, overbudget or changed-source construction cannot expose rows. The
index and bounded receipt are opaque artifacts in a **separate** private RunStore
so existing atomic publication/recovery applies without moving analysis heads.
The derived manifest must disclose its operation and unverified/non-execution
scope; it must not invent an original source inventory.

The request digest includes all limits and supported index/parser versions.
Reuse checks exact original manifest/artifact pins and committed derived-artifact
bytes. It is a byte-derived query optimization, not native analysis reuse.
Changed/corrupt input or index material fails explicitly. No assessment,
dependency, runtime closure or native cache eligibility follows from reuse.

Queries use parameterized SQL, finite page/item/filter budgets, stable ordinal
ordering, a read-only connection and bounded SQLite caches. Selected original
artifact and derived database identities must remain checked through a query.
The complete response is withheld on drift. A later public adapter must retain
one run/manifest pin for the request and report the selected-artifact scope.
Full-run validation APIs keep their existing stronger guarantees.

Acceptance must include transactional rollback/no old-head movement, source and
index drift, corrupt schema/receipts, injected interruption, duplicate row
occurrences, exact category/file filters, unchanged original diagnostics, deep
and wide inputs, concurrent readers and builders, and measured1K/10K/100K tiers.
Original large artifacts and installed API/client checks remain required; small
fixtures or this contract cannot substitute for those checks.
