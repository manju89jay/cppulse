# Source-bound coverage normalization

This development slice distinguishes line, branch and function counters. It does
not infer decision coverage, MC/DC, test adequacy, certification or safety. A
coverage percentage is a ratio of exact counters for one selected file and job,
not an average of report percentages.

## Supported observations

The bounded standard-library adapter in `cppulse.adapters.coverage` reads LCOV
1.x and the Cobertura dialect actually emitted by **gcovr 8.8**. The local
execution normalizer currently accepts **GCC/gcov 14.2.0**, **gcovr 8.8** and the
existing **CTest 3.31.6** execution proof. Other versions and command variants
need their own validation before they can produce execution-positive facts.
There is no gcovr, lxml or compiler import in the core package.

| Format | Kind | Method | Unit identity |
| --- | --- | --- | --- |
| LCOV | Line | `lcov-da-v1` | Source file and reported line |
| LCOV | Branch | `lcov-brda-v1` | File, line, exception flag, block and branch |
| LCOV | Function | `lcov-fnda-v1` | File, reported function name and start line |
| Cobertura | Line | `cobertura-lines-v1` | Source file and reported line |
| Cobertura | Branch | `cobertura-condition-counts-v1` | File and line holding an exact covered/total branch group |

Unit IDs include the canonical source path and method. Cobertura group counts do
not invent individual edge identities. The gcovr Cobertura dialect exposes
method line/branch rates, not direct function-entry counts, so this adapter emits
**no function measurement** for that format. LCOV exception arcs remain branch
counters. A `0/0` denominator is retained as zero counts and does not establish a
positive percentage. Missing reports and empty reports do not become clean zero
coverage claims.

Every aggregate equals the sum of its retained units. Duplicate source/shard
records, duplicate units, contradictory totals, unsupported XML namespaces,
entities, unknown records and truncated reports fail closed. XML is bounded to
16 MiB, 100,000 nodes and depth 64; LCOV unit inventories are bounded too. The
known Cobertura DTD identifier is recognized without fetching it. Exact parsed
SHA-256 and byte length must match the selected archived report descriptor.

## Execution proof

`cppulse.coverage.normalize_coverage(snapshot, **roles)` performs no commands and
reads no live project source. It requires integrity-checked typed
`execution_facts`, a retained collection plan and verified finite source identity.
All role IDs are explicit. They select the report receipt/artifact, generator,
gcov and compiler version receipts, configuration and gcov artifacts,
`proof_receipt_ids`, `test_evidence_ids`, instrumentation and profiles.

The first supported recipe deliberately has a small command surface:

1. Compile each selected C++ translation unit directly with GCC14.2, `--coverage
   -O0 -g -std=c++17 -c`, creating both its `.o` and `.gcno` in the same receipt.
2. Link the observed objects with the same compiler and `--coverage` into the
   selected binary.
3. Exercise that binary through the existing explicit CTest version, inventory,
   JUnit and `LastTest.log` binding. At least one case must actually execute;
   zero/all-skipped cases cannot justify observed coverage.
4. Retain newly created `.gcda` outputs from that test receipt. Their GCC version
   and compile stamps must match the corresponding `.gcno` bytes. Accumulated
   or preexisting counters are unsupported.
5. Run the selected gcovr with an explicit empty configuration, `--no-markers`,
   selected source root, explicit matching gcov bytes, LCOV1.x/Cobertura outputs
   and **explicit `.gcda` search files**. It does not scan a build directory for
   unlisted profiles or merge report shards.

The selected gcov executable is copied into the finite workspace, version-probed
and included among the report inputs. Compiler and generator executable hashes
must match their explicit version probes. Inputs are unchanged before/after the
actual processes; generated objects, mappings, binary, profiles and report have
verified causal same-job lineage. Retained input copies may have different
artifact IDs from producer outputs only when their exact bytes and path lineage
match. Report source paths and units must resolve within selected source and line
bounds. A version string prefix such as `8.80` cannot stand in for `8.8`.

These checks establish this local finite chain, not tool authenticity or a full
runtime/interpreter/header dependency closure. Currently a failed CTest process
prevents dependent report generation under the existing execution scheduler.
Its raw profiles/logs remain available, but this first slice does not promote
coverage from that failed chain. No ancestry rule was weakened to bypass this
limitation.

`normalize_imported_coverage(...)` can retain source-scoped counts from an
explicit report/root/context selection, with `origin: import`, no execution proof
and unknown source hashes. Those numbers cannot become execution-positive
coverage. Usability states remain explicit: usable, missing, malformed,
unsupported, stale or mismatched, according to the observed layer. Incompatible
execution roles raise a typed compatibility/contract error rather than creating
an apparently usable fact.

## Immutable publication

`persist_coverage(snapshot, workspace=..., store=..., **roles)` creates a **new**
derived run, copies every parent artifact with the same ID and byte identity,
retains the parent manifest hash, and adds a typed `coverage_facts` artifact.
It preserves the original source, job contexts and collection configuration
identity. The wrapper checks current source both before and at publication;
mutation aborts without promoting a derived run. Control JSON and the derived
manifest obey the recorded `max_metadata_bytes` cap. An already normalized report
cannot be normalized again in the same lineage.

Multiple facts are not automatically combined. Policy consumers may deduplicate
repeated facts for the same file/job/kind/method only when their **entire** unit
inventories and covered/total values agree. Conflicting or disjoint inventories
remain unknown/incomplete; this slice does not implement shard union.

## Reproduction and current evidence

Install the ordinary project and local verification dependencies using the
repository setup instructions. Select an existing pinned gcovr8.8 executable;
the driver does not install anything. From a source checkout:

```bash
source review/environment.sh  # managed-workspace setup, where available
PYTHONPATH=python python scripts/demo_coverage.py \
  --gcovr /absolute/path/to/gcovr-8.8/bin/gcovr
pytest -v --cov=cppulse.coverage --cov=cppulse.adapters.coverage \
  tests/test_coverage_normalization.py tests/test_coverage_adapters.py
```

The driver creates a fresh uniquely named synthetic workspace and store under
`output/coverage-demo/`. `latest-demo.json` pins the raw and both derived manifest
hashes; old runs remain unchanged. The deliberately unused function and untaken
branch yield these **fresh verified fixture results**, not product benchmarks:

| Report | Line | Branch | Function |
| --- | --- | --- | --- |
| LCOV | 5/8 | 1/2 | 2/3 |
| Cobertura | 5/8 | 1/2 | Unavailable |

All fixture compilation, link, version, CTest and generator commands appear in
retained receipts and logs. The test suite executes this real fixture when the
optional GCC14.2/gcovr8.8/CMake3.31.6 verification toolchain is present; otherwise
those tests explicitly skip rather than claim execution. Pure parser tests need
no external coverage tools.

References: [GCC14.2 gcov documentation](https://gcc.gnu.org/onlinedocs/gcc-14.2.0/gcc/Invoking-Gcov.html),
[gcovr options](https://gcovr.com/en/stable/manpage.html),
[gcovr changelog](https://gcovr.com/en/stable/changelog.html). Format details were
also checked against the installed pinned gcovr8.8 writer implementation.
