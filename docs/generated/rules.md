# Native rule reference

Generated from `python/cppulse/data/rule_registry.json`. Regenerate with `python scripts/check_generated.py --write`; check with `python scripts/check_generated.py`.

All 22 checks are **experimental** and enabled by default. Availability depends on the selected successfully parsed C++ context and libclang AST. A registered check does not establish complete source coverage, correctness, MISRA compliance or certification. Zero findings can coexist with partial or unavailable analysis. `prototype-1` is an implementation label, not a validated stable release.

The `default` scoring profile excludes MISRA findings from scores and ranking; it does not disable MISRA detectors. `safety-critical` includes those experimental signals in scoring. Use an explicit per-rule `enabled: false` to disable a detector.

| ID | Name | Category | Maturity | Default configuration |
| --- | --- | --- | --- | --- |
| CPP-CX-001 | Cyclomatic complexity | complexity | experimental | `{"enabled": true, "error_threshold": 25, "warning_threshold": 15}` |
| CPP-CX-002 | Function length | complexity | experimental | `{"enabled": true, "error_threshold": 150, "warning_threshold": 80}` |
| CPP-CX-003 | Parameter count | complexity | experimental | `{"enabled": true, "error_threshold": 8, "warning_threshold": 5}` |
| CPP-MEM-001 | Raw pointer ownership | memory_safety | experimental | `{"enabled": true}` |
| CPP-MEM-002 | Manual memory management | memory_safety | experimental | `{"enabled": true}` |
| CPP-MEM-003 | C-style array parameters | memory_safety | experimental | `{"enabled": true}` |
| CPP-MOD-001 | C-style casts | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-002 | Deprecated C headers | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-003 | Missing override | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-004 | Raw string literal opportunities | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-005 | Iterator auto opportunities | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-006 | Range-for opportunities | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-007 | Null pointer literals | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-008 | Unscoped enums | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-009 | Typedef aliases | modernization | experimental | `{"enabled": true}` |
| MISRA-001 | Goto statements | misra | experimental | `{"enabled": true}` |
| MISRA-002 | Implicit narrowing conversions | misra | experimental | `{"enabled": true}` |
| MISRA-003 | Union declarations | misra | experimental | `{"enabled": true}` |
| MISRA-004 | C dynamic allocation calls | misra | experimental | `{"enabled": true}` |
| MISRA-005 | Direct recursion | misra | experimental | `{"enabled": true}` |
| MISRA-006 | Multiple return statements | misra | experimental | `{"enabled": true}` |
| MISRA-007 | Uninitialized local variables | misra | experimental | `{"enabled": true}` |

## Detection scope

- **CPP-CX-001:** Detect functions with high cyclomatic complexity. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence. Detector semantics revised on 2026-11-14 with explicit written-type and function/template scope regressions; experimental maturity is unchanged.
- **CPP-CX-002:** Detect functions that are too long. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence. Detector semantics revised on 2026-11-14 with explicit written-type and function/template scope regressions; experimental maturity is unchanged.
- **CPP-CX-003:** Detect functions with too many parameters. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence. Detector semantics revised on 2026-11-14 with explicit written-type and function/template scope regressions; experimental maturity is unchanged.
- **CPP-MEM-001:** Detect use of raw `new` expressions. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MEM-002:** Detect explicit `delete` expressions. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MEM-003:** Detect C-style array parameters. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-001:** Detect C-style cast expressions. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-002:** Detect inclusion of deprecated C headers. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-003:** Detect virtual methods that are missing the override keyword. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-004:** Detect string literals with many escape sequences. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-005:** Suggest `auto` for verbose iterator type declarations. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence. Detector semantics revised on 2026-11-14 with explicit written-type and function/template scope regressions; experimental maturity is unchanged.
- **CPP-MOD-006:** Suggest range-based for loops for index-based loops. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-007:** Detect use of NULL macro or integer 0 as a null pointer. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-008:** Detect unscoped (plain) enum declarations. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-009:** Detect typedef declarations that should use `using`. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **MISRA-001:** Detect use of goto statements. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **MISRA-002:** Detect implicit narrowing conversions. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **MISRA-003:** Detect union declarations. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **MISRA-004:** Detect dynamic memory allocation via C library functions. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **MISRA-005:** Detect direct recursive function calls. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **MISRA-006:** Detect functions with multiple return statements. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **MISRA-007:** Detect variable declarations without initializers. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.

Complexity findings trigger when a value is strictly greater than the warning threshold; error severity requires strictly greater than the error threshold. The generated config is an explicit default example, not a project-specific recommendation. Thresholds use nonnegative integers up to 2147483647 (the supported native int range) in the reviewed config schema. Unknown rule IDs are refused by that schema.
