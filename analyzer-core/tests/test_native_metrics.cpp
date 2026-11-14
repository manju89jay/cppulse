/** @file test_native_metrics.cpp
 * @brief Executed-source regressions for the versioned native metric producer.
 */
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>

#include "analyzer.h"
#include "config.h"
#include "output_writer.h"

namespace {

/** @brief Own source inputs and the serialized report for one real analyzer run. */
class NativeMetricsFixture : public ::testing::Test {
   protected:
    void SetUp() override {
        const auto* info = ::testing::UnitTest::GetInstance()->current_test_info();
        base_ = std::filesystem::temp_directory_path() /
                (std::string{"cppulse_metrics_"} + info->name());
        std::filesystem::remove_all(base_);
        root_ = base_ / "repo";
        std::filesystem::create_directories(root_);
    }

    void TearDown() override {
        std::error_code ec;
        std::filesystem::remove_all(base_, ec);
    }

    void write(const std::filesystem::path& path, const std::string& source) const {
        std::filesystem::create_directories(path.parent_path());
        std::ofstream stream(path, std::ios::binary);
        stream << source;
    }

    nlohmann::json analyze(std::optional<cppulse::ProjectConfig> config = std::nullopt) const {
        cppulse::FileAnalyzer analyzer{root_, std::move(config)};
        analyzer.run();
        EXPECT_TRUE(cppulse::write_findings_json(analyzer.findings(), root_.generic_string(),
                                                 analyzer.file_count(), analyzer.total_loc(),
                                                 base_ / "output", &analyzer.coverage()));
        std::ifstream stream(base_ / "output" / "findings.json");
        return nlohmann::json::parse(stream);
    }

    nlohmann::json metric_file(const nlohmann::json& report,
                               const std::string& name = "source.cpp") const {
        const auto& raw = report.at("metadata").at("analysis").at("native_metrics");
        EXPECT_EQ(raw.at("version"), "1.0.0");
        EXPECT_EQ(raw.at("metric_version"), "cppulse-metrics-1");
        for (const auto& file : raw.at("files")) {
            if (std::filesystem::path{file.at("path").get<std::string>()}.filename() == name) {
                return file;
            }
        }
        ADD_FAILURE() << "Missing measured file " << name;
        return nullptr;
    }

    nlohmann::json function(const nlohmann::json& file, const std::string& name) const {
        for (const auto& item : file.at("functions")) {
            if (item.at("name") == name || (name == "lambda" && item.at("kind") == "lambda")) {
                return item;
            }
        }
        ADD_FAILURE() << "Missing measured callable " << name;
        return nullptr;
    }

    void measured(const nlohmann::json& item, int length, int complexity, int nesting,
                  int parameters) const {
        EXPECT_EQ(item.at("availability"), "measured");
        EXPECT_EQ(item.at("function_length"), length);
        EXPECT_EQ(item.at("cyclomatic_complexity"), complexity);
        EXPECT_EQ(item.at("nesting_depth"), nesting);
        EXPECT_EQ(item.at("parameter_count"), parameters);
        EXPECT_LE(item.at("line").get<int>(), item.at("end_line").get<int>());
        EXPECT_GE(item.at("column").get<int>(), 1);
        EXPECT_GE(item.at("end_column").get<int>(), 1);
    }

