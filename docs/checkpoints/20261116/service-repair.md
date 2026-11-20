> Current separate version0.2 per-process resource work is recorded in [service-resources.md](service-resources.md). The v1 source/artifact observations below retain their original scope; they do not acquire resource claims retroactively.

# Separate trusted service-repair slice — 2026-11-16

M9-02/P11 remains incomplete. The ordinary `cpp17-cmake-ctest-v1` semantic repair
profile was preserved. A separate private `cpp17-elf-relink-loopback-v1` request,
producer and replay validator now retain inspectable, finite trusted-host service
observations. The sub-spec is `docs/development/service-repair.md`; implementation
is `python/cppulse/service_repair.py` and its two private schemas. No original
project source is patched and no service is started/stopped. Execution requires
an explicit trusted-project flag. There is no provider messaging, remote action,
publication or automatic application.

Current source-bound gate:

```
python scripts/record_delivery_check.py \
  --source python/cppulse/service_repair.py \
  --source python/cppulse/contracts/schemas/service_repair_private \
  --source tests/test_service_repair.py \
  --source docs/development/service-repair.md \
  --evidence review/cloud-20261116-service-repair-sealed-producer --timeout 180 -- \
  python -m pytest -q tests/test_service_repair.py --cov=cppulse.service_repair \
    --cov-branch --cov-report=term-missing \
    --basetemp=work/service-repair-sealed-producer-tests
```

Exit 0, **35 passed, no skips**, 11.91 seconds; combined statement/branch coverage
85%, source stable. These tests use a clearly labeled synthetic service-inspector
executable and real GCC ELF compilation/relinking. They do not establish an
actual MongoDB service identity. The first 35-case gate retained 33 passes/two
failures because timeout/output-limit probe mutations triggered
`-Werror=misleading-indentation` before runtime. Braces/newlines corrected that
fixture without changing compiler strictness or assertions; both logs remain.

Independent review retained three material counterexamples at the earlier
producer epoch: a selected compiler replaced temporarily and restored before
post-checks; inconsistent per-stream counts with unchanged combined count; and
step metadata diverging from its original retained progress record. The current
producer executes selected compiler/Docker/supervisor bytes from held Linux
sealed descriptors, records their content/seal facts and actual argv, reconciles
every step with its progress record, and checks stdout/stderr independently.
An independent source-stable replay run passed **10 cases** over the current real
raw-GCC positive fixture. A fresh controlled transient-tool counterexample then
executed zero changed-wrapper calls while preserving the selected original tool.
Evidence and meaningful red records are in `service-repair-independent-review/`.

Frozen module SHA-256:
`b7259b89f6c031f7092bbcfe05ee69cf9d31b75f0f9b015bb07945e0c9b0f6f7`.
Request schema:
`f6ecbfbb57d436412b13b994085d520b54fdd22c114e6bbd4c2af894b25b76cb`.
Report schema:
`4f940b2cc8a085e4266f3ffefd7eba68e15dac696082f153158507bcedb9bc97`.

The selected tool snapshot does not qualify compiler helpers, standard headers,
linker or runtime libraries. Their directory selections remain explicit inherited
inputs, with whole-toolchain closure false. Relocation initially exposed genuine
compiler/runtime configuration failures: empty `GCC_EXEC_PREFIX` prevented
`cc1plus`; relocated GCC needed helper/startup-library/system-include directories;
the custom-prefix Python 3.12 copy could not find encodings. All failures remain.
The current stdlib-only supervisor uses system Python 3.13; cppulse itself still
executes on the supported Python 3.12 environment. This is not package support
qualification for Python 3.13.

## Actual Poco/Mongo observations, explicitly separate epochs

The unchanged pinned Poco `a8aea338d211d6dbce75f5f07d70c449b94f1605`
MongoDB suite had 26 passes/four failures. A protected eight-case probe reproduced
the underlying command-reset defect: `setCommandName(DROP)` retained INSERT
document sequences; the actual owned loopback MongoDB 4.4.29 rejected reused DROP
with server code 40472. A disjoint proposed source adds `_documents.clear()`;
original source and configured libraries remain unchanged.

The implementation translation unit was recompiled PIC and relinked with the
original pinned MongoDB object files into disjoint same-SONAME libraries. The same
protected probe had **six passes/two failures before, eight passes after**, with
no skipped cases. A direct-TU-in-executable initial harness caused duplicate
shared-library global-string initialization and allocator corruption; it was
preserved and corrected by actual library relinking rather than changing tests.

An earlier typed producer attempt retained all ten actual compile/link/probe and
service-inspection steps, with identical owned running container/image/loopback
identity before/after. That attempt **predates the sealed-tool correction**, so
its report is historical and is not promoted to a current producer qualification.
Its complete owned materials, build trees, binary/library artifacts and raw logs
remain under `work/semantic-service-contracts/poco-typed-attempt2`.

The unchanged upstream **30/30 MongoDB tests subsequently passed**, using that
earlier disjoint proposed library through process-local `LD_LIBRARY_PATH`.
Original upstream tests, source and configured libraries stayed unchanged; exact
input, service and log pins are in
`work/semantic-service-contracts/upstream-after/verification.json`. This broadens
the finite observed behavior but retains the earlier library epoch qualification.

The current frozen sealed-tool producer was then executed against the actual
Poco/Mongo fixture in a **new retained attempt**, with no historical report
rewriting:

