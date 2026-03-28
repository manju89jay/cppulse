/**
 * @file range_for.cpp
 * @brief CPP-MOD-006 implementation.
 */

#include "range_for.h"

#include <clang-c/Index.h>

namespace cppulse {

namespace {

/// @brief Check whether a cursor is an integer variable initialized to 0.
bool is_int_initialized_to_zero(CXCursor cursor) {
    if (clang_getCursorKind(cursor) != CXCursor_VarDecl) {
        return false;
    }
    CXType type = clang_getCursorType(cursor);
    const CXTypeKind kind = type.kind;
    if (kind != CXType_Int && kind != CXType_UInt && kind != CXType_Long && kind != CXType_ULong &&
        kind != CXType_LongLong && kind != CXType_ULongLong && kind != CXType_Short &&
        kind != CXType_UShort) {
        return false;
    }

    // Check whether the initializer is an integer literal 0.
    struct ZeroCheck {
        bool found_zero = false;
    } zc;

    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
            auto* zcheck = static_cast<ZeroCheck*>(data);
            if (clang_getCursorKind(child) == CXCursor_IntegerLiteral) {
                // Evaluate the integer literal.
                CXEvalResult eval = clang_Cursor_Evaluate(child);
                if (eval != nullptr) {
                    if (clang_EvalResult_getKind(eval) == CXEval_Int &&
                        clang_EvalResult_getAsInt(eval) == 0) {
                        zcheck->found_zero = true;
                    }
                    clang_EvalResult_dispose(eval);
                }
            }
            return CXChildVisit_Continue;
        },
        &zc);

    return zc.found_zero;
}

}  // namespace

void RangeForRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_ForStmt) {
        return;
    }

    // The first child of a ForStmt is the init expression/declaration.
    struct FirstChild {
        CXCursor child;
        bool found = false;
    } fc;
    fc.child = clang_getNullCursor();

    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
            auto* state = static_cast<FirstChild*>(data);
            if (!state->found) {
                state->child = child;
                state->found = true;
            }
            return CXChildVisit_Break;
        },
        &fc);

    if (!fc.found) {
        return;
    }

    // The init of the ForStmt can be a DeclStmt containing a VarDecl.
    bool is_candidate = false;
    if (clang_getCursorKind(fc.child) == CXCursor_DeclStmt) {
        struct DeclCheck {
            bool found_int_zero = false;
        } dc;
        clang_visitChildren(
            fc.child,
            [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
                auto* dcheck = static_cast<DeclCheck*>(data);
                if (is_int_initialized_to_zero(child)) {
                    dcheck->found_int_zero = true;
                    return CXChildVisit_Break;
                }
                return CXChildVisit_Continue;
            },
            &dc);
        is_candidate = dc.found_int_zero;
    }

    if (!is_candidate) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(
        Finding{.rule_id = "CPP-MOD-006",
                .category = "modernization",
                .severity = "info",
                .file = file_path,
                .line = static_cast<int>(line),
                .column = static_cast<int>(column),
                .message = "Index-based for loop may be replaceable with a range-based for loop",
                .suggestion = "Consider 'for (const auto& elem : container)' instead",
                .confidence = 0.7});
}

}  // namespace cppulse
