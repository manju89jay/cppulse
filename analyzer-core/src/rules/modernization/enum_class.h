/**
 * @file enum_class.h
 * @brief CPP-MOD-008: Detect unscoped (plain) enum declarations.
 */

#ifndef CPPULSE_ENUM_CLASS_H
#define CPPULSE_ENUM_CLASS_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_EnumDecl that are not scoped (not `enum class`).
 *
 * Unscoped enums pollute the enclosing namespace and allow implicit conversions
 * to integers.  Prefer `enum class` or `enum struct` for strong typing.
 */
class EnumClassRule : public RuleBase<EnumClassRule> {
   public:
    /// @brief Inspect one AST cursor for an unscoped enum declaration.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-008";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_ENUM_CLASS_H
