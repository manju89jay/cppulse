/**
 * @file test_hello_libclang.cpp
 * @brief Unit tests for the hello_libclang function extraction.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>

#include "hello_libclang.h"

namespace {

/**
 * @brief Resolve the path to a test fixture file.
 *
 * Searches relative to the source tree (tests/fixtures/) and
 * falls back to common Docker/CI build layouts.
 */
std::filesystem::path fixture_path(const std::string& filename) {
    // When running from build/ inside analyzer-core/
    std::filesystem::path from_build = std::filesystem::path(__FILE__).parent_path() / "fixtures" / filename;
    if (std::filesystem::exists(from_build)) {
        return from_build;
    }
    // Fallback: relative to CWD (e.g. running ctest from build/)
    std::filesystem::path from_cwd = std::filesystem::path("../tests/fixtures") / filename;
    if (std::filesystem::exists(from_cwd)) {
        return from_cwd;
    }
    return from_build; // Return the primary path even if not found — test will fail with a clear message
}

} // namespace

TEST(HelloLibclangTest, ExtractsFunctionNames) {
    auto path = fixture_path("sample.cpp");
    ASSERT_TRUE(std::filesystem::exists(path))
        << "Fixture not found: " << path;

    auto result = cppulse::extract_function_names(path.string());

    ASSERT_TRUE(result.has_value()) << "Parse failed unexpectedly";
    const auto& names = *result;
    ASSERT_GE(names.size(), 3u);
    EXPECT_NE(std::find(names.begin(), names.end(), "hello"), names.end());
    EXPECT_NE(std::find(names.begin(), names.end(), "add"), names.end());
    EXPECT_NE(std::find(names.begin(), names.end(), "nested_func"), names.end());
}

TEST(HelloLibclangTest, ReturnsNulloptForNonexistentFile) {
    auto result = cppulse::extract_function_names("/nonexistent/path.cpp");
    EXPECT_FALSE(result.has_value());
}

TEST(HelloLibclangTest, ReturnsEmptyForEmptyFile) {
    auto path = fixture_path("empty.cpp");
    ASSERT_TRUE(std::filesystem::exists(path))
        << "Fixture not found: " << path;

    auto result = cppulse::extract_function_names(path.string());
    ASSERT_TRUE(result.has_value()) << "Parse failed unexpectedly";
    EXPECT_TRUE(result->empty());
}
