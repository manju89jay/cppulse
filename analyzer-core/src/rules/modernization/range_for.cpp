/**
 * @file range_for.cpp
 * @brief CPP-MOD-006 implementation.
 */

#include "range_for.h"

#include <clang-c/Index.h>

#include <array>
#include <climits>
#include <memory>
#include <string>

namespace cppulse {

namespace {

/** @brief Bound child inspection; unexpected AST shapes are not candidates. */
struct Children {
    std::array<CXCursor, 4> cursors{};
    std::size_t size = 0;
    bool overflow = false;
};

Children children_of(CXCursor cursor) {
    Children children;
    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor, CXClientData data) {
            auto& result = *static_cast<Children*>(data);
            if (result.size == result.cursors.size()) {
                result.overflow = true;
                return CXChildVisit_Break;
            }
            result.cursors.at(result.size++) = child;
            return CXChildVisit_Continue;
        },
        &children);
    return children;
}

/** @brief Ignore only parenthesized/implicit wrappers, preserving explicit conversions. */
CXCursor expression(CXCursor cursor) {
    while (clang_getCursorKind(cursor) == CXCursor_UnexposedExpr ||
           clang_getCursorKind(cursor) == CXCursor_ParenExpr) {
        const auto children = children_of(cursor);
        if (children.overflow || children.size != 1) {
            break;
        }
        cursor = children.cursors.at(0);
    }
    return cursor;
}

bool references(CXCursor cursor, CXCursor declaration) {
    cursor = expression(cursor);
    return clang_getCursorKind(cursor) == CXCursor_DeclRefExpr &&
           clang_equalCursors(clang_getCursorReferenced(cursor), declaration) != 0;
}

/** @brief Require a literal value, not a zero somewhere inside an initializer. */
bool integer_literal(CXCursor cursor, long long expected) {
    cursor = expression(cursor);
    if (clang_getCursorKind(cursor) != CXCursor_IntegerLiteral) {
        return false;
    }
    const std::unique_ptr<void, decltype(&clang_EvalResult_dispose)> value{
        clang_Cursor_Evaluate(cursor), &clang_EvalResult_dispose};
    return value != nullptr && clang_EvalResult_getKind(value.get()) == CXEval_Int &&
           clang_EvalResult_getAsLongLong(value.get()) == expected;
}

bool is_scalar_value(CXType type) {
    type = clang_getCanonicalType(type);
    if (clang_isVolatileQualifiedType(type) != 0) {
        return false;
    }
    switch (type.kind) {
        case CXType_Char_U:
        case CXType_UChar:
        case CXType_Char16:
        case CXType_Char32:
        case CXType_UShort:
        case CXType_UInt:
        case CXType_ULong:
        case CXType_ULongLong:
        case CXType_Char_S:
        case CXType_SChar:
        case CXType_WChar:
        case CXType_Short:
        case CXType_Int:
        case CXType_Long:
        case CXType_LongLong:
        case CXType_Float:
        case CXType_Double:
        case CXType_LongDouble:
            return true;
        default:
            return false;
    }
}

/** @brief Confirm ++ of this declaration, with its result unused by the loop. */
bool unit_increment(CXCursor cursor, CXCursor index) {
    if (clang_getCursorKind(cursor) != CXCursor_UnaryOperator) {
        return false;
    }
    const auto children = children_of(cursor);
    if (children.overflow || children.size != 1 || !references(children.cursors.at(0), index)) {
        return false;
    }
    const CXTranslationUnit unit = clang_Cursor_getTranslationUnit(cursor);
    if (unit == nullptr) {
        return false;
    }
    CXToken* raw_tokens = nullptr;
    unsigned count = 0;
    clang_tokenize(unit, clang_getCursorExtent(cursor), &raw_tokens, &count);
    struct TokenDeleter {
        CXTranslationUnit unit;
        unsigned count;
        void operator()(CXToken* tokens) const noexcept {
            clang_disposeTokens(unit, tokens, count);
        }
    };
    const std::unique_ptr<CXToken, TokenDeleter> tokens{raw_tokens, {unit, count}};
    if (tokens == nullptr || count != 2) {
        return false;
    }
    for (unsigned token_index = 0; token_index < count; ++token_index) {
        CXString spelling = clang_getTokenSpelling(unit, tokens.get()[token_index]);
        const char* text = clang_getCString(spelling);
        const bool increment = text != nullptr && std::string_view{text} == "++";
        clang_disposeString(spelling);
        if (increment) {
            return true;
        }
    }
    return false;
}

/**
 * @brief Prove a small read-only traversal, not arbitrary loop equivalence.
 *
 * Restrict the body to built-in scalar accumulation from one array element.
 * Calls, aliases, deferred scopes, extra index uses and writes to the array are
 * not silently treated as equivalent const-reference traversals.
 */
