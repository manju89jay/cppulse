/** @file test_parse_trace.cpp
 * @brief Observe parser identity and the exact attempted C API arguments.
 */
#include <clang-c/Index.h>
#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>

#include "analyzer.h"
#include "output_writer.h"

namespace {

/** @brief Isolated inputs and reports for one native parse-trace regression. */
class ParseTraceFixture : public ::testing::Test {
   protected:
    void SetUp() override {
        const auto* info = ::testing::UnitTest::GetInstance()->current_test_info();
        root_ = std::filesystem::temp_directory_path() /
                (std::string{"cppulse_parse_trace_"} + info->name());
        std::filesystem::remove_all(root_);
        std::filesystem::create_directories(root_);
    }
    void TearDown() override {
        std::error_code ec;
        std::filesystem::remove_all(root_, ec);
    }
    void write(const std::filesystem::path& name, const std::string& bytes) const {
        std::filesystem::create_directories((root_ / name).parent_path());
        std::ofstream stream(root_ / name);
        stream << bytes;
    }
    void database(const std::vector<std::string>& arguments) const {
        const nlohmann::json commands =
            nlohmann::json::array({{{"directory", (root_ / "build").generic_string()},
                                    {"file", "../source.cpp"},
                                    {"arguments", arguments}}});
        write("build/compile_commands.json", commands.dump());
    }
    nlohmann::json report(cppulse::FileAnalyzer& analyzer) const {
        analyzer.run();
        EXPECT_TRUE(cppulse::write_findings_json(analyzer.findings(), root_.generic_string(),
                                                 analyzer.file_count(), analyzer.total_loc(),
                                                 root_ / "report", &analyzer.coverage()));
        std::ifstream stream(root_ / "report/findings.json");
        nlohmann::json document;
        stream >> document;
        return document;
    }
    nlohmann::json file(const nlohmann::json& document, const std::string& name) const {
        for (const auto& item : document["metadata"]["analysis"]["files"]) {
            if (item["path"] == (root_ / name).generic_string()) {
                return item;
            }
        }
        return nullptr;
    }
    std::filesystem::path root_;
};

TEST_F(ParseTraceFixture, FallbackRecordsExactArgumentsProcessCwdAndActualParserVersion) {
    write("source.cpp", "int main() { return 0; }\n");
    cppulse::FileAnalyzer analyzer{root_};
    const auto output = report(analyzer);
    const auto item = file(output, "source.cpp");
    ASSERT_TRUE(output["metadata"]["analysis"].contains("parser"));
    const CXString version = clang_getClangVersion();
    const std::string expected_version{clang_getCString(version)};
    clang_disposeString(version);
    EXPECT_EQ(output["metadata"]["analysis"]["parser"]["name"], "libclang");
    EXPECT_EQ(output["metadata"]["analysis"]["parser"]["version"], expected_version);
    ASSERT_TRUE(item.contains("parse_arguments"));
    EXPECT_EQ(item["parse_arguments"], (std::vector<std::string>{"-std=c++17", "-x", "c++"}));
    EXPECT_EQ(item["working_directory"], std::filesystem::current_path().generic_string());
    EXPECT_EQ(item["status"], "analyzed");
    EXPECT_EQ(item["compile_context"], "fallback");
}

TEST_F(ParseTraceFixture, DatabasePreservesOrderedDuplicateFlagsAndRemovesOnlyDriverOperands) {
    write("source.cpp", "#ifndef VALUE\n#error missing flag\n#endif\nint value = VALUE;\n");
    write("forced.inc", "// Explicit forced include operand.\n");
    database({"clang++", "-std=c++20", "-DVALUE=7", "-DVALUE=7", "-include", "../forced.inc", "-c",
              "../source.cpp", "-o", "ignored.o"});
    cppulse::FileAnalyzer analyzer{root_};
    const auto item = file(report(analyzer), "source.cpp");
    ASSERT_TRUE(item.contains("parse_arguments"));
    EXPECT_EQ(item["parse_arguments"],
              (std::vector<std::string>{"-working-directory=" + (root_ / "build").generic_string(),
                                        "--driver-mode=g++", "-std=c++20", "-DVALUE=7", "-DVALUE=7",
                                        "-include", "../forced.inc"}));
    EXPECT_EQ(item["working_directory"], std::filesystem::current_path().generic_string());
    EXPECT_EQ(item["compile_context"], "database");
    EXPECT_EQ(item["status"], "analyzed");
}

TEST_F(ParseTraceFixture, InferredHeaderRetainsItsActualInterpolatedArguments) {
    write("source.cpp", "#include \"detail.hpp\"\nint main() { return 0; }\n");
    write("detail.hpp", "#ifndef SELECTED\n#error missing inferred flag\n#endif\n");
    database({"clang++", "-std=c++20", "-DSELECTED", "-c", "../source.cpp"});
    cppulse::FileAnalyzer analyzer{root_};
    const auto item = file(report(analyzer), "detail.hpp");
    ASSERT_TRUE(item.contains("parse_arguments"));
    ASSERT_TRUE(item["parse_arguments"].is_array());
    const auto arguments = item["parse_arguments"].get<std::vector<std::string>>();
    EXPECT_NE(std::find(arguments.begin(), arguments.end(), "-DSELECTED"), arguments.end());
    EXPECT_NE(std::find(arguments.begin(), arguments.end(), "-std=c++20"), arguments.end());
    EXPECT_EQ(std::find(arguments.begin(), arguments.end(), "--"), arguments.end());
    EXPECT_EQ(item["working_directory"], std::filesystem::current_path().generic_string());
    EXPECT_EQ(item["compile_context"], "inferred");
    EXPECT_EQ(item["status"], "analyzed");
}

TEST_F(ParseTraceFixture, FailedParseRetainsTheArgumentsActuallyAttempted) {
    write("source.cpp", "int main() { return 0; }\n");
    database({"clang++", "-x", "cppulse-invalid-language", "-c", "../source.cpp"});
    cppulse::FileAnalyzer analyzer{root_};
    const auto item = file(report(analyzer), "source.cpp");
    ASSERT_TRUE(item.contains("parse_arguments"));
    EXPECT_EQ(item["parse_arguments"],
              (std::vector<std::string>{"-working-directory=" + (root_ / "build").generic_string(),
                                        "--driver-mode=g++", "-x", "cppulse-invalid-language"}));
    EXPECT_EQ(item["working_directory"], std::filesystem::current_path().generic_string());
    EXPECT_EQ(item["status"], "failed");
}

TEST_F(ParseTraceFixture, PartialParseStillRecordsItsAttemptedContext) {
    write("source.cpp", "#include \"missing.hpp\"\ntypedef int Count;\n");
    cppulse::FileAnalyzer analyzer{root_};
    const auto item = file(report(analyzer), "source.cpp");
    ASSERT_TRUE(item.contains("parse_arguments"));
    EXPECT_EQ(item["parse_arguments"], (std::vector<std::string>{"-std=c++17", "-x", "c++"}));
    EXPECT_EQ(item["status"], "partial");
    EXPECT_GT(item["error_count"].get<int>(), 0);
}

TEST_F(ParseTraceFixture, SkippedAndExcludedFilesDoNotInventParseAttempts) {
    write("large.cpp", std::string(501 * 1024, ' '));
    write("excluded.cpp", "int excluded() { return 0; }\n");
    cppulse::ProjectConfig config;
    config.max_file_bytes = 500ULL * 1024ULL;
    config.exclude_paths = {"excluded.cpp"};
    cppulse::FileAnalyzer analyzer{root_, config};
    const auto output = report(analyzer);
    for (const auto* name : {"large.cpp", "excluded.cpp"}) {
        const auto item = file(output, name);
        ASSERT_TRUE(item.contains("parse_arguments"));
        ASSERT_TRUE(item.contains("working_directory"));
        EXPECT_TRUE(item["parse_arguments"].is_null());
        EXPECT_TRUE(item["working_directory"].is_null());
        EXPECT_EQ(item["compile_context"], "none");
    }
}

TEST_F(ParseTraceFixture, ResourceOverrideAndWorkingDirectoryOverrideRemainInExactOrder) {
    write("source.cpp", "int main() { return 0; }\n");
    write("resource/include/stddef.h", "// Fixture resource file.\n");
    const auto override = "-working-directory=" + root_.generic_string();
    database({"clang++", "-std=c++17", override, "-c", "../source.cpp"});
    cppulse::FileAnalyzer analyzer{root_, std::nullopt, root_ / "build", root_ / "resource"};
    const auto item = file(report(analyzer), "source.cpp");
    ASSERT_TRUE(item.contains("parse_arguments"));
    EXPECT_EQ(item["parse_arguments"],
              (std::vector<std::string>{"-working-directory=" + (root_ / "build").generic_string(),
                                        "--driver-mode=g++", "-std=c++17", override,
                                        "-resource-dir=" + (root_ / "resource").generic_string()}));
    EXPECT_EQ(item["working_directory"], std::filesystem::current_path().generic_string());
}

}  // namespace
