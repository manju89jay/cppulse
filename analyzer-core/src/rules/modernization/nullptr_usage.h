/**
 * @file nullptr_usage.h
 * @brief CPP-MOD-007: Detect use of NULL macro or integer 0 as a null pointer.
 */

#ifndef CPPULSE_NULLPTR_USAGE_H
#define CPPULSE_NULLPTR_USAGE_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags macro expansions of NULL and integer literal 0 used as null
 *        pointer constants.
 *
 * In C++11 and later, `nullptr` should be used for null pointer values.
 */
class NullptrUsageRule : public RuleBase<NullptrUsageRule> {
   public:
    /// @brief Inspect one AST cursor for NULL or 0-as-pointer usage.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-007";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_NULLPTR_USAGE_H
