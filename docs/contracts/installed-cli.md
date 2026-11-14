# Installed local CLI contract

> **Historical S3 contract proposal, with superseded gate exits.** The original development description below is preserved. Its old public-exit table and instruction for future gates do not govern the implemented S7 evidence workflows. Use the [current public workflow contract](public-workflows.md#results-and-exits) and [public CLI guide](../development/public-cli.md#exit-codes-and-verification-boundary). Installed acceptance applies only to the exact candidate bytes and recorded platform; this proposal does not qualify later source, Docker or other platforms.

Development target for S3; availability requires its installed-artifact tests.
The existing checkout C++ CLI remains supported and tested separately. The
Python `cppulse` console entry point provides installed orchestration over the
same native analyzer and canonical component implementations. It never searches
the source checkout for installed resources.

## Configuration

Order: explicit command options, selected repository configuration, documented
defaults. `--config` selects exactly one file; otherwise discover
`.cppulserc.yml`, `.cppulserc.yaml`, then `.cppulserc.json` in the selected
repository. Paths explicitly supplied on the command line are relative to the
invocation directory, resolved before subprocess execution. Repository config
selection never executes commands. `init` creates an editable JSON configuration
and refuses to overwrite it. `config` prints effective settings and their source.

The installed analyzer resolves from an explicit `CPPULSE_ANALYZER`, then
prefix-relative `share/cppulse/native-install.json`, then `PATH`. An explicit
`CPPULSE_NATIVE_PREFIX` selects another native prefix. Invalid explicit settings
fail visibly rather than silently falling back. Native metadata is validated;
referenced files remain inside its prefix and must not traverse symlinks.
`doctor` reports actual availability, target compatibility and missing optional
features. Descriptive host requirements are never installation commands.

## Process and output boundaries

Subprocess commands use argument vectors and `shell=False`. Analysis does not
execute the target project's CMake/build/test commands. Those operations belong
to a separately selected collection recipe. Machine output goes to stdout;
diagnostics go to stderr. Optional PDF, web/dashboard and ML dependencies do not
become requirements for JSON/HTML analysis. Ranking remains experimental.

## Current S7 check exits

The implemented `check --policy` and `check --findings` use these outcomes:

| Exit | Current check meaning |
|---|---|
| 0 | Selected gate passed |
| 1 | Selected gate has a known failure |
| 2 | Invalid command, request, selector or unsupported contract/version |
| 3 | Insufficient, stale or unverified evidence, including an operational/integrity gap |
| 130 | Operation cancelled |

Collection/baseline/comparison completion and historical rendering/export success are separate from a passing check. Consult the current workflow contract above for their operation-specific exits. Legacy analyze/report/watch behavior remains separate.

## Historical S3 proposed exit table — obsolete for S7 gates

The original table and future-gate instruction below remain historical text; they are superseded by the current S7 table above.

## Public exits

| Exit | Meaning |
|---|---|
| 0 | Requested operation completed; this alone is not a policy pass |
| 1 | Runtime or tool failure, including missing required optional capability |
| 2 | Invalid command, configuration, contract or unsupported format/version |
| 3 | A requested finding-regression or policy gate failed |
| 4 | Requested assessment lacks usable required evidence |
| 130 | Operation cancelled by the user |

Future gate commands must use these distinctions. The native compatibility
commands retain their existing exit behavior. A collector can complete while
recording an observed test failure; the assessment determines the selected gate.

Diagnostic bundles are explicitly requested local files. Their default content
is version/availability/configuration summaries with paths and sensitive keys
redacted. They do not automatically include source, command logs, environment
variables or credentials and are never uploaded by cppulse.
