# S2 technical review

Status: accepted for the exercised local POSIX scope. Not a released format or
user usefulness review. Project HEAD and refs remain unchanged.

Implemented versioned schemas and semantic validation, conservative legacy
readers, content/context/artifact identities and coherent run storage. An archive
import retains existing bytes without upgrading historical source verification.
The public configuration/exit contract for installed work is in
docs/contracts/installed-cli.md. No collector or policy evaluator is implied by
these contracts.

Final parent command (without an exported PYTHONPATH):

```sh
source review/environment.sh
python -m pytest -v tests/test_contracts_v2.py tests/test_compatibility_v2.py tests/test_identities_v2.py tests/test_run_store_v2.py tests/test_pipeline_snapshot_import.py tests/test_native_install_contract.py
```

**203 passed**, including the S3 native-install schema prerequisite. Exact output
is logs/s2-final-gate-tests.log. Independent final store/import check: 55 passed.
Identity coverage was 91%; store coverage 92%. These are tested lines, not
evidence of detection accuracy, authenticity or product completeness.

Independent review reproduced and corrected policy binding/receipt consistency,
source subject mismatch, receipt cycles, future-dated deviations, a valid policy
publication rejected by list/singleton mismatch, ambiguous artifact ID/path
aliases, and mutable flat imports detected too late. Before-fix reproductions
and final checks are retained under logs/s2-*.log. Real content mutation through
the identities-to-publication callback is now a regression case.

`latest.json` refers to the last completed collection; `latest_attempt.json`
records newer completed/partial/cancelled publications. A completed collection
is not a passed policy. Readers resolve a concrete snapshot once. Staging is
never current. Failed source checks do not replace either pointer. A pointer
interruption may leave a coherent run retained by ID; it cannot expose mixed
artifact bytes.

Limits: POSIX directory APIs; exclusive writer lock with manual stale-lock
recovery; in-memory artifact reads; finite selected source inventories; no
atomic hostile-filesystem snapshot; no producer authentication. Imported legacy
analysis remains unverified against the source inspected after that analysis.
Full policy evaluation, collection and consumer comparison remain later stages.
