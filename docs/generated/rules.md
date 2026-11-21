# Native rule reference

Generated from `python/cppulse/data/rule_registry.json`. Regenerate with `python scripts/check_generated.py --write`; check with `python scripts/check_generated.py`.

All 22 checks are **experimental** and enabled by default. Availability depends on the selected successfully parsed C++ context and libclang AST. A registered check does not establish complete source coverage, correctness, MISRA compliance or certification. Zero findings can coexist with partial or unavailable analysis. `prototype-*` versions are implementation labels, not validated stable releases.

The `default` scoring profile excludes MISRA findings from scores and ranking; it does not disable MISRA detectors. `safety-critical` includes those experimental signals in scoring. Use an explicit per-rule `enabled: false` to disable a detector.

| ID | Version | Name | Category | Maturity | Default configuration |
| --- | --- | --- | --- | --- | --- |
| CPP-CX-001 | prototype-2 | Cyclomatic complexity | complexity | experimental | `{"enabled": true, "error_threshold": 25, "warning_threshold": 15}` |
| CPP-CX-002 | prototype-2 | Function length | complexity | experimental | `{"enabled": true, "error_threshold": 150, "warning_threshold": 80}` |
| CPP-CX-003 | prototype-2 | Parameter count | complexity | experimental | `{"enabled": true, "error_threshold": 8, "warning_threshold": 5}` |
| CPP-MEM-001 | prototype-1 | Raw pointer ownership | memory_safety | experimental | `{"enabled": true}` |
| CPP-MEM-002 | prototype-1 | Manual memory management | memory_safety | experimental | `{"enabled": true}` |
| CPP-MEM-003 | prototype-1 | C-style array parameters | memory_safety | experimental | `{"enabled": true}` |
| CPP-MOD-001 | prototype-2 | C-style casts | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-002 | prototype-2 | Deprecated C headers | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-003 | prototype-1 | Missing override | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-004 | prototype-1 | Raw string literal opportunities | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-005 | prototype-2 | Iterator auto opportunities | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-006 | prototype-2 | Range-for opportunities | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-007 | prototype-1 | Null pointer literals | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-008 | prototype-1 | Unscoped enums | modernization | experimental | `{"enabled": true}` |
| CPP-MOD-009 | prototype-1 | Typedef aliases | modernization | experimental | `{"enabled": true}` |
| MISRA-001 | prototype-1 | Goto statements | misra | experimental | `{"enabled": true}` |
| MISRA-002 | prototype-1 | Implicit narrowing conversions | misra | experimental | `{"enabled": true}` |
| MISRA-003 | prototype-1 | Union declarations | misra | experimental | `{"enabled": true}` |
| MISRA-004 | prototype-1 | C dynamic allocation calls | misra | experimental | `{"enabled": true}` |
| MISRA-005 | prototype-1 | Direct recursion | misra | experimental | `{"enabled": true}` |
| MISRA-006 | prototype-1 | Multiple return statements | misra | experimental | `{"enabled": true}` |
| MISRA-007 | prototype-1 | Uninitialized local variables | misra | experimental | `{"enabled": true}` |

## Detection scope

- **CPP-CX-001:** Detect functions with high cyclomatic complexity. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence. Detector semantics revised on 2026-11-14 with explicit written-type and function/template scope regressions; experimental maturity is unchanged.
- **CPP-CX-002:** Detect functions that are too long. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence. Detector semantics revised on 2026-11-14 with explicit written-type and function/template scope regressions; experimental maturity is unchanged.
- **CPP-CX-003:** Detect functions with too many parameters. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence. Detector semantics revised on 2026-11-14 with explicit written-type and function/template scope regressions; experimental maturity is unchanged.
- **CPP-MEM-001:** Detect use of raw `new` expressions. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MEM-002:** Detect explicit `delete` expressions. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MEM-003:** Detect C-style array parameters. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-001:** Detect non-void C-style cast expressions, including nested non-void conversions inside intentional discards. Canonical void-result casts and void aliases are exempt; named C++ casts are unchanged. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-002:** Suggest C++ replacements only for direct literal unqualified angle operands such as <stdio.h> resolved to compiler-classified system headers. Qualified, quoted, macro-expanded and non-system project shadow includes are excluded; transitive includes are not replacements for their including directive. Compiler-marked system roots are trusted rather than independently standard-library attested. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-003:** Detect virtual methods that are missing the override keyword. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-004:** Detect string literals with many escape sequences. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
- **CPP-MOD-005:** Suggest `auto` for verbose iterator type declarations. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence. Detector semantics revised on 2026-11-14 with explicit written-type and function/template scope regressions; experimental maturity is unchanged.
- **CPP-MOD-006:** Suggest range-for only for a conservative fixed-array accumulation: a zero-initialized int/unsigned index, a matching literal constant-array bound, unit increment and one built-in scalar += of array[index]. Pointer ranges, extra index uses, mutation, calls, aliases, volatile values and other loop shapes remain unassessed. This is a review suggestion, not an automatic rewrite or general equivalence proof. Availability depends on a successfully parsed selected context; findings are experimental signals, not compliance evidence.
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
