/**
 * @file single_exit.cpp
 * @brief MISRA-006 implementation.
 */

#include "single_exit.h"

#include <clang-c/Index.h>

#include <vector>

namespace cppulse {

void SingleExitRule::check_impl(CXCursor cursor, const std::string& file_path) {
    const CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind != CXCursor_FunctionDecl && kind != CXCursor_CXXMethod &&
        kind != CXCursor_Constructor && kind != CXCursor_Destructor) {
        return;
    }

    if (!clang_isCursorDefinition(cursor)) {
        return;
    }

    // Collect all return statement locations.
    struct ReturnCollector {
        std::vector<unsigned int> return_lines;
    } collector;

    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
            auto* col = static_cast<ReturnCollector*>(data);
            if (clang_getCursorKind(child) == CXCursor_ReturnStmt) {
                CXSourceLocation loc = clang_getCursorLocation(child);
                unsigned int line = 0;
                clang_getSpellingLocation(loc, nullptr, &line, nullptr, nullptr);
                col->return_lines.push_back(line);
            }
            return CXChildVisit_Recurse;
        },
        &collector);

    if (collector.return_lines.size() <= 1) {
        return;  // Single exit or no return — compliant.
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int func_line = 0;
    unsigned int func_col = 0;
    clang_getSpellingLocation(loc, nullptr, &func_line, &func_col, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* func_str = clang_getCString(spelling);
    std::string func_name = (func_str != nullptr) ? func_str : "<unnamed>";
    clang_disposeString(spelling);

    add_finding(
        Finding{.rule_id = "MISRA-006",
                .category = "misra",
                .severity = "warning",
                .file = file_path,
                .line = static_cast<int>(func_line),
                .column = static_cast<int>(func_col),
                .message = "Function '" + func_name + "' has " +
                           std::to_string(collector.return_lines.size()) +
                           " return statements; MISRA Rule 6-6-5 requires a single exit point",
                .suggestion = "Restructure function so all exit paths go through a single return",
                .confidence = 1.0});
}

}  // namespace cppulse
