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
