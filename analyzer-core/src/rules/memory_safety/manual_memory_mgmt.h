/**
 * @file manual_memory_mgmt.h
 * @brief CPP-MEM-002: Detect explicit `delete` expressions.
 */

#ifndef CPPULSE_MANUAL_MEMORY_MGMT_H
#define CPPULSE_MANUAL_MEMORY_MGMT_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_CXXDeleteExpr cursors.
 *
 * Explicit `delete` indicates manual ownership management.  Smart pointers
 * should be used so that destructors handle cleanup automatically.
 */
class ManualMemoryMgmtRule : public RuleBase<ManualMemoryMgmtRule> {
   public:
    /// @brief Inspect one AST cursor for a delete-expression.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MEM-002";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "memory_safety";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_MANUAL_MEMORY_MGMT_H
