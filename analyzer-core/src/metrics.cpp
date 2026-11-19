/** @file metrics.cpp
 * @brief Source-spelled lexical and semantic callable measurements.
 */
#include "metrics.h"

#include <algorithm>
#include <array>
#include <iomanip>
#include <limits>
#include <memory>
#include <set>
#include <sstream>
#include <string_view>
#include <tuple>
#include <unordered_map>
#include <vector>

#include "rules/complexity/cyclomatic_complexity.h"

namespace cppulse {
namespace {
using Json = nlohmann::json;

std::string string_and_dispose(CXString value) {
    const char* text = clang_getCString(value);
    std::string result = text == nullptr ? "" : text;
    clang_disposeString(value);
    return result;
}

// SHA-256 binds the observed TU buffer without adding a runtime crypto dependency.
std::uint32_t rotate(std::uint32_t value, unsigned bits) {
    return (value >> bits) | (value << (32u - bits));
}
std::string sha256(std::string_view bytes) {
    constexpr std::array<std::uint32_t, 64> constants{
        {0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
         0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
         0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
         0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
         0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
         0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
         0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
         0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
         0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
         0xc67178f2}};
    std::array<std::uint32_t, 8> state{{0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f,
                                        0x9b05688c, 0x1f83d9ab, 0x5be0cd19}};
    const std::size_t blocks = (bytes.size() + 9u + 63u) / 64u;
    const auto bit_length = static_cast<std::uint64_t>(bytes.size()) * 8u;
    for (std::size_t block = 0; block < blocks; ++block) {
        std::array<std::uint32_t, 64> words{};
        for (std::size_t index = 0; index < 64; ++index) {
            const auto offset = block * 64u + index;
            unsigned char value = 0;
            if (offset < bytes.size())
                value = static_cast<unsigned char>(bytes[offset]);
            else if (offset == bytes.size())
                value = 0x80;
            else if (offset >= blocks * 64u - 8u)
                value =
                    static_cast<unsigned char>(bit_length >> ((blocks * 64u - 1u - offset) * 8u));
            words[index / 4u] |= static_cast<std::uint32_t>(value) << ((3u - index % 4u) * 8u);
        }
        for (std::size_t index = 16; index < words.size(); ++index) {
            const auto a = words[index - 15];
            const auto b = words[index - 2];
            words[index] = words[index - 16] + (rotate(a, 7) ^ rotate(a, 18) ^ (a >> 3)) +
                           words[index - 7] + (rotate(b, 17) ^ rotate(b, 19) ^ (b >> 10));
        }
        auto values = state;
        for (std::size_t index = 0; index < words.size(); ++index) {
            const auto first =
                values[7] + (rotate(values[4], 6) ^ rotate(values[4], 11) ^ rotate(values[4], 25)) +
                ((values[4] & values[5]) ^ (~values[4] & values[6])) + constants[index] +
                words[index];
            const auto second =
                (rotate(values[0], 2) ^ rotate(values[0], 13) ^ rotate(values[0], 22)) +
                ((values[0] & values[1]) ^ (values[0] & values[2]) ^ (values[1] & values[2]));
            for (std::size_t at = 7; at > 0; --at) values[at] = values[at - 1];
            values[4] += first;
            values[0] = first + second;
        }
        for (std::size_t index = 0; index < state.size(); ++index) state[index] += values[index];
    }
    std::ostringstream result;
    result << std::hex << std::setfill('0');
    for (const auto value : state) result << std::setw(8) << value;
    return result.str();
}

std::filesystem::path absolute_path(const std::filesystem::path& path) {
    std::error_code error;
    auto result = std::filesystem::weakly_canonical(path, error);
    return error ? std::filesystem::absolute(path).lexically_normal() : result;
}
std::string project_path(const std::filesystem::path& path, const std::filesystem::path& root) {
    const auto relative = absolute_path(path).lexically_relative(absolute_path(root));
    if (!relative.empty() && !relative.is_absolute() && *relative.begin() != "..")
        return relative.generic_string();
    return absolute_path(path).generic_string();
}
Json unavailable(const FileCoverage& outcome, std::uint64_t limit) {
    const std::string reason =
        outcome.reason.value_or("Source buffer was not measured: " + outcome.status);
    return {{"path", outcome.path},
            {"status", outcome.status},
            {"error_count", outcome.error_count},
            {"measurement_complete", false},
            {"source_content_sha256", nullptr},
            {"physical_loc", nullptr},
            {"code_loc", nullptr},
            {"function_count", nullptr},
            {"functions", Json::array()},
            {"includes", Json::array()},
            {"limitations", {reason}},
            {"token_stream",
             {{"method", "cppulse-spelled-tokens-1"},
              {"availability", "unavailable"},
              {"record_limit", limit},
              {"complete", false},
              {"total_tokens", nullptr},
              {"retained_tokens", 0},
              {"records", Json::array()},
              {"limitations", {reason}}}}};
}

struct TokensDeleter {
    CXTranslationUnit unit;
    unsigned count;
    void operator()(CXToken* value) const noexcept {
        clang_disposeTokens(unit, value, count);
    }
};

bool callable(CXCursorKind kind) {
    return kind == CXCursor_FunctionDecl || kind == CXCursor_FunctionTemplate ||
           kind == CXCursor_CXXMethod || kind == CXCursor_Constructor ||
           kind == CXCursor_Destructor || kind == CXCursor_ConversionFunction ||
           kind == CXCursor_LambdaExpr;
}
bool nested_scope(CXCursorKind kind) {
    return callable(kind) || kind == CXCursor_ClassDecl || kind == CXCursor_StructDecl ||
           kind == CXCursor_ClassTemplate || kind == CXCursor_ParmDecl;
}
bool control(CXCursorKind kind) {
    return kind == CXCursor_IfStmt || kind == CXCursor_ForStmt ||
           kind == CXCursor_CXXForRangeStmt || kind == CXCursor_WhileStmt ||
           kind == CXCursor_DoStmt || kind == CXCursor_SwitchStmt ||
           kind == CXCursor_CXXCatchStmt || kind == CXCursor_ConditionalOperator;
}

CXCursor lambda_body(CXCursor cursor) {
    auto body = clang_getNullCursor();
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
    return body;
}

int nesting(CXCursor cursor, int depth);
struct NestingState {
    int depth;
    int maximum;
};
CXChildVisitResult nesting_child(CXCursor child, CXCursor, CXClientData data) {
    auto& state = *static_cast<NestingState*>(data);
    state.maximum = std::max(state.maximum, nesting(child, state.depth));
    return CXChildVisit_Continue;
}

// libclang omits some init-capture expressions from child traversal. Token annotations
// recover their semantic expression cursors; nested lambda bodies remain separate scopes.
int capture_nesting(CXCursor lambda, int depth) {
    const auto unit = clang_Cursor_getTranslationUnit(lambda);
    const auto body = lambda_body(lambda);
    if (unit == nullptr || clang_Cursor_isNull(body))
        return depth;
    CXToken* raw = nullptr;
    unsigned count = 0;
    clang_tokenize(unit,
                   clang_getRange(clang_getRangeStart(clang_getCursorExtent(lambda)),
                                  clang_getRangeStart(clang_getCursorExtent(body))),
                   &raw, &count);
    std::unique_ptr<CXToken, TokensDeleter> tokens{raw, {unit, count}};
    if (!tokens || !count)
        return depth;
    std::vector<CXCursor> annotations(count);
    clang_annotateTokens(unit, tokens.get(), count, annotations.data());
    int maximum = depth;
    for (unsigned index = 0; index < count; ++index) {
        const auto annotation = annotations[index];
        if (clang_equalCursors(annotation, lambda)) {
            if (string_and_dispose(clang_getTokenSpelling(unit, tokens.get()[index])) == "]")
                break;
        } else if (clang_isExpression(clang_getCursorKind(annotation))) {
            maximum = std::max(maximum, nesting(annotation, depth));
        }
    }
    return maximum;
}
int nesting(CXCursor cursor, int depth) {
    const auto kind = clang_getCursorKind(cursor);
    if (kind == CXCursor_LambdaExpr)
        return capture_nesting(cursor, depth);
    if (nested_scope(kind))
        return depth;
    const auto next_depth = depth + (control(kind) ? 1 : 0);
    NestingState state{next_depth, next_depth};
    clang_visitChildren(cursor, nesting_child, &state);
    return state.maximum;
}

struct FunctionState {
    CXTranslationUnit unit;
    CXFile source;
    std::string relative_path;
    bool partial;
    Json functions = Json::array();
};

Json function_record(CXCursor cursor, const FunctionState& state) {
    const auto kind = clang_getCursorKind(cursor);
    const auto extent = clang_getCursorExtent(cursor);
    unsigned line = 0, column = 0, end_line = 0, end_column = 0;
    CXFile start_file = nullptr, end_file = nullptr;
    clang_getExpansionLocation(clang_getRangeStart(extent), &start_file, &line, &column, nullptr);
    clang_getExpansionLocation(clang_getRangeEnd(extent), &end_file, &end_line, &end_column,
                               nullptr);
    std::string symbol = string_and_dispose(clang_getCursorUSR(cursor));
    const bool fallback = symbol.empty();
    const std::string kind_name = kind == CXCursor_LambdaExpr           ? "lambda"
                                  : kind == CXCursor_FunctionTemplate   ? "function_template"
                                  : kind == CXCursor_CXXMethod          ? "method"
                                  : kind == CXCursor_Constructor        ? "constructor"
                                  : kind == CXCursor_Destructor         ? "destructor"
                                  : kind == CXCursor_ConversionFunction ? "conversion"
                                                                        : "function";
    if (fallback)
        symbol = "location:" + state.relative_path + ":" + kind_name + ":" + std::to_string(line) +
                 ":" + std::to_string(column);
    std::string name = string_and_dispose(clang_getCursorSpelling(cursor));
    if (name.empty())
        name = kind == CXCursor_LambdaExpr ? "<lambda>" : "<unnamed>";
    int parameters = 0;
    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor, CXClientData data) {
            if (clang_getCursorKind(child) == CXCursor_ParmDecl)
                ++*static_cast<int*>(data);
            return CXChildVisit_Continue;
        },
        &parameters);
    const bool located = start_file != nullptr && end_file != nullptr &&
                         clang_File_isEqual(start_file, state.source) &&
                         clang_File_isEqual(end_file, state.source) && line > 0 && column > 0 &&
                         std::tie(end_line, end_column) >= std::tie(line, column);
    Json limitations = Json::array();
    if (fallback)
        limitations.push_back("Location fallback identity has limited edit/rename stability.");
    if (state.partial)
        limitations.push_back(
            "Partial AST: observed callable facts do not establish complete analysis.");
    if (!located)
        limitations.push_back("Callable extent is not a valid main-file source range.");
    auto body = kind == CXCursor_LambdaExpr ? lambda_body(cursor) : cursor;
    NestingState nest{0, 0};
    clang_visitChildren(body, nesting_child, &nest);
    Json result{
        {"symbol", symbol},
        {"identity_kind", fallback ? "source-location-fallback" : "usr"},
        {"name", name},
        {"kind", kind_name},
        {"line", nullptr},
        {"column", nullptr},
        {"end_line", nullptr},
        {"end_column", nullptr},
        {"function_length", nullptr},
        {"cyclomatic_complexity", nullptr},
        {"nesting_depth", nullptr},
        {"parameter_count", nullptr},
        {"availability", located ? (state.partial ? "partial" : "measured") : "unavailable"},
        {"limitations", limitations}};
    if (located) {
        result.update({{"line", line},
                       {"column", column},
                       {"end_line", end_line},
                       {"end_column", end_column},
                       {"function_length", end_line - line + 1},
                       {"cyclomatic_complexity", measure_cyclomatic_complexity(cursor)},
                       {"nesting_depth", nest.maximum},
                       {"parameter_count", parameters}});
    }
    return result;
}
CXChildVisitResult function_child(CXCursor cursor, CXCursor, CXClientData data) {
    auto& state = *static_cast<FunctionState*>(data);
    if (!clang_Location_isFromMainFile(clang_getCursorLocation(cursor)))
        return CXChildVisit_Continue;
    const auto kind = clang_getCursorKind(cursor);
    if (callable(kind) && (kind == CXCursor_LambdaExpr || clang_isCursorDefinition(cursor)))
        state.functions.push_back(function_record(cursor, state));
    return CXChildVisit_Recurse;
}

