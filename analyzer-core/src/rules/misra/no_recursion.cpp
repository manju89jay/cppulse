/**
 * @file no_recursion.cpp
 * @brief MISRA-005 implementation.
 */

#include "no_recursion.h"

#include <clang-c/Index.h>

namespace cppulse {

void NoRecursionRule::check_impl(CXCursor cursor, const std::string& file_path) {
    const CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind != CXCursor_FunctionDecl && kind != CXCursor_CXXMethod) {
        return;
    }

    if (!clang_isCursorDefinition(cursor)) {
        return;
    }

    CXString func_spelling = clang_getCursorSpelling(cursor);
    const char* func_str = clang_getCString(func_spelling);
    std::string func_name = (func_str != nullptr) ? func_str : "";
    clang_disposeString(func_spelling);

    if (func_name.empty()) {
        return;
    }

    // Walk the function body looking for a CallExpr that references this function.
    struct RecursionSearch {
        std::string target_name;
        CXCursor target_cursor;
        bool found = false;
        unsigned int found_line = 0;
        unsigned int found_col = 0;
    } search;
    search.target_name = func_name;
    search.target_cursor = cursor;

    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
            auto* s = static_cast<RecursionSearch*>(data);
            if (s->found) {
                return CXChildVisit_Break;
            }
            if (clang_getCursorKind(child) == CXCursor_CallExpr) {
                CXCursor referenced = clang_getCursorReferenced(child);
                if (!clang_Cursor_isNull(referenced)) {
                    CXString ref_spelling = clang_getCursorSpelling(referenced);
                    const char* ref_str = clang_getCString(ref_spelling);
                    std::string ref_name = (ref_str != nullptr) ? ref_str : "";
                    clang_disposeString(ref_spelling);

                    if (ref_name == s->target_name) {
                        // Confirm it references exactly the same function cursor.
                        if (clang_equalCursors(referenced, s->target_cursor)) {
                            s->found = true;
                            CXSourceLocation loc = clang_getCursorLocation(child);
                            clang_getSpellingLocation(loc, nullptr, &s->found_line, &s->found_col,
                                                      nullptr);
                            return CXChildVisit_Break;
                        }
                    }
                }
            }
            return CXChildVisit_Recurse;
        },
        &search);

    if (!search.found) {
        return;
    }

    add_finding(Finding{.rule_id = "MISRA-005",
                        .category = "misra",
                        .severity = "error",
                        .file = file_path,
                        .line = static_cast<int>(search.found_line),
                        .column = static_cast<int>(search.found_col),
                        .message = "Function '" + func_name +
                                   "' is recursive, making stack depth analysis impossible",
                        .suggestion = "Replace recursive implementation with an iterative one",
                        .confidence = 1.0});
}

}  // namespace cppulse
