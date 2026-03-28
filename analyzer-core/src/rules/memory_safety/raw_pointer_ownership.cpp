/**
 * @file raw_pointer_ownership.cpp
 * @brief CPP-MEM-001 implementation.
 */

#include "raw_pointer_ownership.h"

#include <clang-c/Index.h>

namespace cppulse {

void RawPointerOwnershipRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_CXXNewExpr) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(Finding{
        .rule_id = "CPP-MEM-001",
        .category = "memory_safety",
        .severity = "warning",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "Raw 'new' expression detected; prefer std::make_unique or std::make_shared",
        .suggestion = "Replace 'new T(...)' with 'std::make_unique<T>(...)'",
        .confidence = 1.0});
}

}  // namespace cppulse
