/**
 * @file no_implicit_conversion.cpp
 * @brief MISRA-002 implementation.
 *
 * libclang does not expose CXCursor_ImplicitCastExpr directly.  We detect
 * narrowing by examining variable declarations and binary-operator assignments
 * where the initializer type is wider than the declared type.
 */

#include "no_implicit_conversion.h"

#include <clang-c/Index.h>

namespace cppulse {

namespace {

/// @brief Return true if from_kind is a floating-point type.
bool is_float_type(CXTypeKind kind) {
    return kind == CXType_Float || kind == CXType_Double || kind == CXType_LongDouble;
}

/// @brief Return true if to_kind is an integer type.
bool is_integer_type(CXTypeKind kind) {
    return kind == CXType_Bool || kind == CXType_Char_S || kind == CXType_Char_U ||
           kind == CXType_SChar || kind == CXType_UChar || kind == CXType_Short ||
           kind == CXType_UShort || kind == CXType_Int || kind == CXType_UInt ||
           kind == CXType_Long || kind == CXType_ULong || kind == CXType_LongLong ||
           kind == CXType_ULongLong;
}

/// @brief Return true if converting from_kind to to_kind is a narrowing conversion.
bool is_narrowing(CXTypeKind from_kind, CXTypeKind to_kind) {
    if (from_kind == to_kind) {
        return false;
    }

    // Float -> integer is always narrowing.
    if (is_float_type(from_kind) && is_integer_type(to_kind)) {
        return true;
    }

    // double -> float is narrowing.
    if (from_kind == CXType_Double && to_kind == CXType_Float) {
        return true;
    }
    if (from_kind == CXType_LongDouble && (to_kind == CXType_Double || to_kind == CXType_Float)) {
        return true;
    }

    // long long -> int/short/char is narrowing.
    if ((from_kind == CXType_LongLong || from_kind == CXType_ULongLong) &&
        (to_kind == CXType_Int || to_kind == CXType_UInt || to_kind == CXType_Short ||
         to_kind == CXType_UShort || to_kind == CXType_Char_S || to_kind == CXType_Char_U ||
         to_kind == CXType_SChar || to_kind == CXType_UChar)) {
        return true;
    }

    // long -> int/short/char.
    if ((from_kind == CXType_Long || from_kind == CXType_ULong) &&
        (to_kind == CXType_Int || to_kind == CXType_UInt || to_kind == CXType_Short ||
         to_kind == CXType_UShort || to_kind == CXType_Char_S || to_kind == CXType_Char_U ||
         to_kind == CXType_SChar || to_kind == CXType_UChar)) {
        return true;
    }

    // int -> short/char.
    if ((from_kind == CXType_Int || from_kind == CXType_UInt) &&
        (to_kind == CXType_Short || to_kind == CXType_UShort || to_kind == CXType_Char_S ||
         to_kind == CXType_Char_U || to_kind == CXType_SChar || to_kind == CXType_UChar)) {
        return true;
    }

    return false;
}

}  // namespace

void NoImplicitConversionRule::check_impl(CXCursor cursor, const std::string& file_path) {
    // Detect narrowing in VarDecl: declared type is narrower than initializer.
    if (clang_getCursorKind(cursor) != CXCursor_VarDecl) {
        return;
    }

    CXType declared_type = clang_getCursorType(cursor);
    if (declared_type.kind == CXType_Invalid || declared_type.kind == CXType_Auto) {
        return;
    }

    // Find the initializer expression (first non-type-ref child).
    struct InitInfo {
        CXType init_type;
        bool found = false;
    } info;
    info.init_type.kind = CXType_Invalid;

    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
            auto* state = static_cast<InitInfo*>(data);
            const CXCursorKind ck = clang_getCursorKind(child);
            // Skip type references and namespace refs — they are part of the type, not init.
            if (ck == CXCursor_TypeRef || ck == CXCursor_TemplateRef ||
                ck == CXCursor_NamespaceRef) {
                return CXChildVisit_Continue;
            }
            if (!state->found) {
                state->init_type = clang_getCursorType(child);
                state->found = true;
            }
            return CXChildVisit_Break;
        },
        &info);

    if (!info.found || info.init_type.kind == CXType_Invalid) {
        return;
    }

    if (!is_narrowing(info.init_type.kind, declared_type.kind)) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString from_spelling = clang_getTypeSpelling(info.init_type);
    CXString to_spelling = clang_getTypeSpelling(declared_type);
    const char* from_str = clang_getCString(from_spelling);
    const char* to_str = clang_getCString(to_spelling);
    std::string from_name = (from_str != nullptr) ? from_str : "?";
    std::string to_name = (to_str != nullptr) ? to_str : "?";
    clang_disposeString(from_spelling);
    clang_disposeString(to_spelling);

    CXString var_spelling = clang_getCursorSpelling(cursor);
    const char* var_str = clang_getCString(var_spelling);
    std::string var_name = (var_str != nullptr) ? var_str : "?";
    clang_disposeString(var_spelling);

    add_finding(
        Finding{.rule_id = "MISRA-002",
                .category = "misra",
                .severity = "warning",
                .file = file_path,
                .line = static_cast<int>(line),
                .column = static_cast<int>(column),
                .message = "Implicit narrowing conversion: initializing '" + var_name +
                           "' of type '" + to_name + "' from '" + from_name + "'",
                .suggestion = "Use an explicit cast and verify the value fits in the target type",
                .confidence = 0.85});
}

}  // namespace cppulse
