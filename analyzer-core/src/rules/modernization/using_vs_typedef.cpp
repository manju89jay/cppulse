/**
 * @file using_vs_typedef.cpp
 * @brief CPP-MOD-009 implementation.
 */

#include "using_vs_typedef.h"

#include <clang-c/Index.h>

namespace cppulse {

void UsingVsTypedefRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_TypedefDecl) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* typedef_name = clang_getCString(spelling);
    std::string name_str = (typedef_name != nullptr) ? typedef_name : "<unnamed>";
    clang_disposeString(spelling);

    // Retrieve the underlying type spelling for the suggestion.
    CXType underlying = clang_getTypedefDeclUnderlyingType(cursor);
    CXString type_spelling = clang_getTypeSpelling(underlying);
    const char* type_str = clang_getCString(type_spelling);
    std::string type_name = (type_str != nullptr) ? type_str : "...";
    clang_disposeString(type_spelling);

    add_finding(
        Finding{.rule_id = "CPP-MOD-009",
                .category = "modernization",
                .severity = "info",
                .file = file_path,
                .line = static_cast<int>(line),
                .column = static_cast<int>(column),
                .message = "typedef '" + name_str + "' should use a C++11 type alias instead",
                .suggestion = "Replace 'typedef " + type_name + " " + name_str + "' with 'using " +
                              name_str + " = " + type_name + "'",
                .confidence = 1.0});
}

}  // namespace cppulse
