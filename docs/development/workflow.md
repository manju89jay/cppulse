# Local development and candidate review

`tools/dev.py` is the source-checkout entry point for development. It reuses
CTest, component pytest suites, the dashboard toolchain, candidate scripts and
the public cppulse package. It creates local evidence and has no publishing,
Git-write, deployment or notification command.

Install the project's development dependencies and the optional components
needed by the checks you select. Compiler/libclang/CMake and Node remain
external developer tools. PDF integration also needs the PDF runtime and the
development-only `pypdf` validator. None of these development checks adds a PDF
or Node requirement to the headless installed core.

```bash
python tools/dev.py doctor
python tools/dev.py verify --scope changed
```

Doctor inspects executable availability and versions; it does not execute a
project's CMake files, build commands, tests or arbitrary recipes. Missing
required tools produce exit 2. Docker is reported separately and is only used
when explicitly selected.

Changed-scope verification currently uses the conservative source closure. It
does not pretend that dependency-aware changed-test selection is implemented.
Every selected command, actual exit, log and source identity is retained under
a new `review/development/` directory. Use `--format json` for a machine result,
`--output-dir` for a new explicit location, or `--plan` to inspect commands
without running them. A plan's recorded execution exit is null, never a passed
verification result. Existing evidence directories are not overwritten.

## Checks and prerequisites

The shared runner checks native formatting, Python formatting/lint, the full
delivery-scope ledger, generated metadata, root tests, analyzer CMake/CTest,
Python component tests with legacy and canonical coverage, dashboard tests and
production build, CLI CMake/CTest, and the selected native integration demo.
The native integration demo is labeled synthetic and checks contracts, totals,
paths and actual PDF text. Missing PDF development capability blocks that
check. It does not establish upstream-library accuracy or production readiness.

Native formatting prefers `clang-format-19` on PATH, then `clang-format`. Select
an explicit formatter with `--clang-format PATH` or `CPPULSE_CLANG_FORMAT`; the
selected executable and its actual output remain in the check record. Formatting
is check-only. Native fixtures and generated build trees are excluded, while
source and test code are checked. Python checks cover canonical implementations,
compatibility shims, and changed script/test/tool files.

For an explicitly limited CI job, select its actual scope:

```bash
python tools/dev.py verify --scope changed --section python --component git-miner
python tools/dev.py verify --scope changed --section native
python tools/dev.py verify --scope changed --section integration
python tools/dev.py verify --scope changed --section dashboard
python tools/dev.py verify --scope changed --section generated
python tools/dev.py verify --scope changed --with-docker
```

Subset records state their selection and cannot establish full verification.
The existing GitHub and GitLab configurations call these same local commands.
Editing those definitions is not evidence that their remote jobs ran. GitHub's
integration definition requests Compose; GitLab's native integration does not
claim a Docker-enabled runner. Component coverage writes both canonical JSON
for the actual coverage gate and XML for existing CI report consumers.

GitHub push and pull-request checks target `master`. The formatting job
pins clang-format 19.1.7, Black 24.1.1 and Ruff 0.2.1. It compares the
fetched PR base and head through `CPPULSE_FORMAT_BASE` and
`CPPULSE_FORMAT_HEAD`. The shared formatter combines that merge-base diff with
staged, modified and untracked local Python files under `scripts`, `tests` and
`tools`. Supply both refs to reproduce this selection. On a push or manual
dispatch, `CPPULSE_FORMAT_ALL_TRACKED=true` selects all tracked Python files
in those directories alongside local edits. Unset or `false` keeps the local
selection when no PR range is supplied.

### Hosted source tests and historical assurance

`--section root-public` keeps the source contracts and actual producer tests in
the hosted lane. Its recorded pytest command names the historical comparisons
checked separately by the default `root` section and `--scope full`.

| Historical test | Exact local input |
| --- | --- |
| `test_elf_runtime.py::test_selected_actual_native_metadata_without_execution` | Retained old native TU-buffer analyzer at the path, SHA-256 and size asserted in the test |
| `test_generated_rule_registration.py::test_generator_metadata_preserves_existing_public_v2_contract` | Retained candidate93 installed package and the qualified query20 interpreter and dependency closure selected by the test |
| `test_native_normalizer_streaming.py::test_exact_output_parity_with_preserved_prechange_normalizer` (two cases) | `work/native-normalizer32/analysis-before.py` from the original qualification |
| `test_predictor_input_projection.py::test_public_predictor_preserves_frozen_legacy_results_without_eager_native_load` | Candidate69 manifest and exact installed old69 wheel in its registered isolated prefix |
| `test_store_heads_v3_review.py::test_real_installed_old_wheel_fails_closed_and_reads_explicit_export` | Registered older typed-service reader environment referenced by the test |

Use the unchanged complete local profile with the exact authorized archived
inputs for historical assurance. Keep those inputs in private custody. A
runner's fresh native producer does not replace any historical comparison.