struct IncludeState {
    CXTranslationUnit unit;
    std::filesystem::path root;
    Json edges = Json::array();
    std::unordered_map<CXFile, Json> identities{};
};

Json unavailable_include_identity() {
    return {{"method", "libclang-tu-buffer-sha256-v1"},
            {"status", "unavailable"},
            {"sha256", nullptr},
            {"size_bytes", nullptr}};
}

Json include_identity(IncludeState& state, CXFile file) {
    const auto found = state.identities.find(file);
    if (found != state.identities.end())
        return found->second;
    std::size_t size = 0;
    const char* bytes = clang_getFileContents(state.unit, file, &size);
    auto identity = unavailable_include_identity();
    // The retained TU buffer is the observation. A later filesystem read could
    // describe restored bytes that never produced this AST. Null is unknown,
    // even when no length was returned; it is not evidence of an empty file.
    if (bytes != nullptr) {
        identity.update({{"status", "available"},
                         {"sha256", sha256(std::string_view{bytes, size})},
                         {"size_bytes", size}});
    }
    state.identities.emplace(file, identity);
    return identity;
}

void inclusion(CXFile included, CXSourceLocation* stack, unsigned count, CXClientData data) {
    if (count == 0 || included == nullptr)
        return;
    auto& state = *static_cast<IncludeState*>(data);
    CXFile source = nullptr;
    clang_getExpansionLocation(stack[0], &source, nullptr, nullptr, nullptr);
    if (source == nullptr)
        return;
    const std::filesystem::path target{string_and_dispose(clang_getFileName(included))};
    const std::filesystem::path from{string_and_dispose(clang_getFileName(source))};
    if (target.empty() || from.empty())
        return;
    const auto target_id = project_path(target, state.root);
    const auto target_kind =
        std::filesystem::path{target_id}.is_absolute() ? "external" : "project";
    state.edges.push_back({{"source", project_path(from, state.root)},
                           {"target", target_id},
                           {"target_kind", target_kind},
                           {"direct", count == 1},
                           {"content_identity", include_identity(state, included)}});
}
// Inclusion callbacks omit missing headers. Preprocessing cursors retain their
// spelled identity without inventing a filesystem path or dependency fingerprint.
struct UnresolvedIncludeState {
    IncludeState* includes;
    CXFile main_file;
};
CXChildVisitResult unresolved_inclusion(CXCursor cursor, CXCursor, CXClientData data) {
    if (clang_getCursorKind(cursor) != CXCursor_InclusionDirective ||
        clang_getIncludedFile(cursor) != nullptr)
        return CXChildVisit_Continue;
    auto& state = *static_cast<UnresolvedIncludeState*>(data);
    CXFile source = nullptr;
    clang_getExpansionLocation(clang_getCursorLocation(cursor), &source, nullptr, nullptr, nullptr);
    if (source == nullptr)
        return CXChildVisit_Continue;
    const auto from = string_and_dispose(clang_getFileName(source));
    const auto target = string_and_dispose(clang_getCursorSpelling(cursor));
    if (!from.empty() && !target.empty())
        state.includes->edges.push_back(
            {{"source", project_path(from, state.includes->root)},
             {"target", target},
             {"target_kind", "unresolved"},
             {"direct", clang_File_isEqual(source, state.main_file) != 0},
             {"content_identity", unavailable_include_identity()}});
    return CXChildVisit_Continue;
}
}  // namespace

