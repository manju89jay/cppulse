# Weighted ownership and knowledge maps

FR-GIT-05 is verified against its complete original criterion: weighted ownership,
knowledge maps, offboarding simulation and fragmentation at author/team levels.
The other 173 items remain retained. Counts: 14 verified, 110 open, 61 active,
2 blocked; production remains incomplete. All 187 definitions and P0–P14 are
unchanged. All new work remains uncommitted.

Five actual installed public Git-miner calls on a controlled five-commit history
passed. Their author masses are 1/.5/1, total 2.5; declared core/ops team masses
are 1.5/1. Author fragmentation is .64, team fragmentation .48. Removing the
declared core cohort (Alice and Bob) reports .6 removed, .4 remaining and
Carol, whose retained team is ops. File and component knowledge maps agree.
Bot-only ownership stays unavailable; unrelated unassigned ownership survives
removal of all declared authors. Alias/pair attribution does not double count.

The independent review decoded and verified the actual Git DAG/blobs, checked
all 233 installed payloads, recomputed all five complete reports through installed
APIs and independently checked author/team arithmetic (676 bounded checks).
Review: `work/runtime-review61/knowledge58/review.json`; result:
`work/knowledge-model58/worker/qualification.json`. Canonical command/source
proof: `work/knowledge-model58/canonical-proof.json`. Ledger before/after and
the unchanged definition hash: `work/knowledge-model58/ledger-audit.json`.

The actual successful command, with installed modules first, was:

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/workspace/cppulse/work/installed-git-scope52/installed:/workspace/cppulse/work/closure-fr3/dependencies \
  /workspace/cppulse/work/cloud-resume/installed-query20/core-venv/bin/python \
  /workspace/cppulse/work/knowledge-model58/worker/run_installed.py
```

That retained command creates its local fixture and is evidence, not an
idempotent replay instruction. For use, pass the retained example configuration
`worker/declared-team-core-cohort/requested-config.json` as `behavior_config` to
the installed public `cppulse.git_miner.main.run` API; set `teams` and
`offboarding_ids` to the intended declared cohort. `git_behavior.json` contains
file/component `ownership`, `teams`, fragmentation and offboarding results.

Wheel SHA256: `fc61906e4b2fab82aca9f8cb409988000fd258393a5d4a501f4fea830d5c7c5b`.
Behavior source SHA256:
`9ff7fa81b82af406e976bd4ccde6fbb46599282ef108728e74a18b1dc6395be1`.
Main source SHA256:
`2bf8f76c0e27f8b8cdce1e9602085f71e70aa33e9fe2db25e5d4a97a83eb4e94`.

Teams are declared configuration, not authenticated organization membership.
Team removal uses the explicitly selected author cohort; there is no native
team selector or post-simulation team table. Historical ownership stays
historical. Unknown affiliations remain distinct unassigned identities.
Authorship is visibly a knowledge proxy, not expertise or current availability.
No broader M6 or scale criterion is closed by this result.

The separately active SDK preflight repair changes a different source path.
Older installed/core evidence remains bound to its original bytes until the
current SDK source/artifact refresh is reviewed; no old execution is relabelled.
