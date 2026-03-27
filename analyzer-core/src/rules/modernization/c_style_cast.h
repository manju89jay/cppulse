/**
 * @file c_style_cast.h
 * @brief CPP-MOD-001: Detect C-style cast expressions.
 */

#ifndef CPPULSE_C_STYLE_CAST_H
#define CPPULSE_C_STYLE_CAST_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_CStyleCastExpr cursors.
 *
 * C-style casts (T)expr bypass C++ type-safety checks.  Use static_cast,
 * dynamic_cast, const_cast, or reinterpret_cast explicitly.
 */
class CStyleCastRule : public RuleBase<CStyleCastRule> {
   public:
    /// @brief Inspect one AST cursor for a C-style cast.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-001";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_C_STYLE_CAST_H
