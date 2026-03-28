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
 * @brief Flags simple index-based for loops that iterate from 0 to container.size()
 *        and could be replaced with a range-based for loop.
 *
 * Heuristic: a CXCursor_ForStmt whose init declares an integer variable
 * initialized to 0 is a candidate.
 */
class RangeForRule : public RuleBase<RangeForRule> {
   public:
    /// @brief Inspect one AST cursor for a candidiate index-based for loop.
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
