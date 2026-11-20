# Explicit local collection engine

`cppulse.collection.collect` executes one selected versioned plan and returns a
`RunSnapshot`. Loading configuration, reading a policy or analyzing source does
not call this API implicitly. Public CLI integration is a separate stage.

```python
from pathlib import Path
from cppulse.collection import collect

snapshot = collect(
    plan,
    workspace=Path("selected-workspace"),
    source=source_snapshot,
    contexts=selected_contexts,
    store=Path("local-run-store"),
)
snapshot.verify()
```

The exact effective plan is retained with its `collection_plan` contract, and
`manifest.config_digest` is the canonical digest of that unchanged plan. Source,
context and plan contracts and their cross-references are validated before any
selected command runs. Schema-valid integer-valued JSON numbers are converted to
Python integers only for runtime limits; the retained plan and digest stay exact.
Source scope and compiler contexts are selected declarations. They do not prove
dynamic coverage, header contribution, compiler discovery completeness or a
trusted producer identity.

Each explicit recipe step retains a typed process receipt, bounded stdout/stderr,
observed input facts before/after, output freshness and executable identity.
New collections retain StepResult data as typed `execution_facts` v2, including
original input/output/log artifact maps and separate private-copy binding status.
Legacy uncontracted debug JSON stays untrusted and is not upgraded retroactively.
Parser diagnostics remain hash-checked review data without an authoritative
contract. Plans, receipts, execution facts, evidence and the run manifest use their
packaged schemas and closed-bundle validation.

Regular source/input/output/report/log snapshots are copied into private files
outside RunStore staging. Every observed file is checked against
`max_artifact_bytes` before the store's memory-backed copy. Oversize binary files
are represented by a bounded diagnostic, never a retained binary prefix claiming
the original identity. Log prefixes can be retained with explicit truncation
limitations. Cppulse-authored JSON and the manifest have the separate explicit
`max_metadata_bytes` bound (documented default 16 MiB, maximum 64 MiB). Initial
control metadata that cannot fit is rejected before commands. Later metadata
failures propagate with retained private/staging material; they do not promote a
completed run. These are per-file bounds, not total memory/disk or CPU quotas.

Execution and evidence outcomes remain separate:

| Observation | Retained result |
| --- | --- |
| Zero process exit and fresh selected build artifacts | Passed process and usable build evidence |
| Normal nonzero build exit, binary absent | Failed process and usable observed failure; dependent steps skipped |
| Zero exit, required output absent | Passed process, missing evidence, operationally partial collection |
| Test report contains failures despite zero receipt exit | Passed receipt and failed test evidence with exact reported counts |
| Valid zero/all-skipped cases | Exact counts and skipped evidence; never passed verification |
| Missing, malformed, unsupported or mismatched report/proof | Unknown counts where unavailable, explicit unusable evidence and partial collection |
| Timeout/cancellation | Explicit receipt status; independent completed facts remain retained |
| Source or exercised artifacts change | Stale/mismatched facts, partial or cancelled run, no latest-completed promotion |

Executed test evidence supports the reviewed CTest 3.31.6 dialect. A test binding
must explicitly select distinct version/inventory steps, its JUnit report and
`execution_log_path` (`Testing/Temporary/LastTest.log`, declared as a step output).
The collector does not run hidden version or inventory probes. All three steps
must observe the same actual executable hash. The frozen JUnit and execution-log
parsers identify their exact input bytes; those identities must match retained
artifact descriptors.

Inventory and actual execution command records must agree for each non-skipped
JUnit case, including the working directory. Every selected exercised binary must
be directly invoked by those matched commands and retain identical before/after
content. Interpreter/wrapper command chains and unreviewed CTest argv modes remain
unsupported. Matching case names or a pre-run inventory alone is insufficient:
a decoy build directory or rewritten generated test definition must not borrow
proof from a binary that never ran. Inventory/test directory, configuration,
selection and explicit environment differences are handled conservatively.

The finite selected source inventory is checked before commands, after collection
and immediately before publication. A mutation in the final publication window
aborts that staging run, then publishes the already frozen facts in a new partial,
unverified attempt without rerunning commands. The abandoned stage remains
inspectable. An unexpected publication failure propagates and retains staging
and private material rather than manufacturing a passed result. A published
partial/cancelled attempt advances `latest_attempt`; only a completed collection
can advance `latest`. Completed describes collection, not a passed test suite or
an accepted policy gate.

Selected commands run with inherited environment and user permissions. Concurrency,
wall time, process-group termination and retained logs are bounded; this is not a
hostile-code sandbox. Only the selected executable file is fingerprinted, not its
whole interpreter/runtime dependency closure. Content hashes identify bytes and
do not authenticate authorship. Current execution support is qualified on the
observed POSIX/Linux environment; other platforms need their own actual checks.