CXCursor accumulation_array(CXCursor body, CXCursor index) {
    if (clang_getCursorKind(body) == CXCursor_CompoundStmt) {
        const auto statements = children_of(body);
        if (statements.overflow || statements.size != 1) {
            return clang_getNullCursor();
        }
        body = statements.cursors.at(0);
    }
    if (clang_getCursorKind(body) != CXCursor_CompoundAssignOperator ||
        clang_Cursor_getBinaryOpcode(body) != CX_BO_AddAssign) {
        return clang_getNullCursor();
    }
    const auto operands = children_of(body);
    if (operands.overflow || operands.size != 2) {
        return clang_getNullCursor();
    }
    const CXCursor accumulator = expression(operands.cursors.at(0));
    if (clang_getCursorKind(accumulator) != CXCursor_DeclRefExpr ||
        !is_scalar_value(clang_getCursorType(accumulator))) {
        return clang_getNullCursor();
    }
    const CXCursor accumulator_declaration = clang_getCursorReferenced(accumulator);
    if (clang_getCursorKind(accumulator_declaration) != CXCursor_VarDecl ||
        !is_scalar_value(clang_getCursorType(accumulator_declaration)) ||
        clang_equalCursors(accumulator_declaration, index) != 0) {
        return clang_getNullCursor();
    }
    const CXCursor element = expression(operands.cursors.at(1));
    if (clang_getCursorKind(element) != CXCursor_ArraySubscriptExpr) {
        return clang_getNullCursor();
    }
    const auto subscript = children_of(element);
    if (subscript.overflow || subscript.size != 2 || !references(subscript.cursors.at(1), index)) {
        return clang_getNullCursor();
    }
    const CXCursor array_reference = expression(subscript.cursors.at(0));
    if (clang_getCursorKind(array_reference) != CXCursor_DeclRefExpr) {
        return clang_getNullCursor();
    }
    const CXCursor array = clang_getCursorReferenced(array_reference);
    const CXType type = clang_getCanonicalType(clang_getCursorType(array));
    // libclang can move an element's volatile qualifier to the canonical array.
    if (clang_getCursorKind(array) != CXCursor_VarDecl || type.kind != CXType_ConstantArray ||
        clang_isVolatileQualifiedType(type) != 0 ||
        !is_scalar_value(clang_getArrayElementType(type))) {
        return clang_getNullCursor();
    }
    return array;
}

}  // namespace

void RangeForRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_ForStmt) {
        return;
    }
    const auto loop = children_of(cursor);
    if (loop.overflow || loop.size != 4 ||
        clang_getCursorKind(loop.cursors.at(0)) != CXCursor_DeclStmt) {
        return;
    }
    const auto declarations = children_of(loop.cursors.at(0));
    if (declarations.overflow || declarations.size != 1) {
        return;
    }
    const CXCursor index = declarations.cursors.at(0);
    const CXType index_type = clang_getCanonicalType(clang_getCursorType(index));
    if (clang_getCursorKind(index) != CXCursor_VarDecl ||
        (index_type.kind != CXType_Int && index_type.kind != CXType_UInt) ||
        clang_isVolatileQualifiedType(index_type) != 0 ||
        !integer_literal(clang_Cursor_getVarDeclInitializer(index), 0) ||
        !unit_increment(loop.cursors.at(2), index)) {
        return;
    }
    const CXCursor condition = loop.cursors.at(1);
    if (clang_getCursorKind(condition) != CXCursor_BinaryOperator ||
        clang_Cursor_getBinaryOpcode(condition) != CX_BO_LT) {
        return;
    }
    const auto bounds = children_of(condition);
    if (bounds.overflow || bounds.size != 2 || !references(bounds.cursors.at(0), index)) {
        return;
    }
    const CXCursor array = accumulation_array(loop.cursors.at(3), index);
    if (clang_Cursor_isNull(array) != 0) {
        return;
    }
    const auto length = clang_getArraySize(clang_getCanonicalType(clang_getCursorType(array)));
    if (length <= 0 || length > INT_MAX || !integer_literal(bounds.cursors.at(1), length)) {
        return;
    }
    CXString spelling = clang_getCursorSpelling(array);
    const char* raw_name = clang_getCString(spelling);
    const bool has_name = raw_name != nullptr && raw_name[0] != '\0';
    clang_disposeString(spelling);
    if (!has_name) {
        return;
    }

    CXSourceLocation location = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(location, nullptr, &line, &column, nullptr);

    // The declaration name alone loses qualification and a new local may shadow the accumulator.
    add_finding(Finding{
        .rule_id = "CPP-MOD-006",
        .category = "modernization",
        .severity = "info",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "Fixed-array accumulation uses its index only to read each element",
        .suggestion = "Consider a range-based for loop over the same array and add each element "
                      "to the accumulator",
        .confidence = 0.7});
}

}  // namespace cppulse
