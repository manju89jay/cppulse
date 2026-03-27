/**
 * @file no_recursion.h
 * @brief MISRA-005: Detect direct recursive function calls.
 */

#ifndef CPPULSE_NO_RECURSION_H
#define CPPULSE_NO_RECURSION_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags functions that call themselves directly.
 *
 * Recursion makes stack depth analysis impossible, which is prohibited in
 * safety-critical software.  Replace with iterative implementations.
 */
class NoRecursionRule : public RuleBase<NoRecursionRule> {
   public:
    /// @brief Inspect one AST cursor for a recursive call.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "MISRA-005";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "misra";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_NO_RECURSION_H
