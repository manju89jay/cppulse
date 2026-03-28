/**
 * @file missing_override.h
 * @brief CPP-MOD-003: Detect virtual methods that are missing the override keyword.
 */

#ifndef CPPULSE_MISSING_OVERRIDE_H
#define CPPULSE_MISSING_OVERRIDE_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_CXXMethod cursors that override a base class method
 *        but do not carry the `override` specifier.
 *
 * Without `override`, a typo in the method signature silently creates a new
 * virtual method instead of overriding the intended one.
 */
class MissingOverrideRule : public RuleBase<MissingOverrideRule> {
   public:
    /// @brief Inspect one AST cursor for a missing override specifier.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-003";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_MISSING_OVERRIDE_H
