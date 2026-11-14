# Attributed external compiler diagnostics

The first external adapter imports the GNU G++ 14.2.0 JSON diagnostic format.
It is a compiler-diagnostic importer, not a new complete C++ analysis engine.
`gcc-json` adapter 1.0.0 supports located errors, warnings and child notes from
one translation-unit array. The official format reference is
[GCC 14.2 diagnostic formatting](https://gcc.gnu.org/onlinedocs/gcc-14.2.0/gcc/Diagnostic-Message-Formatting-Options.html).

`parse_gcc_json(content, source_root=..., scope_files=..., producer=...)` reads
only supplied bytes and metadata. Explicit supported producer metadata is
required for availability; omission remains unavailable rather than inventing
a version. Invalid JSON/UTF-8, ambiguous duplicate fields, nonfinite values and
unsupported record shapes never become a zero-result claim. Unlocated records
remain in the raw report and make normalization unavailable instead of acquiring
an invented source location.

Limits: 10 MiB raw JSON, 100,000 JSON nodes, depth 64 and 10,000 diagnostic
occurrences. File mapping is lexical POSIX root-relative mapping to explicit
scope; no basename matching, live project reads, commands or network are used.
Columns use positive one-based GCC byte-column values; a missing byte column
stays null rather than copying a display-column value. The actual demo selects
byte units and origin one explicitly.

## Checked local import

`normalize_gcc_import(snapshot, report_artifact_id=..., context_id=...,
source_root=..., scope_files=..., producer=...)` consumes integrity-checked raw
artifacts. Every supported occurrence receives a distinct ID. Original rule
options remain intact, with a separate `gcc:` namespace; unusual rule strings
use a full-hash suffix without losing the original. Native findings and counts
are not deduplicated or merged with these imports. Matching co-location is not
independent confirmation.

All external facts have origin `import` and scope completeness `unverified`,
even when the report was collected by an actual local compiler command. A valid
empty array is parseable but never establishes a completed clean scan. Producer,
version and source-root correspondence remain imported claims. Fingerprints are
versioned by this adapter and include source position; they do not claim S7's
line-shift baseline semantics.

`persist_gcc_import(snapshot, workspace=..., store=..., **selection)` publishes a
new immutable derived snapshot, preserving original bytes, IDs, config digest
and source identity. It rechecks selected local inputs, including idempotent
reads and final publication. Readable derivation metadata retains original
manifest identity and the supplied producer/root/scope mapping. It refuses to
reuse an old assessment as the assessment of new facts; import into an
unassessed collection, then assess the derived run. Malformed/unavailable imports
publish partial attempts while retaining the last completed snapshot.
Foreign transfer reports can be normalized read-only with their import label;
current-source publication requires a local `RunSnapshot`. Matching local files
does not turn an imported wrapper into a local execution record.

## Actual demonstration

After the recorded tool setup:

```sh
source review/environment.sh
PYTHONPATH=python python scripts/demo_gcc_diagnostics.py
```

The explicitly synthetic source selects a warning, a clean report or an
intentional missing-name error through compiler macros. Commands use argv and
the shared bounded collector; a separate clean consumer is actually built.
No executable is run. Actual reports contain one warning, zero diagnostics and
one error respectively. The error process fails and remains recorded as failed.
Each report is then imported with its own raw bytes and unverified completeness.
Results, original/derived manifest hashes and limitations are retained under
`output/gcc-diagnostics-demo/`; source never gains simulated Git history.

Focused parser/import regressions include repeated occurrences, unsupported
versions/locations, corruption, source races, parent config preservation,
idempotence and assessed-parent refusal. Their passing result does not qualify
other compiler releases, operating systems or a complete external scan.
