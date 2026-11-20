# Full-program reconciliation, 16 November 2026

The live checkout remains `/workspace/cppulse` on
`codex/cppulse-local-core-20261114`, HEAD
`6f8b662a89b367f8c6883298dc97950150d7ba4f`, with all implementation changes
uncommitted. No replacement checkout, reset, commit or push occurred.

The endpoint is tasks.md section14, AC-01–16 and full-plan P14. The exact command
`/workspace/cppulse/.venv/bin/python scripts/verify_delivery.py --require-complete`
returned **3**, both before and after the inventory correction. `complete:false`
means the program remains incomplete. The JSON records contain all187 current
IDs and each remaining item's phase, state, work and blocker. No requirement
was accepted merely because a source file, candidate or test subset exists.

Planning JSON/CSV/guard and plan wording now retain the same **118 numbered
requirements,60 tasks,nine additional obligations and P0–P14** as the execution
ledger. The explicit `ENV-DOCKER-COMPOSE` row was added to the old eight-item
planning supplement; no authoritative requirements/design/tasks text changed.
A regression rejects removing that ninth obligation. The planning guard passes
coverage only, never production acceptance.

Key current deviations/unfinished work include public scheduling and checked
incremental cache/history/query integration (`M2-02`–`M2-06`), complete corpus and
accuracy qualification (`M4-05`,`AC-15`), empirical temporal labels/evaluation
(`M6-05`), full client workflow/large-result agreement (`M7-02`,`AC-12`), reviewed
domain packs (`M5-07`), release/platform/usefulness qualification (`ENV-MATRIX`,
`HUMAN-USEFULNESS`,P9), and all remaining M8/M9/P14 acceptance. The records retain
all other remaining IDs rather than substituting this short list for the scope.

Actual unavailable Windows/MSVC/MinGW/macOS and consenting usefulness studies
remain blocked inputs. Authorized standards editions/qualified mapping review,
provider/language/hosting decisions and separately authorized external effects
remain explicit obligations. Independent reversible work continues around them.

The persistent Goal UI request could not be executed: the exposed tool catalog
contains no Goal creation/status tool. No active Goal state or changed Goal
budget is claimed. The authorization remains active in this task and ledger;
a local record is not a replacement for a tool-confirmed persistent Goal.

Re-run `scripts/verify_delivery.py --require-complete` after substantive work.
A zero result is necessary but not sufficient: evidence must still satisfy the
original acceptance and independent review. No weakening or scope removal is
permitted to force a successful exit.
