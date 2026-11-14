# Local check adapter and unqualified action draft

The action source now delegates to the same installed `cppulse check` engine.
It consumes an explicitly supplied local store, workspace and policy or finding
request. It performs no checkout, collection, comment, credential lookup or
upload. No workflow was added, executed or published during this implementation.

**Docker and the GitHub runner are unverified.** Local Bash control tests and
public CLI tests have separate retained evidence. Do not treat the old `@main`
examples as installation instructions for these uncommitted changes.

## Run the adapter locally

With the candidate installed and the selected store already collected:

```bash
GITHUB_WORKSPACE="$PWD" \
INPUT_STORE_PATH=/absolute/evidence-store \
INPUT_POLICY_FILE=/absolute/policy.json \
bash .github/actions/cppulse/entrypoint.sh
```

Alternatively set `INPUT_FINDING_REQUEST` and leave `INPUT_POLICY_FILE` empty.
The wrapper preserves the actual CLI exit and stdout JSON in a unique local
`cppulse-check-result.*.json`. If `GITHUB_OUTPUT` names a local runner output
file, it records `exit-code` and `result-path`; it never uploads that result.
Optional `INPUT_RUN_ID` and `INPUT_MANIFEST_SHA256` select an exact historical
run before checking its declared current materials.

| Input | Meaning |
|---|---|
| repo-path | Workspace relative to the runner workspace, or absolute; default `.` |
| store-path | Required existing local evidence store |
| policy-file | Policy JSON; mutually exclusive with finding-request |
| finding-request | Versioned finding comparison request |
| run-id / manifest-sha256 | Optional exact pair; both required together |

Legacy `base-ref`, comments, implicit PDF generation and separate
`fail-on-regression` switches are rejected with exit 2. The selected shared check
already supplies the gate. `github-token` is deprecated and unused, defaults to
empty, and is not mapped into the container environment. The historical comment
and diff scripts remain draft source and are not invoked by this adapter.

## Scope and result interpretation

Collection completion, policy satisfaction and finding regression are different
results. Current checks validate selected source and generated-output bytes;
changed material requires recollection. A matching upstream package does not
replace application tests. A copied checksum is not producer authentication.
See [public commands](development/public-cli.md) and
[local integrations](development/local-check-integrations.md).

The former two-minute setup promise, PR bug-probability/compliance language,
changed-file shortcut and repository-size timing table were unverified draft
claims. They are retired, not reused as benchmarks. Ranking remains experimental;
detector accuracy, performance at scale and production suitability are unproven.
Until dependency-aware invalidation is qualified, collect the full relevant
declared scope rather than treating changed-file output as project-wide evidence.
