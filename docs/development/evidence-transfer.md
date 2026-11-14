# Local evidence transfer

`cppulse.transfer` copies retained run bytes into a bounded standalone directory. It supports separate named roots from different sources and preserves every original manifest and artifact byte. It does not extract archives, execute tools, refresh source files, authenticate producers, publish a local run or update `latest` pointers.

This is archival transfer. SHA-256 and size checks detect disagreement with the supplied inventory. Someone able to rewrite the descriptor and payload can produce a different internally consistent bundle; hashes are not a signature or authentication mechanism.

## Export and inspect

The API accepts already selected local `RunSnapshot` objects:

```python
from pathlib import Path
from cppulse.run_store import RunStore
from cppulse.transfer import export_bundle, open_bundle

snapshot = RunStore(Path("output")).open_run("recorded-run-id")
bundle = export_bundle(
    {"upstream": snapshot},
    Path("review/upstream-transfer"),
)

loaded = open_bundle(bundle.path)
foreign = loaded.open_run("upstream")
print(foreign.origin)           # import
print(foreign.authentication)   # unverified
print(foreign.source_freshness) # not_rechecked
original_manifest = foreign.manifest
checked_bytes = foreign.read_bytes("original-artifact-id")
```

Export does not require or execute the original project. It checks source snapshot files against their frozen manifest while copying. A changed artifact or manifest is an integrity error. A verified source flag inside the original manifest is retained as an original producer claim; the imported wrapper never converts it to current local verification.

`ImportedRun` provides `run_id`, `manifest_sha256`, a copied `manifest`, exact `read_manifest_bytes`, `read_bytes`, `read_json` and `verify`. JSON reads require an explicit or originally declared contract. Both raw reads and verification use frozen checked buffers. Editing the input directory after opening cannot redirect one read to another run. Open the directory again to inspect its current bytes.

`TransferBundle.metadata` returns a copy of the descriptor; `root_ids` lists separate root labels. Root labels select the original run namespace, not a local source identity. Equal filenames or run IDs under two roots do not imply equal source contents, build contexts or assurance.

## Copy an imported bundle

```python
from cppulse.transfer import copy_bundle

copy = copy_bundle(
    Path("review/upstream-transfer"),
    Path("review/imported-copy"),
)
copy.verify()
```

`import_bundle` is an alias for this standalone copy operation. It does not construct a `RunStore` or insert imported facts into a local policy bundle. Its descriptor and payload remain byte-identical to the checked input. Copying an already opened `TransferBundle` deliberately copies its frozen buffers; copying a path opens and checks the current directory first.

The directory format is:

```text
transfer_bundle.json
roots/<root-label>/runs/<original-run-id>/run_manifest.json
roots/<root-label>/runs/<original-run-id>/<original-artifact-path>
```

The descriptor lists every payload file's canonical relative path, size and SHA-256. It records each root's original source digest, run ID, manifest path and manifest SHA-256. The descriptor is excluded from its own payload inventory and is separately size-bounded. Root manifests and contracted JSON are validated from the same checked bytes. Closed cross-document references are validated separately within each root.

Readers reject unlisted or missing files/directories, symlinks (including ancestors), special files, traversal, absolute paths, case aliases, duplicate identities, changed hashes, mismatched root inventories and publication-pointer payloads. This first format supports regular-file directories only; ZIP and TAR extraction are not implemented.

## Bounds and publication

`TransferLimits` controls local caps. An input descriptor can lower these bounds but cannot raise them:

| Bound | Default | Hard maximum |
| --- | ---: | ---: |
| Payload file count | 10,000 | 10,000 |
| One payload file | 256 MiB | 256 MiB |
| Payload total | 1 GiB | 1 GiB |
| Descriptor, one root manifest or one contracted JSON document | 4 MiB | 16 MiB |

Paths have at most 64 components. Payload limits exclude the descriptor. The complete accepted payload is retained in memory; choose lower caps for constrained callers. Size bounds are checked before metadata parsing. Oversized contracted metadata is rejected before its payload is read.

Writers create a private sibling staging directory, write and flush all payload files, write the descriptor last, then publish with Linux `renameat2(RENAME_NOREPLACE)`. An existing or concurrently created destination is never overwritten. Unsupported atomic no-replace support produces an explicit error; there is no overwrite fallback. An interrupted operation removes its private staging directory. Destinations inside an input run or transfer directory are rejected.

This path is qualified for the current Linux/POSIX environment. It does not protect against a filesystem owner rewriting stored data, establish current source freshness, or establish that a foreign build/test/assessment claim is authentic. Imported artifacts require separate local provenance and applicability handling before reuse; transfer alone never creates a policy pass.
