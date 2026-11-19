/** @file test_work_unit_selection.cpp
 * @brief Native finite-selection acceptance and source-root boundary tests.
 */
#include <gtest/gtest.h>

#include "test_temp_directory.h"

#include <filesystem>
#include <fstream>
#include <string>

#include "analyzer.h"
#include "native_execution_limits.h"

namespace {
class WorkUnitSelectionTest : public ::testing::Test {
   protected:
    void SetUp() override {
        base_ = cppulse::test::make_test_directory("cppulse_unit");
        root_ = base_ / "repo";
        std::filesystem::create_directories(root_ / "a");
        std::filesystem::create_directories(root_ / "b");
        write(root_ / "a" / "same.cpp", "int a() { return 1; }\n");
        write(root_ / "b" / "same.cpp", "int b() { return 2; }\n");
    }
    void TearDown() override {
        std::error_code error;
        std::filesystem::remove_all(base_, error);
    }
    void write(const std::filesystem::path& file, const std::string& text) const {
        std::ofstream stream(file, std::ios::binary);
        stream << text;
    }
    std::filesystem::path base_;
    std::filesystem::path root_;
};

TEST_F(WorkUnitSelectionTest, SelectsExactlyOneOfEqualBasenames) {
    const auto list = base_ / "selection.json";
    write(list, "[\"b/same.cpp\"]");
    const auto selection = cppulse::read_selected_files(root_, list);
    cppulse::FileAnalyzer analyzer{root_, std::nullopt, std::nullopt, std::nullopt, selection};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), 1u);
    EXPECT_EQ(std::filesystem::path{analyzer.coverage().files.front().path}, root_ / "b/same.cpp");
    EXPECT_EQ(analyzer.file_count(), 1);
}

TEST_F(WorkUnitSelectionTest, RejectsMalformedEscapingDuplicateAndMissingSelections) {
    const auto list = base_ / "selection.json";
    for (const auto* text : {"[]", "{}", "[1]", "[\"../escape.cpp\"]", "[\"/a.cpp\"]",
                             "[\"a/./same.cpp\"]", "[\"a//same.cpp\"]", "[\"missing.cpp\"]",
                             "[\"a/same.cpp\",\"a/same.cpp\"]", "[\"a\"]", "[\"x.txt\"]"}) {
        write(list, text);
        EXPECT_THROW(cppulse::read_selected_files(root_, list), std::runtime_error) << text;
    }
}

TEST_F(WorkUnitSelectionTest, RejectsSymlinkFileAndDirectoryComponents) {
    std::error_code error;
    std::filesystem::create_symlink(root_ / "a/same.cpp", root_ / "linked.cpp", error);
    if (error)
        GTEST_SKIP() << error.message();
    std::filesystem::create_directory_symlink(root_ / "a", root_ / "linked", error);
    ASSERT_FALSE(error);
    const auto list = base_ / "selection.json";
    for (const auto* text : {"[\"linked.cpp\"]", "[\"linked/same.cpp\"]"}) {
        write(list, text);
        EXPECT_THROW(cppulse::read_selected_files(root_, list), std::runtime_error);
    }
}

TEST_F(WorkUnitSelectionTest, DefaultDiscoveryStillAnalyzesBothFiles) {
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    EXPECT_EQ(analyzer.file_count(), 2);
}

TEST_F(WorkUnitSelectionTest, RejectsUnusablyLowAddressSpaceBeforeParsing) {
    cppulse::NativeExecutionLimits limits;
    limits.address_space_bytes = 1;
    EXPECT_THROW(cppulse::apply_native_execution_limits(limits), std::runtime_error);
}
}  // namespace
