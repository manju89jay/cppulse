// Generated from cppulse/data/rule_registry.json; use scripts/check_generated.py.
#pragma once
#include <variant>

#include "rules/complexity/cyclomatic_complexity.h"
#include "rules/complexity/function_length.h"
#include "rules/complexity/parameter_count.h"
#include "rules/memory_safety/manual_memory_mgmt.h"
#include "rules/memory_safety/raw_pointer_ownership.h"
#include "rules/memory_safety/unsafe_array_access.h"
#include "rules/misra/init_all_vars.h"
#include "rules/misra/no_dynamic_alloc.h"
#include "rules/misra/no_goto.h"
#include "rules/misra/no_implicit_conversion.h"
#include "rules/misra/no_recursion.h"
#include "rules/misra/no_union.h"
#include "rules/misra/single_exit.h"
#include "rules/modernization/auto_usage.h"
#include "rules/modernization/c_style_cast.h"
#include "rules/modernization/deprecated_headers.h"
#include "rules/modernization/enum_class.h"
#include "rules/modernization/missing_override.h"
#include "rules/modernization/nullptr_usage.h"
#include "rules/modernization/range_for.h"
#include "rules/modernization/raw_string_literal.h"
#include "rules/modernization/using_vs_typedef.h"

namespace cppulse {
using AnyRule =
    std::variant<RawPointerOwnershipRule, ManualMemoryMgmtRule, UnsafeArrayAccessRule,
                 CStyleCastRule, DeprecatedHeadersRule, MissingOverrideRule, RawStringLiteralRule,
                 AutoUsageRule, RangeForRule, NullptrUsageRule, EnumClassRule, UsingVsTypedefRule,
                 CyclomaticComplexityRule, FunctionLengthRule, ParameterCountRule, NoGotoRule,
                 NoImplicitConversionRule, NoUnionRule, NoDynamicAllocRule, NoRecursionRule,
                 SingleExitRule, InitAllVarsRule>;
}  // namespace cppulse
