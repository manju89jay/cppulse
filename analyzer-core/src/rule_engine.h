/**
 * @file rule_engine.h
 * @brief std::variant container that holds all 22 analysis rules.
 *
 * RuleVariant holds one instance of each concrete rule.  The engine uses
 * std::visit to dispatch check() calls uniformly without virtual dispatch.
 */

#ifndef CPPULSE_RULE_ENGINE_H
#define CPPULSE_RULE_ENGINE_H

#include <clang-c/Index.h>

#include <variant>
#include <vector>

#include "finding.h"

// Memory Safety rules
#include "rules/memory_safety/manual_memory_mgmt.h"
#include "rules/memory_safety/raw_pointer_ownership.h"
#include "rules/memory_safety/unsafe_array_access.h"

// Modernization rules
#include "rules/modernization/auto_usage.h"
#include "rules/modernization/c_style_cast.h"
#include "rules/modernization/deprecated_headers.h"
#include "rules/modernization/enum_class.h"
#include "rules/modernization/missing_override.h"
#include "rules/modernization/nullptr_usage.h"
#include "rules/modernization/range_for.h"
#include "rules/modernization/raw_string_literal.h"
#include "rules/modernization/using_vs_typedef.h"

// Complexity rules
#include "rules/complexity/cyclomatic_complexity.h"
#include "rules/complexity/function_length.h"
#include "rules/complexity/parameter_count.h"

// MISRA rules
#include "rules/misra/init_all_vars.h"
#include "rules/misra/no_dynamic_alloc.h"
#include "rules/misra/no_goto.h"
#include "rules/misra/no_implicit_conversion.h"
#include "rules/misra/no_recursion.h"
#include "rules/misra/no_union.h"
#include "rules/misra/single_exit.h"

namespace cppulse {

/**
 * @brief A std::variant that can hold any one of the 22 concrete rule types.
 *
 * The engine creates one instance per rule and stores them in a
 * std::vector<AnyRule>, then uses std::visit for uniform dispatch.
 */
using AnyRule = std::variant<
    // Memory Safety
    RawPointerOwnershipRule, ManualMemoryMgmtRule, UnsafeArrayAccessRule,
    // Modernization
    CStyleCastRule, DeprecatedHeadersRule, MissingOverrideRule, RawStringLiteralRule, AutoUsageRule,
    RangeForRule, NullptrUsageRule, EnumClassRule, UsingVsTypedefRule,
    // Complexity
    CyclomaticComplexityRule, FunctionLengthRule, ParameterCountRule,
    // MISRA
    NoGotoRule, NoImplicitConversionRule, NoUnionRule, NoDynamicAllocRule, NoRecursionRule,
    SingleExitRule, InitAllVarsRule>;

/**
 * @brief Visitor that calls check() on whichever rule type is active.
 */
struct CheckVisitor {
    CXCursor cursor;
    const std::string& file_path;

    template <typename Rule>
    void operator()(Rule& rule) const {
        rule.check(cursor, file_path);
    }
};

/**
 * @brief Visitor that extracts the findings from whichever rule is active.
 */
struct FindingsVisitor {
    std::vector<Finding>& out;

    template <typename Rule>
    void operator()(const Rule& rule) const {
        const auto& rf = rule.findings();
        out.insert(out.end(), rf.begin(), rf.end());
    }
};

/**
 * @brief Visitor that clears findings on whichever rule is active.
 */
struct ClearFindingsVisitor {
    template <typename Rule>
    void operator()(Rule& rule) const {
        rule.clear_findings();
    }
};

}  // namespace cppulse

#endif  // CPPULSE_RULE_ENGINE_H
