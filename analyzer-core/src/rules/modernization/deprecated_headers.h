/**
 * @file deprecated_headers.h
 * @brief CPP-MOD-002: Detect inclusion of deprecated C headers.
 */

#ifndef CPPULSE_DEPRECATED_HEADERS_H
#define CPPULSE_DEPRECATED_HEADERS_H

#include <string>
#include <string_view>

#include "rule_base.h"

namespace cppulse {

/**
 * @brief Flags direct literal standard C header operands resolved as system headers.
 *
 * C headers such as <stdio.h> have C++ replacements (<cstdio>).  Using
 * the C++ versions provide their standard C++ declarations. Qualified, quoted,
 * macro-expanded and non-system shadow includes are not replacement candidates.
 * Compiler-marked system include roots are trusted, not independently attested.
 */
class DeprecatedHeadersRule : public RuleBase<DeprecatedHeadersRule> {
   public:
    /// @brief Inspect one AST cursor for a deprecated C header inclusion.
    void check_impl(CXCursor cursor, const std::string& file_path);

    /// @brief Return the rule identifier.
    [[nodiscard]] std::string_view rule_id_impl() const noexcept {
        return "CPP-MOD-002";
    }

    /// @brief Return the rule category.
    [[nodiscard]] std::string_view category_impl() const noexcept {
        return "modernization";
    }
};

}  // namespace cppulse

#endif  // CPPULSE_DEPRECATED_HEADERS_H
