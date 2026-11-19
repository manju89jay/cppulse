# M8-03 bounded local branch/data-contract checkpoint

This implements a finite local slice of M8-03; full M8/P10 remain open. Production
scope still requires provider/access/history contracts, actual configured workflow
integration, and human interpretation evidence. Authored task/delivery events are
caller assertions, not successful provider deliveries or DORA qualification.

Source: `python/cppulse/branch_delivery.py`, the private `branch_delivery_private`
schemas, `tests/test_branch_delivery.py`, and `docs/development/branch-delivery.md`.
No shared CLI, Git miner, checkout/ref, remote API, or notification was modified.
Contracts precede repository reads; producer retains bounded actual Git receipts,
raw graph and tool identities; pure consumer validates pins and replay bindings.

Actual Git2.52.0 tests cover three selected refs, non-fast-forward merging,
divergence, unmerged work, task environment and explicit-time handling, shallow
clones, truncated/cancelled commands, missing pins, promisor denial, cherry-pick
non-equivalence, SHA-256, hostile literal paths and unsupported producer version.
The initial invariant red gate retained five failures in
`work/branch-invariants-red.log`; fixes passed18 and later expanded29 cases.
Independent review then reproduced inherited literal-zero `GIT_DIR` redirection
and a shallow-flag replay tamper. Both were fixed, with five additional regression
cases. Only `GIT_CONFIG_COUNT=0` is neutral; all other nonempty repository overrides
are denied. Shallow flags and matched before/after ref pins are bound to successful
probe receipts. Current34 tests passed11.13s; Black/Ruff passed.

`branch-delivery-actual.json` records an actual authored three-ref capture and
consumer replay, exact artifact hashes, per-environment declared observations,
selected task linkage, tool identity and elapsed runtime. Original config/capture/
report objects remain under ignored `work/branch-actual/`; the final proof uses
`fixture-reviewed`. Earlier fixture bytes are not relabeled as current-source
proof. One sample duration is evidence of execution, not a production budget.

Run focused verification:

```sh
PYTHONPATH=python .venv/bin/python -m pytest -q \
  --basetemp=/workspace/cppulse/work/branch-review-fixes \
  tests/test_branch_delivery.py
```

No commit or push was made. Internal projection/hash checks bind retained inputs;
no cryptographic authenticity, signed Git-object verification, historical ref
reconstruction, full OS CPU/RSS enforcement or cross-platform qualification is
claimed. All production requirements remain in the whole-scope ledger.

Root's subsequent independent review reproduced an inherited `GIT_TRACE_REFS`
write (6,260 bytes) during real Git reads. The red proof is retained in
`branch-delivery-trace-red.json`. The producer now masks every inherited
`GIT_TRACE*` key, disables repository-configured Trace2 targets, pins index/config/
attribute environment sources, and rejects shallow-file/config-file selectors.
Five additional real-Git regressions cover trace destinations, index/attribute
invariance, shallow override denial, and repository Trace2 configuration. Exact
combined module39+CLI14 gate:53 passed16.89s. The current actual capture proof
uses `fixture-trace-isolated`, superseding earlier capture summaries. These
changes preserve the no-authenticity and provider-qualification limits above.
