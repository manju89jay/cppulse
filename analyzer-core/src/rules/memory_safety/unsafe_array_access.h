/**
 * @file unsafe_array_access.h
 * @brief CPP-MEM-003: Detect C-style array parameters.
 */

#ifndef CPPULSE_UNSAFE_ARRAY_ACCESS_H
#define CPPULSE_UNSAFE_ARRAY_ACCESS_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags function parameters declared as C-style arrays (e.g. int arr[]).
 *
 * C-style array parameters decay to raw pointers with no bounds information.
 * Prefer std::span, std::array, or std::vector.
 */
class UnsafeArrayAccessRule : public RuleBase<UnsafeArrayAccessRule> {
   public:
    /// @brief Inspect one AST cursor for a C-style array parameter.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MEM-003";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "memory_safety";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_UNSAFE_ARRAY_ACCESS_H