For live health tests, run the native section from the checkout, then use
`tools/register_ci_native.py` with its `development-results.json` and the
matching Clang resource directory. Set `CPPULSE_CI_NATIVE_REGISTRATION`,
`CPPULSE_WORK_UNIT_NATIVE`, and `CPPULSE_CLANG_RESOURCE_DIR` before executing the
nine cases. The historical health invocation retains its original binary guard
when no current registration is supplied.

Live evidence tests also require genuine producer inputs. The workflow uses
`scripts/demo_coverage.py` to produce an LCOV run and binds its immutable
identity and CLI through `CPPULSE_POLICY115_INPUTS`.
`scripts/prepare_ci_evidence.py` produces the twelve sanitizer cases and the
selected CTest/JUnit, header and archive runs. It reopens the coverage run and
registers the actual producer outputs in `CPPULSE_EVIDENCE116_INPUTS`. The
Python contracts job runs in a digest-pinned Python 3.11 Debian environment on
the Ubuntu runner. It installs the GCC, GNU binutils, libabigail, and Clang-Tidy
versions required by the actual producer tests. The selected hosted lane
builds the Git 2.52.0 provider used by branch-delivery tests from the pinned
public release archive. The selected hosted lane does not establish P14.

## Full candidate verification

Full verification cannot filter out sections or components. It also requires a
prepared candidate, its exact extracted native prefix and a configured reference
benchmark suite. Missing inputs or unsupported host capabilities are blocked;
they cannot be omitted to obtain a successful full result.

```bash
python tools/dev.py verify --scope full \
  --candidate PATH/TO/CANDIDATE \
  --native-prefix PATH/TO/EXTRACTED/NATIVE/PREFIX \
  --benchmark-suite PATH/TO/reference.json \
  --output-dir review/my-new-full-verification
```

The candidate checksum inventory is revalidated, its source identity must match
the current tree, and the native prefix must match the archive's actual files.
The existing installed smoke driver installs the candidate's offline core into
a separate environment and checks its origin and real commands outside the
checkout. The current driver is POSIX-only; other hosts remain explicitly
unqualified. Verification records never briefly claim success while their
required package/measurement stages are pending. Concurrent source edits make
the run incomplete and require a fresh run on a stable tree.

Full success covers the recorded checks and host. It does not certify the tool,
establish all platforms or close every production requirement. The separate
[delivery ledger](../plans/production-delivery-ledger.json) retains the complete
production scope and independent acceptance evidence.

## Extension drafts and measurements

```bash
python tools/dev.py new-rule CPP-MEM-004 --destination PATH/TO/EXISTING/DIRECTORY
python tools/dev.py new-adapter example-tool --destination PATH/TO/EXISTING/DIRECTORY
python tools/dev.py new-policy example-policy --destination PATH/TO/EXISTING/DIRECTORY
python tools/dev.py benchmark --suite PATH/TO/suite.json --output-dir review/new-measurements
```

Generators create explicitly incomplete drafts and never activate them. A rule
identifier is normalized to a directory slug; the draft still needs reviewed
metadata, behavior and meaningful positive/negative fixtures before registration.

The versioned benchmark recipe lives under `tools/contracts/`. It declares
literal argv, a working directory relative to the suite file, repetitions and a
wall-time bound for each case. The runner executes those commands only when
explicitly selected. It preserves known failures, unavailable tools, timeouts
and cancellation instead of producing zero-time successes. It records wall
time, and wait4 CPU/peak RSS where available, with explicit resource scope.
Peak RSS is not an aggregate of concurrent process memory. Unsupported resource
measurements remain null.

`--suite reference` resolves `tools/benchmarks/reference.json`. It is blocked
until that representative suite exists. A custom quick measurement does not
establish the required cold/warm/edit semantic equivalence, 1K/10K/100K tiers,
reference-host budgets or scalability. No numerical release budget is invented
by the measurement runner.

## Package and review exact artifacts

```bash
python tools/dev.py package --candidate \
  --native-archive PATH/TO/NATIVE.tar.gz \
  --wheelhouse PATH/TO/LOCAL/WHEELS \
  --output-dir review/new-candidates

python tools/dev.py release --dry-run \
  --candidate PATH/TO/CANDIDATE \
  --verification PATH/TO/development-results.json
```

Packaging reuses the [local candidate builder](candidate.md), including its
offline dependency closure and source-change checks. Preparation is not installed
verification. Release dry-run requires a passed full record for those exact
candidate and source bytes, checks command-log hashes again, and writes a local
review result. It cannot publish, tag, push or deploy. Add `--require-complete`
only for the final full-program gate; ordinary development must still be usable
while production requirements remain open.

Developer exits are 0 for a completed selected operation, 1 for known failed
checks, 2 for invalid/blocked operations and 130 for explicit cancellation. These
developer-tool exits are separate from the product CLI's policy/incomplete
assessment contract. Passing a unit or configuration test does not qualify an
unexecuted installed package, CI job, platform or Docker workflow.
