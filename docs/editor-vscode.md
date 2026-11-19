# VS Code preview qualification

The local preview reads retained cppulse results through public CLI and SARIF
contracts. See [installation and host-runner inputs](../editors/vscode/README.md).
It remains part of P2/P8/M7 of the full production plan.

## Recorded environment and evidence

On 14 November 2026 the pinned VS Code 1.105.1 Linux x86_64 runtime installed the
packaged `cppulse-0.2.0-preview.vsix` into a fresh isolated extensions directory.
Current evidence is under `review/production-20261114/p2-resumed/`.

The original backend install mixed a newly built cppulse wheel and an older
wheel of the same version from separate directories. pip selected the older
artifact and correctly rejected it against the new wheel's expected SHA-256.
The resumed check copied dependencies into a single closed wheelhouse, added
the newly built wheel, derived its exact lock, and installed with
`--no-index --require-hashes`. That fresh installation passed `cppulse doctor`
and ran native analysis on three fixture files. Optional web/PDF/ML packages
were absent. The native runtime is the earlier explicitly selected installed
dev2 candidate, not a freshly qualified production native build.

The real extension host could not start in this command environment: Xvfb
cannot create its Unix listening sockets. Ozone headless execution also failed
before host initialization because GTK requires a display. Neither failure is
a passing editor test. No host-test JSON success report was created.

## Repeatable host runner

`npm run test:host` installs the VSIX into a temporary profile, selects those
installed package bytes as the extension under test, and uses a forwarding
probe to the separately installed CLI. It checks activation without CLI
execution, backend/editor run pins, duplicate basenames, unsaved-source
invalidation, Unicode source navigation, duplicated SARIF observations, digest
mismatches and explicit clearing. It restores the unsaved buffer and removes
its temporary Unicode fixture. Use a disposable workspace as documented.

Passing those cases would qualify only that named environment and fixture.
The runner disables Workspace Trust prompting; Restricted Mode needs its own
execution. Typed producer/consumer matrices, all workflow commands, missing and
incompatible backends, delayed/cancelled actions, platform variants and bounded
large-project behavior remain required by the full production plan.

## Cloud continuation verification, 16 November 2026

The current extension compiled, passed **18 unit/contract checks**, and packaged
from a fresh checkout after repairing the missing artifact-directory creation.
Three finite resource settings now match the client's existing supported
bounds. Source navigation handles CR-only files and matches native LFCR
semantics (LFCR is two terminators; CRLF is one).

A real VS Code **1.105.1 Linux x86_64** extension host installed and executed the
VSIX in an isolated profile. All **ten host cases passed**, including actual
installed CLI run/hash agreement for native findings in duplicate basenames,
activation without CLI execution, unsaved-source invalidation, Unicode and
non-BMP navigation, repeated SARIF observations, CR/LF/CRLF/LFCR locations,
digest mismatch and clearing. This supersedes the earlier inability to start a
host for this named Cloud environment only. The host used locally extracted
Xvfb 21.1.16 over TCP and the SDK runner with inherited global `NODE_PATH`
cleared for Electron; the global module path otherwise crashed Electron's
package resolver after installation.

- VSIX SHA-256: `34a502c9f0c0728394e5e3a006e95b1a16a376561dc3966feef3767eb6c30ea8`.
- Separately installed core wheel SHA-256: `eeb2e8b6172d12f8aa1228527c3c48060e44c1e2c9e59b08cc9db9f260c6d116`.
- Selected run: `1e0a264c0396499a9b41c54599a5d48c`.
- Manifest SHA-256: `10f58281e99f8e5e3e6026b0acd7556676b7f4ef6628aca280ffbcc26ae3ff40`.

Retained findings are explicitly unverified legacy analysis observations, not a
verified production assessment. Unicode and line-ending SARIF cases are authored
client fixtures; the two-basename findings were produced by the actual native
analyzer and selected through the actual separately installed CLI. The fixture
analysis used the Cloud baseline native binary and does not qualify a final
whole-product candidate. Workspace Trust was enabled by the harness. The full
platform, Restricted Mode, all execution/cancellation UI, large-data and
cross-interface production scenarios remain open. Source-bound commands,
results and report are retained in `docs/checkpoints/20261116/editor.md` and
its companion editor-host result JSON.
