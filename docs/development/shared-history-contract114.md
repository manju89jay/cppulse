# Shared history contract

`shared_history`, version `2.0.0`, defines the M6-01 interface for contributor
identity, persistent file identity and rename history, distinct-commit coupling
support, and current component and declared symbol history. Load and validate it
through the existing namespaced API:

```python
from datetime import datetime, timezone
from cppulse.contracts import load_schema, validate
from cppulse.contracts.history_contract import (
    from_history_scan, validate_history_binding,
)
from cppulse.git_miner.history import scan_history

schema = load_schema("shared_history")
scan = scan_history(repo)  # existing checked shared scan, not a second collector
facts = from_history_scan(
    scan, behavior_config,
    source_digest=selected_source_digest,
    context_id=selected_context_id,
    repository_id="stable-local-repository-identity",
    cutoff=datetime.now(timezone.utc),
    head=repo.head.commit.hexsha,
)
validate("shared_history", facts)
validate_history_binding(
    facts, source_digest=selected_source_digest,
    context_id=selected_context_id,
)
```

The caller supplies the expected source digest, context and stable repository
identity. Validation checks their shape and cross-references; the binding helper
checks equality with independently selected inputs. Neither a digest, a
validated document nor the declared producer name authenticates a producer.
`producer.authenticated` is always false. Authorship remains a knowledge proxy,
not proof of expertise.

| Area | Contract and checked boundary |
| --- | --- |
| Contributors | Canonical identifiers use trimmed, case-folded spellings. Each alias belongs to exactly one canonical contributor; aliases cannot collide with canonical IDs. Bot and former-contributor flags remain distinct. Former contributors retain their observed history; bots are excluded from participants. |
| Pair attribution | `author_only` declares one contributor. Explicit `coauthor_trailers` uses the existing finite trailer parser. Participants are unique canonical non-bot identities, so repeated actors, aliases and bot trailers cannot create duplicate contributors. |
| Commits | A unique full Git object ID, parent IDs, timestamp, delta availability, explicit participant/file IDs and exactly one exclusion reason or an accepted state. The policy retains cutoff/window, merge, bulk, explicit exclusion, support and truncation choices. |
| Unknown deltas | A shallow boundary can look like a root whose tree lists all current files. That listing is not a verified change set. The existing adapter's canonical `has_known_change_delta` flag makes the delta unavailable; this contract publishes no changed-file IDs or total and counts no ownership/co-change for it. Missing first-parent ancestry is also conservative unavailable scope. Known later commits remain usable. |
| Persistent files | IDs derive from stable repository ID plus observed introduction commit/path. A later observed first-parent rename retains that anchor and ID. Current path and explicit rename edges are separate. Partial/shallow/merge lineage promises stability only in the observed selected history; it never claims identity across unobserved ancestry or branches. |
| Rename events | Each event names a known file/commit and distinct canonical relative old/new paths. Events must form a connected chain back from the current path, cannot repeat a file/commit pair and require an available changed-file delta. |
| Co-change support | `historical_cochange`, counted in distinct accepted commits. Each pair carries the exact supporting commit IDs and both touch denominators. A commit/file/component contributes once; pair support is the intersection of eligible touch sets. Minimum support and deterministic record truncation are explicit. This is not a static include/call dependency. |
| Components | Current configuration partitions declared files exactly once, including an unassigned component where needed. Component history is the union of accepted member-file changes. It projects today's map; it does not reconstruct historical architecture or sum duplicate file touches as duplicate component commits. |
| Symbols | A stable declared anchor key, current/previous keys, file ID, explicit declared lineage state and supporting commit IDs. Ambiguous or missing lineage is unavailable. Actual Git projection returns no symbols and explicitly unavailable symbol history: there is no symbol-history producer here. Typed examples are consumer-authored synthetic declarations, not native observations or implementation of FR-GIT-04. Availability concerns the supplied declared symbols only. |
| Empty/partial scope | An empty or wholly unusable history is defined and unavailable, not clean or complete. Missing ancestry, selected traversal bounds and scanner limitations remain visible. Counts must reconcile observed, accepted and excluded commits. |

The schema is closed, local Draft-07 and packaged with the existing v2 schemas.
Unsupported versions/options, duplicate IDs, conflicting aliases, unsafe paths,
unknown references, impossible totals, duplicate participants/support,
disconnected renames and contradictory availability are errors. The semantic
validator recomputes the support sets and denominators from the declared commit
facts. It introduces no ownership weights, scoring model or second Git scan.

`tests/test_shared_history_contract114.py` exercises real disposable local Git
histories containing aliases, bots, a former pair contributor, a bulk commit,
an actual branch merge and an actual rename. Separate real append/rename and
depth-one shallow histories check persistent identity and unknown-delta scope.
Authored negative documents are retained in each test's output directory. The
symbol example is named as a consumer-authored declaration and its negative
controls reject unknown support, ambiguous availability and producer claims.
Fixture commits stay local and must never be uploaded.

This interface does not qualify streaming/cache scale, a symbol-history
producer, function-level coupling, producer authentication, expertise inference
or complete release/platform acceptance. Those original requirements remain in
the delivery plan.
