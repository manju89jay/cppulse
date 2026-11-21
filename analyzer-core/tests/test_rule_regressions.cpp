/**
 * @file test_rule_regressions.cpp
 * @brief Detector regressions for written types, function definitions and modernization precision.
 */
#include <gtest/gtest.h>

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include "rules/complexity/cyclomatic_complexity.h"
#include "rules/complexity/function_length.h"
#include "rules/complexity/parameter_count.h"
#include "rules/modernization/auto_usage.h"
#include "rules/modernization/c_style_cast.h"
#include "rules/modernization/deprecated_headers.h"
#include "rules/modernization/range_for.h"
#include "test_temp_directory.h"

namespace {

/** @brief Own one isolated, parsed fixture without requiring system headers. */
class RuleRegressionFixture : public ::testing::Test {
   protected:
    void parse(const std::string& filename) {
        parse_path(std::filesystem::path(__FILE__).parent_path() / "fixtures" / filename);
    }

    void parse_path(const std::filesystem::path& path,
                    const std::vector<std::string>& extra_arguments = {}) {
        path_ = path;
        ASSERT_TRUE(std::filesystem::exists(path_));
        unit_.reset();
        index_.reset(clang_createIndex(0, 0));
        ASSERT_NE(index_, nullptr);
        std::vector<std::string> arguments{"-std=c++17", "-x", "c++"};
        const char* resources = std::getenv("CPPULSE_CLANG_RESOURCE_DIR");
        if (resources != nullptr && resources[0] != '\0') {
            arguments.push_back(std::string{"-resource-dir="} + resources);
        }
        arguments.insert(arguments.end(), extra_arguments.begin(), extra_arguments.end());
        std::vector<const char*> raw_arguments;
        for (const auto& argument : arguments) {
            raw_arguments.push_back(argument.c_str());
        }
        unit_.reset(clang_parseTranslationUnit(index_.get(), path_.string().c_str(),
                                               raw_arguments.data(),
                                               static_cast<int>(raw_arguments.size()), nullptr, 0,
                                               CXTranslationUnit_DetailedPreprocessingRecord));
        ASSERT_NE(unit_, nullptr);
        for (unsigned diagnostic_index = 0; diagnostic_index < clang_getNumDiagnostics(unit_.get());
             ++diagnostic_index) {
            CXDiagnostic diagnostic = clang_getDiagnostic(unit_.get(), diagnostic_index);
            const auto severity = clang_getDiagnosticSeverity(diagnostic);
            clang_disposeDiagnostic(diagnostic);
            ASSERT_LT(severity, CXDiagnostic_Error) << "Fixture must parse without errors";
        }
    }

    std::vector<int> marked_lines(const std::string& marker) {
        std::ifstream source{path_};
        EXPECT_TRUE(source.good());
        std::vector<int> lines;
        std::string text;
        int line = 0;
        while (std::getline(source, text)) {
            ++line;
            if (text.find(marker) != std::string::npos) {
                lines.push_back(line);
            }
        }
        return lines;
    }

    template <typename Rule>
    std::vector<cppulse::Finding> findings(Rule& rule) {
        struct VisitState {
            Rule* rule;
            std::string path;
        } state{&rule, path_.string()};
        clang_visitChildren(
            clang_getTranslationUnitCursor(unit_.get()),
            [](CXCursor cursor, CXCursor, CXClientData data) {
                auto* state = static_cast<VisitState*>(data);
                if (clang_Location_isFromMainFile(clang_getCursorLocation(cursor))) {
                    state->rule->check(cursor, state->path);
                }
                return CXChildVisit_Recurse;
            },
            &state);
        return rule.findings();
    }

    void expect_complexity(const std::vector<cppulse::Finding>& results,
                           const std::string& function, int expected) {
        const std::string prefix = "Function '" + function + "' has cyclomatic complexity of ";
        const auto matching = std::count_if(results.begin(), results.end(), [&](const auto& item) {
            return item.message.find(prefix) == 0;
        });
        ASSERT_EQ(matching, 1) << function;
        const auto result = std::find_if(results.begin(), results.end(), [&](const auto& item) {
            return item.message.find(prefix) == 0;
        });
        EXPECT_EQ(result->message.find(prefix + std::to_string(expected) + " "), 0u)
            << result->message;
    }

    std::filesystem::path path_;
    std::unique_ptr<void, decltype(&clang_disposeIndex)> index_{nullptr, &clang_disposeIndex};
    std::unique_ptr<CXTranslationUnitImpl, decltype(&clang_disposeTranslationUnit)> unit_{
        nullptr, &clang_disposeTranslationUnit};
};

TEST_F(RuleRegressionFixture, AlreadyDeducedIteratorTypesStayClean) {
    parse("iterator_deduction_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::AutoUsageRule rule;
    const auto results = findings(rule);
    ASSERT_EQ(results.size(), 2u);
    EXPECT_EQ(results[0].line, 6);
    EXPECT_EQ(results[1].line, 14);
}

TEST_F(RuleRegressionFixture, CountsLogicalOperatorsOncePerAstNode) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    const auto results = findings(rule);
    expect_complexity(results, "logical_chain", 4);
    expect_complexity(results, "alternative_chain", 4);
    expect_complexity(results, "nested_comparison", 3);
    expect_complexity(results, "bitwise_condition", 2);
}

TEST_F(RuleRegressionFixture, CountsMacroExpandedLogicalOperatorsOnce) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    expect_complexity(findings(rule), "macro_chain", 4);
}

