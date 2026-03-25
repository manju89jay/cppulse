/**
 * @file raw_pointer_ownership.h
 * @brief CPP-MEM-001: Detect use of raw `new` expressions.
 */

#ifndef CPPULSE_RAW_POINTER_OWNERSHIP_H
#define CPPULSE_RAW_POINTER_OWNERSHIP_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_CXXNewExpr cursors that indicate raw `new` ownership.
 *
 * Modern C++ should use std::make_unique or std::make_shared instead of
 * allocating with `new` directly.
 */
class RawPointerOwnershipRule : public RuleBase<RawPointerOwnershipRule> {
   public:
    /// @brief Inspect one AST cursor for a raw new-expression.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MEM-001";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "memory_safety";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_RAW_POINTER_OWNERSHIP_H
