# Approved three-requirement batch

The user's latest authorization covers only FR-UX-12, FR-EVD-09 and FR-GIT-03,
necessary verification, evidence and ledger integration. All other implementation
remains queued. The 118 requirements, 60 M0–M9 tasks, nine obligations and P0–P14
remain unchanged. Tasks section 14, AC-01..16 and full P14 still define full delivery.
There are no commits, pushes or publication in this batch.

Independent review and canonical ledger integration are recorded in the adjacent
`three-item-closure-audit.json`; this document alone is not an acceptance proof.

## Artifact and source identity

- Checkout HEAD: `6f8b662a89b367f8c6883298dc97950150d7ba4f`.
- Reused wheel: `work/cloud-resume/wheel-query20/wheels/cppulse-0.2.0.dev2-py3-none-any.whl`,
  SHA256 `6bffdeb9dce30adb87cab3f800f33545fc06eb67af7271440b9baf433d918624`.
- Native archive: `work/installed-runtime11/cppulse-native-0.2.0.dev2-linux-x86_64.tar.gz`,
  SHA256 `96bee81401f068c45c4b0329f551e0f30b15c553140a49666085ccca5d01c19d`.
- Installed analyzer: SHA256 `5f7a130b5871c5a25307304d50542babeaf84e52cbdfeddbba97e149ff1c7b9d`.
- Matching installed package inventory, 228 matching source/test/helper pins and
  frozen evidence: `work/closure-fr3/batch-freeze.json`. The native reuse addendum
  verifies 89 analyzer source paths against the retained candidate.
- Later changes to unrelated issue/CTest/projection code are outside the reused
  wheel's scope. This batch does not qualify those modules or a new release set.

## FR-UX-12

Original: “Offline runtime operation shall be supported after dependencies and
packs have been installed. No account is required for core analysis.”

`work/closure-fr3/invocation-attempt3.json` records the actual installed bounded
native CLI journey, using a fresh account-free profile and whitelisted environment.
Two translation units complete with schema-checked snapshots and exit 0. No source
checkout package is on the runtime import path. A byte-verified overlay supplies
already installed GitPython/gitdb/smmap; no dependencies are fetched or rebuilt.

`deny_network.py` loads a kernel seccomp filter inherited across exec and all
children. IPv4, IPv6 and Unix socket probes return ENETUNREACH (101); socket,
socketpair, connect and send syscalls remain denied. Receipt:
`work/closure-fr3/network-denial-attempt3.json`.

After preinstalling the versioned local coverage policy pack, a second filtered
journey assesses retained real line-coverage facts, checks current inputs, and
writes JSON and HTML reports: all four commands exit 0, with a genuinely passed
policy gate. `coverage-pack-preinstalled.json` binds unchanged pack bytes before
the filter is loaded; `preinstalled-pack-check/verification.json` and
`invocation-positive-pack.json` retain commands, outputs and exact run/hash pins.

The earlier finding-limit pack returns honest insufficient_evidence (3) because
the compatibility native run lacks its required typed finding facts. This is
retained in attempt4 and is not counted as policy compliance. Its explain and
JSON/HTML reports exit 0. The positive coverage-pack result supplies a passing
installed-pack journey without changing runtime architecture or boundaries.

Usable installed invocation (the retained inputs and native dependencies must
remain installed):

```sh
export CPPULSE_NATIVE_PREFIX="$PWD/work/installed-runtime11/cppulse-native-0.2.0.dev2-linux-x86_64"
export LD_LIBRARY_PATH="$PWD/work/native-deps/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
work/cloud-resume/installed-query20/core-venv/bin/cppulse analyze \
  --repo work/closure-fr3/attempt2/identity-history \
  --compilation-database work/closure-fr3/attempt2/identity-history/compile_commands.json \
  --execution bounded --jobs 1 --no-history --format json --output /tmp/cppulse-offline-review
```

To reproduce kernel denial, use the complete explicit environment and launcher command in the
invocation receipts; use a fresh evidence output name rather than overwriting
the qualified artifacts. No account or access token is involved.

## FR-EVD-09

Original: “Keep line, branch, function, decision, and MC/DC coverage distinct.
Do not infer MC/DC from branch coverage.”

