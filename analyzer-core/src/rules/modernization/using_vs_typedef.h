/**
 * @file using_vs_typedef.h
 * @brief CPP-MOD-009: Detect typedef declarations that should use `using`.
 */

#ifndef CPPULSE_USING_VS_TYPEDEF_H
#define CPPULSE_USING_VS_TYPEDEF_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_TypedefDecl cursors.
 *
 * In C++11 and later, type aliases should be expressed with `using` rather
 * than `typedef` for consistency and template-alias support.
 */
class UsingVsTypedefRule : public RuleBase<UsingVsTypedefRule> {
   public:
    /// @brief Inspect one AST cursor for a typedef declaration.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-009";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_USING_VS_TYPEDEF_H