Json measure_native_file(CXTranslationUnit unit, const std::filesystem::path& source,
                         const std::filesystem::path& repo_root, const FileCoverage& outcome,
                         std::uint64_t max_token_records) {
    Json result = unavailable(outcome, max_token_records);
    const auto file = clang_getFile(unit, source.string().c_str());
    std::size_t size = 0;
    const char* bytes = file == nullptr ? nullptr : clang_getFileContents(unit, file, &size);
    if (file == nullptr || (bytes == nullptr && size != 0) ||
        size > std::numeric_limits<unsigned>::max()) {
        result["limitations"] = {
            "Main-file TU buffer was unavailable or exceeded libclang offset range."};
        result["token_stream"]["limitations"] = result["limitations"];
        return result;
    }
    // Empty files can expose a null buffer. No fresh filesystem read replaces TU contents.
    const std::string_view content{bytes == nullptr ? "" : bytes, size};
    // Match Clang's source line table: CR and LF terminate one line, with
    // CRLF paired as one terminator. LFCR remains two terminators.
    std::uint64_t physical = 0;
    for (std::size_t offset = 0; offset < content.size(); ++offset) {
        const auto byte = content[offset];
        if (byte != '\r' && byte != '\n')
            continue;
        ++physical;
        if (offset + 1 < content.size() && byte == '\r' && content[offset + 1] == '\n')
            ++offset;
    }
    if (!content.empty() && content.back() != '\r' && content.back() != '\n')
        ++physical;
    result["physical_loc"] = physical;
    result["source_content_sha256"] = sha256(content);
    result["limitations"] = Json::array();
    const bool partial = outcome.status != "analyzed" || outcome.error_count != 0;
    if (partial)
        result["limitations"].push_back(
            "Partial parse: lexical observations and callable facts do not establish complete "
            "analysis.");
    auto& stream = result["token_stream"];
    stream["limitations"] = Json::array();
    const auto range =
        clang_getRange(clang_getLocationForOffset(unit, file, 0),
                       clang_getLocationForOffset(unit, file, static_cast<unsigned>(size)));
    CXToken* raw = nullptr;
    unsigned count = 0;
    clang_tokenize(unit, range, &raw, &count);
    std::unique_ptr<CXToken, TokensDeleter> tokens{raw, {unit, count}};
    std::set<unsigned> code_lines;
    std::uint64_t total = 0;
    for (unsigned index = 0; index < count; ++index) {
        const auto token = tokens.get()[index];
        const auto kind = clang_getTokenKind(token);
        if (kind == CXToken_Comment)
            continue;
        const auto token_range = clang_getTokenExtent(unit, token);
        unsigned line = 0, column = 0, end_line = 0, end_column = 0, start_offset = 0,
                 end_offset = 0;
        clang_getSpellingLocation(clang_getRangeStart(token_range), nullptr, &line, &column,
                                  &start_offset);
        clang_getSpellingLocation(clang_getRangeEnd(token_range), nullptr, &end_line, &end_column,
                                  &end_offset);
        // Extent ends are exclusive; a literal ending at column 1 does not occupy that line.
        const auto last = end_line - (end_column == 1 && end_line > line ? 1u : 0u);
        for (unsigned at = line; at <= last && at > 0 && at <= physical; ++at)
            code_lines.insert(at);
        ++total;
        if (stream["records"].size() >= max_token_records)
            continue;
        const auto spelling = string_and_dispose(clang_getTokenSpelling(unit, token));
        if (spelling.empty())
            continue;
        const char* kind_name = kind == CXToken_Punctuation  ? "punctuation"
                                : kind == CXToken_Keyword    ? "keyword"
                                : kind == CXToken_Identifier ? "identifier"
                                                             : "literal";
        stream["records"].push_back({{"kind", kind_name},
                                     {"spelling", spelling},
                                     {"line", line},
                                     {"column", column},
                                     {"end_line", end_line},
                                     {"end_column", end_column}});
    }
    const bool complete = stream["records"].size() == total;
    stream.update({{"availability", complete ? "measured" : "partial"},
                   {"complete", complete},
                   {"total_tokens", total},
                   {"retained_tokens", stream["records"].size()}});
    if (!complete)
        stream["limitations"].push_back(
            "Configured max_token_records exhausted; token stream is truncated and complete "
            "duplication is unavailable.");
    result["code_loc"] = code_lines.size();
    FunctionState functions{unit, file, project_path(source, repo_root), partial};
    clang_visitChildren(clang_getTranslationUnitCursor(unit), function_child, &functions);
    std::sort(functions.functions.begin(), functions.functions.end(),
              [](const Json& left, const Json& right) {
                  return std::tie(left["line"], left["column"], left["symbol"]) <
                         std::tie(right["line"], right["column"], right["symbol"]);
              });
    bool function_complete = !partial;
    for (const auto& function : functions.functions)
        if (function["availability"] != "measured")
            function_complete = false;
    result["measurement_complete"] = function_complete;
    if (function_complete)
        result["function_count"] = functions.functions.size();
    result["functions"] = std::move(functions.functions);
    IncludeState includes{unit, repo_root};
    clang_getInclusions(unit, inclusion, &includes);
    UnresolvedIncludeState unresolved{&includes, file};
    clang_visitChildren(clang_getTranslationUnitCursor(unit), unresolved_inclusion, &unresolved);
    result["includes"] = std::move(includes.edges);
    return result;
}

