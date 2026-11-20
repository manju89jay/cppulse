# Native-bound dry-run repair preview

This private P11 preview prepares a reviewable textual proposal. It never applies
source edits, starts a compiler/test, commits, creates a PR, invokes a model or
contacts a service. Its initial supported transformation is deliberately narrow:
one ordinary builtin C++ typedef statement on one physical line, such as
`typedef unsigned long Count;`, becomes `using Count = unsigned long;`.

The plan requires an explicitly pinned immutable run produced by verified
collection and native normalization. A loose findings JSON or an unverified
`analyze` archive cannot supply this provenance. The selected file must have
complete, matched native analysis, the rule actually executed, a matching rule
`prototype-1` version/retained registry, an observed C++11/14/17/20 parse argument and retained
original source bytes. Current finite source and generated-output identities are
checked before and after planning.

Run the installed package module explicitly:

```sh
python -m cppulse.repairs \
  --store /absolute/path/to/results --workspace /absolute/path/to/project \
  --run-id RUN --manifest-sha256 SHA256 \
  --output /absolute/path/to/proposal.json
```

`--observation-id ID` can be repeated to select at most 64 observations.
Without it, only native `CPP-MOD-009` observations are selected. Other findings
are not silently described as fixed or clean. Output creation is exclusive and
atomic: a preexisting output, including a symlink, is never replaced. Output anywhere inside the selected
store or its immutable runs is rejected before publication.

The private schema is
`python/cppulse/contracts/schemas/repairs_private/plan.schema.json`. Each edit
retains canonical file identity, old/new file hashes, precise byte offsets,
original/replacement text, and the original observation, parse/job context,
inventory, receipt, rule-version and registry-hash references. Repeated compatible
observations can share one edit without losing their provenance. The diff and
plan have deterministic integrity digests; these do not authenticate a producer.

Exit 0 means a finite plan was prepared (possibly a supported-rule no-op), 3
means selected observations include unsupported cases, and 2 means invalid,
stale, inaccessible or conflicting input/output;130 records cancellation. No exit establishes that a
patch was applied or that behavior was verified. Original receipts remain the
original executions; proposal creation never manufactures fresh evidence.

Macros/directives, explicit compiler macro definitions (including `-DNDEBUG`) or forced includes/macros,
line splices, control-character paths, multi-declarations, arrays, pointers/function types, user-defined
or dependent types, ambiguous/mismatched typedef names, partial parsing and
unsupported language contexts are rejected with reasons. The current finite
preview accepts at most a 32 MiB retained snapshot, one-MiB source files, 64
selected observations and an eight-MiB published plan. Large runs need the
separate indexed/bounded query infrastructure; omission is never a clean result.

Tests exercise actual GCC C++11/14/17/20 compilation, static type checks and
runtime return behavior before and after the proposed bytes for the authored
builtin-alias fixture. Actual native collection/module/installed proofs are
recorded in the checkpoint. These examples do not establish general semantic,
ABI, performance, runtime or safety equivalence. The responsible user must build
and test every required configuration before accepting a proposal. Unlisted
source additions and the general host/dependency closure remain explicit limits.

M9-01 whole-task acceptance and M9-02 semantic/AI repair remain separate work;
this module is not an automatic repair agent or a production-completion claim.
