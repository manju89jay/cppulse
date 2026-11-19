# Frozen input filesystem prerequisite: proposed private profile 0.1

This is an implementation proposal for M2-03, NFR-SCL-03/06/10 and P5.
It does not change their acceptance states or enable reuse. The current
descriptive observer and production scheduler continue to report unqualified
closure and execute every unit fresh. No image was built for this proposal.

## Evidence and reason for this boundary

The source-bound observer run retained in
`work/cache-closure-observation3/reviewed-source-bound-check.json` passed51
tests with81% statement/branch coverage. Its checked source hashes identify
the implementation tested; a parser success is not a filesystem boundary.
The four actual native negative-query controls and the create/delete ancestor
control remain in that directory. They demonstrate missing inputs that a
resolved-header inventory cannot cover.

The existing-image readonly controls in
`work/cache-closure-observation3/readonly-container-v2/verification.json`
passed six finite checks. In particular, a host edit and previously absent
header both became visible through a readonly host bind. Therefore inputs
must become image-layer bytes before execution; readonly host binds cannot
constitute this profile. Rootless Docker currently reports VFS storage and
no CPU, memory or PID cgroup enforcement.

## Contracts before producer

Introduce private `frozen_input_private/{request,manifest,report}.schema.json`
and a validator in `contracts/frozen_input.py`, independently versioned0.1.
All objects reject additional properties, duplicate identities, noncanonical
paths, NULs, invalid UTF-8 and excessive byte/count/depth limits.

The request pins the original work-unit request, the selected native binary
SHA/size, runtime payload manifest, explicit project/external/SDK input roots,
exact argv, complete explicit nonsensitive environment and cwd, Linux
architecture/platform, finite limits and the path-map version. It contains no
reusable receipt. The builder is not permitted to discover an undeclared host
include directory and silently append it.

The manifest records every directory, regular file and supported symlink,
including empty directories and negative namespace boundaries. Each entry
records canonical container path, type, mode, file SHA/size or symlink target,
selected source-root identity and original relative path. Reject devices,
FIFOs, sockets, escaping symlinks, hardlink aliases in the first profile and
mounts below selected roots. Include normalized ownership and exact retained
mtime: Clang can observe directory state, file metadata and `__TIMESTAMP__`.
The identity is SHA256 of canonical ordered manifest bytes plus exact
normalized layer bytes and image config; it is not merely a list of positive
files. The full layer is retained to reproduce absent paths.

The report pins request/manifest/layer/config/image identities, Docker version
and daemon properties, exact create/start/wait/inspect/diff invocations,
actual container identity, mounted namespaces, runtime paths and stream
artifacts. Required constants initially remain `cache_eligible:false` and
`closure:unqualified`. Separate fields describe `frozen_filesystem_observed`
and explicit unresolved non-filesystem inputs. A Docker client exit0 cannot
be labelled a native invocation. An inside-container native receipt must
come from actual execution and retain container argv/cwd; the original host
work-unit receipt stays intact. Host/container path mappings are explicit
evidence, never an in-place rewrite of an original report.

## Finite producer and runtime

1. Preflight storage and immutable input identities before allocating. Stream
   selected regular files into a retained normalized tar with per-file hashes,
   checking open descriptor identities before/after each read. Source mutation
   rejects the capture. Cross-file capture is a declared snapshot of selected
   bytes, not proof those bytes simultaneously existed on the live host.
2. Preserve native, loader, actual dependency libraries and selected SDK in
   their declared image paths. The current ldd inventory is only a candidate
   inventory: lazy dlopen, NSS, locale and transitive runtime reads must be
   tested inside the result. No host library bind or implicit image pull.
3. Import the exact retained layer locally and pin its resulting immutable
   image/config identity. The image contains project and external input trees
   as layers, never live host input binds. Run a unique task-labelled container
   with readonly root, UID1000, capabilities dropped, no-new-privileges and
   network none. No Docker socket or host-device mounts. Use already present
   output mountpoints, avoiding bootstrap directory changes.
4. Permit only a declared finite output location, initially bounded streams.
   If native requires temporary paths, add a separately described writable
   scratch namespace and classify all resulting reads before qualification.
   Docker's implicit `/etc/hosts`, `/etc/hostname`, `/etc/resolv.conf`, `/proc`,
   `/sys`, `/dev`, shm and tmpfs are not covered by an image digest; inspect
   and report them explicitly. Never mark them frozen because root is readonly.
5. Retain inspect/diff/streams and verified inside report before removing only
   the stopped owned container. Preserve layer/image artifacts and all failed
   controls. A timeout or killed client is not proof the container stopped;
   inspect its actual state before any cleanup.

The profile initially supports only finite trusted fixtures. Actual native
wall timeout and stream limits are required. Per-process rlimits can be added
with their actual receipt and setup-failure control; Docker flags here cannot
claim aggregate CPU/RSS/PID limits. A quota-capable host remains a separate
platform gate.

## Storage and rollout gates

