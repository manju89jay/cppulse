/**
 * @file no_dynamic_alloc.cpp
 * @brief MISRA-004 implementation.
 */

#include "no_dynamic_alloc.h"

#include <clang-c/Index.h>

#include <set>
#include <string>
#include <string_view>

namespace cppulse {

namespace {

/// @brief C dynamic allocation functions to flag.
const std::set<std::string> kDynAllocFunctions{"malloc", "calloc", "realloc", "free",
                                               "aligned_alloc"};

}  // namespace

void NoDynamicAllocRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_CallExpr) {
        return;
    }

    // Get the callee function name.
    CXCursor callee = clang_getCursorReferenced(cursor);
    if (clang_Cursor_isNull(callee)) {
        return;
    }

    CXString callee_spelling = clang_getCursorSpelling(callee);
    const char* callee_str = clang_getCString(callee_spelling);
    std::string callee_name = (callee_str != nullptr) ? callee_str : "";
    clang_disposeString(callee_spelling);

    if (kDynAllocFunctions.count(callee_name) == 0) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(
        Finding{.rule_id = "MISRA-004",
                .category = "misra",
                .severity = "error",
                .file = file_path,
                .line = static_cast<int>(line),
                .column = static_cast<int>(column),
                .message = "Dynamic allocation via '" + callee_name +
                           "()' violates MISRA C++ Rule 18-4-1 (no dynamic heap allocation)",
                .suggestion = "Use stack allocation, std::array, or a pre-allocated memory pool",
                .confidence = 1.0});
}

}  // namespace cppulse
