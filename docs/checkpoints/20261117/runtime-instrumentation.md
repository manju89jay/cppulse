# Original FR-EVD-08 closure

Original criterion: Scope runtime evidence to the consumer binary and actual instrumentation. A prebuilt uninstrumented library requires an explicit limitation.

Exactly FR-EVD-08 moved open -> verified after independent review (`work/runtime-review7/memory-and-instrumentation44/review.json`). The 187 definitions and P0–P14 are unchanged. Ledger before/after and definition SHA are in `work/evidence-scope40/fr08-ledger-audit.json`; counts are10verified/113open/62active/2blocked. FR-EVD-02 and M5 remain open.

The installed harness `work/evidence-scope40/fr08-installed/run_installed.py` executes against wheel00846, with no repository imports, producer rerun or network. It re-normalizes and persists three exact retained genuineGNU14.2/binutils2.44/CTest3.31.6 runs, validates schemas, and invokes installed public JSON and HTML reports. Actual wrapper `work/heavyweight-jobs/fr08-installed40/record.json` exits0, all six report commands exit0; 301 original input pins and installed233payloads are stable. Worker36checks and independent614component/artifact checks remain distinct scopes.

The original ar-built `libprebuilt.a` signature, receipt and exact link-input SHA are verified; it is not inferred from an object filename. The clean binary with incomplete library instrumentation stays unsupported, the credible observed sanitizer failure remains failed, and both show an explicit unverified-component limitation. The substituted binary yields unsupported with no exercise proof, not a claimed hard exception. No producer authentication, runtime dependency closure, additional platform/sanitizer support or full187-item acceptance follows.

Current canonical proof is `work/evidence-scope40/fr08-canonical-proof.json` (436source/material pins), accepted by the unchanged proof protocol. Current source changes in the independent work-unit component have not yet been packaged; this FR08 scope uses matching unchanged consumer interfaces from00846 and makes no current whole-source claim.

To inspect a retained public result, use the actual `commands.json` or `case-results.json` in that packet for run ID and manifest SHA, then select a new output path:

```sh
PYTHONPATH=/workspace/cppulse/work/installed-provenance38/installed:/workspace/cppulse/work/closure-fr3/dependencies \
  work/cloud-resume/installed-query20/core-venv/bin/python -m cppulse report \
  --input work/evidence-scope40/fr08-installed/asan-prebuilt-gap/store --evidence \
  --run-id RUN_ID --manifest-sha256 MANIFEST_SHA256 --format html --output /tmp/prebuilt-instrumentation.html
```

Strict command `.venv/bin/python scripts/verify_delivery.py --require-complete --output work/evidence-scope40/require-complete-after-fr08.json` actually returns2: stale older nine-criterion whole-source proof for `python/cppulse/work_unit_analysis.py`. Its log/command record is preserved; no JSONresult is created on invalid proof. A combined fresh candidate/qualification is queued after this source freeze, rather than retagging old output or weakening the verifier. Even when source evidence is refreshed, the remaining177 items keep the full program incomplete.