The measured runtime205,477,216B + native5,115,552B + SDK13,577,805B totals
224,170,573B before input fixtures. The retained tar plus VFS imported rootfs
plus possible export requires450–675MB peak, not just image size. Current
free space was5,839,900,672B at this design read. Preserve at least4GiB and
coordinate with the parent's approximately700MB fresh-root-test requirement.
No large export is necessary if retained layer/config and exact image inspect
suffice. Do not delete existing sources, logs, artifacts or shared images to
fit this experiment. Restore archived generated objects before relevant
upstream rebuilds.

Before a native image build, review the concrete contracts, payload list,
storage bound and owned cleanup plan with the coordinator. Then implement
contract red/green tests before the producer. Preserve actual controls for:

- Source/header mutation and missing-header appearance after image capture
  cannot change that image's native result; rebuilding changes its identity
  and matches a new clean native run.
- Same primary/old-header hashes with an earlier external include appearing,
  `__has_include`, empty-directory changes and ancestor create/delete.
- Outside-root and escaping symlink inputs, undeclared libraries, writable
  input attempts, unexpected mounts, truncated output and native/client crash.
- Actual native bytes, selected SDK bytes and inside-container path/argv
  identity, plus independent evidence verification against retained artifacts.

## Qualification still missing after those controls

A frozen filesystem does not freeze clocks, vDSO, host CPU features, random
devices, kernel behavior or runtime generated data. `__DATE__`, `__TIME__`,
plugins, PCH/modules and unsupported preprocessing mechanisms remain
unqualified until a supported checked boundary exists. A lexical token scan
alone cannot establish their absence through arbitrary macro expansion.
No positive cache reuse can be authorized merely by passing the filesystem
controls above. A later explicit eligibility profile must prove which remaining
inputs affect the measured facts, pin or exclude them through an enforced
mechanism, and pass warm-versus-clean equality and invalidation controls.
Retain the original native receipt on any eventual replay and compute fresh
policy assessment separately. This prerequisite cannot complete M2-03 or P14.

## Implemented prerequisite checkpoint

Contracts-first implementation was approved. Private schemas and
`contracts/frozen_input.py` now validate bounded requests/manifests/reports,
canonical cross-document identities, source mappings, and distinct client/native
receipt invocations. `cppulse/frozen_input.py` inventories selected directories
through checked nofollow descriptors with finite entry, payload and depth limits.
The first producer rejects symlinks, hardlinks, mount crossings and special files.
Empty directories, modes, mtimes and file SHA/size are retained in the inventory.

Actual tiny-tree controls reject same-size source rewrites and ancestor
create/delete races during traversal. Missing-header creation changes the
namespace with the primary SHA unchanged. This inventory does not retain file
bytes or establish a simultaneous host snapshot. A future layer producer must
hash the same bytes streamed into its retained layer, rather than trust this
earlier inventory and reread live paths.

Source-bound49tests passed1.09s at89% combined statement/branch coverage;
all seven implementation/schema/test hashes were stable. Exact command,
hashes/log/coverage: `work/cache-closure-observation3/frozen-profile4/`.
Combined new and existing observer checks passed100tests2.87s. No image was
built and there is no new full-plan acceptance or positive cache reuse.

Actual immutable native9004/libclang19 mechanism probes are retained under
`work/cache-closure-observation3/`:

- `clang-time-profile4-v3/verification.json`: SOURCE_DATE_EPOCH0 selected actual
  DATE/TIME/TIMESTAMP include headers `Jan  1 1970`, `00:00:00`, and
  `Thu Jan  1 00:00:00 1970`. Epoch86401 changed all three, including TIMESTAMP
  despite source mtime0. TZ=EST5 with epoch0 selected the same UTC names.
  All three native runs exited0/status analyzed. The earlier missing timestamp
  header partial-AST control is preserved in v2.
- `clang-target-profile4/verification.json`: original explicit
  `--target=x86_64-pc-linux-gnu -march=x86-64` selected baseline.h; original
  `-march=native` selected avx2.h on this host with the same primary SHA.
  Both native runs analyzed successfully; distinct original argv/databases
  are retained. A derived fixed-target profile must disclose its changed
  semantics.

`clang-profile4-files.json` pins52 raw probe reports, streams, selected inputs,
compile databases and scripts (194,957B). These finite observations support
profile design; they do not establish universal time/CPU or runtime closure.

The later `frozen-profile4-final/` source epoch supersedes that49-test inventory
source for current verification:50 new checks plus51 observer checks passed
101tests4.41s, with all14 source/test/schema pins stable. New producer/contract
coverage is88% combined statement/branch. This epoch adds capped scandir
enumeration rather than materializing an unbounded directory listing; a real
22-entry fixture with selected limit2 consumes only3 entries before rejection.
Independent review is still required. The proposed streaming import/storage
plan is `oci-streaming-build-plan4.json`; it reserves1,280MiB across compressed
retention, import temporary space, VFS rootfs/clone and fixture/slack, and has
not been executed. At its5,656,248,320B free-space read that reservation left
only approximately20MB above the4GiB reserve, so safe build headroom remains
unresolved and the full root gate must be serialized with image work.
