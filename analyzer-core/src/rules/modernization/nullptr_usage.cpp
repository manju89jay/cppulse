/**
 * @file nullptr_usage.cpp
 * @brief CPP-MOD-007 implementation.
 */

#include "nullptr_usage.h"

#include <clang-c/Index.h>

namespace cppulse {

void NullptrUsageRule::check_impl(CXCursor cursor, const std::string& file_path) {
    // Check for CXCursor_MacroExpansion named "NULL".
    if (clang_getCursorKind(cursor) == CXCursor_MacroExpansion) {
        CXString spelling = clang_getCursorSpelling(cursor);
        const char* name = clang_getCString(spelling);
        const bool is_null_macro = (name != nullptr && std::string_view{name} == "NULL");
        clang_disposeString(spelling);

        if (is_null_macro) {
            CXSourceLocation loc = clang_getCursorLocation(cursor);
            unsigned int line = 0;
            unsigned int column = 0;
            clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

            add_finding(
                Finding{.rule_id = "CPP-MOD-007",
                        .category = "modernization",
                        .severity = "warning",
                        .file = file_path,
                        .line = static_cast<int>(line),
                        .column = static_cast<int>(column),
                        .message = "NULL macro used as null pointer constant; prefer nullptr",
                        .suggestion = "Replace NULL with nullptr",
                        .confidence = 1.0});
        }
        return;
    }

    // Also check: integer literal 0 being implicitly converted to a pointer type.
    if (clang_getCursorKind(cursor) == CXCursor_IntegerLiteral) {
        // Check if the canonical type of the parent context is a pointer.
        // We check by seeing if the result type of the current cursor is a pointer.
        CXType result_type = clang_getCursorType(cursor);
        if (result_type.kind == CXType_Invalid) {
            return;
        }

        // A literal 0 in pointer context typically has NullPtr or pointer type.
        if (result_type.kind == CXType_NullPtr) {
            CXSourceLocation loc = clang_getCursorLocation(cursor);
            unsigned int line = 0;
            unsigned int column = 0;
            clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

            add_finding(
                Finding{.rule_id = "CPP-MOD-007",
                        .category = "modernization",
                        .severity = "warning",
                        .file = file_path,
                        .line = static_cast<int>(line),
                        .column = static_cast<int>(column),
                        .message = "Integer 0 used as null pointer constant; prefer nullptr",
                        .suggestion = "Replace 0 with nullptr",
                        .confidence = 0.9});
        }
    }
}

}  // namespace cppulse
