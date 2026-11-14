# Selected distributed packages and consumer applicability

The local S6 API keeps three questions separate:

1. Which exact distribution files were selected?
2. Did an observed compiler actually consume those selected bytes in this context?
3. Which required local application checks have usable results?

A compatible configuration is not a test, policy, release or certification pass.
Source identities remain per run. A library maintainer and an application can
use identical package bytes while having different source manifests; cppulse
does not rewrite either manifest to make their complete source digests equal.

## Declarations and immutable retention

`cppulse.consumer.describe_distribution` selects logical package paths mapped
to exact artifact IDs in an owning checked `RunSnapshot`. IDs, SHA-256 hashes,
sizes and actual source subsets are validated. A consumer with only a package
uses `source_relation: distribution_only` and an empty original-library source
subset, with an explicit limitation. A declared `compiled` kind alone does not
prove the file was compiled, linked or tested.

`declare_consumer_matrix` records expected contexts, configurations, check names,
selected template-use descriptions and requested header self-containment. An
expected context or usage may be missing; that is a requirement, not an implicit
success. Unknown configuration values stay null.

`persist_consumer_documents` appends supported documents in a new immutable run.
Original artifact bytes and IDs remain unchanged, with the parent manifest
retained as provenance. The finite selected workspace inputs are rechecked;
source mutation aborts publication. An unverified parent is never promoted by
merely copying its declarations. Imported wrappers cannot be published as
current local runs through this API.

## Actual package-use normalization

`normalize_consumer_usage` supports the exercised direct GCC14.2.0 / GNU ld2.44
slice. It consumes checked stored facts only and launches no tools. A verified
record needs source-verified, successful and byte-bound compiler execution,
an exact retained plan step, and these observations:

- The actual translation-unit operand, resolved against the receipt's real
  working directory, is a retained selected source with matching bytes. A
  similarly named root file cannot stand in for an unlisted subdirectory file.
- A fresh GCC dependency file names the actual output target, translation unit
  and requested packaged headers. Workspace-local dependencies must be retained
  compiler inputs. Make variables and ambiguous multi-rule formats are rejected.
- A compiled archive contributes actual named members in the initial GNU
  linker-map selection section. An archive merely appearing in a `LOAD` line,
  `-I` path or command argument is insufficient.
- Independent explicit macro and target probes use the same compiler hash,
  context and selected flags before compilation. The macro probe's retained TU
  is the reviewed minimal `bits/c++config.h` include, not arbitrary code that can
  replace the purported compiler facts.

Observed configuration includes compiler identity, OS, target, language standard,
explicit macros, exception/RTTI settings, selected linking mode and actual retained
local dependencies. Its ABI label records compiler/library macros; it does not
prove general binary compatibility. Unknown compiler options, response files and
unreviewed context-changing flags remain unverified. Host system headers and the
complete runtime dependency closure are outside this finite proof.

A self-containment claim additionally requires a separate retained minimal TU
containing only the selected include and an empty main, with an actual dependency
record naming that packaged header. Including a header inside a larger consumer
does not establish self-containment. Template names describe authored selected
test scope; no exhaustive semantic template coverage is inferred.

## Comparing foreign evidence and local checks

```python
from cppulse.consumer import compare_consumers, persist_consumer_documents

result = compare_consumers(
    imported_bundle.open_run("upstream"),
    local_snapshot,
    upstream_subject_id="fmt-10.2.1",
    local_subject_id="fmt-10.2.1",
    upstream_matrix_id="fmt-10.2.1-consumers",
    local_matrix_id="fmt-10.2.1-consumers",
    generated_at=explicit_utc_time,
)
derived = persist_consumer_documents(
    local_snapshot,
    [("consumer_comparison", result.document)],
    workspace=selected_workspace,
    store=local_store,
    raw_artifacts=result.artifacts,
)
```

The caller supplies UTC time; the comparison reads no clock, processes, network
or live project files. Original upstream/local manifest bytes and the upstream
subject/matrix stay generic retained blobs in the local namespace. Foreign typed
documents are validated independently and never merged into the local source
bundle. Import origin remains `import`, authentication `unverified`, and foreign
source freshness is not rechecked. See [evidence transfer](evidence-transfer.md).

Configuration correspondence requires the selected distribution identities and
all known dimensions to match independently observed usage for the same subject.
Another package's successful usage cannot satisfy the selected subject. A real
package kind/path/byte mismatch is explicitly recorded as `distribution`, without
inventing a compiler mismatch. A C++20 local build can pass while remaining
incompatible with reuse of evidence scoped only to C++17; that does not claim the
library cannot support C++20.

Local test checks select exact retained evidence-check names/IDs. This first API
does not silently search arbitrary JUnit case names. A current passed/failed
result must be usable execution evidence in the correct context, have credible
test counts, and exercise the actual compiler output bytes through the recorded
producer ancestry. Unrelated tests cannot borrow credit merely by sharing a
context name. Missing, zero/all-skipped, expired or mismatched results remain
unknown. Configuration can be `compatible` while `local_test_status` is unknown
and required application checks remain listed as missing.

## Reproducible selected package demonstration

After the documented native dependencies are configured and the exact source
revisions in `demo/corpus-lock.json` are cached under `tests/tmp/corpus`:

```sh
source review/environment.sh
PYTHONPATH=python python scripts/demo_consumer.py
```

The driver never downloads sources or updates Git refs. It builds/installs the
pinned fmt archive and utfcpp headers, then compiles consumers against retained
packaged bytes. The unused unmaterialized utfcpp test submodule is explicitly
excluded; upstream full test suites are not claimed. The seeded throwing header
is synthetic and separate from those upstream libraries.

Selected scenarios cover a matching consumer, an unselected required local
workload test, a C++20 context mismatch, actual `-fno-exceptions` compilation
failure, a changed package identity, and a separate packaged-header check.
Commands, raw/derived snapshots, receipts, maps, dependency files, actual CTest
reports and comparisons are retained beneath `output/consumer-demo/batches/`.
`latest-demo.json` names the completed demonstration batch; it is not a product
release-acceptance pointer.

`--phase package` runs only package collection. The explicit
`--reuse-package-summary PATH` development option reuses an already hash-checked
package snapshot and does not claim a fresh library rebuild. The default full
command performs fresh packaging. These are internal local APIs/demo commands;
public installed workflow integration belongs to S7. Windows, macOS, containers,
other compiler/linker versions and large-workload limits remain separately
unqualified.
