# Local rulesets: detector selection with retained identity

Rulesets are local JSON data, format `1.0.0`. A pack has a name and a core
semantic version (`major.minor.patch`), independent of cppulse's version,
the registry **format** version `2.0.0`, and each detector's prototype version.
There remain 22 experimental native checks. The three selected external
clang-tidy families are separate producer capabilities, not new native checks.

```json
{
  "format_version": "1.0.0",
  "name": "review",
  "version": "1.0.0",
  "preset": "all-native",
  "native": {
    "rules": {"CPP-CX-001": {"warning_threshold": 15}},
    "exclude_paths": ["vendor/**"]
  }
}
```

`inherits` is an ordered array of local pack paths relative to the declaring
pack. Parents apply in order, followed by the child. Shared diamond parents
apply once. Cycles, conflicting bytes for one name/version, more than 32 packs,
depth above eight, and files above 64 KiB fail actionably. No commands,
plugins, remote includes or network operations are accepted by pack loading.

Detector precedence is preset → inherited packs → child pack → project native
settings → explicit `--rule-option ID.OPTION=JSON`. Repeated command options use
their last value. Arrays such as `exclude_paths` replace the inherited array;
rule option objects merge by rule and option. `all-native`/`no-native` set all
22 enabled values. `native.select` explicitly selects a list from those 22;
unknown IDs fail. Selection applies before the same pack's explicit rule options.

Existing JSON/YAML project configuration still works. Its optional `ruleset`
path is relative to that project file. CLI `--ruleset PATH` replaces that pack
selection, then project native settings and command rule options still apply.
`cppulse config` prints resolved settings, origins and content identities.
`cppulse config --repo /path/to/project --ruleset /path/to/pack.json --profile safety-critical --native-output output/native.json` writes native-compatible settings plus
`output/native.json.identity.json`, refusing existing files. Both Docker stages
can select that same mounted file with `CPPULSE_CONFIG=/output/native.json`.
The scoring profile is inside this file. A nonempty container `CPPULSE_PROFILE`
is rejected with an instruction to resolve it into that file; the native
executable has no `--profile` option. Public host CLI profile precedence remains
unchanged. All selected preset baselines apply before explicit parent/child
native options, so a child preset cannot erase an inherited explicit threshold.
With no explicit container config, both wrappers discover the same single
`.cppulserc.json`/`.yml`/`.yaml` in `/repo` (`CPPULSE_REPO_ROOT` changes that
declared mount root); multiple files fail before either stage starts. Pack-based
project configuration must first be resolved to the shared native JSON file.
This forwarding contract is separate from actual Docker image/host qualification.

The predictor keeps `--config=None` without implicit discovery. Empty/commented
YAML and a missing profile retain the legacy default. Explicit missing files,
unknown profiles and unsupported fields fail. A supplied configuration is now
validated even with an explicit `--profile`; the profile overrides its value,
not validity. Absolute config paths work independently of the working directory.

`default` and `safety-critical` remain **scoring profiles**, selected by the
existing project/CLI profile precedence. A ruleset cannot declare scoring
weights, a policy, a health score or an acceptance gate. Disabled/excluded
required evidence must remain missing or incomplete, rather than improving a
gate or manufacturing a clean full-scope health result.

## Explicit clang-tidy recipes

The supported provider declaration is `providers.clang-tidy` with version
`19.1.7`, literal relative POSIX `scope_files`, and a `checks` object containing
only the following families. Every check has boolean `enabled`.

| Family | Supported options, under its `options` object |
| --- | --- |
| `bugprone-use-after-move` | None |
| `bugprone-dangling-handle` | Explicit `HandleClasses` array |
| `bugprone-unused-return-value` | Explicit `CheckedFunctions`, `CheckedReturnTypes` arrays and boolean `AllowCastToVoid` |

The default qualified handle classes are `std::basic_string_view` and
`std::experimental::basic_string_view`; arbitrary borrowing types are not
qualified. LLVM interprets the checked-function/return-type patterns. Arrays
render as semicolon-separated tool options. `AllowCastToVoid=false` treats an
explicit void cast as a positive; it differs from standard nodiscard warnings.

The resolver exposes exact `provider_arguments` for an explicit collector
recipe. Resolving a pack never executes that recipe. A diagnostic import
remains `origin=import`, with unverified scan completeness, even when its raw
bytes were locally captured. Empty diagnostics alone cannot prove clean
execution. Original IDs and occurrences remain; notes do not multiply findings,
and overlap is not independent confirmation.

Use-after-move is flow-sensitive, not path-sensitive: correlated conditions can
produce a false positive. Reinitialization and a single mutually exclusive
if/else are qualified clean controls. Member/global moves are outside the
qualified check scope. These are finite producer checks, not an accuracy study.

For collection, declare `ruleset` relative to the workspace (or select it with
`cppulse collect --ruleset PATH`). Include every inherited pack in `source.files`
and declare a matching `clang-tidy-text` external import. The explicit recipe
must contain the exact resolved `--checks` and `--config` arguments and matching
scope/version. Competing settings are rejected before collection. The collector
retains its generated `resolved_ruleset`; callers cannot supply that field as
execution proof. Changing a selected pack invalidates source currentness.

## Identity and readers

Pack content hashes, versions, declaring origins, native registry identity,
tool/rule versions and resolved settings are retained with the run. Content
identity changes when a parent changes, even if its detector settings happen to
remain equal. Readers inspect the selected retained bytes; they do not resolve
today's pack or defaults to reinterpret an older run. Hashes identify bytes and
do not authenticate imported producers.

The full 187-item production plan and P0–P14 remain unchanged. This batch does
not close broad Docker/platform/editor qualification or claim new native rules.

Predictor output publication uses private staging inside the selected output directory, including when that directory is a container bind mount. Both generated documents and the original input integrity check must pass before either target is replaced. Each file replacement is atomic; the two replacements are not a transaction, and failure of the second is reported as an error. Existing output directory/leaf symlinks and nonregular leaves are rejected.
