/**
 * @file enum_class.cpp
 * @brief CPP-MOD-008 implementation.
 */

#include "enum_class.h"

#include <clang-c/Index.h>

namespace cppulse {

void EnumClassRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_EnumDecl) {
        return;
    }

    // clang_EnumDecl_isScoped returns non-zero for `enum class` / `enum struct`.
    if (clang_EnumDecl_isScoped(cursor) != 0) {
        return;  // Already a scoped enum — nothing to report.
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* enum_name = clang_getCString(spelling);
    std::string name_str =
        (enum_name != nullptr && enum_name[0] != '\0') ? enum_name : "<anonymous>";
    clang_disposeString(spelling);

    add_finding(Finding{
        .rule_id = "CPP-MOD-008",
        .category = "modernization",
        .severity = "warning",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "Unscoped enum '" + name_str +
                   "' pollutes the enclosing namespace and allows implicit integer conversion",
        .suggestion = "Replace 'enum " + name_str + "' with 'enum class " + name_str + "'",
        .confidence = 1.0});
}

}  // namespace cppulse
