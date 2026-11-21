/**
 * @file range_for.h
 * @brief CPP-MOD-006: Suggest range-based for loops for index-based loops.
 */

#ifndef CPPULSE_RANGE_FOR_H
#define CPPULSE_RANGE_FOR_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Suggests range-for for a conservative fixed-array accumulation pattern.
 *
 * Recognizes a zero-initialized int/unsigned index, a literal bound matching the
 * constant scalar array size, unit increment, and a single built-in scalar +=
 * of array[index]. Pointer ranges, calls, index reuse, writes and other shapes
 * remain unassessed. This is a review suggestion, not an automatic rewrite or
 * a general semantic-equivalence engine.
 */
class RangeForRule : public RuleBase<RangeForRule> {
   public:
    /// @brief Inspect one AST cursor for a proven fixed-array traversal shape.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-006";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_RANGE_FOR_H
