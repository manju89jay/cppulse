// Generated from cppulse/data/rule_registry.json; use scripts/check_generated.py.
#pragma once
#include <cstddef>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>

#include "generated_rule_types.h"

namespace cppulse {
inline constexpr std::size_t generated_native_rule_count = 22;

inline std::set<std::string> generated_native_rule_options(std::string_view id) {
    if (id == "CPP-MEM-001")
        return {"enabled"};
    if (id == "CPP-MEM-002")
        return {"enabled"};
    if (id == "CPP-MEM-003")
        return {"enabled"};
    if (id == "CPP-MOD-001")
        return {"enabled"};
    if (id == "CPP-MOD-002")
        return {"enabled"};
    if (id == "CPP-MOD-003")
        return {"enabled"};
    if (id == "CPP-MOD-004")
        return {"enabled"};
    if (id == "CPP-MOD-005")
        return {"enabled"};
    if (id == "CPP-MOD-006")
        return {"enabled"};
    if (id == "CPP-MOD-007")
        return {"enabled"};
    if (id == "CPP-MOD-008")
        return {"enabled"};
    if (id == "CPP-MOD-009")
        return {"enabled"};
    if (id == "CPP-CX-001")
        return {"enabled", "error_threshold", "warning_threshold"};
    if (id == "CPP-CX-002")
        return {"enabled", "error_threshold", "warning_threshold"};
    if (id == "CPP-CX-003")
        return {"enabled", "error_threshold", "warning_threshold"};
    if (id == "MISRA-001")
        return {"enabled"};
    if (id == "MISRA-002")
        return {"enabled"};
    if (id == "MISRA-003")
        return {"enabled"};
    if (id == "MISRA-004")
        return {"enabled"};
    if (id == "MISRA-005")
        return {"enabled"};
    if (id == "MISRA-006")
        return {"enabled"};
    if (id == "MISRA-007")
        return {"enabled"};
    throw std::invalid_argument("Unknown registry rule ID: " + std::string{id});
}

inline bool generated_native_rule_default_enabled(std::string_view id) {
    if (id == "CPP-MEM-001")
        return true;
    if (id == "CPP-MEM-002")
        return true;
    if (id == "CPP-MEM-003")
        return true;
    if (id == "CPP-MOD-001")
        return true;
    if (id == "CPP-MOD-002")
        return true;
    if (id == "CPP-MOD-003")
        return true;
    if (id == "CPP-MOD-004")
        return true;
    if (id == "CPP-MOD-005")
        return true;
    if (id == "CPP-MOD-006")
        return true;
    if (id == "CPP-MOD-007")
        return true;
    if (id == "CPP-MOD-008")
        return true;
    if (id == "CPP-MOD-009")
        return true;
    if (id == "CPP-CX-001")
        return true;
    if (id == "CPP-CX-002")
        return true;
    if (id == "CPP-CX-003")
        return true;
    if (id == "MISRA-001")
        return true;
    if (id == "MISRA-002")
        return true;
    if (id == "MISRA-003")
        return true;
    if (id == "MISRA-004")
        return true;
    if (id == "MISRA-005")
        return true;
    if (id == "MISRA-006")
        return true;
    if (id == "MISRA-007")
        return true;
    throw std::invalid_argument("Unknown registry rule ID: " + std::string{id});
}

template <typename AddRule, typename ApplyConfig>
inline void register_generated_native_rules(AddRule&& add_rule, ApplyConfig&& apply_config) {
    {
        RawPointerOwnershipRule rule;
        add_rule(std::move(rule), true);
    }
    {
        ManualMemoryMgmtRule rule;
        add_rule(std::move(rule), true);
    }
    {
        UnsafeArrayAccessRule rule;
        add_rule(std::move(rule), true);
    }
    {
        CStyleCastRule rule;
        add_rule(std::move(rule), true);
    }
    {
        DeprecatedHeadersRule rule;
        add_rule(std::move(rule), true);
    }
    {
        MissingOverrideRule rule;
        add_rule(std::move(rule), true);
    }
    {
        RawStringLiteralRule rule;
        add_rule(std::move(rule), true);
    }
    {
        AutoUsageRule rule;
        add_rule(std::move(rule), true);
    }
    {
        RangeForRule rule;
        add_rule(std::move(rule), true);
    }
    {
        NullptrUsageRule rule;
        add_rule(std::move(rule), true);
    }
    {
        EnumClassRule rule;
        add_rule(std::move(rule), true);
    }
    {
        UsingVsTypedefRule rule;
        add_rule(std::move(rule), true);
    }
    {
        CyclomaticComplexityRule rule;
        rule.set_warn_threshold(15);
        rule.set_error_threshold(25);
        apply_config(rule);
        add_rule(std::move(rule), true);
    }
    {
        FunctionLengthRule rule;
        rule.set_warn_threshold(80);
        rule.set_error_threshold(150);
        apply_config(rule);
        add_rule(std::move(rule), true);
    }
    {
        ParameterCountRule rule;
        rule.set_warn_threshold(5);
        rule.set_error_threshold(8);
        apply_config(rule);
        add_rule(std::move(rule), true);
    }
    {
        NoGotoRule rule;
        add_rule(std::move(rule), true);
    }
    {
        NoImplicitConversionRule rule;
        add_rule(std::move(rule), true);
    }
    {
        NoUnionRule rule;
        add_rule(std::move(rule), true);
    }
    {
        NoDynamicAllocRule rule;
        add_rule(std::move(rule), true);
    }
    {
        NoRecursionRule rule;
        add_rule(std::move(rule), true);
    }
    {
        SingleExitRule rule;
        add_rule(std::move(rule), true);
    }
    {
        InitAllVarsRule rule;
        add_rule(std::move(rule), true);
    }
}
}  // namespace cppulse
