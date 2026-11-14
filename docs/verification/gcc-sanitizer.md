# Observed GCC sanitizer checks (experimental)

This local producer records a finite selected C++ input, direct compilation,
object inspections, final linking and actual CTest execution. The fixtures are
**explicitly synthetic**: their overflow and race branches are intentional.
They are not findings attributed to an upstream project or an accuracy benchmark.

## Reproduce

Use GCC/G++ 14.2.0, GNU binutils `nm`/`readelf` 2.44, CMake/CTest 3.31.6 and
Python 3.12 with cppulse's core dependencies. This first adapter is qualified only
for Linux x86-64, little-endian ELF64, unstripped, non-LTO direct argv. In the
current cloud workspace, the recorded tool/dependency setup is
`review/environment.sh`:

```sh
source review/environment.sh
PYTHONPATH=python .venv/bin/python scripts/demo_sanitizers.py \
  --sanitizer all --scenario all --output output/sanitizer-demo
```

`--fixture` selects the fixture directory explicitly. The same script can run
outside the checkout using an installed core package, without `PYTHONPATH`.
`--collect-only` stops after actual observations; `--resume-batch <summary.json>`
normalizes the original manifest-SHA-pinned observations. Existing derived runs
are reverified and reused. This command executes trusted selected local code;
it is not a sandbox.

The command writes `latest-demo.json`, a unique batch directory and a RunStore.
Each case has original and derived run IDs, original manifest SHA-256 pins,
retained raw stdout/stderr, inputs, object/binary files, JUnit, LastTest.log,
collection plans and typed facts. Derived snapshots preserve the original
selected source, configuration digest and artifact descriptors/bytes. A
successful collection process is not a sanitizer or policy pass.

## What the producer establishes

1. An explicit compiler-version receipt and the actual compiler file hash match
   compile and link executions. One selected source is bound to each fresh
   object output, including source-byte identity and before/after material facts.
2. `nm -u` undefined **data/check** symbols intersect actual
   `readelf -h -S -r -W` executable `.text` call relocations. Init/version symbols,
   debug/data relocations, flags, runtime linkage or symbol-name strings alone
   cannot prove an object was instrumented.
3. The actual link consumes those object bytes. Compile, link and file-inspection
   commands must run in the observed workspace root; their relative operands
   cannot name different unlisted files in a subdirectory. Final ELF inspection
   (`readelf -h -S -d -s -W`) records the selected sanitizer's `DT_NEEDED` runtime:
   `libasan.so.8`, `libubsan.so.1` or `libtsan.so.2`. The actual full symbol table
   also rejects known custom sanitizer default-options, suppression/report hooks
   and report-redirection APIs as unsupported configurations.
4. CTest's version, inventory, JUnit and structurally parsed LastTest.log bind
   non-skipped selected cases to the actual binary-input bytes. A different plain
   binary cannot inherit the instrumented binary's proof.
5. Diagnostics are parsed only from the selected cases' captured Output blocks.
   Recovering UBSan signed-overflow diagnostics fail the sanitizer check even
   when the program and CTest exit successfully. TSan runtime startup/mapping
   failures remain unsupported/unknown; an ordinary failed test is not
   automatically a sanitizer finding.

The selected sanitizer options explicitly set empty suppressions and the stderr
log sink. Known custom source-defined runtime options/reporting hooks are outside
this first configuration slice; this does not claim exhaustive defense against a
hostile program. CTest per-case environment overrides, indirect definitions and
arbitrary CMake commands are unsupported. Inventory and test executions must bind
the same retained direct `CTestTestfile.cmake` bytes and both `CTestCustom.cmake`
and `CTestCustom.ctest` files with exact inert sentinel bytes. This prevents
unobserved automatic customization or an after-inventory property rewrite from
turning a suppressed error into a clean check. The primary definition grammar
accepts only direct literal commands and plain single-line comments.

The loader search path is recorded explicitly because selected CMake/CTest may
require host shared libraries. `LD_PRELOAD` and `LD_AUDIT` are cleared. The
environment and dynamic-loader closure are not an authenticity boundary.

## Cases and interpretation

| Actual case | Expected interpretation when runtime is usable |
| --- | --- |
| ASan clean / intentional heap overflow | Passed / failed with bound diagnostic |
| UBSan clean / recovering signed overflow | Passed / failed, even when CTest passes |
| TSan synchronized / intentional data race | Passed / failed; startup failure instead gives unknown |
| Plain object with sanitizer only at link | Unknown: no selected object callsite proof |
| Instrumented binary replaced by plain CTest input | Unknown: exercised binary differs |
| Zero tests / all cases skipped | Unknown: no actual non-skipped selected execution |
| Clean selected binary plus uninstrumented prebuilt archive | Unknown: selected component/source gap |
| Intentional ASan defect plus uninstrumented archive | Credible failure retained; completeness remains limited |

Raw `sanitizer_facts` uses `outcome=unsupported` and `usability=unsupported` for
these proof gaps; the policy consumer maps unavailable verification to unknown.
Ordinary test outcomes retain their original process/report status independently.
The dedicated policy predicate requires evaluator profile 1.1.0; a normalized fact
by itself is not a policy assessment.

## Public API and limits

`cppulse.sanitizers` exports `ObjectSelection`, `SanitizerSelection`,
`normalize_gcc_sanitizer(snapshot, selection)` and
`persist_gcc_sanitizer(snapshot, workspace=..., store=..., selection=...)`.
Selectors name original receipt/evidence IDs; callers cannot supply observed
symbols, success booleans or outcomes. The pure normalizer runs no commands and
performs no live project discovery. Publication separately checks live selected
source bytes again. Derived JSON retains the collection plan's metadata byte
limit. Logical fact IDs remain intact while hashed storage/stage IDs avoid
length and portable-filename collisions.

This first slice supports one direct source per compile and retained user object
or archive link inputs. A recognized callsite proves selected instrumentation,
not every access, function or execution path. System headers, the standard library,
third-party runtime internals and the actually loaded shared-library closure are
not proven instrumented. `DT_NEEDED` is not a hash of a loaded runtime. Hashes and
editable diagnostic output do not authenticate a producer. Imported reports are
not promoted into observed clean verification. Unknown formats, LTO, stripped
objects, wrappers, static sanitizer runtimes and unsupported diagnostic dialects
remain unavailable. No certification, memory-safety guarantee or general platform
support is claimed.

CTest customization behavior was checked against the exact
[CTest 3.31.6 source](https://github.com/Kitware/CMake/blob/v3.31.6/Source/cmCTest.cxx)
and [the 3.31 custom-files documentation](https://cmake.org/cmake/help/v3.31/command/ctest_read_custom_files.html).

Primary sanitizer reference: [GCC 14.2 instrumentation options](https://gcc.gnu.org/onlinedocs/gcc-14.2.0/gcc/Instrumentation-Options.html).
