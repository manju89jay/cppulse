/**
 * @file c_style_cast.cpp
 * @brief CPP-MOD-001 implementation.
 */

#include "c_style_cast.h"

#include <clang-c/Index.h>

namespace cppulse {

void CStyleCastRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_CStyleCastExpr) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(Finding{
        .rule_id = "CPP-MOD-001",
        .category = "modernization",
        .severity = "warning",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "C-style cast bypasses C++ type-safety checks",
        .suggestion = "Replace with static_cast<T>, dynamic_cast<T>, or reinterpret_cast<T>",
        .confidence = 1.0});
}

}  // namespace cppulse
