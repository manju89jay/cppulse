/**
 * @file no_union.cpp
 * @brief MISRA-003 implementation.
 */

#include "no_union.h"

#include <clang-c/Index.h>

namespace cppulse {

void NoUnionRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_UnionDecl) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* union_name = clang_getCString(spelling);
    std::string name_str =
        (union_name != nullptr && union_name[0] != '\0') ? union_name : "<anonymous>";
    clang_disposeString(spelling);

    add_finding(Finding{
        .rule_id = "MISRA-003",
        .category = "misra",
        .severity = "error",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message =
            "Union '" + name_str + "' allows type punning and violates MISRA C++ type safety rules",
        .suggestion = "Replace union with std::variant for type-safe discriminated unions",
        .confidence = 1.0});
}

}  // namespace cppulse
