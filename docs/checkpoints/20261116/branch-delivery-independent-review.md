# Independent private branch/delivery review — 16 November 2026

Read-only source review of branch_delivery.py, private schemas and test_branch_delivery.py. Only ignored work artifacts were written. Prior clean-agent records remain separate; no complete M8/provider/release qualification is claimed.

## Blockers reproduced

### P2: ambient GIT_DIR=0 redirects capture to another repository

At the ambient guard, every override is considered harmless when its string value is `0`. Only GIT_CONFIG_COUNT has a natural zero-disable interpretation; GIT_DIR=0 is a real relative repository path. The process helper merges supplied environment entries onto os.environ, leaving this override active.

The local reproducer creates the authored merge graph and a bare clone under the original repository's child `0`, then moves original main back to its root commit. With GIT_DIR=0, capture(original_root,cfg) reads the child bare clone: repo_path claims original_root, main is matched to the old merge pin and graph_status is available with no limitations, while main in the actual selected original repository points to the different root commit. Because the substituted repository is bare, the producer skips its --show-toplevel comparison.

Artifacts: `work/branch-independent/reproduce.py`, `results.json`. The recorded `selected_actual_main` inside the override scope follows the same override and is intentionally superseded by `selected_actual_main_without_override`, which records the actual selected repository ref after clearing it.

Fix: reject any nonempty repository/config override except individually documented neutral values, particularly allow zero only for GIT_CONFIG_COUNT if desired. Alternatively clear the whole relevant Git environment before launching. Bind the observed absolute gitdir/common-dir identity as well as top-level worktree, including bare repositories. Test GIT_DIR=0 against a different nested bare repository.

### P2: shallow flag mutation upgrades incomplete history to complete on replay

`validate_capture` binds raw graph bytes and some execution flags, but never binds capture.shallow to the observed --is-shallow-repository receipt. Git hides parent edges at shallow boundaries, so graph closure alone cannot restore this fact.

An actual local --depth=2 clone yields shallow=True, history_complete=False and complete_in_window_count=null. Changing only capture.shallow=False is accepted by validate_capture; analyze then produces history_complete=True and complete_in_window_count=3. Even the original shallow/incomplete limitation is still present, so the accepted result is internally contradictory. This is an offline replay consistency issue, not a producer-authentication claim.

Artifacts: `work/branch-independent/shallow-replay.py`, `shallow-replay-results.json`. The shallow clone is real and lives under ignored work/branch-independent/shallow.

Fix: preserve/bind probe outputs to their command receipts and derive shallow/ref/tool/repository admission flags from those exact outputs. For the boolean shallow probe, comparing the unique matching successful nontruncated receipt SHA against the digest of true/false plus newline can enforce the basic binding without a large payload. Apply equivalent checks to initial and post-capture ref-pin observations and exact finite rev-list argv. Add mutation regressions for shallow flag alone, changed-ref status promotion and substituted command arguments.

## Other inspected semantics

The aware half-open cutoff and event-recorded-at constraints, environment-specific linkage, explicit caller-declaration origin, no historical-ref reconstruction, no task/patch equivalence inference, finite command/wall/log/commit budgets, and unknown ancestry handling otherwise fit the stated narrow source slice. Positive ancestry may be observed in incomplete graphs; negative/diverged/count completeness requires full closure and nonshallow successful extraction. Ref timestamps do not reconstruct historical branch tips. Declared delivery counts remain claims even when Git chronology is inconsistent; this is labeled in each event.

The producer uses separate argv with --end-of-options/ref validation, fixed read-only Git metadata operations, no lazy fetch and protocol denial. Time/log bounds do not establish Python/filesystem or OS CPU/memory guarantees. The two blockers above must remain visible despite passing normal tests.

## Fix recheck

Both reproduced blockers are resolved at module SHA-256 `4c565a0472ed3eb94f5a56934a1a27232d4b22737ea639a4f9f70cd7426bb3d4`. Rechecking the original retained local repositories with current code:

- GIT_DIR=0 produces unavailable graph with zero commands and explicit ambient-override limitation; it cannot read the nested alternate bare repository.
- Actual shallow clone capture with only shallow=False changed rejects: `Shallow boundary flag contradicts retained probe receipt`.
- Removing matched-ref verification receipts rejects: `Matched ref lacks consistent before/after probe receipts`.

Independent recheck script/output: `work/branch-independent/recheck.py`, `recheck-results.json` (SHA-256 `7c8a15f6d33ad8f892f4e83e3e855516caa23a4726269d185cf8e7ed22233256`). Initial red proof artifacts remain unchanged.

Focused recheck command:

```sh
PYTHONPATH=python .venv/bin/python -m pytest -q --basetemp=/workspace/cppulse/work/branch-independent-pytest-recheck tests/test_branch_delivery.py
```

Observed **34 passed in 10.72s**, exit 0; log `work/branch-independent-pytest-recheck.log`. The earlier independent run also passed 34 in 11.51s while source-owner fixes were landing, so the explicit latest recheck supplies the final result.

Reviewed final identities:

| File | SHA-256 |
|---|---|
| tests/test_branch_delivery.py | 4f853745437ac14318a415519ac0649f371f879ad303cc537f86885bbcb13230 |
| private capture.schema.json | 5675d931a6c46291d761018edb4902176f6f70f0d3ddecb606e75440e0b6ebc2 |
| private config.schema.json | f289b003702f41fc45e44ebc65403869b3a872acb8ad7a24366abab5d6c15d83 |
| private report.schema.json | 5fec1b224f0f8c97933dbc9994573d5873db422441d9a5c95972d4cba6bb848d |

No remaining demonstrated blocker from this review. This result concerns the bounded local producer/consumer slice and these exact bytes; full M8, external provider and released-package qualification remain open. No shared source, schemas, tests or docs were edited by this reviewer.
