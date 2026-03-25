/**
 * @file raw_string_literal.h
 * @brief CPP-MOD-004: Detect string literals with many escape sequences.
 */

#ifndef CPPULSE_RAW_STRING_LITERAL_H
#define CPPULSE_RAW_STRING_LITERAL_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags string literals containing three or more backslash escape
 *        sequences that could be expressed more clearly as raw string literals.
 *
 * Example: "C:\\Users\\foo\\bar" is clearer as R"(C:\Users\foo\bar)".
 */
class RawStringLiteralRule : public RuleBase<RawStringLiteralRule> {
   public:
    /// @brief Inspect one AST cursor for a string literal with many escapes.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-004";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_RAW_STRING_LITERAL_H
