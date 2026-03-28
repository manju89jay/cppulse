/**
 * @file no_union.h
 * @brief MISRA-003: Detect union declarations.
 */

#ifndef CPPULSE_NO_UNION_H
#define CPPULSE_NO_UNION_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_UnionDecl cursors.
 *
 * Unions allow type punning that bypasses the C++ type system and can cause
 * undefined behavior.  Prefer std::variant for type-safe discriminated unions.
 */
class NoUnionRule : public RuleBase<NoUnionRule> {
   public:
    /// @brief Inspect one AST cursor for a union declaration.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "MISRA-003";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "misra";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_NO_UNION_H
