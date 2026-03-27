/**
 * @file manual_memory_mgmt.cpp
 * @brief CPP-MEM-002 implementation.
 */

#include "manual_memory_mgmt.h"

#include <clang-c/Index.h>

namespace cppulse {

void ManualMemoryMgmtRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_CXXDeleteExpr) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(Finding{
        .rule_id = "CPP-MEM-002",
        .category = "memory_safety",
        .severity = "warning",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message =
            "Explicit 'delete' detected; prefer smart pointers for automatic lifetime management",
        .suggestion = "Use std::unique_ptr or std::shared_ptr to avoid manual delete",
        .confidence = 1.0});
}

}  // namespace cppulse
