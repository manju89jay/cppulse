# cppulse VS Code preview client contract 1.0

This is an explicit finite client of public cppulse commands. It has no evaluator
or policy/scorer implementation. Production code follows this contract only
after its fixture tests and the backend capability gate pass.

## Selection and execution

Activation only registers UI/commands/listeners; opening a folder runs no process,
build, test, collector, version probe or analysis. Explicit CLI actions require a
trusted local filesystem workspace. Opening a user-selected SARIF document is a
separate read-only operation and never runs a CLI command.

The configured executable is a single program and optional prefix arguments are
an array. Use child_process.spawn with shell=false; there is no shell command
template. Each action probes `cppulse capabilities --format json`, validating
contract1.0, required methods, snapshot2.0, SARIF2.1 and column semantics. Unknown
versions/capabilities produce actionable errors rather than inferred support.

`explain --store STORE` resolves the latest attempt once, or accepts both
`--run-id ID --manifest-sha256 SHA`. A half pin pair is invalid. After receiving
snapshot_view2.0 the client verifies its run/manifest/source envelope and invokes
`export-sarif --store STORE --run-id ID --manifest-sha256 SHA` with those exact
pins. SARIF owning/input run/manifest and source must agree with the selected
snapshot. No second unpinned read may populate diagnostics.

The preview bounds one stdout/stderr response to16MiB, one selected snapshot to
20,000 diagnostics and selected source reads to16MiB per file. Overflow is
explicit incomplete/error state, never a truncated clean view. These finite
limits are not evidence of indexed large-project support.

## Locations, freshness and presentation

Only canonical repository-relative source paths beneath the explicitly selected
workspace root are mapped. Reject absolute paths, URI schemes, traversal,
malformed URI escapes and symlink escapes. Equal basenames retain independent
URIs and every occurrence survives. Only matching local source bytes receive
current diagnostics; dirty unsaved or changed disk documents clear applicable
diagnostics and show a stale state. Historical snapshots stay historical.

SARIF unicodeCodePoints are converted to the editor's zero-based UTF-16 positions
using actual matching source text, including non-BMP characters. UTF-16 SARIF
units are honored when declared. Native UTF-8 byte coordinates are not silently
reused as editor columns. Missing columns remain line-only diagnostics with an
explicit note. Exact score display strings are displayed without floating-point
conversion or gate recomputation.

Run status, input verification, contexts, policy gate, control reasons, gaps,
limitations and evidence descriptors remain visible. Hashes identify bytes and
do not authenticate producers. Report/evidence links open only checked local
paths, with artifact hashes verified before opening. No arbitrary command or
network URI supplied by a result becomes an executable editor link.

## Lifecycle

Each request receives an increasing generation. Superseded reads/results cannot
replace current UI. Cancellation/timeout stops the spawned process tree on
qualified platforms, retains backend partial/cancelled facts where supported,
and clears any implied current green state. Known failed and incomplete exits
remain distinct. Report rendering success does not change the stored gate.

The clean real-host tests install the actual VSIX into fresh user/extensions
directories and load those installed bytes in a real VS Code extension host.
Pure contract tests complement those checks, not replace them. Unsupported
hosts and missing integration evidence remain open; preparing a VSIX is not
Marketplace publication or complete M7 delivery.
