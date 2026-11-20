# Job-application demo and verification

Verified 2026-11-13 on Linux. Source baseline is branch
`codex/job-application-demo-20261113`, commit
`b89dce9d22b37ef44843a68eb3373c525b4b8e94`, with uncommitted stabilization edits.
No project commits, pushes, branch updates, GitHub writes or external CI were performed.
Only isolated synthetic/test Git repositories receive local fixture commits.

## Demonstration

After the README dependency setup and builds, run `bash scripts/demo.sh` from
any directory using the script's full path, or from the checkout root as shown.
It runs the existing C++ CLI, analyzer, Git miner, predictor and report generator.
The pinned source fixture has two files, 11 physical lines, five intentional detected
findings in `intentional.cpp` and none in `clean.cpp`. Generated fixture commits
use current timestamps and an explicit automation identity, not simulated
human history. Their revision is recorded with the output.

Fresh native output: `output/demo/`: `findings.json`, `git_metrics.json`,
`risk_scores.json`, `roadmap.json`, `report.pdf`, aggregate `report.json`,
`report-text.txt`, and `fixture-revision.txt`.
The weighted per-file score is 95.5. The model is heuristic, experimental, with
10 input features, two samples and no measured F1. The PDF has seven pages.
`verify_demo.py` checks schemas with date formats, counts, identities, clean and
trigger behavior, hotspot finding counts, and readable PDF content.

## Interview walkthrough (three minutes)

1. Explain the closed CRTP/variant C++ rule set and why libclang supplies parsing.
   Run the demo and show the clean file beside intentional allocation/delete,
   typedef, enum and C-style-cast patterns. Detectors have limited coverage.
2. Open findings and Git metrics. Show repository-relative identities and the
   schema boundaries that let components run independently. Git authorship is
   a history signal, not proof of knowledge or team ownership.
3. Open risk metadata: this small fixture uses a heuristic, not a trained
   classifier. Explain the per-file health deduction, severity/age hotspot
   proxy, and the difference between ranking and validated prediction accuracy.
4. Start the API and built dashboard as described in README. Browse all sections
   and download the PDF. Explain the API envelope adapter and local CSS bundle.
5. Discuss regressions and limits: empty input is unscored; model/profile metadata
   is explicit; checkout-relative paths work; PDF dependencies are constrained.
   Docker execution and cross-platform installation remain unverified here.

## Actual local checks

`bash scripts/check_local.sh` is the shared local path. It runs root tests,
CMake builds/CTest for analyzer and CLI, `pytest -v --cov=src tests/` separately
in each Python component, then dashboard tests and production build. Logs are
under `review/logs/`. API/browser verification is separate:
`python scripts/verify_web_demo.py` uses real fresh artifacts, HTTP routes,
Vite production preview proxy, actual PDF response, and browser navigation.

Environment specifics and resolved Python dependencies are retained in
`review/environment.sh` and `review/python-freeze.txt`; that shell file contains
paths for this cloud workspace, not an installable distribution.
Compiler GCC 14.2, libclang 19.1.7, CMake 3.31.6, Python 3.12.14, Node 24.22.1,
npm 11.9, Chromium headless shell 156.0.8078.79, Poppler 26.05.
CMake/C++ development packages were downloaded from the configured Debian
snapshot and extracted into a user-owned adjacent `toolchain/` prefix because
system package installation was unavailable. SHAP was built using GCC.
WeasyPrint 61.2 requires the added `pydyf==0.10.0` constraint for this workflow.
Playwright's browser download failed; the configured Debian headless-shell
package plus its matching existing Chromium runtime resources was used instead.

Docker executable and `/var/run/docker.sock` are absent. The Compose integration
script exits 2 with an explicit blocked result. **Compose did not pass.**
Source fixes use root Python build contexts so schemas are included, host output
bind mounts instead of an invisible named volume, a PDF one-shot service, and
waiting for each producer's actual exit status before checking running services.
These need execution on a Docker host. The host input must contain `.git`;
the default integration fixture now creates it explicitly.

## Scope and limitations

The newer `origin/main` (`82120d2`) was inspected without merging. Its
shallow-history helper/tests and PDF native-import error handling informed
selected fixes. Its scoring rewrite and regenerated examples were not imported.
All preexisting assurance drafts remain context; collect/assess/evidence-policy,
certification, hosting and broad production backlog were not implemented.

Historical example counts disagree internally (see README audit); they are
retained and cannot support benchmark/accuracy claims. Ranking and effort/impact
estimates remain experimental. The synthetic case proves component integration,
not detector recall, prediction accuracy, performance on large repos or safety.
Default scoring excludes MISRA, while detector selection is independently
configured. The legacy hotspot `complexity_score` field is severity/3, not a
measured complexity metric. Watch repeats full analysis. Concurrent writers to
the same output folder are not supported. CLI is checkout based; it is not a
portable installed package. Browser coverage is one Linux Chromium engine.
Dependency deprecation warnings and a dashboard bundle-size warning remain.
