/**
 * @file parameter_count.h
 * @brief CPP-CX-003: Detect functions with too many parameters.
 */

#ifndef CPPULSE_PARAMETER_COUNT_H
#define CPPULSE_PARAMETER_COUNT_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags function declarations with an excessive number of parameters.
 *
 * Thresholds:
 *  - params > 5  → warning
 *  - params > 8  → error
 */
class ParameterCountRule : public RuleBase<ParameterCountRule> {
   public:
    /// @brief Inspect one AST cursor for a parameter-heavy function.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-CX-003";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "complexity";
    }

    void set_warn_threshold(int value) noexcept {
        warn_params_ = value;
    }
    void set_error_threshold(int value) noexcept {
        error_params_ = value;
    }
    [[nodiscard]] int warn_threshold() const noexcept {
        return warn_params_;
    }
    [[nodiscard]] int error_threshold() const noexcept {
        return error_params_;
    }

   private:
    int warn_params_{5};
    int error_params_{8};
};

}  // namespace cppulse

#endif  // CPPULSE_PARAMETER_COUNT_H
