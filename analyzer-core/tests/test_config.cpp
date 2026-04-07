/**
 * @file test_config.cpp
 * @brief Unit tests for the .cppulserc.yml/.json config parser.
 */

#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>

#include "config.h"

namespace {

/// @brief Write a temporary file with the given content.
std::filesystem::path write_temp_file(const std::filesystem::path& dir, const std::string& filename,
                                      const std::string& content) {
    auto path = dir / filename;
    std::ofstream ofs(path);
    ofs << content;
    return path;
}

// ---------------------------------------------------------------------------
// YAML parsing tests
// ---------------------------------------------------------------------------

class ConfigYamlTest : public ::testing::Test {
   protected:
    std::filesystem::path tmp_dir_;

    void SetUp() override {
        tmp_dir_ = std::filesystem::temp_directory_path() / "cppulse_config_test";
        std::filesystem::create_directories(tmp_dir_);
    }

    void TearDown() override {
        std::error_code ec;
        std::filesystem::remove_all(tmp_dir_, ec);
    }
};

TEST_F(ConfigYamlTest, ParsesProfile) {
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", "profile: safety-critical\n");
    auto config = cppulse::load_config(path);
    EXPECT_EQ(config.profile, "safety-critical");
}

TEST_F(ConfigYamlTest, DefaultProfile) {
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", "profile: default\n");
    auto config = cppulse::load_config(path);
    EXPECT_EQ(config.profile, "default");
}

TEST_F(ConfigYamlTest, MissingProfileDefaultsToDefault) {
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", "exclude_paths:\n  - vendor/**\n");
    auto config = cppulse::load_config(path);
    EXPECT_EQ(config.profile, "default");
}

TEST_F(ConfigYamlTest, ParsesExcludePaths) {
    const std::string content =
        "exclude_paths:\n"
        "  - vendor/**\n"
        "  - third_party/**\n"
        "  - build/**\n";
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", content);
    auto config = cppulse::load_config(path);
    ASSERT_EQ(config.exclude_paths.size(), 3);
    EXPECT_EQ(config.exclude_paths[0], "vendor/**");
    EXPECT_EQ(config.exclude_paths[1], "third_party/**");
    EXPECT_EQ(config.exclude_paths[2], "build/**");
}

TEST_F(ConfigYamlTest, ParsesRuleDisabled) {
    const std::string content =
        "rules:\n"
        "  CPP-MEM-001:\n"
        "    enabled: false\n";
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", content);
    auto config = cppulse::load_config(path);
    ASSERT_EQ(config.rules.count("CPP-MEM-001"), 1);
    EXPECT_FALSE(config.rules.at("CPP-MEM-001").enabled);
}

TEST_F(ConfigYamlTest, ParsesRuleThresholds) {
    const std::string content =
        "rules:\n"
        "  CPP-CX-001:\n"
        "    warning_threshold: 20\n"
        "    error_threshold: 30\n";
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", content);
    auto config = cppulse::load_config(path);
    ASSERT_EQ(config.rules.count("CPP-CX-001"), 1);
    const auto& rc = config.rules.at("CPP-CX-001");
    EXPECT_TRUE(rc.enabled);
    ASSERT_TRUE(rc.warning_threshold.has_value());
    EXPECT_EQ(rc.warning_threshold.value(), 20);
    ASSERT_TRUE(rc.error_threshold.has_value());
    EXPECT_EQ(rc.error_threshold.value(), 30);
}

TEST_F(ConfigYamlTest, ParsesFullConfig) {
    const std::string content =
        "profile: safety-critical\n"
        "exclude_paths:\n"
        "  - vendor/**\n"
        "  - build/**\n"
        "rules:\n"
        "  CPP-CX-001:\n"
        "    warning_threshold: 20\n"
        "  CPP-MEM-001:\n"
        "    enabled: false\n";
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", content);
    auto config = cppulse::load_config(path);
    EXPECT_EQ(config.profile, "safety-critical");
    EXPECT_EQ(config.exclude_paths.size(), 2);
    EXPECT_EQ(config.rules.size(), 2);
    EXPECT_FALSE(config.rules.at("CPP-MEM-001").enabled);
    EXPECT_EQ(config.rules.at("CPP-CX-001").warning_threshold.value(), 20);
}

TEST_F(ConfigYamlTest, HandlesComments) {
    const std::string content =
        "# This is a comment\n"
        "profile: default  # inline comment\n"
        "exclude_paths:\n"
        "  - vendor/**\n"
        "  # - this_is_commented_out/**\n";
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", content);
    auto config = cppulse::load_config(path);
    EXPECT_EQ(config.profile, "default");
    EXPECT_EQ(config.exclude_paths.size(), 1);
}

TEST_F(ConfigYamlTest, EmptyFileReturnsDefaults) {
    auto path = write_temp_file(tmp_dir_, ".cppulserc.yml", "");
    auto config = cppulse::load_config(path);
    EXPECT_EQ(config.profile, "default");
    EXPECT_TRUE(config.exclude_paths.empty());
    EXPECT_TRUE(config.rules.empty());
}

// ---------------------------------------------------------------------------
// JSON parsing tests
// ---------------------------------------------------------------------------

TEST_F(ConfigYamlTest, ParsesJsonConfig) {
    const std::string content = R"({
        "profile": "safety-critical",
        "exclude_paths": ["vendor/**", "build/**"],
        "rules": {
            "CPP-CX-001": {"warning_threshold": 25},
            "CPP-MEM-001": {"enabled": false}
        }
    })";
    auto path = write_temp_file(tmp_dir_, ".cppulserc.json", content);
    auto config = cppulse::load_config(path);
    EXPECT_EQ(config.profile, "safety-critical");
    ASSERT_EQ(config.exclude_paths.size(), 2);
    EXPECT_EQ(config.rules.size(), 2);
    EXPECT_EQ(config.rules.at("CPP-CX-001").warning_threshold.value(), 25);
    EXPECT_FALSE(config.rules.at("CPP-MEM-001").enabled);
}

// ---------------------------------------------------------------------------
// find_config tests
// ---------------------------------------------------------------------------

TEST_F(ConfigYamlTest, FindConfigDiscoversYml) {
    write_temp_file(tmp_dir_, ".cppulserc.yml", "profile: default\n");
    auto found = cppulse::find_config(tmp_dir_);
    ASSERT_TRUE(found.has_value());
    EXPECT_EQ(found->filename().string(), ".cppulserc.yml");
}

TEST_F(ConfigYamlTest, FindConfigDiscoversJson) {
    write_temp_file(tmp_dir_, ".cppulserc.json", "{}");
    auto found = cppulse::find_config(tmp_dir_);
    ASSERT_TRUE(found.has_value());
    EXPECT_EQ(found->filename().string(), ".cppulserc.json");
}

TEST_F(ConfigYamlTest, FindConfigReturnsNulloptWhenMissing) {
    auto found = cppulse::find_config(tmp_dir_);
    EXPECT_FALSE(found.has_value());
}

TEST_F(ConfigYamlTest, FindConfigPrefersYmlOverJson) {
    write_temp_file(tmp_dir_, ".cppulserc.yml", "profile: safety-critical\n");
    write_temp_file(tmp_dir_, ".cppulserc.json", "{\"profile\": \"default\"}");
    auto found = cppulse::find_config(tmp_dir_);
    ASSERT_TRUE(found.has_value());
    EXPECT_EQ(found->filename().string(), ".cppulserc.yml");
}

// ---------------------------------------------------------------------------
// Glob matching tests
// ---------------------------------------------------------------------------

TEST(ExcludePatternTest, DoubleStarMatchesDeep) {
    EXPECT_TRUE(cppulse::matches_exclude_pattern("vendor/foo/bar.cpp", {"vendor/**"}));
}

TEST(ExcludePatternTest, DoubleStarMatchesShallow) {
    EXPECT_TRUE(cppulse::matches_exclude_pattern("vendor/bar.cpp", {"vendor/**"}));
}

TEST(ExcludePatternTest, SingleStarDoesNotMatchSlash) {
    EXPECT_FALSE(cppulse::matches_exclude_pattern("vendor/deep/file.cpp", {"vendor/*.cpp"}));
}

TEST(ExcludePatternTest, SingleStarMatchesFileInDir) {
    EXPECT_TRUE(cppulse::matches_exclude_pattern("vendor/file.cpp", {"vendor/*.cpp"}));
}

TEST(ExcludePatternTest, NoMatchReturnsFalse) {
    EXPECT_FALSE(cppulse::matches_exclude_pattern("src/main.cpp", {"vendor/**"}));
}

TEST(ExcludePatternTest, EmptyPatternsReturnsFalse) {
    EXPECT_FALSE(cppulse::matches_exclude_pattern("src/main.cpp", {}));
}

TEST(ExcludePatternTest, MultiplePatterns) {
    std::vector<std::string> patterns = {"vendor/**", "build/**"};
    EXPECT_TRUE(cppulse::matches_exclude_pattern("vendor/lib.cpp", patterns));
    EXPECT_TRUE(cppulse::matches_exclude_pattern("build/output.cpp", patterns));
    EXPECT_FALSE(cppulse::matches_exclude_pattern("src/main.cpp", patterns));
}

}  // namespace
