/**
 * @file single_exit.h
 * @brief MISRA-006: Detect functions with multiple return statements.
 */

#ifndef CPPULSE_SINGLE_EXIT_H
#define CPPULSE_SINGLE_EXIT_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags function definitions that contain more than one return statement.
 *
 * MISRA C++:2008 Rule 6-6-5 requires that a function have a single point of
 * exit to simplify reasoning about post-conditions and resource cleanup.
 */
class SingleExitRule : public RuleBase<SingleExitRule> {
   public:
    /// @brief Inspect one AST cursor for a function with multiple returns.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "MISRA-006";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "misra";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_SINGLE_EXIT_H
