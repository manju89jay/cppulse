# Service profile per-process resources

The separate trusted service lane accepts version0.2.0 requests using profile
`cpp17-elf-relink-loopback-v2`. Version0.1.0 request/report schemas and their
historical replay remain unchanged. Existing v1 observations do not acquire new
resource claims.

A v2 request adds `process_resources.build` and `.test`, each containing
`cpu_seconds` (null or an ordered positive soft/hard pair) and
`address_space_bytes` (null or a finite byte cap). Build applies to compilation,
ELF linking and probe compilation; test applies to protected probe execution.
The two service inspection steps remain outside these project-resource scopes.
Null preserves inherited limits and does not assert an unlimited environment.

Before each project exec, the selected sealed Python supervisor imports its
required modules, observes inherited RLIMIT_CPU/RLIMIT_AS, applies explicitly
requested limits, and records actual getrlimit values in an exclusive retained
step JSON file. Setup failure writes its reason and exits125 without executing
the project command. Hard limits imposed by the outer environment cannot be
raised beyond that authority. Each receipt records its PID, selected step ID, exact selected exec argv and
Linux per-process scope. Replay bounds each JSON receipt to8MiB, sufficient for
the profile's finite argv count/string limits. It is bound into the original progress row and the report's
hash/size artifact inventory. Replay requires requested/applied values to agree,
valid OS soft/hard ordering (minus1 means infinity), exact step-specific receipt
paths and all eight project steps for a verified finite regression.

These limits apply to a process and are inherited by its children. They are not
aggregate CPU across descendants, resident-memory, PID, cgroup, storage, network
or hostile-project containment. The report's conservative global CPU/memory/
cgroup qualification flags remain false; the per-step receipt is the precise
resource observation. The helper/compiler/runtime closure remains unverified.
A SIGKILL result alone does not identify CPU exhaustion or exclude another
external cause. Separate actual controlled probes establish the selected CPU
soft-handler/hard-limit and address-space behavior in the recorded environment.

Current controls retain a native CPUsoft1/hard2 handler exit78, a separate
ignore-soft hard-kill observation, and a64MiB address-space allocation-failure
control versus an uncapped successful allocation. The finite service producer
also executes its complete ten-step before/after pair with checked receipts.
They do not establish full P11/M9 adequacy, platform support, semantic
equivalence or any full production acceptance. All uncommitted source and
meaningful failing observations remain retained.
