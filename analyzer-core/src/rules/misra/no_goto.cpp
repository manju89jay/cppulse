/**
 * @file no_goto.cpp
 * @brief MISRA-001 implementation.
 */

#include "no_goto.h"

#include <clang-c/Index.h>

namespace cppulse {

void NoGotoRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_GotoStmt) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(Finding{
        .rule_id = "MISRA-001",
        .category = "misra",
        .severity = "error",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "goto statement violates MISRA C++ Rule 6-6-2 (no goto)",
        .suggestion =
            "Replace goto with structured control flow (loops, exceptions, or early return)",
        .confidence = 1.0});
}

}  // namespace cppulse
