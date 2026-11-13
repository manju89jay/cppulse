/** @file test_coverage.cpp
 * @brief Regression tests for incomplete analysis and build-directory flags.
 */
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>

#include "analyzer.h"
#include "output_writer.h"

namespace {

/** @brief An isolated source tree. */
class CoverageFixture : public ::testing::Test {
   protected:
    void SetUp() override {
        root_ = std::filesystem::temp_directory_path() / "cppulse_coverage_test";
        std::filesystem::create_directories(root_);
    }
    void TearDown() override {
        std::error_code ec;
        std::filesystem::remove_all(root_, ec);
    }
    void write(const std::filesystem::path& name, const std::string& content) const {
        std::filesystem::create_directories((root_ / name).parent_path());
        std::ofstream stream(root_ / name);
        stream << content;
    }
    std::filesystem::path root_;
};

TEST_F(CoverageFixture, MissingIncludeIsPartialAndStillProducesFindings) {
    write("sample.cpp", "#include \"missing_dependency.hpp\"\ntypedef int Count;\n");
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), 1u);
    const auto& file = analyzer.coverage().files.front();
    EXPECT_EQ(file.status, "partial");
    EXPECT_GE(file.error_count, 1);
    EXPECT_EQ(file.compile_context, "fallback");
    EXPECT_FALSE(analyzer.findings().empty());
}

TEST_F(CoverageFixture, RecordsSkippedAndExcludedFiles) {
    write("large.cpp", std::string(501 * 1024, ' '));
    write("excluded.cpp", "void skipped() {}\n");
    cppulse::ProjectConfig config;
    config.exclude_paths = {"excluded.cpp"};
    config.rules["CPP-MOD-001"].enabled = false;
    cppulse::FileAnalyzer analyzer{root_, config};
    analyzer.run();
    int skipped = 0;
    int excluded = 0;
    for (const auto& file : analyzer.coverage().files) {
        skipped += file.status == "skipped" ? 1 : 0;
        excluded += file.status == "excluded" ? 1 : 0;
    }
    EXPECT_EQ(skipped, 1);
    EXPECT_EQ(excluded, 1);
    for (const auto& rule : analyzer.coverage().enabled_rules) {
        EXPECT_NE(rule, "CPP-MOD-001");
    }
}

TEST_F(CoverageFixture, ExternalDatabaseResolvesRelativeIncludes) {
    write("sample.cpp", "#include \"dependency.hpp\"\nvoid valid() {}\n");
    write("config/include/dependency.hpp", "#pragma once\n");
    const auto build_dir = root_ / "config";
    const nlohmann::json database =
        nlohmann::json::array({{{"directory", build_dir.generic_string()},
                                {"file", (root_ / "sample.cpp").generic_string()},
                                {"arguments",
                                 {"clang++", "-std=c++17", "-Iinclude", "-c",
                                  (root_ / "sample.cpp").generic_string()}}}});
    write("config/compile_commands.json", database.dump());
    cppulse::FileAnalyzer analyzer{root_, std::nullopt, build_dir};
    analyzer.run();
    ASSERT_GE(analyzer.coverage().files.size(), 1u);
    for (const auto& file : analyzer.coverage().files) {
        EXPECT_EQ(file.status, "analyzed") << file.path;
        EXPECT_EQ(file.compile_context, "database");
        EXPECT_EQ(file.error_count, 0);
    }
    ASSERT_TRUE(cppulse::write_findings_json(analyzer.findings(), root_.generic_string(),
                                             analyzer.file_count(), analyzer.total_loc(),
                                             root_ / "out", &analyzer.coverage()));
    std::ifstream stream(root_ / "out/findings.json");
    nlohmann::json output;
    stream >> output;
    EXPECT_EQ(output["metadata"]["analysis"]["files"].size(), analyzer.coverage().files.size());
    EXPECT_FALSE(output["metadata"]["analysis"]["enabled_rules"].empty());
}

}  // namespace
