/**
 * @file no_goto.h
 * @brief MISRA-001: Detect use of goto statements.
 */

#ifndef CPPULSE_NO_GOTO_H
#define CPPULSE_NO_GOTO_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_GotoStmt cursors.
 *
 * MISRA C++:2008 Rule 6-6-2 prohibits goto because it produces spaghetti
 * control flow that is hard to reason about formally.
 */
class NoGotoRule : public RuleBase<NoGotoRule> {
   public:
    /// @brief Inspect one AST cursor for a goto statement.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "MISRA-001";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "misra";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_NO_GOTO_H
