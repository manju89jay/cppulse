/** @file test_config_limits.cpp
 * @brief Regression cases for configurable native analysis file limits.
 */
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <string>

#include "analyzer.h"
#include "config.h"
#include "output_writer.h"
#include "test_temp_directory.h"

namespace {

/** @brief Own an independent source tree for each large-header case. */
class NativeConfigLimitsTest : public ::testing::Test {
   protected:
    void SetUp() override {
        base_ = cppulse::test::make_test_directory("cppulse_limits");
        root_ = base_ / "repo";
        std::filesystem::create_directories(root_);
    }
    void TearDown() override {
        std::error_code error;
        std::filesystem::remove_all(base_, error);
    }
    void write(const std::filesystem::path& path, const std::string& text) const {
        std::ofstream stream(path, std::ios::binary);
        stream << text;
    }
    cppulse::ProjectConfig settings(const std::string& text) const {
        const auto path = base_ / ".cppulserc.json";
        write(path, text);
        return cppulse::load_config(path);
    }
    std::filesystem::path base_;
    std::filesystem::path root_;
};

TEST_F(NativeConfigLimitsTest, AnalyzesOrdinaryHeaderAboveHistorical500KiBLimit) {
    write(root_ / "amalgamated.hpp", "/*" + std::string(513000, 'x') + "*/\nint value = 1;\n");
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), 1u);
    EXPECT_EQ(analyzer.coverage().files.front().status, "analyzed");
    EXPECT_EQ(analyzer.file_count(), 1);
}

TEST_F(NativeConfigLimitsTest, ConfiguredSmallLimitPreservesIndependentFileAndExplainsSkip) {
    write(root_ / "large.hpp", "/*" + std::string(1024, 'x') + "*/\nint large = 1;\n");
    write(root_ / "clean.hpp", "int small = 1;\n");
    cppulse::FileAnalyzer analyzer{root_, settings("{\"max_file_bytes\":128}")};
    analyzer.run();
    EXPECT_EQ(analyzer.file_count(), 1);
    const auto output = base_ / "output";
    ASSERT_TRUE(cppulse::write_findings_json(analyzer.findings(), root_.generic_string(),
                                             analyzer.file_count(), analyzer.total_loc(), output,
                                             &analyzer.coverage()));
    std::ifstream stream(output / "findings.json");
    nlohmann::json findings;
    stream >> findings;
    bool saw_skipped = false;
    bool saw_analyzed = false;
    for (const auto& file : findings["metadata"]["analysis"]["files"]) {
        if (std::filesystem::path{file["path"].get<std::string>()}.filename() == "large.hpp") {
            EXPECT_EQ(file["status"], "skipped");
            EXPECT_EQ(file["compile_context"], "none");
            ASSERT_TRUE(file.contains("reason"));
            EXPECT_NE(file["reason"].get<std::string>().find("max_file_bytes=128"),
                      std::string::npos);
            saw_skipped = true;
        } else {
            EXPECT_EQ(file["status"], "analyzed");
            saw_analyzed = true;
        }
    }
    EXPECT_TRUE(saw_skipped);
    EXPECT_TRUE(saw_analyzed);
}

TEST_F(NativeConfigLimitsTest, RejectsInvalidFileLimits) {
    for (const auto& content :
         {"{\"max_file_bytes\":0}", "{\"max_file_bytes\":-1}", "{\"max_file_bytes\":true}",
          "{\"max_file_bytes\":\"128\"}", "{\"max_file_bytes\":1.5}"}) {
        EXPECT_THROW(settings(content), std::runtime_error) << content;
    }
}

}  // namespace
