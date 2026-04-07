/**
 * @file cyclomatic_complexity.h
 * @brief CPP-CX-001: Detect functions with high cyclomatic complexity.
 */

#ifndef CPPULSE_CYCLOMATIC_COMPLEXITY_H
#define CPPULSE_CYCLOMATIC_COMPLEXITY_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Computes the cyclomatic complexity of each function by counting
 *        decision points (if, for, while, do, case, &&, ||, ?:).
 *
 * Thresholds:
 *  - complexity > 15  → warning
 *  - complexity > 25  → error
 */
class CyclomaticComplexityRule : public RuleBase<CyclomaticComplexityRule> {
   public:
    /// @brief Inspect one AST cursor for a complex function.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-CX-001";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "complexity";
    }

    /// @brief Override the warning threshold (default: 15).
    void set_warn_threshold(int value) noexcept { warn_threshold_ = value; }

    /// @brief Override the error threshold (default: 25).
    void set_error_threshold(int value) noexcept { error_threshold_ = value; }

    [[nodiscard]] int warn_threshold() const noexcept { return warn_threshold_; }
    [[nodiscard]] int error_threshold() const noexcept { return error_threshold_; }

   private:
    int warn_threshold_{15};
    int error_threshold_{25};
};

}  // namespace cppulse

#endif  // CPPULSE_CYCLOMATIC_COMPLEXITY_H
