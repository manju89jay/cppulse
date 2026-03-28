/**
 * @file no_implicit_conversion.h
 * @brief MISRA-002: Detect implicit narrowing conversions.
 */

#ifndef CPPULSE_NO_IMPLICIT_CONVERSION_H
#define CPPULSE_NO_IMPLICIT_CONVERSION_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags CXCursor_ImplicitCastExpr nodes that perform narrowing
 *        conversions (e.g. double to int, long to short).
 *
 * Narrowing conversions silently discard information and are a common
 * source of subtle bugs in safety-critical software.
 */
class NoImplicitConversionRule : public RuleBase<NoImplicitConversionRule> {
   public:
    /// @brief Inspect one AST cursor for a narrowing implicit cast.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "MISRA-002";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "misra";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_NO_IMPLICIT_CONVERSION_H
