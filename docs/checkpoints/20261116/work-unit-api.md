# Private work-unit catalog HTTP continuation slice

The optional `GET /api/v1/work-units` endpoint reads an explicitly selected
existing catalog through `CPPULSE_WORK_UNIT_CATALOG`. It does not create a
catalog, publish runs, execute native work, follow latest pointers or claim
source freshness. Existing API-key authentication applies.

Required query parameters are `run_id` and `manifest_sha256`. Optional
`page_size` is 1–200, `outcome` is a supported private work-unit outcome, and
`cursor` is the opaque base64 token from the preceding response. A cursor binds
run/hash/filter/page size and transfer-byte limits; mixed queries fail 422.
Rows are finite summaries, not full findings, and default pages remain within
1 MiB. The response labels the protocol private and retains the no-current-
assessment limitation. Missing configuration returns 503, unavailable or
mismatched catalog state fails explicitly. The API opens SQLite in read-only
mode and sends `Cache-Control: no-store`.

Four actual FastAPI TestClient checks cover direct catalog/API equality,
second-page ordering, pin/filter/size cursor mismatches, auth, malformed input,
read-only byte stability, absent-parent preservation, 80 Unicode-rich rows
across byte-bounded pages, and rejection of an externally corrupted oversized
row. Initial three tests failed because read-only catalog construction was
absent; they passed after the scale owner implemented it. No acceptance test
was removed or skipped.

Independent review of the scale implementation found unbounded stored payload
reads, count-only query limits, symlink ancestors, and an exact page-size
boundary. The scale owner repaired those issues with store regressions.
The optional route initially introduced an eager dependency into minimal
packaged rendering; existing packaged-report regression caught it. The route
now imports the catalog backend lazily only when configured reads occur.

Commands from `/workspace/cppulse`:

```sh
.venv/bin/python -m pytest -q tests/test_work_unit_api.py
.venv/bin/python -m pytest -q report-engine/tests/test_packaged_report.py tests/test_work_unit_api.py
.venv/bin/python -m pytest -q report-engine/tests tests/test_work_unit_api.py
CPPULSE_WORK_UNIT_NATIVE=/workspace/cppulse/analyzer-core/build-cloud-resume/cppulse-analyzer \
LD_LIBRARY_PATH=/workspace/cppulse/work/native-deps/usr/lib/x86_64-linux-gnu \
.venv/bin/python -m pytest -q tests/test_work_unit_runtime.py tests/test_work_unit_store.py tests/test_work_unit_draft_contracts.py
```

Final checks: API **4/4 passed**; packaged renderer plus API **9/9 passed**;
complete report-engine plus API **129/129 passed** (20 dependency deprecation
warnings, no skips). Ruff and Black checks passed for the new route/tests.

Result logs are under `work/`: `work-unit-api-tests-final.log`,
`editor-api-packaged-check.log`, `editor-report-regression-final.log`,
`editor-scale-review-tests.log`. The first independent scale run passed56/56
with the actual native binary and no skips; later hardening is separately
checked by its owner. This is not the full findings/history index, cache
closure, scale benchmark or P5 completion.

Final independent combined native work-unit/runtime/store/private-contract/API
review passed **78/78** with no skips in 15.29 seconds, after the store owner's
final hardening and malformed-checkpoint/postflight-input changes. Log: `work/editor-scale-review-final.log`.
