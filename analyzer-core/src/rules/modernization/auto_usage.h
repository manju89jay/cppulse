/**
 * @file auto_usage.h
 * @brief CPP-MOD-005: Suggest `auto` for verbose iterator type declarations.
 */

#ifndef CPPULSE_AUTO_USAGE_H
#define CPPULSE_AUTO_USAGE_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags variable declarations whose type contains "iterator" and
 *        could be simplified with `auto`.
 *
 * For example:
 *   std::vector<int>::iterator it = v.begin();
 * should be written as:
 *   auto it = v.begin();
 */
class AutoUsageRule : public RuleBase<AutoUsageRule> {
   public:
    /// @brief Inspect one AST cursor for a verbose iterator declaration.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-005";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_AUTO_USAGE_H