TEST_F(RuleRegressionFixture, NestedLambdaDecisionsDoNotInflateEnclosingFunction) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    expect_complexity(findings(rule), "contains_lambda", 2);
}

TEST_F(RuleRegressionFixture, MeasuresUninstantiatedFunctionAndMemberTemplates) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    const auto results = findings(rule);
    expect_complexity(results, "template_branch", 4);
    expect_complexity(results, "member_template", 4);
}

TEST_F(RuleRegressionFixture, MeasuresUninstantiatedTemplateLength) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::FunctionLengthRule rule;
    rule.set_warn_threshold(1);
    const auto results = findings(rule);
    const auto matching = std::count_if(results.begin(), results.end(), [](const auto& item) {
        return item.message.find("Function 'template_length' is 5 lines long ") == 0;
    });
    ASSERT_EQ(matching, 1);
}

TEST_F(RuleRegressionFixture, MeasuresUninstantiatedTemplateParameters) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::ParameterCountRule rule;
    rule.set_warn_threshold(2);
    const auto results = findings(rule);
    const auto matching = std::count_if(results.begin(), results.end(), [](const auto& item) {
        return item.message.find("Function 'template_parameters' has 3 parameters ") == 0;
    });
    ASSERT_EQ(matching, 1);
}

TEST_F(RuleRegressionFixture, LambdaCaptureInitializerBelongsToEnclosingFunction) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    expect_complexity(findings(rule), "lambda_capture_initializer", 2);
}

TEST_F(RuleRegressionFixture, LocalClassBodyHasSeparateControlFlow) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    const auto results = findings(rule);
    expect_complexity(results, "contains_local_class", 1);
    expect_complexity(results, "nested_method", 3);
}

TEST_F(RuleRegressionFixture, BranchlessAndOverloadedOperatorCallsAreNotDecisions) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(1);
    const auto results = findings(rule);
    for (const auto& result : results) {
        EXPECT_EQ(result.message.find("Function 'branchless_function'"), std::string::npos);
        EXPECT_EQ(result.message.find("Function 'overloaded_logical'"), std::string::npos);
        EXPECT_EQ(result.message.find("Function 'declared_only'"), std::string::npos);
    }
}

TEST_F(RuleRegressionFixture, CaptureRecoveryPreservesNestedLambdaAndOverloadSemantics) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    const auto results = findings(rule);
    expect_complexity(results, "nested_lambda_capture", 1);
    expect_complexity(results, "overloaded_lambda_capture", 1);
}

TEST_F(RuleRegressionFixture, RecoversDirectAndConditionalCaptureInitializers) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    const auto results = findings(rule);
    expect_complexity(results, "direct_lambda_capture", 2);
    expect_complexity(results, "conditional_lambda_capture", 2);
}

