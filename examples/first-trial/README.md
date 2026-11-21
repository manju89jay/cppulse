# A finite C++ build/test policy trial

Fresh Cloud verification ran this trial with the installed cppulse console from
outside the checkout, using GCC 14.2 and CTest 3.31.6 on Linux x86_64. Collection,
policy evaluation and HTML reporting returned exit 0 with three executed tests
passing. Missing test evidence and a changed source file each produced exit 3
with the reason shown below. [Batch verification record](../../docs/development/reviewer-fixes.md).

This authored three-file C++17 example demonstrates one selected consumer and
three real CTest cases. It does not claim OSS provenance, exhaustive template
coverage, static-analysis cleanliness, coverage, sanitizers or release readiness.
The collector retains actual source/binary identities, commands and CTest facts;
the policy requires those tests in that explicit context. No XML or counts are
supplied by the preparation script.

Prerequisites: a POSIX host, installed cppulse core, Python 3.11–3.12, a C++17
compiler, CMake and **CTest 3.31.6**. The execution-backed `ctest-junit` adapter
version 1.0.0 currently qualifies that exact producer. A different installed
CTest version is refused by this example, not silently treated as tested.
Native analysis is a separate optional journey requiring matching libclang19+
and the cppulse native component. This example needs no ML, PDF or account.

From the selected cppulse source checkout, after its installation:

```bash
# Preparation only probes explicit tool versions and creates a NEW workspace.
# Choose fresh names; existing workspaces are never deleted or overwritten.
TRIAL="$PWD/output/first-trial"
STORE="$PWD/output/first-trial-store"
python examples/first-trial/prepare.py --workspace "$TRIAL"

# Review collection-request.json and policy.json before running chosen commands.
cppulse collect --request "$TRIAL/collection-request.json" \
  --workspace "$TRIAL" --store "$STORE"
cppulse check --store "$STORE" --workspace "$TRIAL" \
  --policy "$TRIAL/policy.json"
cppulse report --input "$STORE" --evidence --format html \
  --output "$PWD/output/first-trial-report.html"
```

Expected acceptance: collect exit0, then check exit0 / `status: passed`. The tests
must report exactly three executed cases, all passing, with no failures/skips.
Capture completion and policy acceptance are distinct. Retain each command's
returned run ID and manifest SHA256; those identify the actual result bytes.
The standalone HTML renders with inline CSS; audit links require the matching
local API server, so they are not promised as standalone artifact downloads.

## Missing-evidence control

Prepare a separate workspace without a tests recipe or tests binding. The
policy is unchanged and still requires `trial-tests`:

```bash
MISSING="$PWD/output/first-trial-missing"
MISSING_STORE="$PWD/output/first-trial-missing-store"
python examples/first-trial/prepare.py --workspace "$MISSING" --omit-tests
cppulse collect --request "$MISSING/collection-request.json" \
  --workspace "$MISSING" --store "$MISSING_STORE"
cppulse check --store "$MISSING_STORE" --workspace "$MISSING" \
  --policy "$MISSING/policy.json"
```

Expected: capture can complete with exit0; check must return exit3 / insufficient
evidence. No empty or manufactured test report can stand in for absent execution.

## Stale-source control

After the successful trial, change only its copied source and recheck the same
store. The original repository example and old pinned result remain intact:

```bash
printf '\n// Deliberate stale-source negative control.\n' >> "$TRIAL/checks.cpp"
cppulse check --store "$STORE" --workspace "$TRIAL" \
  --policy "$TRIAL/policy.json"
```

Expected: exit3 with `STALE_SOURCE`. Rechecking executes no build/tests. To obtain
current evidence, recollect changed inputs in a fresh workspace/output; never
retarget an old positive result by changing its hash label.

For actual compiler-context analysis after building this example, use its real
`build/compile_commands.json` with `cppulse analyze --compilation-database`.
Parsing, findings, maintenance health, ranking and this test-policy gate remain
separate results. See [public CLI semantics](../../docs/development/public-cli.md).
