# Checked native analysis normalization

`cppulse.analysis` converts one explicitly selected native analysis job into
versioned `analysis_inventory` and `observations` documents. It reads checked
snapshot bytes, not the live project, and never runs a compiler, Git or a probe.

```python
from cppulse.analysis import normalize_native_analysis, persist_native_analysis

selection = dict(
    receipt_id="native-analysis",
    report_artifact_id=report_id,
    registry_artifact_id=registry_input_id,
    config_artifact_id=config_input_id,
    compilation_database_artifact_id=database_input_id,
    resource_manifest_artifact_id=resource_input_id,
    requested_files=["main.cpp"],
    requested_rules=["CPP-MEM-001"],
)
result = normalize_native_analysis(snapshot, **selection)
derived = persist_native_analysis(
    snapshot, workspace=workspace, store=store, **selection
)
```

The IDs are the **original** observed input/output IDs from typed
`execution_facts.binding` maps. The normalizer checks the receipt, native executable
hash against its declared job, fresh report bytes, unchanged inputs, source
verification, explicit invocation paths, source paths, rule IDs, locations and
internal totals. The selected report must be the observed native
`--output/findings.json` location, including the native default `output` directory.
Legacy imported/uncontracted debug JSON cannot be upgraded into observed execution.

The first adapter supports the current distribution's native registry and tool
version. The retained registry must have the packaged rule definitions, versions,
maturity and defaults; its raw bytes remain independently hashed. Formatting and
rule-list order do not replace that exact retained-byte identity. Arbitrary/custom
registries are unsupported until the native producer reports a versioned registry
identity. All current rules remain experimental.

Each requested file has an explicit row, including missing, failed, skipped,
excluded and partial states. A successfully traversed analyzed file records known
enabled rules actually considered; partial and other incomplete states never
invent completed rule consideration. Disabled requested rules do not become a
zero-finding pass. Known enabled findings for requested files are retained even
when their rule was not requested, so later evaluation can report known failures.
Other files and findings remain available in the original archived report.

A parse context contains the actual native-reported libclang identity, exact ordered
C API arguments and process cwd. Duplicate flags and C API additions such as
`--driver-mode=g++` are preserved. The normalizer does not emulate libclang argument
rewriting or relabel the coarse build/analyzer job as a measured parse context.
Identical parse-context definitions are reused by digest; every finding occurrence
has a distinct job/receipt/report/occurrence ID. Fingerprints are explicitly
versioned as `native-1`; final rename/line-shift baseline behavior is a later stage.

Strict matching requires a bound explicit compilation database with one unambiguous
file command, plus retained configuration and a finite selected Clang resource
manifest. Inferred/fallback, external resources, omitted roles and ambiguous DB
variants remain unverified. Resource files are copied under the manifest's selected
root and individually retained in source/native inputs, with `include/stddef.h`
present. The manifest itself belongs outside that root. The retained resource
prefix, manifest entries, hashes and byte sizes must agree. This binds selected
resource bytes; it does not establish the complete host/runtime read set or observe
unlisted future additions. GCC build commands are not claimed equivalent to the
actual libclang parse.

The publication wrapper creates a **new immutable run**. It copies parent artifacts
without changing their bytes/IDs, adds byte-identical typed registry/resource copies,
appends measured parse contexts and normalized documents, and retains the exact
parent manifest as uncontracted provenance. The original collection-plan digest and
job context stay unchanged. Parent partial/cancelled state is preserved; incomplete
requested analysis creates a partial derived attempt. This is not a policy pass.

The wrapper checks current finite selected source bytes before publication and
again in the store's final callback. Mutation raises `InputChanged`; a final-window
failure retains staging and does not update completed/attempt pointers. Generated
control JSON and the new manifest obey the effective metadata cap. A receipt is
normalized once in a derived lineage; select its original collection snapshot for
a new normalization request instead of duplicating observations in that lineage.

Hash identities do not authenticate a producer or certify standards compliance.
Source/resource selection is finite, rule findings are experimental, and observed
zero counts apply only to the explicitly selected, available context and rules.