    std::filesystem::path base_;
    std::filesystem::path root_;
};

TEST_F(NativeMetricsFixture, MeasuresOrdinaryFunctionWithoutThresholdFinding) {
    write(root_ / "source.cpp",
          "int choose(bool first, bool second) {\n"
          "    if (first && second) return 1;\n"
          "    return 0;\n"
          "}\n");
    const auto report = analyze();
    const auto file = metric_file(report);
    EXPECT_EQ(file.at("physical_loc"), 4);
    EXPECT_EQ(file.at("code_loc"), 4);
    EXPECT_EQ(file.at("function_count"), 1);
    EXPECT_TRUE(file.at("measurement_complete"));
    measured(function(file, "choose"), 4, 3, 1, 2);
    for (const auto& finding : report.at("findings")) {
        EXPECT_NE(finding.at("rule_id"), "CPP-CX-001");
    }
}

TEST_F(NativeMetricsFixture, MeasuresUninstantiatedTemplateWithPrefixAndOrdinaryParameters) {
    write(root_ / "source.cpp",
          "template <typename Value>\n"
          "Value choose(Value first, Value second, Value third) {\n"
          "    if (first && second && third) return first;\n"
          "    return second;\n"
          "}\n");
    const auto file = metric_file(analyze());
    EXPECT_EQ(file.at("physical_loc"), 5);
    EXPECT_EQ(file.at("code_loc"), 5);
    EXPECT_EQ(file.at("function_count"), 1);
    measured(function(file, "choose"), 5, 4, 1, 3);
}

TEST_F(NativeMetricsFixture, CountsExpandedSemanticLogicalDecisionsOnce) {
    write(root_ / "source.cpp",
          "#define BOTH(first, second) ((first) && (second))\n"
          "bool choose(bool first, bool second, bool third) {\n"
          "    if (BOTH(first, second) && third) return true;\n"
          "    return false;\n"
          "}\n");
    const auto file = metric_file(analyze());
    EXPECT_EQ(file.at("physical_loc"), 5);
    EXPECT_EQ(file.at("code_loc"), 5);
    measured(function(file, "choose"), 4, 4, 1, 3);
}

TEST_F(NativeMetricsFixture, SeparatesNestedLambdaBodyFromItsEnclosingFunction) {
    write(root_ / "source.cpp",
          "int outer(bool first) {\n"
          "    auto callback = [](bool left, bool right) { if (left && right) return 1; return 0; "
          "};\n"
          "    if (first) return 1;\n"
          "    return callback(first, false);\n"
          "}\n");
    const auto file = metric_file(analyze());
    EXPECT_EQ(file.at("function_count"), 2);
    measured(function(file, "outer"), 5, 2, 1, 1);
    measured(function(file, "lambda"), 1, 3, 1, 2);
    EXPECT_NE(function(file, "outer").at("symbol"), function(file, "lambda").at("symbol"));
}

TEST_F(NativeMetricsFixture, AttributesLambdaCaptureInitializerToEnclosingFunction) {
    write(root_ / "source.cpp",
          "int outer(bool first, bool second) {\n"
          "    auto callback = [selected = first && second]() { return selected ? 1 : 0; };\n"
          "    return callback();\n"
          "}\n");
    const auto file = metric_file(analyze());
    measured(function(file, "outer"), 4, 2, 0, 2);
    measured(function(file, "lambda"), 1, 2, 1, 0);
}

TEST_F(NativeMetricsFixture, DistinguishesCommentsBlanksAndPhysicalFunctionExtent) {
    write(root_ / "source.cpp",
          "// comment\nint value() {\n/* block\ncomment */\n    return 1;\n}\n");
    const auto file = metric_file(analyze());
    EXPECT_EQ(file.at("physical_loc"), 6);
    EXPECT_EQ(file.at("code_loc"), 3);
    measured(function(file, "value"), 5, 1, 0, 0);
    for (const auto& token : file.at("token_stream").at("records")) {
        EXPECT_NE(token.at("spelling"), "comment");
    }
}

TEST_F(NativeMetricsFixture, EmptySourceHasMeasuredZeroScopeAndNoFunctions) {
    write(root_ / "source.cpp", "");
    const auto file = metric_file(analyze());
    EXPECT_TRUE(file.at("measurement_complete"));
    EXPECT_EQ(file.at("physical_loc"), 0);
    EXPECT_EQ(file.at("code_loc"), 0);
    EXPECT_EQ(file.at("function_count"), 0);
    EXPECT_TRUE(file.at("functions").empty());
    const auto& tokens = file.at("token_stream");
    EXPECT_TRUE(tokens.at("complete"));
    EXPECT_EQ(tokens.at("total_tokens"), 0);
    EXPECT_EQ(tokens.at("retained_tokens"), 0);
}

TEST_F(NativeMetricsFixture, PartialAstRetainsObservedFactsWithoutCompleteFunctionCount) {
    write(root_ / "source.cpp", "#include \"missing.hpp\"\nint value() { return 1; }\n");
    const auto report = analyze();
    const auto file = metric_file(report);
    EXPECT_EQ(file.at("status"), "partial");
    EXPECT_GT(file.at("error_count").get<int>(), 0);
    EXPECT_FALSE(file.at("measurement_complete"));
    EXPECT_EQ(file.at("physical_loc"), 2);
    EXPECT_EQ(file.at("code_loc"), 2);
    EXPECT_TRUE(file.at("function_count").is_null());
    const auto item = function(file, "value");
    EXPECT_EQ(item.at("availability"), "partial");
    EXPECT_FALSE(item.at("limitations").empty());
    EXPECT_FALSE(file.at("limitations").empty());
}

TEST_F(NativeMetricsFixture, LargeHeaderIsMeasuredUnderConfiguredByteBudget) {
    write(root_ / "large.hpp",
          "/*" + std::string(600000, 'x') + "*/\ninline int value() { return 1; }\n");
    const auto file = metric_file(analyze(), "large.hpp");
    EXPECT_EQ(file.at("status"), "analyzed");
    EXPECT_EQ(file.at("physical_loc"), 2);
    EXPECT_EQ(file.at("code_loc"), 1);
    measured(function(file, "value"), 1, 1, 0, 0);
}

TEST_F(NativeMetricsFixture, InactiveDefinitionsRemainInLexicalLocButNotFunctionInventory) {
    write(root_ / "source.cpp",
          "#if 0\nint inactive() { return 1; }\n#endif\nint active() { return 1; }\n");
    const auto file = metric_file(analyze());
    EXPECT_EQ(file.at("physical_loc"), 4);
    EXPECT_EQ(file.at("code_loc"), 4);
    EXPECT_EQ(file.at("function_count"), 1);
    measured(function(file, "active"), 1, 1, 0, 0);
    bool inactive_token = false;
    for (const auto& token : file.at("token_stream").at("records")) {
        inactive_token = inactive_token || token.at("spelling") == "inactive";
    }
    EXPECT_TRUE(inactive_token);
}

TEST_F(NativeMetricsFixture, MultilineLiteralCountsAllSpelledLinesAndNoTerminalPhantomLine) {
    write(root_ / "source.cpp", "const char* text = R\"tag(first\nsecond\nthird)tag\";");
    const auto file = metric_file(analyze());
    EXPECT_EQ(file.at("physical_loc"), 3);
    EXPECT_EQ(file.at("code_loc"), 3);
    bool multiline_literal = false;
    for (const auto& token : file.at("token_stream").at("records")) {
        if (token.at("kind") == "literal") {
            multiline_literal = token.at("line") == 1 && token.at("end_line") == 3;
        }
    }
    EXPECT_TRUE(multiline_literal);
}

TEST_F(NativeMetricsFixture, NestingCountsControlDepthAndParameterPackAsOneDeclaration) {
    write(root_ / "source.cpp",
          "template <typename... Values>\n"
          "int nested(bool ready, Values... values) {\n"
          "    if (ready) { while (ready) { if (sizeof...(values)) return 1; } }\n"
          "    else if (sizeof...(values)) return 2;\n"
          "    return 0;\n"
          "}\n");
    const auto file = metric_file(analyze());
    measured(function(file, "nested"), 6, 5, 3, 2);
}

TEST_F(NativeMetricsFixture, OverloadsHaveDistinctStableUsrIdentitiesAcrossRuns) {
    write(root_ / "source.cpp",
          "int value(int item) { return item; }\n"
          "double value(double item) { return item; }\n");
    const auto first = metric_file(analyze());
    const auto second = metric_file(analyze());
    ASSERT_EQ(first.at("functions").size(), 2u);
    EXPECT_EQ(first.at("functions"), second.at("functions"));
    EXPECT_EQ(first.at("functions").at(0).at("identity_kind"), "usr");
    EXPECT_EQ(first.at("functions").at(1).at("identity_kind"), "usr");
    EXPECT_NE(first.at("functions").at(0).at("symbol"), first.at("functions").at(1).at("symbol"));
}

TEST_F(NativeMetricsFixture, SourceFingerprintMatchesObservedBytesAndChangesWithSource) {
    write(root_ / "source.cpp", "int value() { return 1; }\n");
    const auto first = metric_file(analyze());
    EXPECT_EQ(first.at("source_content_sha256"),
              "867a282ce5d75112761991e6f7186a4e9e4155ef0e4cfe94419fc9f2ef34064c");
    write(root_ / "source.cpp", "int value() { return 2; }\n");
    const auto second = metric_file(analyze());
    EXPECT_EQ(second.at("source_content_sha256"),
              "9c8463bd4c22a2dd0f54722d64eab6106aaf055e5d1c40b66381f6d78bf6b65d");
}

TEST_F(NativeMetricsFixture, SkippedAndExcludedFilesHaveUnavailableMeasurements) {
    write(root_ / "source.cpp", "int value() { return 1; }\n");
    write(root_ / "excluded.hpp", "int hidden();\n");
    cppulse::ProjectConfig config;
    config.max_file_bytes = 1;
    config.exclude_paths = {"excluded.hpp"};
    const auto report = analyze(config);
    const auto skipped = metric_file(report);
    const auto excluded = metric_file(report, "excluded.hpp");
    EXPECT_EQ(skipped.at("status"), "skipped");
    EXPECT_EQ(excluded.at("status"), "excluded");
    for (const auto& file : {skipped, excluded}) {
        EXPECT_FALSE(file.at("measurement_complete"));
        EXPECT_TRUE(file.at("physical_loc").is_null());
        EXPECT_TRUE(file.at("code_loc").is_null());
        EXPECT_TRUE(file.at("function_count").is_null());
        EXPECT_TRUE(file.at("functions").empty());
        EXPECT_FALSE(file.at("limitations").empty());
        EXPECT_EQ(file.at("token_stream").at("availability"), "unavailable");
        EXPECT_TRUE(file.at("token_stream").at("total_tokens").is_null());
    }
}

TEST_F(NativeMetricsFixture, ConfiguredTokenBoundRetainsObservedTotalsAndVisibleTruncation) {
    write(root_ / "source.cpp", "int value() { return 1; }\n");
    const auto config_path = base_ / "config.json";
    write(config_path, "{\"max_token_records\": 3}");
    const auto report = analyze(cppulse::load_config(config_path));
    const auto file = metric_file(report);
    const auto& raw = report.at("metadata").at("analysis").at("native_metrics");
    const auto& tokens = file.at("token_stream");
    EXPECT_EQ(raw.at("max_token_records"), 3);
    EXPECT_EQ(tokens.at("record_limit"), 3);
    EXPECT_EQ(tokens.at("retained_tokens"), 3);
    EXPECT_EQ(tokens.at("records").size(), 3u);
    EXPECT_GT(tokens.at("total_tokens").get<int>(), 3);
    EXPECT_FALSE(tokens.at("complete"));
    EXPECT_EQ(tokens.at("availability"), "partial");
    EXPECT_FALSE(tokens.at("limitations").empty());
    EXPECT_TRUE(file.at("measurement_complete"));
    measured(function(file, "value"), 1, 1, 0, 0);
}

TEST_F(NativeMetricsFixture, TokenRecordConfigurationRejectsInvalidBoundsAndTypes) {
    const auto config_path = base_ / "config.json";
    for (const auto* value : {"0", "-1", "true", "1.5", "\"3\"", "9223372036854775808"}) {
        SCOPED_TRACE(value);
        write(config_path, std::string{"{\"max_token_records\":"} + value + "}");
        EXPECT_THROW(static_cast<void>(cppulse::load_config(config_path)), std::runtime_error);
    }
}

TEST_F(NativeMetricsFixture, TokenRecordConfigurationAcceptsBothInclusiveBounds) {
    const auto config_path = base_ / "config.json";
    for (const auto* value : {"1", "9223372036854775807"}) {
        SCOPED_TRACE(value);
        write(config_path, std::string{"{\"max_token_records\":"} + value + "}");
        EXPECT_NO_THROW(static_cast<void>(cppulse::load_config(config_path)));
    }
}

TEST_F(NativeMetricsFixture, DefaultTokenRecordBudgetIsExplicitInEveryStream) {
    write(root_ / "source.cpp", "int value() { return 1; }\n");
    const auto report = analyze();
    const auto file = metric_file(report);
    const auto& raw = report.at("metadata").at("analysis").at("native_metrics");
    EXPECT_EQ(raw.at("max_token_records"), 100000);
    EXPECT_EQ(file.at("token_stream").at("record_limit"), 100000);
}

TEST_F(NativeMetricsFixture, IncludeEdgesIdentifyProjectAndExternalTargets) {
    write(root_ / "detail.hpp", "#pragma once\ninline int detail() { return 1; }\n");
    write(base_ / "external.hpp", "#pragma once\n");
    write(root_ / "source.cpp", "#include \"detail.hpp\"\n#include \"" +
                                    (base_ / "external.hpp").generic_string() +
                                    "\"\nint value() { return detail(); }\n");
    const auto file = metric_file(analyze());
    bool project_edge = false;
    bool external_edge = false;
    for (const auto& edge : file.at("includes")) {
        if (edge.at("target_kind") == "project" && edge.at("target") == "detail.hpp") {
            EXPECT_TRUE(edge.at("direct"));
            EXPECT_EQ(edge.at("source"), "source.cpp");
            project_edge = true;
        }
        if (edge.at("target_kind") == "external") {
            EXPECT_TRUE(edge.at("direct"));
            EXPECT_EQ(edge.at("target"), (base_ / "external.hpp").generic_string());
            external_edge = true;
        }
    }
    EXPECT_TRUE(project_edge);
    EXPECT_TRUE(external_edge);
    EXPECT_EQ(file.at("function_count"), 1);
}

}  // namespace