TEST_F(RuleRegressionFixture, LambdaDefaultArgumentsDoNotBelongToEnclosingFunction) {
    parse("complexity_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CyclomaticComplexityRule rule;
    rule.set_warn_threshold(0);
    expect_complexity(findings(rule), "lambda_default_argument", 1);
}

TEST_F(RuleRegressionFixture, VoidDiscardsDoNotHideNestedNonvoidCasts) {
    parse("modernization_precision_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::CStyleCastRule rule;
    const auto results = findings(rule);
    const auto expected_lines = marked_lines("// EXPECT_CAST");
    ASSERT_EQ(expected_lines.size(), 6u);
    ASSERT_EQ(results.size(), expected_lines.size());
    std::vector<int> actual_lines;
    for (const auto& result : results) {
        EXPECT_EQ(result.rule_id, "CPP-MOD-001");
        EXPECT_EQ(result.file, path_.string());
        EXPECT_GT(result.column, 0);
        EXPECT_EQ(result.message, "C-style cast bypasses C++ type-safety checks");
        actual_lines.push_back(result.line);
    }
    EXPECT_EQ(actual_lines, expected_lines);
}

constexpr char kRangeForSuggestion[] =
    "Consider a range-based for loop over the same array and add each element to the accumulator";

TEST_F(RuleRegressionFixture, RangeForRequiresProvenFixedArrayAccumulation) {
    parse("modernization_precision_regressions.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::RangeForRule rule;
    const auto results = findings(rule);
    const auto expected_lines = marked_lines("// EXPECT_RANGE");
    ASSERT_EQ(expected_lines.size(), 2u);
    ASSERT_EQ(results.size(), expected_lines.size());
    std::vector<int> actual_lines;
    for (const auto& result : results) {
        EXPECT_EQ(result.rule_id, "CPP-MOD-006");
        EXPECT_EQ(result.file, path_.string());
        EXPECT_GT(result.column, 0);
        EXPECT_EQ(result.message,
                  "Fixed-array accumulation uses its index only to read each element");
        EXPECT_EQ(result.suggestion, kRangeForSuggestion);
        actual_lines.push_back(result.line);
    }
    EXPECT_EQ(actual_lines, expected_lines);
}

TEST_F(RuleRegressionFixture, PositiveRangeRewriteHasEquivalentSupportedShape) {
    parse("range_for_equivalence_before.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::RangeForRule before_rule;
    const auto results = findings(before_rule);
    const auto expected_lines = marked_lines("// EXPECT_RANGE");
    ASSERT_EQ(expected_lines.size(), 2u);
    ASSERT_EQ(results.size(), expected_lines.size());
    std::vector<int> actual_lines;
    for (const auto& result : results) {
        EXPECT_EQ(result.suggestion, kRangeForSuggestion);
        actual_lines.push_back(result.line);
    }
    EXPECT_EQ(actual_lines, expected_lines);
    parse("range_for_equivalence_after.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::RangeForRule after_rule;
    EXPECT_TRUE(findings(after_rule).empty());
    // These executable fixtures must also be compiled/run by the qualification
    // recipe; a parse-only test does not establish the rewrite's runtime result.
}

/** @brief Own real project shadow headers without impersonating system library headers. */
class HeaderPrecisionFixture : public RuleRegressionFixture {
   protected:
    void SetUp() override {
        temporary_ = cppulse::test::make_test_directory("cppulse-header-precision");
    }

    void TearDown() override {
        unit_.reset();
        index_.reset();
        std::error_code ignored;
        std::filesystem::remove_all(temporary_, ignored);
    }

    void write(const std::string& relative, const std::string& contents) {
        const auto path = temporary_ / relative;
        std::filesystem::create_directories(path.parent_path());
        std::ofstream source{path};
        ASSERT_TRUE(source.good());
        source << contents;
        ASSERT_TRUE(source.good());
    }

    std::filesystem::path temporary_;
};

TEST_F(HeaderPrecisionFixture, DirectSystemCHeadersRetainRealReplacements) {
    write("main.cpp", "#include <string.h>\n#include <stdio.h>\n");
    parse_path(temporary_ / "main.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::DeprecatedHeadersRule rule;
    const auto results = findings(rule);
    ASSERT_EQ(results.size(), 2u);
    EXPECT_EQ(results[0].line, 1);
    EXPECT_EQ(results[0].suggestion, "Replace <string.h> with <cstring>");
    EXPECT_EQ(results[1].line, 2);
    EXPECT_EQ(results[1].suggestion, "Replace <stdio.h> with <cstdio>");
    for (const auto& result : results) {
        EXPECT_EQ(result.rule_id, "CPP-MOD-002");
        EXPECT_EQ(result.file, path_.string());
        EXPECT_GT(result.column, 0);
    }
}

TEST_F(HeaderPrecisionFixture, QualifiedQuotedAndCppHeadersStayClean) {
    write("kj/string.h", "struct KjString { int project_value; };\n");
    write("project/string.h", "struct ProjectString { int project_value; };\n");
    write("main.cpp",
          "#include <kj/string.h>\n#include \"project/string.h\"\n#include <cstring>\n"
          "KjString first; ProjectString second;\n");
    parse_path(temporary_ / "main.cpp", {"-I" + temporary_.string()});
    ASSERT_NE(unit_, nullptr);
    cppulse::DeprecatedHeadersRule rule;
    EXPECT_TRUE(findings(rule).empty());
}

TEST_F(HeaderPrecisionFixture, BareProjectShadowHeadersAreNotSystemReplacements) {
    write("shadow/string.h", "struct ProjectStringHeader { int value; };\n");
    write("shadow/stdio.h", "struct ProjectStdioHeader { int value; };\n");
    write("main.cpp",
          "#include <string.h>\n#include \"stdio.h\"\n"
          "ProjectStringHeader first; ProjectStdioHeader second;\n");
    parse_path(temporary_ / "main.cpp", {"-I" + (temporary_ / "shadow").string()});
    ASSERT_NE(unit_, nullptr);
    cppulse::DeprecatedHeadersRule rule;
    EXPECT_TRUE(findings(rule).empty());
}

TEST_F(HeaderPrecisionFixture, MacroAndTransitiveIncludesAreNotDirectReplacementHints) {
    write("wrapper.h", "#include <stdio.h>\n");
    write("main.cpp",
          "#define C_HEADER <string.h>\n#include C_HEADER\n"
          "#include \"wrapper.h\"\n#include <cstring>\n");
    parse_path(temporary_ / "main.cpp");
    ASSERT_NE(unit_, nullptr);
    cppulse::DeprecatedHeadersRule rule;
    EXPECT_TRUE(findings(rule).empty());
}

}  // namespace
