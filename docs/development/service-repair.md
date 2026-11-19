# Trusted loopback-service repair observations

`cppulse.service_repair` implements the separate private
`cpp17-elf-relink-loopback-v1` profile for P11/M9-02. It does not relax the existing
`cpp17-cmake-ctest-v1` profile. Calling its validator does not execute a project.
Executing requires `--execute-trusted-project`:

```
python -m cppulse.service_repair --request request.json --output fresh-attempt \
  --execute-trusted-project
```

The request pins one original and one proposed C++ implementation, a protected
probe, every declared header/object/shared-library file, the compiler, supervisor
Python and Docker client. Sources must differ. Material names are finite,
canonical, unique (including case aliases), and cannot traverse directories.
Input pins are checked with safe regular-file reads before reserving a new output;
all bytes are copied and checked before execution. Existing output is refused.
Headers/objects/libraries are declared caller selections, not an inferred complete
project or an authenticated relationship between object files and source.

The executor performs ten actual observations: existing service inspection;
original source compile, library relink, protected probe build and execution;
proposed source compile, library relink, protected probe build and execution;
existing service inspection. Each lane uses a disjoint library/executable, with
the requested SONAME and copied dependency library bytes. Original source and
service configuration are never patched, started or stopped. Project code is
trusted host execution and can mutate the selected service. Callers must supply
their own disposable fixtures. A fresh generated database namespace is passed to
each probe; inspecting its reported namespace does not prove that arbitrary
project code respected it or that service state was isolated.

Both inspection results must identify the pinned running container and image,
the requested `cppulse.task`/`cppulse.fixture` ownership labels, and the exact
single loopback TCP port mapping. This is a local daemon observation, not remote
provider authentication, a consistent database snapshot or deployment attestation.
Docker is invoked only with `inspect --type container` by this executor.

Compiler, probe and inspector commands run through the selected supervisor Python
with `-I`; a retained inline `execve` helper unsets compiler/include/dynamic-loader
injection environment variables. Selected compiler, Docker client and supervisor
bytes execute from held Linux `memfd` snapshots with all four
`SEAL|SHRINK|GROW|WRITE` seals established before launch. Reports retain their
SHA-256, size, seal value and actual `/proc/<owner>/fd/<descriptor>` argv paths.
These paths identify the historical descriptor lifetime; replay checks retained
bytes and metadata without trying to reopen expired descriptors. Executing the
original tool path after hashing it was insufficient: an actual independent
counterexample changed the selected compiler temporarily, executed the replacement
and restored its bytes before final checks. The sealed snapshot closes that
selected-file race while toolchain helpers remain outside the verified closure.
Setting `GCC_EXEC_PREFIX` to an empty string is
not equivalent to unsetting it and broke the initial real compiler attempt; that
failure is retained. Relocating a GCC driver requires explicit helper, startup
library and system-include search directories in the request; those directory
contents are inherited rather than authenticated or snapshotted. The supervisor
must run after relocation; this Cloud's system Python 3.13 supports that stdlib-only
role, while the initial custom-prefix Python 3.12 copy failed to find encodings.
This does not claim cppulse package support on Python 3.13. Other host tools,
compiler helper programs, system headers,
linker and runtime libraries are inherited. Whole-toolchain closure is explicitly
unverified. No arbitrary compiler argument strings or shell commands are accepted.

The fixed probe emits strict finite JSON containing the generated namespace,
exactly the requested boolean case IDs, and an observations object. Before must
execute every case with at least one failure and exit 1. After must execute every
case successfully and exit 0. Clean before, zero/missing/skipped cases, malformed,
duplicate or nonfinite JSON, output truncation, missing steps, failed builds,
timeout, cancellation or changed declared bytes cannot verify a regression.

The resulting report retains actual argv/outcomes and raw stdout/stderr pins,
copied material pins, built object/library/probe bytes and progress records. Each
reported step must agree exactly with its retained original progress record;
stdout/stderr counts are checked separately against their raw files. Its
validator requires the retained artifact directory and recomputes observations;
a report JSON alone cannot establish success. Original and copied material hashes
are rechecked after execution. Failed/partial attempts remain on disk. Exit 0
means `verified_finite_regression` for this exact finite probe; 3 means incomplete,
2 invalid/refused and 130 an interrupted CLI invocation.

Only per-step wall time, bounded captured stdout/stderr and declared input-copy
bytes are supervised. The process primitive terminates owned POSIX process
groups; it does not promise containment of escaped processes. Arbitrary generated
files, aggregate tool CPU/RSS, network, PID count and service storage are not
enforced by this profile. Separate actual OCI CPU/native address-space probes do
not grant those capabilities to this executor. Every report explicitly records
CPU/memory/cgroup enforcement and service-state isolation as false.

This lane supplies finite regression evidence and a retained local proposal. It
does not establish semantic equivalence, unrestricted correctness, ABI/API
compatibility, test adequacy, production readiness or full M9/P11 acceptance.
Installed/public-CLI, wider service/platform/resource matrices and broader
proposal/model/provider qualification remain separate full-plan gates.

## Public command

The root CLI forwards the same separate finite profile, with explicit trusted
execution required:

```sh
cppulse verify-service-proposal --request request.json --output new-attempt \
  --execute-trusted-project
```

The request pins the selected inputs, tools, protected finite cases and owned
service identity. The output must be new. Exit0 means the selected finite
regression was observed failing before and passing after with checked retained
receipts; it does not establish semantic equivalence or authorize deployment.
Exit3 retains incomplete observations; exit2 reports invalid input or an
operational failure. The existing ordinary `verify-proposal` profile retains its
separate CMake/CTest semantics. Source tests of this forwarding command do not
qualify an installed wheel; that acceptance check remains separate.

## Versioned per-process controls

Version0.2.0/profile`cpp17-elf-relink-loopback-v2` adds explicit build/test
RLIMIT_CPU soft/hard pairs and RLIMIT_AS byte limits. Null leaves inherited
values unchanged. The selected supervisor records requested, inherited and
actual values before each project exec; a failed setup does not execute that
command. Original resource receipts, progress rows and raw process outcomes
remain available for replay. V1 historical observations retain their original
wall/log-only meaning. See [the precise resource contract](../contracts/service-process-resources.md)
for the per-process scope and aggregate/isolation limits. A fresh installed
artifact and independent review are required for this new version; the earlier
wheel60fabb qualification applies to its original v1 source epoch.