The real retained GCC14/gcovr8.8 producer is reused after checking every retained
artifact and current declared source material, not relabeled as new execution.
Its original run is `28956956d0544409bfd344fe5877e239`; exact source/manifest pins
are in `attempt4/coverage-retained-input-pins.json`.

Installed public import/normalization, assessment, current check and JSON/HTML
report flows retain these distinct outcomes:

| Adapter | Line | Branch | Function |
| --- | --- | --- | --- |
| LCOV | 5/8, passes 60% | 1/2, fails 60% | 2/3, passes 60% |
| Cobertura | 5/8, passes 60% | 1/2, fails 60% | unavailable/unknown |

`attempt4/results.json`, per-command stdout/stderr and pinned report views retain
the exact facts and independent policy outcomes. Expected branch failures exit 1.
Import-only facts retain origin `import`; all installed public evaluator controls
are unknown. Public assessment exits 3 and refuses to upgrade unverified historical
material; JSON/HTML historical reports still succeed. No imported report claims
current execution merely because its numeric counts are present.

Decision and MC/DC have no supported producer/denominator/condition identities in
this finite adapter profile. They are explicitly unsupported, never zero, passing
or copied from branch counts. Installed public negative policies requesting either
kind with a branch method and a zero threshold are rejected (2) rather than
manufacturing a positive outcome. No decision/MC/DC measurement support is claimed.

Example using retained store and policy:

```sh
work/cloud-resume/installed-query20/core-venv/bin/cppulse check \
  --store work/closure-fr3/attempt4/coverage-lcov-store \
  --workspace /tmp/cppulse-coverage12-live/actual-coverage0/workspace \
  --policy work/closure-fr3/attempt4/lcov-policy.json
```

Use the exact run/hash arguments in `attempt4/commands.json` for historical
qualification. Latest-head queries may select the later positive pack assessment.

## FR-GIT-03

Original: “Support contributor aliases, bot exclusion, former contributors, and
configured pair-programming attribution. Authorship is a knowledge proxy, not
proof of expertise.”

Five controlled local commits exercise alias consolidation, a bot-only commit,
former-contributor flags and configured pair attribution. Duplicate pair/self/alias/
bot trailers do not add credit. Four installed public `analyze --history` runs
exit 0: configured, identical repeat, author-only and bots-included control.
Configured reports are byte-equivalent as documents. Both files have three accepted
touches and weighted mass three. Shares are Alice/Bob 1/2–1/2 for a.cpp and
2/3–1/3 for b.cpp. Author-only changes the shares as expected; disabling exclusion
adds the bot and exactly one touch/mass per file. Former Bob remains explicitly
flagged. Aliased and excluded identities do not reappear as separate contributors.

The public `git_behavior-json` artifact retains the visible limitation:
“Authorship is a historical familiarity/knowledge proxy, not proof of expertise,
individual performance or current availability.” It remains a profile of historical
contribution, not proof of expertise, availability or individual performance.

`attempt2/commands.json`, `attempt4/history-input-pins.json` and the four immutable
run/manifest pins in `attempt4/results.json` bind the public output to the exact
controlled histories. The local fixture has no remote and must never be uploaded.
The focused component run passed 86 tests covering attribution regressions and
coverage adapters/contracts; command, result and source pins are in the freeze.

Use `analyze --history --behavior-config <recorded-config> --behavior-cutoff
2026-11-16T00:00:00Z` with the recorded fixture and installed dependencies. Exact
commands are retained in attempt2. M6-01, M6-02 and wider M6/M8 acceptance do not
close from this requirement-specific evidence.

## Limits and preserved failures

Evidence qualifies this installed Linux/x86_64 host with preinstalled dependencies,
native kit and authored local policy packs. It does not qualify all platforms,
network installation, all report formats, marketplaces, editor lifecycle or full
production delivery. The 3,327-pass historical frozen baseline is preserved.
No broad suite or package rebuild was needed because no product code changed.

Failed attempts 1–3 remain recorded: initial untyped artifact read, unsupported
decision/MC/DC policy requests, empty job-context policy, incorrect absent-function
method, expected insufficient-evidence pack result and attempted assessment read
after imported material was correctly refused. These are harness/selection errors
or meaningful negative controls, not silently deleted passing evidence. Corrected
checks bind matching existing producers rather than rerunning or weakening them.

The strict final verifier must still run unchanged. Exit 3 means the full program
remains incomplete; individual reviewed closures do not change that endpoint.
