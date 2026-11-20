# VS Code Cloud continuation checkpoint — 16 November 2026

The later [exact-health and source-lifecycle checkpoint](editor-v4.md) records
the current qualified VSIX, repaired actual-host counterexamples and agreement
with the current installed SDK backend. The original ten-case gate below is
historical evidence for its named artifact.

This is a verified implementation slice, not completion of P2/P8/M7/FR-UX-10.
No commit, push, publication or marketplace action was performed. The disposable
fixture has its own local Git commit, as explicitly permitted by the task.

## Changes and baseline

Original checkout compile and original 16 unit tests passed after using a
writable npm cache. Plain `npm ci` failed because the inherited cache path
`/home/agent/.npm` was read-only; misleading tarball warnings preceded the
final cache mkdir failure. `npm ci --cache /workspace/cppulse/work/npm-cache`
installed the locked dependencies successfully without changing the lock.

- Exposed existing bounded response/source/diagnostic limit configuration in
  the extension manifest and documented their ranges. New regression initially
  failed with missing `cppulse.responseLimitMiB`; final limits match runtime.
- Fresh-checkout packaging originally failed because `artifacts/` did not
  exist. A cross-platform Node prepackage hook creates it.
- Fixed editor source line splitting: CR, LF, CRLF and LFCR now agree with
  measured libclang locations. Preserved LFCR as two terminators; no merging.
  New regression initially failed because `splitSourceLines` was absent.
- Host runner clears global `NODE_PATH` only for Electron installation/host
  processes: inherited Codex module paths otherwise caused a fatal V8
  `original-fs`/package resolver abort after successful VSIX installation.

## Actual checks

Working directory: `/workspace/cppulse/editors/vscode`.

```sh
npm ci --cache /workspace/cppulse/work/npm-cache
npm run compile
npm run test:unit
npm run package
```

Compile passed. Final unit/contract suite **18/18 passed**, no skips.
Package produced the VSIX; no submission/upload.

The SDK downloader did not use the required inherited network proxy and failed
with ECONNREFUSED. Curl downloaded the pinned release through the configured
proxy. Dependencies were extracted into workspace paths; no sudo/system package
modification was needed for this track:

```sh
curl -fL https://update.code.visualstudio.com/1.105.1/linux-x64/stable \
  -o work/editor-deps/vscode.tar.gz
# tar extracted beneath work/editor-deps/vscode
# Debian xvfb_21.1.16-1.3+deb13u4_amd64.deb extracted beneath work/editor-deps/root
work/editor-deps/root/usr/bin/Xvfb :95 -screen 0 1280x900x24 \
  -ac -nolisten unix -listen tcp
```

`DISPLAY=127.0.0.1:95 xdpyinfo` succeeded. Actual native analysis ran on two
tracked authored C++ files `one/same.cpp` and `two/same.cpp`, each containing
manual allocation/deletion and typedef triggers. The analysis used:

```sh
CPPULSE_ANALYZER=/workspace/cppulse/analyzer-core/build-cloud-resume/cppulse-analyzer \
CPPULSE_CLANG_RESOURCE_DIR=/workspace/cppulse/work/native-deps/usr/lib/llvm-19/lib/clang/19 \
LD_LIBRARY_PATH=/workspace/cppulse/work/native-deps/usr/lib/x86_64-linux-gnu \
.venv/bin/cppulse analyze --repo /workspace/cppulse/work/editor-fixture \
  --output /workspace/cppulse/work/editor-store --format json
```

Exit 0, `analysis_status=completed`, with explicit archive-import/unverified
source limitations. It did not become a verified production assessment.
A wheel was built and installed into `work/editor-installed` independently of
the editable environment; the host invoked that installed CLI for capability,
explain and pinned SARIF calls. The separately installed wheel intentionally
had core dependencies only, no PDF/web/ML extras.

```sh
DISPLAY=127.0.0.1:95 \
XDG_CACHE_HOME=/workspace/cppulse/work/editor-cache \
CPPULSE_VSCODE_EXECUTABLE=/workspace/cppulse/work/editor-deps/vscode/code \
CPPULSE_HOST_CLI=/workspace/cppulse/work/editor-installed/bin/cppulse \
CPPULSE_HOST_WORKSPACE=/workspace/cppulse/work/editor-fixture \
CPPULSE_HOST_STORE=/workspace/cppulse/work/editor-store \
CPPULSE_HOST_REPORT=/workspace/cppulse/work/editor-host-evidence/report.json \
CPPULSE_HOST_ARTIFACTS=/workspace/cppulse/work/editor-host-evidence \
timeout --signal=INT --kill-after=10s 120s npm run test:host
```

Ten real installed-host cases passed (see `editor-evidence/host-result.json`).
The first pass explicitly unset global `NODE_PATH`; the final runner embeds
this correction in its Electron subprocess environment. The host tested
installed VSIX bytes, not checkout `dist`. Exact artifact and run hashes are
recorded in `docs/editor-vscode.md`. Source hashes and actual CLI calls are
retained alongside this checkpoint. Source hashes exclude the self-referential
checkpoint and narrative documentation.

## Limits retained

Linux x86_64/VS Code 1.105.1 only. Workspace Trust enabled by the harness.
Actual native findings are legacy observations; imported Unicode/line-ending
SARIF are client fixtures. No full current-policy assessment, complete explicit
workflow/error/cancellation UI matrix, Restricted Mode, Windows/macOS, final
combined candidate, large-data indexed queries, MCP/portable skill or developer
usefulness study is inferred. Those acceptance checks remain in the full plan.

Final README-inclusive VSIX hash is
`34a502c9f0c0728394e5e3a006e95b1a16a376561dc3966feef3767eb6c30ea8`.
A repeat run exposed a host-fixture ordering race: delayed filesystem events
from one direct source write can invalidate the next explicit source read.
The production client correctly cleared diagnostics in this case. The host
fixture now waits for its actual filesystem notification before issuing the
next read; no assertion was weakened and no arbitrary sleep was added.
The final source host run passed **10/10**, exit 0; log
`work/editor-host-final-source.log`. The fixture also closes the Unicode document before subsequent direct disk
rewrites so asynchronous document reload events cannot masquerade as a newer
edit. The host runner removes any prior requested success-report file before a
new attempt; failed attempts cannot leave a stale green receipt at that path.
