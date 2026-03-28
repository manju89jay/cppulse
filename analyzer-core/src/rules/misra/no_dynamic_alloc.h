/**
 * @file no_dynamic_alloc.h
 * @brief MISRA-004: Detect dynamic memory allocation via C library functions.
 */

#ifndef CPPULSE_NO_DYNAMIC_ALLOC_H
#define CPPULSE_NO_DYNAMIC_ALLOC_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags calls to malloc, calloc, realloc, and free.
 *
 * MISRA C++:2008 forbids dynamic heap allocation in safety-critical code.
 * Use stack allocation, std::array, or pre-allocated pools instead.
 */
class NoDynamicAllocRule : public RuleBase<NoDynamicAllocRule> {
   public:
    /// @brief Inspect one AST cursor for a C dynamic allocation call.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "MISRA-004";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "misra";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_NO_DYNAMIC_ALLOC_H
