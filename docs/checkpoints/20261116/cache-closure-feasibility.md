# Cache input-closure feasibility: actual negative path observations

M2-03 remains unfinished. Public units still execute fresh; no production cache
code, eligibility predicate or acceptance state changed in this investigation.
No requirement is accepted by the following finite observations.

Four tiny actual native/strace controls passed. Native SHA256 is
`9004df27f73a73901e3c231834628c24009ffded1730e598754acd6e7c7a6373`.
The installed strace6.13 can trace its own child without extra packages.
The exact binary hashes, explicit scrubbed environment, commands, host, limits,
raw native reports and trace hashes are retained in
`cache-closure-feasibility-evidence/verification.json`.

| Control | Missing external path | After the same external path appears |
| --- | --- | --- |
| Earlier `-I` directory precedes unchanged later header | Actual `openat` returns ENOENT; native CC1 uses later header | Successful `openat`; native CC2 uses new earlier header |
| `__has_include` checks external flag header | Actual `openat` returns ENOENT; native CC1 | Successful `openat`; native CC2 |

Each pair retains the exact same primary-source and original later-header
SHA256. All four native processes exited0. Traces total219,669bytes; the original
work directory was384KiB at capture. Finite controls applied3GiB address-space,
30CPU seconds,60wall seconds and2MiB per output file. These are observations,
not released performance budgets or cgroup/aggregate enforcement claims.

A resolved-inclusion inventory cannot account for the first missing path in
either example. The loader also probes missing `glibc-hwcaps` and libclang
candidates. Recording only header search failures would omit runtime-selection
inputs capable of changing the implementation itself.

## Next contract before any cache eligibility

Add a separate, finite **descriptive filesystem-query observation** contract.
Its identity must pin the original request/result/receipt, analyzer and tracer
bytes, trace configuration, explicit complete environment, actual cwd and raw
trace artifact. Retain selected query paths, operation/flags, returned errno or
result, observed process/thread ownership and ordering, and the relation to
actual TU buffer identities. Its initial qualification must be unqualified and
cache eligibility false. Raw traces remain independently inspectable.

The first parser/producer gate must prove strict behavior for truncated or
capped traces; unknown syscall/flag forms; unfinished/resumed syscalls;
fork/clone and shared cwd/fd semantics; `openat`/`openat2`, relative dirfds and
`fchdir`; symbolic-link chains; non-UTF8/escaped paths; interrupted syscalls;
EACCES and ENOTDIR versus true absent-path observations; thread/process loss;
and tracer/native crashes. Unsupported events remain unknown, never silently
ignored as closure. Output-write classification cannot assume an arbitrary
path is irrelevant to compiler inputs.

For replay, every absent lookup needs checked ancestor-directory/symlink
identity as well as its observed errno. A create/delete race can restore an
absent pathname while changing its containing directory. Existing positive
file and actual TU-buffer checks must remain intact. The genuine controls here
must fail stale reuse when the earlier include target or queried flag appears.

## Remaining closure boundaries

Successful strace exit0 is not proof of a complete or authenticated input
universe. File/process traces do not capture actual mapped shared-library bytes,
vDSO/clock or CPUID values, every environment/runtime influence, external VFS or
PCH/module internals. Hashing a runtime pathname after execution cannot prove
which transient bytes were mapped. A qualified future producer therefore needs
an additional checked runtime/input boundary, such as genuinely retained
immutable execution/input views and explicitly supported compiler mechanisms,
with actual counterexamples and platform applicability verified. This paragraph
is a design requirement, not an implemented boundary.

Preserve the distinction between cached semantic facts with their original
receipt and a new assessment. Cache replay cannot manufacture a native
invocation, target test result or fresh source approval. The finite observation
protocol is the next implementable prerequisite; it is not completion of
M2-03, NFR-SCL-03/06/10, P5 or the full production plan.