static Json native_metrics_header(const AnalysisCoverage& coverage) {
    return {{"version", "1.0.0"},
            {"metric_version", "cppulse-metrics-1"},
            {"max_token_records", coverage.max_token_records},
            {"definitions",
             {{"physical_loc",
               "Physical lines including blanks/comments; CR and LF terminate one line, CRLF is "
               "paired, LFCR is two terminators; terminal newline adds no extra line."},
              {"code_loc",
               "Union of non-comment source-spelled token lines, including directives, inactive "
               "branches and multiline literals."},
              {"function_length",
               "Inclusive source extent in physical lines, including a template prefix."},
              {"cyclomatic_complexity",
               "One base plus semantic if/for/range-for/while/do/case/conditional/short-circuit "
               "decisions; nested callable bodies and default arguments are separate; lambda "
               "capture initializers belong to enclosing scope."},
              {"nesting_depth",
               "Maximum control/conditional nesting excluding nested callable bodies; else-if is "
               "nested."},
              {"parameter_count",
               "Ordinary declared parameters; template parameters excluded; a parameter pack is "
               "one declaration."},
              {"tokens",
               "cppulse-spelled-tokens-1: libclang source-spelled tokens excluding "
               "comments/whitespace, preserving identifiers and literals."},
              {"include_content_identity",
               "libclang-tu-buffer-sha256-v1: SHA-256 and size of an observed retained TU include "
               "buffer. Unavailable or legacy path-only observations do not prove dependency "
               "bytes; complete dependency closure is not established."}}},
            {"limitations",
             {"Physical/code LOC describe source spelling; callable definitions describe the "
              "active parse context only. Inactive definitions and arbitrary template "
              "instantiations are not verified.",
              "No duplication metric is claimed by the lexical token inventory; duplication "
              "requires a separately executed algorithm.",
              "Include paths alone do not establish dependency identity. Available content "
              "identities describe observed TU buffers, not complete dependency closure."}}};
}
Json native_metrics_document(const AnalysisCoverage& coverage) {
    auto result = native_metrics_header(coverage);
    result["files"] = Json::array();
    for (const auto& file : coverage.files) {
        if (file.metrics)
            result["files"].push_back(*file.metrics);
        else
            result["files"].push_back(unavailable(file, coverage.max_token_records));
    }
    return result;
}

void write_native_metrics(std::ostream& stream, const AnalysisCoverage& coverage) {
    const auto header = native_metrics_header(coverage);
    stream << '{';
    for (const auto& member : header.items())
        stream << Json(member.key()) << ':' << member.value() << ',';
    stream << "\"files\":[";
    bool first = true;
    for (const auto& file : coverage.files) {
        if (!first)
            stream << ',';
        first = false;
        if (file.metrics)
            stream << *file.metrics;
        else
            stream << unavailable(file, coverage.max_token_records);
        if (!stream)
            return;
    }
    stream << "]}";
}
}  // namespace cppulse