```
python scripts/record_delivery_check.py \
  --source python/cppulse/service_repair.py \
  --source python/cppulse/contracts/schemas/service_repair_private \
  --source docs/development/service-repair.md \
  --evidence review/cloud-20261116-service-repair-poco-sealed --timeout 240 -- \
  python -m cppulse.service_repair \
    --request work/semantic-service-contracts/poco-request.json \
    --output work/semantic-service-contracts/poco-typed-sealed-current \
    --execute-trusted-project
```

Exit **0**, source stable, 46.705 seconds. All ten actual steps are retained.
Before executes all eight cases with six passes/two failures and server 40472;
after executes eight passes, no skips. Compiler, Docker and supervisor report
`linux-sealed-memfd-sha256-v1` with seal value 15; all selected material hashes
match before/after. Request digest:
`5b899b11a1c509cc7158f7ac8cfcb38bcf0edc57e68d8dbfe285c6f7955f5ff3`.
After library SHA-256:
`f9872f55909c5d1a4c3976cb7197fe0a8e7b924f31cc469a91f351a765f0a09c`.
Complete material/artifact bytes remain in that work attempt. Compact report,
request, raw probe/inspection logs and source-bound check are retained alongside
the earlier epochs in `service-repair-evidence`.

The unchanged upstream **30/30 MongoDB tests also passed against this new current
sealed-producer library**. Exact source/library/service pins and raw stdout are
`work/semantic-service-contracts/upstream-after-sealed-current/verification.json`.
Original Poco Git status remains clean. This qualifies the selected finite
service lane; helper/runtime closure, resource isolation and full acceptance
claims remain unchanged.

## Preservation and remaining gates

Workspace headroom is a real constraint. Completed generated test tool-copy files
were hardlink-deduplicated only after verifying identical bytes/hash/size/mode.
All paths, raw logs, artifacts and contents remain. No source, dependency or live
process input was replaced; full artifact inventories were rechecked. Each
preservation manifest is retained under `work/semantic-service-contracts`; compact
evidence includes the final manifest. This does not alter any recorded result.

The current real Poco run needed approximately 126 MiB rather than the initial
90 MiB estimate because retained configured Net/Foundation libraries total
41 MiB. Root restored workspace headroom through verified preservation of
completed installed third-party dependencies, allowing the fresh attempt while
retaining the 4 GiB reserve. After execution, identical generated tool copies were
deduplicated with all paths/bytes/modes retained; current report replay passed
again. Reflink copying was probed on a tiny plain text artifact and is unsupported
by this workspace filesystem; that diagnostic remains retained.

Root added the public `verify-service-proposal` forwarding boundary and capability
entry, with two actual source CLI checks. A fresh exact ordinary cppulse wheel
then passed the root minimal installed verifier (49 schemas, optional
Git/ML/PDF/web dependencies absent):
`work/cloud-resume/wheel-typed-sdk-service-current/wheels/cppulse-0.2.0.dev2-py3-none-any.whl`,
SHA-256
`60fabb121d6ed87bbb7b400a7d4ac6e3b56060346c8d04f16d38c960d19f7d4e`.

This track additionally ran that installed environment with `python -I` from
`/tmp`, clearing `PYTHONPATH`, `PYTHONHOME`, `NODE_PATH` and every `CPPULSE_`
override. Ten selected installed module/schema/kernel/CLI/capability files match
the exact wheel's bytes and import from its owned site-packages. The installed
validator replayed the actual current Poco report and all retained artifact
bytes. An actual installed public CLI invocation then compiled/relinked the tiny
protected C++ fixture: two passes/one failure before, three passes after, no skips,
all ten observations retained. Its inspector is explicitly a controlled synthetic
fixture, separate from the actual MongoDB/Poco execution. Without the explicit
trusted-execution flag, the installed public CLI exited 2 and created no output.

The source guard remained stable across this installed check, including public
CLI/capability code. The complete owned tiny store and scripts remain in
`work/semantic-service-installed-current`; compact verification, source binding,
stdout/stderr, actual commands and exact wheel/module hashes are retained under
`service-repair-evidence`. No new environment, second full Poco source copy or
source edit was needed. This proves the installed finite lane and actual Poco
report replay; it is not a second installed execution of the full Poco fixture.
Broader clients, service/property/resource/platform/provider matrices remain
full-plan work.

The exact mandatory verifier was rerun after this implementation:
`/workspace/cppulse/.venv/bin/python scripts/verify_delivery.py --require-complete`.
Exit **3**, `complete:false`: all 187 ledger items remain, with 120 open,
65 active and two blocked. The ledger was stable across the command. The retained
record includes every current requirement/task/obligation ID and every P0–P14 ID;
no acceptance requirement was changed to make this slice pass.
The command was rerun again after installed/public-CLI verification, also exit 3
with the same 187 IDs/states and stable ledger. Both exact records remain.

This executor supervises step wall time, captured stdout/stderr and declared input
copy size. It does not enforce CPU, address-space/RSS, cgroup, PID, network,
arbitrary generated-file storage or service-state isolation. Separate OCI CPU
and native address-space probe results do not grant those features here. Tests
establish these finite observations, not semantic equivalence, universal behavior
or adequacy. Wider service/language/resource/platform/provider matrices and all
applicable full-plan AC-01..16/P14 checks remain required. No whole task or
requirement is declared complete by this checkpoint.
