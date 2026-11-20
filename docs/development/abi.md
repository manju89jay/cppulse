# Private ELF/DWARF ABI adapter

This is a bounded, local P12 / M9-03 evidence slice, not completion of the
API/ABI, fuzzing or dependency requirements. The supported producer is native
Linux `abidiff` **2.6.0** from libabigail, comparing ELF `ET_DYN` objects.
GNU readelf **2.44** is the explicitly pinned structural/DIE reader. Inputs need
in-file, uncompressed `.debug_info` and `.debug_abbrev`. The test matrix uses
GCC 14 shared libraries with actual DWARF. Other tool versions, separate debug
files, compressed debug sections, extended section numbering, other object
formats and operating systems remain unsupported.

The adapter independently checks embedded debug sections and runs
`readelf --debug-dump=info --debug-dump=abbrev --dwarf-check` on each input.
Any warning/error, missing actual level-zero compile-unit DIE in any info CU,
failure, timeout or truncated validation output prevents a complete comparison.
A tag present only in an unused abbreviation does not satisfy this check.
Partial/skeleton/type units remain unsupported until separately qualified. This also rejects the actual
review fixtures with zeroed `.debug_info`/`.debug_abbrev` bodies, null root
DIEs, and a valid CU hiding another null-root CU.

Embedded section presence alone is insufficient: libabigail's
`--fail-no-debug-info` can still return zero for a stripped file sharing the
other input's build ID. A missing-debug input therefore never becomes a clean
result through that shortcut.

## Explicit request and execution

`python -m cppulse.abi --request /absolute/request.json --output /new/output`
reads the private `abi_private/request.schema.json` contract. All tool and binary
paths must be absolute. A request has `version: "1.0.0"`, `tool` (`path`, exact
`sha256`, `version: "2.6.0"`, explicit `library_directory` or null), `reader`
(`path`, exact `sha256`, `version: "2.44"`), `limits`
(`input_bytes`, `wall_seconds`, `log_bytes`) and one to 32 `pairs`, each with a
unique safe `id` and `old`/`new` objects containing `path` and `sha256`.

The new output directory is exclusive: existing output is never overwritten.
Input binaries and the pinned tool are copied there; optional local runtime
libraries are copied and hashed into a private directory. The environment is
minimal, with a private HOME and no inherited preload/suppression configuration.
Arguments are passed directly without a shell. The analyzed libraries are never
executed. `abidiff` runs with `--no-default-suppression --fail-no-debug-info`.

Each input is bounded at at most 512 MiB, aggregate staged input is capped at
512 MiB, each tool at 64 MiB, and explicit local libraries at 512 MiB / 1,024 names.
Each comparison shares one finite wall deadline (at most 3,600 seconds) and
combined stdout/stderr cap (at most 8 MiB) across both DWARF validations and
abidiff. Each tool version preflight has a separate five-second, 4 KiB limit. Exceeding wall/log limits kills the subprocess group and records an
unusable result. Original input, tool, reader and explicit library hashes are
rechecked before publication; changed inputs prevent publication of any positive report.
Preparation failures retain the new directory's staged evidence but do not emit
`report.json`. Captured text is decoded as UTF-8 with replacement and capped
again after decoding; its digest binds the stored text, not unretained bytes.

CPU and address-space limits are **not enforced**. This adapter is not a security
sandbox: the explicitly selected native tool runs with the invoking user's
permissions. System loader and implicit runtime dependencies are not fully
inventoried. Input integrity and tool version claims do not authenticate the
producer. There is no compiler-receipt lineage, so source binding is always
`unverified`.

## Results and exit semantics

The report retains binary hashes/sizes, tool/reader/local-library hashes, producer
version, limits, exact return code, bounded log/digest and elapsed wall time.

| Tool result | Report status | Meaning |
| --- | --- | --- |
| 0, complete scoped execution | `no_changes_reported` | This producer found no changes in available exported ABI / DWARF scope |
| 4 | `changes_reported` | Changes reported; includes the tested indirect struct-layout break |
| 12 | `incompatible_changes_reported` | Producer also set its incompatible-change bit; tested exported-function removal |
| Missing/unsupported/malformed embedded DWARF, malformed ELF, tool errors | `unsupported` | No compatibility conclusion |
| Wall or log limit reached | `unusable` | No compatibility conclusion |

`no_changes_reported` is not universal compatibility certification, and exit 4
is not a claim that the change is compatible. A tested additive symbol returns
4, as does a tested indirect struct layout break. The raw producer distinction
is preserved instead of inventing a stronger compatibility classification.

The module exits 0 when every comparison has a complete producer result
(including differences); 3 when any is unsupported/unusable; and 2 for invalid
requests, stale inputs, unsupported tool version or preparation/publication
errors. A report's aggregate `reported` means only that its observations are
available. It never means “ABI safe”. Consumers that require “no changes” must
inspect every result, and must still retain the scope limitations.

`validate_report(report, expected_request=request)` anchors the request digest,
input/tool identities, comparison IDs and limits. Structural validation alone
cannot authenticate a report. The reader diagnostics and producer logs retain individual hashes; the combined
log budget covers both. Cancellation terminates/reaps the owned process group
before propagating, and caller mutation cannot change the frozen request.

No policy assessment, public CLI/API/report or
editor integration is claimed by this private module. API compatibility,
fuzzing, provenance/dependency evidence and the wider platform matrix remain
separate open work.
