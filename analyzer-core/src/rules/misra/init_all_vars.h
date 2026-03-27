/**
 * @file init_all_vars.h
 * @brief MISRA-007: Detect variable declarations without initializers.
 */

#ifndef CPPULSE_INIT_ALL_VARS_H
#define CPPULSE_INIT_ALL_VARS_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags local variable declarations that have no initializer.
 *
 * Uninitialized variables contain indeterminate values, which is undefined
 * behavior if read.  MISRA C++ requires all variables to be initialized at
 * the point of declaration.
 */
class InitAllVarsRule : public RuleBase<InitAllVarsRule> {
   public:
    /// @brief Inspect one AST cursor for an uninitialized variable.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "MISRA-007";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "misra";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_INIT_ALL_VARS_H
