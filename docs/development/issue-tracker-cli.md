# Explicit issue collection CLI

`python -m cppulse.issue_tracker_cli --request request.json --output new-output`
wraps the reviewed public read-only GitHub observer. The output must be new.
The shared `cppulse issues` entry is a separate integration step; this module
supplies its argument boundary. Full M8-04 / P10 acceptance remains open.

The request follows `issues_private/request.schema.json`: an explicit public
`owner/repository`, creation window, finite page/body/wall limits and optional
caller-declared cost inputs. No account/token or tracker-write options exist.
The selected provider is GitHub REST `2022-11-28`. The reviewed leaf producer
performs all issue projection and financial arithmetic; the wrapper adds no
financial inference or approval.

Before creating output or contacting a provider, the CLI reads at most 128 KiB
from one regular UTF-8 file. It rejects symlinks in the file or ancestors,
FIFOs, traversal, duplicate fields, nonfinite/overflowing numbers, deep malformed
JSON and schema/semantic errors. Input and output paths may be relative to the
invocation directory. This no-follow storage boundary is qualified on POSIX;
other platforms fail explicitly before collection.

Output ancestors are opened without following symlinks. The final directory is
created exclusively and privately, and its identity is retained on an open
handle and checked before collection/publication. Existing output and all its
bytes are preserved. Files are written exclusively; partial artifacts are never
cleaned up or overwritten. These checks do not make the filesystem owner or
selected native/runtime environment an authenticated producer or security
sandbox.

The new invocation retains:

- `request.original.json`: the exact original input bytes, including whitespace.
- `observations/`: the leaf producer's canonical request, bounded raw pages and
  validated report when collection reaches report publication.
- `diagnostics.txt`: bounded diagnostics for failed or cancelled invocations.
- `outcome.json`: status, exit code, original/canonical request digests and a
  bounded byte/hash inventory of retained artifacts. The report file must match
  the validated in-memory projection, and page hashes must match the report.

The JSON stdout record supplies the selected `outcome` path and its SHA256.
Consumers should use that selected path and check the process exit status. A
cancellation after an outcome was already written preserves that file and
selects `outcome.cancelled.json`; any completed underlying observations remain
available. Cancellation during finalization marks the artifact inventory
incomplete instead of inventing a verified inventory. Disk/permission failure
can prevent writing an outcome; stdout then records failure and the retained
output path. Inspect those files and use a fresh directory for a retry.

| Exit | Meaning |
| --- | --- |
| 0 | Complete selected collection, validated retained projection and artifact inventory |
| 3 | Partial or unavailable provider scope; total remains unknown |
| 2 | Invalid request/path, refused existing output, collection or artifact/publication failure |
| 130 | Cancelled; created request/raw/diagnostic artifacts remain available |

Zero means only complete collection in this provider/request scope. A partial
page budget, rate limit or malformed response never becomes zero known issues.
Financial rows retain the leaf method, estimated/observed caller basis and
currency separation. Missing inputs retain unknown ROI; reported inputs and
hashes do not establish financial authentication or causal savings.

The wrapper inventories only its finite known artifact namespace. Raw pages
respect each request's page-byte bound; canonical requests respect 128 KiB;
normalized reports have a 32 MiB wrapper read bound; diagnostics have a 16 KiB
bound. Hashing streams in 64 KiB blocks. No CPU/address-space enforcement or
platform/provider/account matrix is inferred from these byte limits.
