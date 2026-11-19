# Behavioral Git producer Cloud checkpoint

Source remains uncommitted on `codex/cppulse-local-core-20261114` at
`6f8b662a89b367f8c6883298dc97950150d7ba4f`. No remote refs were changed.

Implemented a finite producer slice for FR-GIT-03/04/05 and component aggregation
from FR-GIT-06. New standalone versioned config/report schemas precede the pure
producer; an optional consumer reuses the miner's existing rename-projected scan.
It emits separate validated `git_behavior.json`; the legacy output schema and
ordinary miner invocation retain their behavior. See `docs/contracts/git-behavior.md`.

The result retains explicit UTC cutoff/window/bounds, aliases, bot exclusion,
configured pair shares, former-contributor labels, team and per-file ownership,
fragmentation/offboarding, minimum-support historical co-change, component
aggregation, every denominator and incomplete/truncated limitations.

Executed checks (overlapping, not additive counts):

- Initial producer tests failed collection because the runtime module was absent:
  `behavior-logs/producer-red.log`.
- Stored formula mutation cases exposed missing semantic rejection before the
  validator was completed: `behavior-logs/semantics-red.log` (five failed).
- Independent review found noncanonical double-slash/trailing-slash paths and
  body `Co-authored-by` examples incorrectly counted as trailers. Red regression
  proof is `behavior-logs/review-red.log`; both causes were fixed. The reviewer
  rechecked 28 focused cases and recorded `git-behavior-independent-review.md`.
- `python -m pytest -q tests/test_git_behavior.py tests/test_optional_history.py`:
  **31 passed** (`behavior-logs/behavior-history.log`).
- Required component command from `git-miner`:
  `../.venv/bin/python -m pytest -v --cov=src --cov=cppulse.git_miner tests/`:
  **90 passed** (`behavior-logs/git-miner-component.log`).
- Extended component gate including the new producer and history cases:
  `../.venv/bin/python -m pytest -v --cov=src --cov=cppulse.git_miner tests/ ../tests/test_git_behavior.py ../tests/test_optional_history.py`:
  **121 passed**, reported aggregate component coverage **91%**
  (`behavior-logs/git-miner-extended.log`). This is not whole-project coverage.
- Black and Ruff checks passed for all changed production/test files.
- Actual frozen cppulse repository history through the optional miner command:
  **125 observed commits**, **102 current tracked C++ files**, **16 accepted**,
  **9 retained file coupling pairs**, partial because merge/rename lineage is
  not verified. Exclusions include one bulk commit, sixteen merges, and ninety-two
  commits with no current selected paths. Final exact command, source/artifact
  hashes, cutoff, counts and limitations: `git-behavior-evidence.json`.

All controlled Git fixture commits are temporary and never uploaded. The actual
checkpoint run mines preexisting committed history; it does not attribute
uncommitted edits or establish current contributor availability/expertise.

Remaining: shared bounded/incremental scanner reuse with silo/SZZ; rewrite/shallow
and cross-branch lineage qualification; function/symbol coupling; representative
resource measurements; release/installed top-level workflow routing, indexed API
and dashboard/goal consumers. The optional miner module is directly callable.
The pair footer parser supports its documented finite blank-separated single-line
trailer dialect, not all Git trailer forms. Neither P6 nor whole M6/FR-GIT tasks
are marked complete from this slice.
