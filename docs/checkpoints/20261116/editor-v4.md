# Installed editor, exact stored health and source lifecycle — 16 November 2026

This is a verified finite slice of FR-UX-10, M7-01/M7-02, IDE-02/03/05 and
P2/P8. It does not close those requirements, AC-12, P14 or the full production
plan. All 118 requirements, nine additional obligations, 60 M0–M9 tasks and
P0–P14 remain retained. All changes are uncommitted; no publication or remote
Git action was performed.

## Result and exact artifacts

The installed VSIX is SHA-256
`0838719deebdd74789b17d4976b006ba2830be7dea573e28533c5169cffe36f5`.
It is preserved at
`editors/vscode/artifacts/history/0838719deebdd74789b17d4976b006ba2830be7dea573e28533c5169cffe36f5.vsix`.
The local package output contains the same bytes. The original existing
`34a502…` VSIX remains in the earlier checkpoint artifact archive and was also
recovered and hash-verified under `work/editor-artifact-preservation/`.
Packaging now preserves previous generated VSIX bytes by digest before
replacing the current local package output.

- Compile and **45 unit/contract checks passed, zero skips**, with source hashes
  unchanged and every compiled JavaScript/map file matching the VSIX archive.
- **27 installed VS Code 1.105.1 host cases passed**, Linux x86-64, exit 0.
  These include actual legacy-v3 and v4 clean/finding retained runs, exact
  run/manifest/artifact/configuration identities, literal score tokens,
  multi-root settings, unsaved edits, unopened and aliased roots, changed source
  during a first pending read, immediate first alias-target modification,
  malformed/oversize responses, missing executable, timeout, clear-driven
  cancellation and a delayed older response.
- Independent review passed **10 parser and seven actual-filesystem checks**
  (already included in the 45 above), four actual v3/v4 projections and
  1,500 separate decimal-oracle inputs. The seven filesystem checks also passed
  in VS Code's actual Electron Node runtime. Two separate installed-host
  counterexamples passed after repair on the exact VSIX: a real 1,554,929-byte
  retained artifact is refused by a 1 MiB artifact limit, and the first immediate
  canonical-target write clears an alias-only SARIF diagnostic.
- A further **two actual-host cases passed against the current installed wheel
  `60fabb121d6ed87bbb7b400a7d4ac6e3b56060346c8d04f16d38c960d19f7d4e`**
  and the new bounded SDK stores. Qualified run
  `8d8c982f8e484c3bbae1df0162c83812` displays stored `100.0`/`scored`;
  unsupported-query run `3ea44af25d6d4d7eaa4a377235ad365f` displays
  `null`/`partial`, without converting unknown to zero. Both match the exact
  manifest, original health artifact and scorer/configuration identities.

The current backend origin is under
`work/cloud-resume/installed-typed-sdk-service-current/core-venv/lib/python3.12/site-packages/cppulse/`.
Its existing installed verification records 49 packaged schemas. The first
27-case host gate used the earlier exact wheel `3c37a0…` separately; the two
current-backend cases establish the additional artifact agreement without
relabeling that earlier backend as current.

## Repairs and boundaries

`stored.ts` reads the original retained health JSON with bounded depth/bytes,
rejects duplicate keys and preserves number lexemes. It checks descriptor and
source identities, supported scorer/method versions, common fact-ID syntax,
availability/assurance states and exact decimal score bounds. There is no
editor scorer or policy evaluator. The tree shows original calculations,
configuration and artifact hashes. Historical v3 is explicitly labeled as not
requiring parsed source/header byte verification; v4 explains that inferred
parsing opt-in does not waive byte verification.

Actual review found and repaired several additional defects:

1. Artifact opening used the response cap instead of the configured source and
   evidence-read cap. The original actual-host bypass is retained.
2. Project settings were read per folder, but manifest scope prevented VS Code
   from writing folder overrides. The actual host failure and a contract red
   test are retained; project settings now declare resource scope.
