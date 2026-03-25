/**
 * @file function_length.h
 * @brief CPP-CX-002: Detect functions that are too long.
 */

#ifndef CPPULSE_FUNCTION_LENGTH_H
#define CPPULSE_FUNCTION_LENGTH_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags function definitions whose body spans too many source lines.
 *
 * Thresholds:
 *  - lines > 80   → warning
 *  - lines > 150  → error
 */
class FunctionLengthRule : public RuleBase<FunctionLengthRule> {
   public:
    /// @brief Inspect one AST cursor for an overly long function.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-CX-002";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "complexity";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_FUNCTION_LENGTH_H
