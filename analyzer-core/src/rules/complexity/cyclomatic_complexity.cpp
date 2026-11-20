/**
 * @file cyclomatic_complexity.cpp
 * @brief CPP-CX-001 implementation.
 */

#include "cyclomatic_complexity.h"

#include <clang-c/Index.h>

#include <algorithm>
#include <memory>
#include <optional>
#include <unordered_set>
#include <vector>

namespace cppulse {

namespace {

/** @brief Compare libclang cursors without relying on their internal representation. */
struct CursorHash {
    std::size_t operator()(CXCursor cursor) const noexcept {
        return clang_hashCursor(cursor);
    }
};

struct CursorEqual {
    bool operator()(CXCursor left, CXCursor right) const noexcept {
        return clang_equalCursors(left, right) != 0;
    }
};

using CursorSet = std::unordered_set<CXCursor, CursorHash, CursorEqual>;

/** @brief One function's decision count; annotations and traversal share deduplication. */
struct Counter {
    int count = 1;
    CursorSet decisions;
    CursorSet capture_lambdas;

    void add(CXCursor cursor) {
        if (decisions.insert(cursor).second) {
            ++count;
        }
    }
};

struct ExpressionRange {
    CXCursor cursor;
    CXFile file;
    unsigned begin;
    unsigned end;
};

/** @brief Locate a spelled expression in the expanded source file. */
std::optional<ExpressionRange> expression_range(CXCursor cursor) {
    const CXSourceRange extent = clang_getCursorExtent(cursor);
    CXFile begin_file = nullptr;
    CXFile end_file = nullptr;
    unsigned begin = 0;
    unsigned end = 0;
    clang_getExpansionLocation(clang_getRangeStart(extent), &begin_file, nullptr, nullptr, &begin);
    clang_getExpansionLocation(clang_getRangeEnd(extent), &end_file, nullptr, nullptr, &end);
    if (begin_file == nullptr || end_file == nullptr ||
        clang_File_isEqual(begin_file, end_file) == 0 || end <= begin) {
        return std::nullopt;
    }
    return ExpressionRange{cursor, begin_file, begin, end};
}

CXChildVisitResult count_cursor(CXCursor cursor, CXCursor parent, CXClientData data);

/**
 * @brief Recover capture initializer expressions omitted by libclang child traversal.
 *
 * Token annotations expose their actual AST cursors. Traverse maximal expression
 * roots, preserving semantic operators and nested lambda scope rather than
 * counting textual && tokens or double-counting a visible child expression.
 */
void count_capture_initializers(CXCursor lambda, Counter& counter) {
    if (!counter.capture_lambdas.insert(lambda).second) {
        return;
    }
    const auto lambda_range = expression_range(lambda);
    if (!lambda_range.has_value()) {
        return;
    }
    CXSourceLocation body_start = clang_getRangeEnd(clang_getCursorExtent(lambda));
    clang_visitChildren(
        lambda,
        [](CXCursor child, CXCursor, CXClientData data) {
            if (clang_getCursorKind(child) == CXCursor_CompoundStmt) {
                *static_cast<CXSourceLocation*>(data) =
                    clang_getRangeStart(clang_getCursorExtent(child));
                return CXChildVisit_Break;
            }
            return CXChildVisit_Continue;
        },
        &body_start);

    const CXTranslationUnit unit = clang_Cursor_getTranslationUnit(lambda);
    if (unit == nullptr) {
        return;
    }
    CXToken* raw_tokens = nullptr;
    unsigned count = 0;
    clang_tokenize(unit,
                   clang_getRange(clang_getRangeStart(clang_getCursorExtent(lambda)), body_start),
                   &raw_tokens, &count);
    struct TokenDeleter {
        CXTranslationUnit unit;
        unsigned count;
        void operator()(CXToken* tokens) const noexcept {
            clang_disposeTokens(unit, tokens, count);
        }
    };
    const std::unique_ptr<CXToken, TokenDeleter> tokens{raw_tokens, {unit, count}};
    if (tokens == nullptr || count == 0) {
        return;
    }
    std::vector<CXCursor> annotations(count);
    clang_annotateTokens(unit, tokens.get(), count, annotations.data());
    CursorSet candidates;
    std::vector<ExpressionRange> expressions;
    for (unsigned token_index = 0; token_index < count; ++token_index) {
        const CXCursor annotation = annotations[token_index];
        if (clang_equalCursors(annotation, lambda) != 0) {
            CXString spelling = clang_getTokenSpelling(unit, tokens.get()[token_index]);
            const char* value = clang_getCString(spelling);
            const bool capture_end = value != nullptr && std::string_view{value} == "]";
            clang_disposeString(spelling);
            if (capture_end) {
                break;
            }
            continue;
        }
        if (clang_isExpression(clang_getCursorKind(annotation)) == 0 ||
            !candidates.insert(annotation).second) {
            continue;
        }
        auto range = expression_range(annotation);
        if (range.has_value() && clang_File_isEqual(range->file, lambda_range->file) != 0 &&
            range->begin >= lambda_range->begin && range->end < lambda_range->end) {
            expressions.push_back(*range);
        }
    }
    std::sort(expressions.begin(), expressions.end(), [](const auto& left, const auto& right) {
        return left.begin != right.begin ? left.begin < right.begin : left.end > right.end;
    });
    std::optional<unsigned> covered_until;
    for (const auto& expression : expressions) {
        if (covered_until.has_value() && expression.end <= *covered_until) {
            continue;
        }
        covered_until = expression.end;
        if (count_cursor(expression.cursor, lambda, &counter) == CXChildVisit_Recurse) {
            clang_visitChildren(expression.cursor, count_cursor, &counter);
        }
    }
}

CXChildVisitResult count_cursor(CXCursor child, CXCursor parent, CXClientData data) {
    auto* ctr = static_cast<Counter*>(data);
    const CXCursorKind kind = clang_getCursorKind(child);
    // A local function/class or lambda body has its own control flow.
    // Lambda capture initializers still execute in the enclosing scope,
    // so prune the body rather than the whole lambda expression.
    if (kind == CXCursor_ParmDecl || kind == CXCursor_FunctionDecl || kind == CXCursor_CXXMethod ||
        kind == CXCursor_FunctionTemplate || kind == CXCursor_Constructor ||
        kind == CXCursor_Destructor || kind == CXCursor_ClassDecl || kind == CXCursor_StructDecl ||
        kind == CXCursor_ClassTemplate ||
        (kind == CXCursor_CompoundStmt && clang_getCursorKind(parent) == CXCursor_LambdaExpr)) {
        return CXChildVisit_Continue;
    }
    if (kind == CXCursor_LambdaExpr) {
        count_capture_initializers(child, *ctr);
    }
    switch (kind) {
        case CXCursor_IfStmt:
        case CXCursor_ForStmt:
        case CXCursor_CXXForRangeStmt:
        case CXCursor_WhileStmt:
        case CXCursor_DoStmt:
        case CXCursor_CaseStmt:
        case CXCursor_ConditionalOperator:
            ctr->add(child);
            break;
        case CXCursor_BinaryOperator: {
            // Count this operator, not tokens in its entire subtree:
            // nested expressions otherwise count an inner && twice.
            // The semantic opcode also handles macros and `and`/`or`.
            const auto operation = clang_Cursor_getBinaryOpcode(child);
            if (operation == CX_BO_LAnd || operation == CX_BO_LOr) {
                ctr->add(child);
            }
            break;
        }
        default:
            break;
    }
    return CXChildVisit_Recurse;
}

/// @brief Count decision points in one function's body, excluding nested callable bodies.
int count_decision_points(CXCursor function_cursor) {
    Counter counter;
    clang_visitChildren(function_cursor, count_cursor, &counter);

    return counter.count;
}

}  // namespace

int measure_cyclomatic_complexity(CXCursor cursor) {
    if (clang_getCursorKind(cursor) != CXCursor_LambdaExpr) {
        return count_decision_points(cursor);
    }
    // A lambda's own body is a callable scope; the enclosing measurement prunes it.
    CXCursor body = clang_getNullCursor();
    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor, CXClientData data) {
            if (clang_getCursorKind(child) == CXCursor_CompoundStmt) {
                *static_cast<CXCursor*>(data) = child;
                return CXChildVisit_Break;
            }
            return CXChildVisit_Continue;
        },
        &body);
    return count_decision_points(body);
}

void CyclomaticComplexityRule::check_impl(CXCursor cursor, const std::string& file_path) {
    const CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind != CXCursor_FunctionDecl && kind != CXCursor_FunctionTemplate &&
        kind != CXCursor_CXXMethod && kind != CXCursor_Constructor && kind != CXCursor_Destructor) {
        return;
    }

    // Only analyze definitions, not declarations.
    if (!clang_isCursorDefinition(cursor)) {
        return;
    }

    const int complexity = measure_cyclomatic_complexity(cursor);
    if (complexity <= warn_threshold_) {
        return;
    }

    const std::string severity = (complexity > error_threshold_) ? "error" : "warning";

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
                                   std::to_string(warn_threshold_) + ", error>" +
                                   std::to_string(error_threshold_) + ")",
                        .suggestion = "Decompose into smaller functions to reduce complexity",
                        .confidence = 1.0});
}

}  // namespace cppulse
