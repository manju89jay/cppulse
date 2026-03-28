/**
 * @file cyclomatic_complexity.cpp
 * @brief CPP-CX-001 implementation.
 */

#include "cyclomatic_complexity.h"

#include <clang-c/Index.h>

namespace cppulse {

namespace {

constexpr int kWarnThreshold = 15;
constexpr int kErrorThreshold = 25;

/// @brief Count decision points inside a function body.
int count_decision_points(CXCursor function_cursor) {
    struct Counter {
        int count = 1;  // Start at 1 (the function itself is one path).
    } counter;

    clang_visitChildren(
        function_cursor,
        [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
            auto* ctr = static_cast<Counter*>(data);
            const CXCursorKind kind = clang_getCursorKind(child);
            switch (kind) {
                case CXCursor_IfStmt:
                case CXCursor_ForStmt:
                case CXCursor_CXXForRangeStmt:
                case CXCursor_WhileStmt:
                case CXCursor_DoStmt:
                case CXCursor_CaseStmt:
                case CXCursor_ConditionalOperator:
                    ++ctr->count;
                    break;
                case CXCursor_BinaryOperator: {
                    // Check for && or || operators by looking at tokens.
                    CXTranslationUnit tu = clang_Cursor_getTranslationUnit(child);
                    CXSourceRange range = clang_getCursorExtent(child);
                    CXToken* tokens = nullptr;
                    unsigned int num_tokens = 0;
                    clang_tokenize(tu, range, &tokens, &num_tokens);
                    for (unsigned int idx = 0; idx < num_tokens; ++idx) {
                        if (clang_getTokenKind(tokens[idx]) == CXToken_Punctuation) {
                            CXString tok = clang_getTokenSpelling(tu, tokens[idx]);
                            const char* tok_str = clang_getCString(tok);
                            if (tok_str != nullptr) {
                                std::string_view sv{tok_str};
                                if (sv == "&&" || sv == "||") {
                                    ++ctr->count;
                                }
                            }
                            clang_disposeString(tok);
                        }
                    }
                    if (tokens != nullptr) {
                        clang_disposeTokens(tu, tokens, num_tokens);
                    }
                    break;
                }
                default:
                    break;
            }
            return CXChildVisit_Recurse;
        },
        &counter);

    return counter.count;
}

}  // namespace

void CyclomaticComplexityRule::check_impl(CXCursor cursor, const std::string& file_path) {
    const CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind != CXCursor_FunctionDecl && kind != CXCursor_CXXMethod &&
        kind != CXCursor_Constructor && kind != CXCursor_Destructor) {
        return;
    }

    // Only analyze definitions, not declarations.
    if (!clang_isCursorDefinition(cursor)) {
        return;
    }

    const int complexity = count_decision_points(cursor);
    if (complexity <= kWarnThreshold) {
        return;
    }

    const std::string severity = (complexity > kErrorThreshold) ? "error" : "warning";

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* func_name = clang_getCString(spelling);
    std::string name_str = (func_name != nullptr) ? func_name : "<unnamed>";
    clang_disposeString(spelling);

    add_finding(Finding{.rule_id = "CPP-CX-001",
                        .category = "complexity",
                        .severity = severity,
                        .file = file_path,
                        .line = static_cast<int>(line),
                        .column = static_cast<int>(column),
                        .message = "Function '" + name_str + "' has cyclomatic complexity of " +
                                   std::to_string(complexity) + " (threshold: warning>" +
                                   std::to_string(kWarnThreshold) + ", error>" +
                                   std::to_string(kErrorThreshold) + ")",
                        .suggestion = "Decompose into smaller functions to reduce complexity",
                        .confidence = 1.0});
}

}  // namespace cppulse
