# Two finite consumers of fmt 10.2.1

The example builds pinned [fmt 10.2.1](https://github.com/fmtlib/fmt/tree/e69e5f977d458f2650bb346dadf2ad30c5320281)
from the revision in [the corpus lock](../../demo/corpus-lock.json). Both
configurations run the same authored integer-formatting workload under CTest.

| Configuration | Selected distribution | Use checked independently of the test policy |
| --- | --- | --- |
| `fmt-compiled` | Installed fmt headers and `libfmt.a` | The GCC depfile names the authored source and `fmt/format.h`. GNU ld selects a member of the supplied static archive. |
| `fmt-header-only` | Installed fmt headers | The actual compiler and macro probe use `-DFMT_HEADER_ONLY=1`. The depfile names the same authored source and header, and the link uses no fmt archive. |

Each configuration also compiles a translation unit that includes
`fmt/format.h` by itself. The runner checks this compile and its depfile
separately. It retains package-use records and matrix declarations for both
configurations. [The finite policy](policy.json) gates the two bound workload
outcomes and the required context IDs. A policy pass alone cannot establish
package use or consumer applicability.

## Run the example

Use a Linux host with the installed cppulse console and Python, Git, GCC
14.2.0, GNU ld 2.44, and CMake/CTest 3.31.6. After installing those tools,
run the following from the cppulse checkout. Use new output directories.

```bash
# Explicit network acquisition of fmt only. Omit this step if you already
# have a clean checkout of the locked commit.
python scripts/demo_fmt_matrix.py fetch --output "$PWD/output/fmt-source"

# The remaining steps use local tools and the supplied fmt checkout.
python scripts/demo_fmt_matrix.py run --compiler g++-14 \
  --fmt-source "$PWD/output/fmt-source/fmt" --output "$PWD/output/fmt-matrix"
```

Both acquisition and execution check the full upstream revision. Execution
builds a fresh copy of the pinned Git archive and compares the installed
headers with their source bytes. The example saves each runnable
`collection-request.json`, exact commands, source and tool pins, separate
stores, test inventory and receipts, and the selected JSON/HTML reports.
Start with `summary.json` and `passing/report.html`. In each scenario the
collection request uses the adjacent `workspace`; supplied absolute tool and
binary paths are local to that run. Recreate the request for another host.

| Scenario | Expected policy exit | Meaning |
| --- | ---: | --- |
| Both configurations | 0 | One authored CTest workload passed in each configuration. |
| Deliberately wrong expectation | 1 | The header-only workload expects `answer=9999` and actually produces `answer=0042`. The other lane still passes. |
| Required header-only configuration omitted | 3 | The header-only requirement remains visible, with no context, receipt or passing evidence for that lane. |
| Copied source changed after collection | 3 | The same previously passing run is selected by ID and manifest hash; the check rejects it with `STALE_SOURCE`. |

The runner succeeds only when all four outcomes match. The deliberately
wrong expectation tests the gate and says nothing about a defect in fmt.
In the missing-configuration case, the shared package headers are still
inventoried. The declaration and those bytes supply no header-only execution.
The stale control edits and then restores only an owned copy of the authored
source. The earlier pinned positive stores and reports remain historical
records of their own bytes.

The two distribution views cover selected headers and one archive. They
do not establish full upstream source coverage or run fmt's upstream tests.
The original bounded [fmt trial](../../docs/development/simulated-audience-review.md)
recorded partial analysis. This build/test example makes no new native
analysis claim. Uninstantiated template paths, other headers and targets,
performance and safety remain outside the selected work.
