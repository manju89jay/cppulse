# cppulse stabilization handoff — 2026-11-13

Implementation and verification completed in this cloud checkout. All project
changes remain uncommitted. No project commit, push, branch/ref update, GitHub
write, merge, deploy, publication, messaging or new external CI service occurred.
Local Git commits exist only in isolated test/synthetic input repositories.

Baseline and current HEAD: `b89dce9d22b37ef44843a68eb3373c525b4b8e94`.
Branch: `codex/job-application-demo-20261113`.
Read-only main inspection: `82120d26b51f99b64068f9d66f6e000fcaee97c2`.
Workspace: `/workspace/scratch/b3d4e6fff494/cppulse`.

## What changed

- Repository-relative analyzer identities; legacy absolute/relative feature joins.
- Physical LOC counts corrected for empty and newline-terminated files.
- API envelope adapters, factor objects, nested health, silo dates and finding pagination reconciled with React; local Tailwind build removes runtime CDN dependency.
- Null/no-data health; real model/profile/feature-count/formula metadata; heuristic F1 unset; zero-score files omitted from hotspots; experimental labels visible.
- Checkout-based CLI component discovery, caller-relative input/output/config paths, explicit profile precedence, JSON/PDF dispatch and successful subprocess logs.
- Main's shallow-Git boundary helper/tests selectively reused, not merged. WeasyPrint native-import errors normalized and compatible pydyf version pinned. API/PDF inputs validate contracts.
- Compose root Python contexts include schemas; host binds expose outputs; analyzer command/runtime libraries corrected; PDF one-shot and successful-job exit handling added. Docker execution remains unavailable.
- Shared local checks, transparent synthetic fixture, artifact validation, real API/browser integration, README, portfolio walkthrough and D28–D30 decisions.

## Actual final results

| Check | Actual result | Evidence log |
|---|---|---|
| Root schema/structure tests | 16 passed | logs/root-tests.log |
| Analyzer CMake build + CTest | 62 passed | logs/analyzer-tests.log |
| Git miner pytest | 78 passed, 91% coverage | logs/git-miner-tests.log |
| Predictor pytest | 76 passed, 91% coverage | logs/predictor-tests.log |
| Report engine pytest | 77 passed, 94% coverage, no skips | logs/report-engine-tests.log |
| Dashboard Vitest + production build | 33 passed; build passed | logs/dashboard-tests-build.log |
| CLI CMake build + CTest | 17 passed | logs/cli-tests.log |
| Native demo/contracts/counts/PDF | Passed | logs/native-demo.log |
| Actual HTTP API + built dashboard | All six routes via preview proxy, PDF and every navigation section passed; no page errors | logs/web-integration.log |
| Caller-relative CLI paths/config/profile overrides | Passed from demo/ working directory | logs/cli-relative-profiles.log |
| PDF rendering | Seven pages rendered with Poppler and visually reviewed | report-1.png through report-7.png |
| Ruff on modified core Python and verification scripts | Passed | logs/ruff.log |
| Whitespace diff check | Passed | logs/diff-check.log |
| Docker / Compose | BLOCKED: no executable or socket; integration exits 2 | logs/docker-check.log, logs/compose-integration.log |

The final shared invocation was `bash scripts/check_local.sh`. It runs
`python3 -m pytest -v tests/`, CMake configure/build/CTest on both native components,
`python3 -m pytest -v --cov=src tests/` within each Python component, and
`npm test && npm run build` within dashboard. The demo command was
`bash scripts/demo.sh`; live integration was `python3 scripts/verify_web_demo.py`.
PDF pages were rendered with
`pdftoppm -scale-to 900 -png output/demo/report.pdf review/report`.
All commands used the activated environment recorded in `environment.sh`.
Additional relative-path/profile test command and assertions are retained in
`check-relative-profiles.py` (run using that same environment).

## Environment

Linux x86_64, glibc 2.41, GCC 14.2, CMake 3.31.6, libclang 19.1.7,
Python 3.12.14, Node 24.22.1, npm 11.9.0, Chromium headless 156.0.8078.79,
Poppler 26.05. `environment.json`, `debian-packages.txt`, `python-freeze.txt`
and `node-dependencies.txt` record exact details. The CMake/native dependencies
were extracted into the adjacent user-owned `toolchain/` prefix, not installed
system-wide; binaries/virtualenv are not included in the review ZIP. On a normal
Linux host install the README prerequisites and component requirements.

## Demo and artifacts

In this existing workspace:

```bash
cd /workspace/scratch/b3d4e6fff494/cppulse
source review/environment.sh
bash scripts/demo.sh
```

For a new checkout, apply stabilization.patch to the baseline, follow README's
native setup, activate the virtualenv and use the same demo command.
The patch includes new source files as well as tracked modifications and was
checked for applicability to a clean export of the baseline.

Fresh outputs are in `output/demo/`: four schema-validated JSON documents,
aggregate `report.json`, `report.pdf`, extracted PDF text, actual synthetic
fixture revision, automation commit metadata and source SHA-256 manifest.
The fixed synthetic source is `demo/fixture/`. It contains two files and 11
physical lines. There are five findings in intentional.cpp, none in clean.cpp,
health 95.5 (dashboard rounds to 96), one positive hotspot, two history metrics,
and heuristic experimental ranking. The PDF has seven readable pages.
Generated fixture Git IDs and actual timestamps vary; no synthetic Git objects
are included in the ZIP or uploaded to a Git service.

The three-minute interview walkthrough is in
`docs/portfolio/demo-verification.md`; the application overview and README
reflect this run. Screenshot: dashboard-overview.png. Real HTTP responses:
api-responses.json; rendered section text: dashboard-sections.json.

## Remaining limitations

Compose source is corrected but unexecuted. Windows/macOS installation, broad
rule accuracy, calibrated predictions, large-repository performance and safety
or production suitability are not established. Ranking, SZZ/keyword labels,
health weights, effort/impact estimates and global factor proxies remain
experimental. Health is weighted findings per merged file, not KLOC or evidence
coverage. All detectors register by default; the scoring profile is separate
from detector selection. Watch repeats full analysis; shared output directories
do not support concurrent writers. Dependency deprecation and JS bundle-size
warnings remain. The CLI is source-checkout based, not a portable package.
Historical example arrays disagree with their category/severity totals; README
records the audit and does not reuse those artifacts as benchmark evidence.
The proposed evidence-policy product, certification, hosting and production
backlog remain outside this task.
