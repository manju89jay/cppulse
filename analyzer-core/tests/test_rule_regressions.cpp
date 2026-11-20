/**
 * @file test_rule_regressions.cpp
 * @brief Meaningful detector regressions for written types and function definitions.
 */
#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include "rules/complexity/cyclomatic_complexity.h"
#include "rules/complexity/function_length.h"
#include "rules/complexity/parameter_count.h"
#include "rules/modernization/auto_usage.h"

namespace {

/** @brief Own one isolated, parsed fixture without requiring system headers. */
class RuleRegressionFixture : public ::testing::Test {
   protected:
    void parse(const std::string& filename) {
        path_ = std::filesystem::path(__FILE__).parent_path() / "fixtures" / filename;
        ASSERT_TRUE(std::filesystem::exists(path_));
        index_.reset(clang_createIndex(0, 0));
        ASSERT_NE(index_, nullptr);
        const char* arguments[] = {"-std=c++17", "-x", "c++"};
        unit_.reset(clang_parseTranslationUnit(index_.get(), path_.string().c_str(), arguments, 3,
                                               nullptr, 0,
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

}  // namespace