3. Clean disk reloads were mislabeled as unsaved edits. Dirty-state transitions
   can arrive as empty text-change events, so the client handles dirty-state
   changes and leaves clean reloads to filesystem monitoring.
4. Previously only opened workspace roots were watched, and a first pending
   selection had no tracked source identity. Current and pending selections
   now share finite source tracking, with canonical and declared alias names.
5. VS Code watcher registration has no ready acknowledgment. A new alias-only
   SARIF view could miss its first immediate source change; an independent
   extra CLI roundtrip made the same old artifact pass. The new synchronous
   `SourceMonitor` watches selected parent directories nonrecursively before
   accepting bytes, including a pre-resolved canonical target. It handles
   ancestor/root replacement, null/unreadable event names, watcher failures
   and directory inode replacement. An actual old-inode failing test remains.

Monitoring is bounded to 4,096 directories across current/pending scopes. A
monitoring failure or excess scope makes current diagnostics unavailable. It
does not recursively scan unrelated repository state. The editor still reads
historical retained facts; source matching is not producer authentication or
consumer assurance. SDK/tool/executable freshness and current policy acceptance
remain backend workflows, not an editor filesystem-attestation claim.

The host runner clears inherited `PYTHONPATH` as well as Electron `NODE_PATH`,
compares installed code with the exact selected archive, checks every manifest
field except installer-added `__metadata`, and guards the archive hash before
and after the run. It accepts an explicit immutable `CPPULSE_HOST_VSIX` path.
The full host's independent expected-value CLI queries are synchronous test
controls; their occasional host-responsiveness log messages are not a product
responsiveness benchmark. Production command invocation remains asynchronous.

## Commands and evidence

Working directory: `/workspace/cppulse`.

```sh
npm --prefix editors/vscode run compile
npm --prefix editors/vscode run test:unit
npm --prefix editors/vscode run package
.venv/bin/python work/editor-v4-source-check/verify.py \
  --root /workspace/cppulse --output work/editor-v4-source-check-final \
  --vsix editors/vscode/artifacts/history/0838719deebdd74789b17d4976b006ba2830be7dea573e28533c5169cffe36f5.vsix
```

The source/coverage gate is exit 0. Node's loaded-module coverage is 86.66%
lines and 86.43% branches; this excludes `extension.ts`, which is exercised by
the separate real-host gate, and is not a whole-extension coverage claim.
The full host command is the existing `npm --prefix editors/vscode run test:host`
with the absolute CLI/workspace/store/VSIX inputs recorded in
[owner-host-inputs.json](editor-v4-evidence/owner-host-inputs.json), display
`127.0.0.1:95`, and the four scenarios in `work/editor-health-cases-v3-v4.json`.
Its actual log and report are copied into this checkpoint. The current-backend
host uses the preserved work-only driver/module under
`work/editor-current-backend/`; expected number tokens come from the current
installed Python with `-I`, `parse_float=str` and `parse_int=str`.

The compact [evidence manifest](editor-v4-evidence/manifest.json) identifies each
proof's source, byte count and hash. Source hashes, exact commands, current
backend origin, host case names, original failing controls and independent
review are retained there. All test data are local authored or actual retained
run fixtures; no fixture Git objects or refs are exported.

Mandatory full-plan command, rerun after this work:

```sh
/workspace/cppulse/.venv/bin/python scripts/verify_delivery.py --require-complete
```

**Exit 3: incomplete**, 187 items, 120 open / 65 active / two blocked. All
current IDs, states and remaining-work text are recorded in
[delivery-state.json](editor-v4-evidence/delivery-state.json). No acceptance
requirement or meaningful failing assertion was weakened.

## Still open

The full M7/IDE and production gates still require actual Windows/MSVC/MinGW
and macOS hosts, Restricted Mode, the complete explicit analyze/collect/check/
report outcome and dependency-failure matrix, the notification Cancel button,
indexed large-data paging/search, all remaining producer views, compatibility/
upgrade matrices and developer usefulness evidence. The new health display is
experimental stored maintenance information, not predictive validation,
standards certification, release qualification or full P14 acceptance.
