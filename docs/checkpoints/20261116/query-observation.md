# Finite descriptive filesystem/process query observations

M2-03/P5 remains open; production public units still run fresh. This module is a
prerequisite for understanding observed inputs, never a cache-eligibility switch.
Its private request/report contracts enforce `closure: unqualified` and
`cache_eligible: false`. No warm-cache command or fabricated native receipt was
introduced.

`query_observation.collect_query_observation` requires explicit selected-tool
execution, a new owned output directory, exact analyzer/tracer byte pins, the
supported strace6.13 version, an explicit environment without inheritance, and
finite wall/trace/stdout/line/event/process-observation bounds. Selected native
and tracer executable bytes run through held sealed Linux memfds. Runtime loader
and shared-library bytes remain unverified. The recorded actual invocation uses
those descriptors; the original declared argv remains separate.

The report retains the actual tracer process receipt plus independently parsed
native exec/termination observations, exact original request, raw trace/native
logs, selected-tool version observation and optional original native report. It
does not impersonate an existing work-unit execution receipt or source binding.
Native report capture requires a matching owned output path and explicit native
8MiB file-output bound. Input source identity remains a caller claim.

The parser retains operation/result/errno, PID and ordered raw arguments,
absolute paths, observed dirfd annotations, descriptor-only paths, process
creation and terminal observations. It reconciles unfinished/resumed syscalls by
PID. Missing children/terminals, truncated streams and record bounds stay
incomplete. Unknown syscalls, malformed/non-UTF8 strings, unresolved relative
paths, lexical parent traversal and unframed diagnostics stay unsupported.
`complete_observation` means supported framing and observed terminals, never
complete input closure. PID bounds restrict observation and trigger owned-group
cleanup; no cgroup/PID isolation or escaped-descendant containment is claimed.

Initial21 tests passed; a meaningful new missing-child control first failed
because a clone-created child never appearing in the trace was overlooked. The
parser now accounts for the created PID and withholds complete observation.
Current29 tests include actual sealed selected-tool execution, trace-limit
cleanup, strict request/replay forgeries, and four actual native negative-path
controls. Before/after source hashes, coverage and exact commands are retained
in the companion evidence directory. Combined statement/branch coverage in the
first29-case run was80%; the contract file separately measured79%.

The actual analyzer controls preserve the same primary source and old later
header bytes. Creating either an earlier external `-I` header or an external
`__has_include` flag changes native CC1 to2; ENOENT and successful queries remain
visible. The actual native captures correctly remain unsupported because native
stderr diagnostics share the trace stream and because some loader/filesystem
semantics are deliberately unqualified. Their raw reports still identify the
actual libclang19.1.7 parser. No unsupported record is discarded to obtain a
complete label.

## Next runtime and filesystem guard boundary

A next descriptive replay-guard contract should retain the observed lookup
result and lstat identities for every lexical parent/symlink chain, including
nearest existing ancestors of ENOENT/ENOTDIR paths. Use a bounded two-pass
metadata/content window over all relevant ancestors and positive files; changes
in device/inode/type/ctime or actual TU SHA/size invalidate the guard. Capture
status must still remain unqualified until supported operation/namespace semantics
are covered. Before/after path hashes alone do not identify transient mapped
runtime bytes. An observed EACCES result is not proof of an absent file.

The independent runtime boundary needs more than these guards. Kernel-selected
ELF interpreter, loader cache/preload and glibc-hwcaps candidates, library lookup
namespaces and actual mapped dependency bytes must be bound. One candidate
profile is a genuinely frozen read-only OCI execution/input view with selected
source/include-directory/SDK snapshots, checked fixed virtual-path mapping and
explicit exclusions for dynamic proc/sys/dev, PCH/VFS and host-native target
mechanisms. This is a proposed profile, not an implemented closure guarantee.
Even a sealed main executable leaves its interpreter/libraries unresolved.

The next observable refinement is a separate bounded trace FD stream, preserving
native stderr independently, with versioned parser/receipt semantics and retained
v0.1 replay. That should precede expanding supported loader/path semantics.
Neither refinement may authorize reuse from the absence of dynamic operators or
an empty positive inclusion graph. Qualified facts caching and separate
assessment caching still require genuine clean-versus-cached controls over
source/header/flag/tool/policy edits and negative path appearance/disappearance.

## Current independent review and namespace controls

Independent review retained18 meaningful integrity failures across three batches.
Repairs require coherent tracer exit/stream counts and version receipts; distinct
held tool descriptors; actual successful native exec/environment observations;
correct process terminal/exit/child state; bounded numeric domains before integer
conversion; strict C escapes/results; and refusal of a dot output-report path.
Encoded argv and environment `KEY=value` byte lengths are checked before output
creation. The current producer/replay gate passed **51 tests**, source hashes
stable, combined statement/branch coverage81%; the independent51-case gate also
passed with stable hashes and70 actual artifact pins. Exact records are in
`query-observation-evidence/` and `query-observation-independent-review/`.

An actual owned directory control restored a queried pathname to absent after
create/delete while changing its nearest existing ancestor's ctime. That is why
final-path absence alone cannot authorize reuse.

Approved read-only namespace controls used the exact already-local Ubuntu image,
nonroot UID1000, networknone, all capabilities dropped and no-new-privileges.
Actual writes to rootfs `/tmp` and a read-only bind failed EROFS. Nevertheless,
host changes to an existing file and creation of a previously missing flag were
visible through that read-only bind. A read-only mount is not a frozen input
snapshot. Image/container inspections, raw logs, exact commands and checksums
were preserved before removing only the new owned stopped containers. Images
and other task containers were untouched.

The initial assertion that a newly created `/input` mountpoint left an empty
rootfs diff failed: Docker had added that empty directory during bootstrap.
That failure is retained. A bounded streamed export confirmed only the empty
changed directory in rootfs; its bytes/metadata were archived before cleanup.
The repeated control mounted the image's existing `/mnt` and preserved the
original empty-diff assertion, which passed. This fixture correction does not
weaken read-only or host-mutation predicates.

Read-only storage measurement for a possible scratch native view found
205,477,216 unique runtime/interpreter bytes,5,115,552 native bytes and13,577,805
SDK bytes in241 regular files:224,170,573 bytes minimum before input trees and
an honest inside-container native supervisor. VFS import and retained archives
must be budgeted at peak, not just final image size. No scratch image was built.
A frozen namespace producer and actual original native receipts remain future
work; Docker client execution must not be relabeled as native execution.
