# S3 installed local core technical review

Accepted for the exercised Linux x86_64 environment. This is a local development
candidate, not publication, certification or a human usefulness review.

The canonical Python namespace replaces implementation copies behind compatible
`src.*` aliases. Schemas/templates are package resources. Core JSON/HTML runs
without ML, PDF, API, browser or Node packages. The installed console dispatcher
uses argument vectors and a separately qualified native analyzer; the original
C++ checkout CLI remains tested. Configuration, doctor, local redacted diagnostics,
extension scaffolds and shared verification/candidate preparation are available.

## Actual checks

```sh
source review/environment.sh
python scripts/check_local.py --output-dir review/autonomous/logs/s3-final-shared-checks
python scripts/package_candidate.py --native-archive output/packages/cppulse-native-0.2.0.dev0-linux-x86_64.tar.gz --wheelhouse review/autonomous/wheelhouse --output-dir output/candidates/s3-preview
bash scripts/demo.sh output/s3-demo
python scripts/verify_web_demo.py --data output/s3-demo --evidence review/autonomous/s3-web
```

All 15 final shared checks passed: root364, analyzer77, Git90, predictor95,
report95, dashboard37 and CLI20 tests, plus formatting/generated checks and the
production dashboard build. Canonical Python coverage: 91.28%, 90.12%, 93.95%.
Candidate corrective gate: 25 tooling tests plus Black/Ruff. This separate gate
covers output-directory overlap and vendored wheel metadata corrections made
after the full runner started; it is not an invented rerun of every suite.

Independent review also corrected lost failure logs, unrecorded component exits,
historical snapshot rendering, protected snapshot destinations, concurrent export
temporary names, request-bound API snapshots, stale PDF fallback and zero-test
CTest success. Initial failures and final logs are retained.

The native archive's six actual qualification cases pass. Installed RUNPATH is
only `$ORIGIN/../../lib/cppulse`; fmt/spdlog and matching Clang19 builtin headers
are bundled with notices. Host libclang/LLVM, system runtime and compiler headers
remain explicit dependencies. `BUILD_TESTING=OFF` builds without GoogleTest;
the shared runner forces tests on and uses `--no-tests=error`.

## Actual installed-artifact proof

The candidate contains 18 core distributions, 51 inventoried files and 52 checksum
entries. Its wheel SHA-256 is
`bb6f7b7c00eb876d2655bab50edbe75b788ddf2349aa79120b9c562901433bcc`.
The native archive SHA-256 is
`56aaf5caf73068663dff9b1751159985ba5254ace96da0f8003ec4d24624a419`.

Candidate directory:
`output/candidates/s3-preview/cppulse-0.2.0.dev0-linux-x86_64-candidate`.
The builder's source identity describes its frozen preparation point; later
review documentation does not change those candidate bytes.

The exact candidate wheel/core closure and native prefix were copied outside the
checkout. The original checkout path was then temporarily absent while a fresh
venv installed entirely from those local wheels. It ran doctor/init/config,
analysis, HTML/JSON reports and diagnostics from an unrelated directory. Native
paths contained spaces, input/output names contained quotes and shell-like text,
optional packages were absent, Node was not visible and ordinary HTTP proxies
pointed at a closed local port. This is not a hostile-code/network sandbox.
Missing PDF/web requests returned actionable errors. No project build command
ran as part of analysis.

The installed smoke produced three intentional findings in two synthetic files,
none in its clean file, independently checked totals and health96.5. A separate
external application built against clean copies of the pinned fmt/utfcpp sources
also parsed in its exact compilation-database context: two findings, one source
file, no Git history. Its selected CTest passed before analysis. This is not the
full upstream test suite or a detector accuracy benchmark.

The checkout was restored and refs compare byte-for-byte with the starting ref
inventory. Proof summaries/transcript and byte binding are in installed/; full
external evidence is `/workspace/scratch/b3d4e6fff494/s3-installed-final`.

The original checkout demo still produces five findings, health95.5 and a readable
seven-page PDF. Its built dashboard/API/PDF/navigation browser checks passed.
API requests now resolve one run; incomplete attempts return409, corrupt stores
503 and missing current PDF404. Legacy flat mode remains explicit.

## Support limits

Qualified here: Python3.12.14, Linux x86_64/glibc2.41, GCC14.2, libclang19.1.7,
CMake3.31.6, Node24.22.1 for dashboard builds. Python3.11 is declared by packaging
but not installed-artifact qualified here. Docker availability was checked and
blocked; Compose was not run. Windows/macOS, other native runtimes, broad accuracy,
large-input limits, memory quotas and human usefulness remain unqualified.
The analyze workflow archives source binding conservatively as unverified;
explicit build/test collection and policy assessment are subsequent stages.
