# Independent native streaming/publication review — 16 November 2026

Reviewed `metrics.cpp/.h`, `output_writer.cpp/.h` and
`test_output_streaming.cpp` without editing those source files.

The streaming JSON envelopes preserve JSON escaping through the existing
serializer, iterate metric rows by reference and avoid copying the large
metric inventory into a second whole-report object. Empty/present/unavailable
metric rows have valid separators. Output errors leave stream failure flags
set; the writer checks after flush and close before publishing. POSIX rename
preserves the previous final report when publication fails. Pending-path RAII
runs during serialization exceptions. Unicode bytes/quotes/newlines are handled
by the JSON serializer, not manually escaped. The actual tests exercise valid
UTF-8 (é); this does not qualify arbitrary invalid UTF-8 filenames or Windows
native paths. Windows `MoveFileExW` replacement was inspected only, not run.

Independent focused CTests:

```sh
LD_LIBRARY_PATH=/workspace/cppulse/work/native-deps/usr/lib/x86_64-linux-gnu \
work/native-tools/cmake/data/bin/ctest \
  --test-dir analyzer-core/build-cloud-resume --output-on-failure \
  -R 'StreamingOutputFixture|OutputWriterTest|NativeMetricsFixture'
```

**28/28 passed** in 4.61 seconds, including the 32 MiB payload under a 24 MiB
additional address-space budget, forced output-limit failure preserving the
previous report, unavailable metrics, source line endings and Unicode JSON.
Log: `work/editor-streaming-review.log`.

Review found a concrete publication-path defect in the first streaming writer:
its predictable `.findings.json.partial.<pid>.<sequence>` staging path used
`ofstream(...trunc)` and unconditional path cleanup. A preexisting staging
symlink could therefore truncate an unrelated target and then become the
published report. A preexisting empty staging directory could be deleted on
open failure. This was reproduced against the built static library in the
review-owned `work/streaming-review/` harness, without modifying production
source or user inputs. `staging-probe.log` recorded `writer_success=1` and
`victim_preserved=0`. The final report was a symlink to the altered controlled
fixture. Native owner and coordinator were notified before approval.

Resolution and final verification must be recorded below after the owner
repairs exclusive staging ownership. This initial review is not approval of
the vulnerable staging implementation. Full platform/whole-product acceptance
is not established by these focused checks.

## Exclusive staging resolution and fresh verification

The repaired writer creates a private staging **directory** exclusively with
POSIX `mkdir(...,0700)`, treats existing names as collisions, retries at most64
names, and only cleans paths beneath a successfully created owned directory.
Copy operations are deleted, avoiding duplicate cleanup ownership. Windows uses
exclusive `create_directory`; Windows ACL/platform behavior remains unexecuted.

Rebuilt the unchanged independent probe against `build-cloud-final`: now
`writer_success=1`, `victim_preserved=1`; the colliding symlink stays untouched
and the published report is a regular file. Evidence:
`work/streaming-review/staging-probe-fixed.log`. This reviews collision handling
against preexisting paths, not an adversary with the same operating-system UID.

Fresh commands (after sourcing `work/cloud-resume/environment.sh`):

```sh
cmake --build analyzer-core/build-cloud-final -j2
ctest --test-dir analyzer-core/build-cloud-final --output-on-failure
python docs/checkpoints/20261116/native/verify_actual_metrics.py \
  --analyzer analyzer-core/build-cloud-final/cppulse-analyzer \
  --resource-dir "$CPPULSE_CLANG_RESOURCE_DIR" --output work/native-staging-actual
```

All commands exited0: **147/147 CTests** (23.54seconds), plus **11 actual native
reports** passed schema and independent semantic assertions. The regression
retains a preexisting empty directory and4095 staging symlinks without writing
through or removing them. Build/test/raw logs and exact source/binary/evidence
hashes: `native/staging-final-source-evidence.json`. This resolves the reproduced
publication defect for Linux. Whole-product/platform/corpus acceptance stays open.
