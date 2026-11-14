# cppulse for VS Code — local preview

Read retained C++ findings in Problems, inspect run/context/policy gaps, and
explicitly invoke an installed cppulse CLI. Opening a folder or activating this
extension runs no CLI command, build, test or recipe.

This preview is part of the full cppulse production program. A VSIX is not a
published extension or complete M7 delivery. The current qualification is the
named host/test matrix in [the editor guide](../../docs/editor-vscode.md).

## Install locally

1. Install the matching cppulse Python/native candidate separately. Verify
   `cppulse capabilities --format json` and `cppulse doctor` in that environment.
2. Install the prepared VSIX with VS Code's **Extensions: Install from VSIX**.
3. Select the installed CLI with `cppulse.executable`. This is one program path;
   `cppulse.arguments` is an array of literal prefix arguments, never a shell
   command. For example, a selected Python executable can use `["-m","cppulse"]`.
4. Open the local source workspace and select **cppulse: Read Retained Run**.
   `cppulse.storeDirectory` defaults to `.cppulse-output` beneath that workspace.

This preview's package pins VS Code 1.105.1 and CLI capability contract 1.0,
snapshot view 2.0 and SARIF 2.1. Installations need their own native dependencies.
No optional PDF/web/ML package or network account is required to read results.

## Commands

| Command | Behavior |
| --- | --- |
| Read Retained Run | Resolve latest once, then use the exact returned run/hash for SARIF |
| Open Local SARIF | Read selected local data; no CLI execution; available in Restricted Mode |
| Inspect Installed Tools | Explicit doctor/native startup inspection |
| Analyze Selected Workspace | Explicit source/history analysis, not a project build |
| Collect Explicit Request | Choose and execute a reviewed JSON collection recipe |
| Check Selected Policy | Choose a policy and evaluate retained current material |
| Render Selected Evidence Report | Render the selected historical pins to an explicit output |
| Clear Editor View | Remove diagnostics/view and cancel an active owned process |

CLI execution requires Workspace Trust. Read-only requests still invoke the
configured program and are guarded accordingly. Local imported SARIF does not
authenticate a producer or imply a policy pass. Current matching file bytes do
not promote unverified historical observations to verified execution evidence.

Typed findings map only when current local source matches the retained digest.
Modified or unsaved inputs clear diagnostics and retain historical pins with a
stale message. Legacy analysis snapshots can expose unverified observations;
without retained C++ bytes their locations are explicitly historical/line-only.
Every occurrence is retained, including duplicate basenames and stored suppressed
observations. Gate/score values are displayed from the backend, never calculated
in the editor.

## Preview limits

One response stream and one source read are bounded to 16 MiB. The selected view
supports at most 20,000 diagnostic occurrences. Overflow is an explicit error,
not a truncated clean result. These limits do not establish large-project
scalability or indexed query support. Windows/macOS and full product views need
their own qualification; this preview is not the full VS Code/MCP/skill roadmap.

## Build and verify

```bash
npm ci --ignore-scripts
npm run compile
npm run test:unit
npm run package
```

Real extension-host tests require the pinned VS Code runtime, a display/Xvfb,
and an actual installed cppulse candidate with retained C++ fixture results.
See the test runner's documented environment inputs; pure client tests are not
a substitute for that installed-host verification. Packaging performs no login,
Marketplace submission, Git change or upload.

The host runner installs the packaged VSIX into a temporary profile and tests
that installed extension, rather than the checkout's compiled files. Supply
absolute `CPPULSE_HOST_CLI`, `CPPULSE_HOST_WORKSPACE` and `CPPULSE_HOST_STORE`
paths. The workspace must be disposable and its retained run must include
native findings for `one/same.cpp` and `two/same.cpp`. Tests temporarily edit an
unsaved buffer and create/remove a Unicode source fixture there. The CLI must
be installed separately with its native runtime configured; optional web/PDF/ML
extras are unnecessary. Set `CPPULSE_VSCODE_EXECUTABLE` to an existing pinned
VS Code executable to avoid downloading a runtime. `CPPULSE_HOST_REPORT` selects
an optional JSON result path. Then run `npm run test:host`.

On Linux a working display or Xvfb is required. The current managed command
environment prevents the X server's Unix sockets; attempts with both Xvfb and
headless Ozone failed before extension tests could run. VSIX installation was
successful, but no passing extension-host qualification is claimed. Windows,
macOS, Restricted Mode, full command/cancellation UI and scale remain separate
qualification requirements. A host report is written only after every case
passes; it lists its exact limited coverage.

MIT licensed. Third-party SDK/testing dependencies retain their own licenses.
