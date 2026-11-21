/** @file test_native_scope.cpp
 * @brief Native source-scope and compilation-context regression cases.
 */
#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <string>

#include "analyzer.h"
#include "file_discovery.h"
#include "native_execution_limits.h"
#include "test_temp_directory.h"

namespace {

/** @brief Own a source tree and external sibling for each regression. */
class NativeScopeFixture : public ::testing::Test {
   protected:
    void SetUp() override {
        base_ = cppulse::test::make_test_directory("cppulse_scope");
        root_ = base_ / "repo";
        std::filesystem::create_directories(root_);
    }
    void TearDown() override {
        std::error_code ec;
        std::filesystem::remove_all(base_, ec);
    }
    void write(const std::filesystem::path& path, const std::string& source) const {
        std::filesystem::create_directories(path.parent_path());
        std::ofstream stream(path);
        stream << source;
    }
    void database(const std::filesystem::path& directory, const std::string& source,
                  const std::vector<std::string>& args) const {
        const nlohmann::json entries = nlohmann::json::array(
            {{{"directory", directory.generic_string()}, {"file", source}, {"arguments", args}}});
        write(directory / "compile_commands.json", entries.dump());
    }
    const cppulse::FileCoverage* coverage_for(const cppulse::FileAnalyzer& analyzer,
                                              const std::filesystem::path& file) const {
        for (const auto& outcome : analyzer.coverage().files) {
            if (std::filesystem::path{outcome.path} == file) {
                return &outcome;
            }
        }
        return nullptr;
    }
    std::filesystem::path base_;
    std::filesystem::path root_;
};

TEST_F(NativeScopeFixture, AcceptsCompilationDatabaseFile) {
    write(root_ / "source.cpp",
          "#ifndef RECORDED\n#error missing flags\n#endif\nvoid valid() {}\n");
    const auto build = root_ / "build";
    database(build, "../source.cpp",
             {"clang++", "-DRECORDED", "-std=c++17", "-c", "../source.cpp"});
    cppulse::FileAnalyzer analyzer{root_, std::nullopt, build / "compile_commands.json"};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), 1u);
    EXPECT_EQ(analyzer.coverage().files.front().status, "analyzed");
    EXPECT_EQ(analyzer.coverage().files.front().compile_context, "database");
}

TEST_F(NativeScopeFixture, DistinguishesInferredHeaderContext) {
    write(root_ / "source.cpp", "#include \"detail.hpp\"\nvoid valid() {}\n");
    write(root_ / "detail.hpp", "#pragma once\n");
    database(root_, "source.cpp", {"clang++", "-std=c++17", "-c", "source.cpp"});
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    const auto* source = coverage_for(analyzer, root_ / "source.cpp");
    const auto* header = coverage_for(analyzer, root_ / "detail.hpp");
    ASSERT_NE(source, nullptr);
    ASSERT_NE(header, nullptr);
    EXPECT_EQ(source->compile_context, "database");
    EXPECT_EQ(header->compile_context, "inferred");
}

TEST_F(NativeScopeFixture, IncludedHeaderFindingsBelongToHeaderOnce) {
    write(root_ / "source.cpp", "#include \"detail.hpp\"\nvoid valid() {}\n");
    write(root_ / "detail.hpp", "#pragma once\ntypedef int Counter;\n");
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    int typedef_count = 0;
    for (const auto& finding : analyzer.findings()) {
        if (finding.rule_id == "CPP-MOD-009") {
            ++typedef_count;
            EXPECT_EQ(finding.file, "detail.hpp");
        }
    }
    EXPECT_EQ(typedef_count, 1);
}

TEST_F(NativeScopeFixture, ExternalIncludeIsNotAttributedToMainFile) {
    const auto external = base_ / "external.hpp";
    write(external, "typedef int ExternalCount;\n");
    write(root_ / "source.cpp",
          "#include \"" + external.generic_string() + "\"\nvoid valid() {}\n");
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    for (const auto& finding : analyzer.findings()) {
        EXPECT_NE(finding.rule_id, "CPP-MOD-009");
    }
}

TEST_F(NativeScopeFixture, DiscoversHeaderImplementationExtensions) {
    for (const auto* extension : {".hh", ".ipp", ".inl", ".tpp"}) {
        write(root_ / (std::string{"detail"} + extension), "// C++ header input\n");
    }
    EXPECT_EQ(cppulse::discover_cpp_files(root_).size(), 4u);
}

TEST_F(NativeScopeFixture, DiscoversAndSelectsOriginalCPlusPlusExtensions) {
    write(root_ / "array.c++", "int array_value;\n");
    write(root_ / "array-test.C++", "int test_value;\n");
    write(root_ / "consumer.cpp", "int consumer_value;\n");
    const auto files = cppulse::discover_cpp_files(root_);
    ASSERT_EQ(files.size(), 3u);
    EXPECT_TRUE(std::is_sorted(files.begin(), files.end()));
    const auto selected =
        cppulse::validate_selected_files(root_, {"array.c++", "array-test.C++", "consumer.cpp"});
    EXPECT_EQ(selected.size(), 3u);
}

TEST_F(NativeScopeFixture, OriginalCPlusPlusUnitsRetainDatabaseContext) {
    nlohmann::json entries = nlohmann::json::array();
    const auto build = root_ / "build";
    for (const auto* name : {"array.c++", "array-test.c++", "consumer.cpp"}) {
        write(root_ / name,
              "#if __cplusplus != 201402L\n#error wrong standard\n#endif\n"
              "#if RECORDED != 7\n#error missing defines\n#endif\nint value;\n");
        const auto operand = std::string{"../"} + name;
        entries.push_back(
            {{"directory", build.generic_string()},
             {"file", operand},
             {"arguments", {"g++", "-std=gnu++14", "-DRECORDED=7", "-x", "c++", "-c", operand}}});
    }
    write(build / "compile_commands.json", entries.dump());
    cppulse::FileAnalyzer analyzer{root_, std::nullopt, build / "compile_commands.json"};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), 3u);
    for (const auto& outcome : analyzer.coverage().files) {
        EXPECT_EQ(outcome.status, "analyzed");
        EXPECT_EQ(outcome.compile_context, "database");
        EXPECT_EQ(outcome.error_count, 0);
        ASSERT_TRUE(outcome.parse_arguments.has_value());
        for (const auto& expected : {"-std=gnu++14", "-DRECORDED=7", "-x", "c++"}) {
            EXPECT_NE(std::find(outcome.parse_arguments->begin(), outcome.parse_arguments->end(),
                                expected),
                      outcome.parse_arguments->end());
        }
        EXPECT_EQ(outcome.parse_arguments->front(), "-working-directory=" + build.string());
    }
}

TEST_F(NativeScopeFixture, UnassessedDeclarationsRemainExplicitWithoutParserFacts) {
    write(root_ / "good.cpp", "int good;\n");
    write(root_ / "unsupported.txt", "#error unsupported input must not be parsed\n");
    write(base_ / "external.cpp", "#error external input must not be parsed\n");
    nlohmann::json entries = nlohmann::json::array();
    for (const auto* name : {"good.cpp", "missing.c++", "unsupported.txt", "../external.cpp"}) {
        entries.push_back({{"directory", root_.generic_string()},
                           {"file", name},
                           {"arguments", {"g++", "-std=c++17", "-x", "c++", "-c", name}}});
    }
    write(root_ / "compile_commands.json", entries.dump());
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), 4u);
    EXPECT_EQ(analyzer.file_count(), 1);
    for (const auto& outcome : analyzer.coverage().files) {
        if (std::filesystem::path{outcome.path}.filename() == "good.cpp") {
            EXPECT_EQ(outcome.status, "analyzed");
        } else {
            EXPECT_EQ(outcome.status, "skipped");
            EXPECT_EQ(outcome.compile_context, "none");
            EXPECT_FALSE(outcome.parse_arguments.has_value());
            ASSERT_TRUE(outcome.reason.has_value());
            EXPECT_NE(outcome.reason->find("declared compilation"), std::string::npos);
        }
    }
}

TEST_F(NativeScopeFixture, GeneratedClassificationIsRetainedAsExplicitExclusion) {
    const std::vector<std::filesystem::path> generated{
        "message.pb.h",       "message.pb.cc",     "message.pb.cpp",
        "message.upb.h",      "message.upbdefs.h", "message.upb_minitable.h",
        "schema_generated.h", "moc_window.cpp",    "qrc_assets.cpp",
        "ui_window.h",        "upb-gen/table.c++", "upbdefs-gen/table.hpp"};
    for (const auto& name : generated) {
        write(root_ / name, "#error generated-looking source must be explicitly excluded\n");
        EXPECT_TRUE(cppulse::is_generated_source(name));
    }
    write(root_ / "ordinary.cpp", "int ordinary;\n");
    EXPECT_FALSE(cppulse::is_generated_source("ordinary.cpp"));
    EXPECT_EQ(cppulse::discover_cpp_files(root_).size(), generated.size() + 1);
    // An explicit database declaration must not make the generated file vanish.
    database(root_, "message.pb.cpp", {"g++", "-std=c++17", "-c", "message.pb.cpp"});
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), generated.size() + 1);
    EXPECT_EQ(analyzer.file_count(), 1);
    for (const auto& outcome : analyzer.coverage().files) {
        if (std::filesystem::path{outcome.path}.filename() == "ordinary.cpp")
            continue;
        EXPECT_EQ(outcome.status, "excluded");
        EXPECT_FALSE(outcome.parse_arguments.has_value());
        ASSERT_TRUE(outcome.reason.has_value());
        EXPECT_NE(outcome.reason->find("heuristic"), std::string::npos);
    }
}

TEST_F(NativeScopeFixture, ConfiguredCPlusPlusExclusionRemainsInSelectedScope) {
    write(root_ / "excluded.c++", "#error excluded source must not be parsed\n");
    write(root_ / "excluded.cc", "int ordinary() { return 1; }\n");
    cppulse::ProjectConfig config;
    config.exclude_paths = {"excluded.c++"};
    cppulse::FileAnalyzer analyzer{
        root_, config, std::nullopt, std::nullopt,
        std::vector<std::filesystem::path>{"excluded.c++", "excluded.cc"}};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), 2u);
    const auto* excluded = coverage_for(analyzer, root_ / "excluded.c++");
    const auto* included = coverage_for(analyzer, root_ / "excluded.cc");
    ASSERT_NE(excluded, nullptr);
    ASSERT_NE(included, nullptr);
    EXPECT_EQ(excluded->status, "excluded");
    EXPECT_FALSE(excluded->parse_arguments.has_value());
    ASSERT_TRUE(excluded->reason.has_value());
    EXPECT_NE(excluded->reason->find("configured exclude_paths"), std::string::npos);
    EXPECT_EQ(included->status, "analyzed");
}

TEST_F(NativeScopeFixture, DoesNotDiscoverExternalFileSymlink) {
    write(base_ / "external.cpp", "typedef int ExternalCount;\n");
    std::error_code ec;
    std::filesystem::create_symlink(base_ / "external.cpp", root_ / "alias.cpp", ec);
    if (ec) {
        GTEST_SKIP() << "File symlink unavailable: " << ec.message();
    }
    EXPECT_TRUE(cppulse::discover_cpp_files(root_).empty());
}

TEST_F(NativeScopeFixture, DoesNotTraverseExternalDirectorySymlink) {
    write(base_ / "external" / "source.cpp", "typedef int ExternalCount;\n");
    std::error_code ec;
    std::filesystem::create_directory_symlink(base_ / "external", root_ / "alias", ec);
    if (ec) {
        GTEST_SKIP() << "Directory symlink unavailable: " << ec.message();
    }
    EXPECT_TRUE(cppulse::discover_cpp_files(root_).empty());
}

TEST_F(NativeScopeFixture, DeclaredSymlinkCannotBeHiddenByParentNormalization) {
    write(root_ / "source.c++", "#error unsafe declared context must not be parsed\n");
    std::filesystem::create_directories(base_ / "external");
    std::error_code error;
    std::filesystem::create_directory_symlink(base_ / "external", root_ / "linked", error);
    if (error) {
        GTEST_SKIP() << "Directory symlink unavailable: " << error.message();
    }
    database(root_, "linked/../source.c++", {"g++", "-std=c++17", "-c", "linked/../source.c++"});
    cppulse::FileAnalyzer analyzer{root_};
    analyzer.run();
    ASSERT_EQ(analyzer.coverage().files.size(), 1u);
    const auto& outcome = analyzer.coverage().files.front();
    EXPECT_EQ(outcome.status, "skipped");
    EXPECT_FALSE(outcome.parse_arguments.has_value());
    ASSERT_TRUE(outcome.reason.has_value());
    EXPECT_NE(outcome.reason->find("symlink"), std::string::npos);
}

TEST_F(NativeScopeFixture, PreservesForcedIncludeWithSameBasename) {
    write(root_ / "src" / "sample.cpp",
          "#ifndef INCLUDED\n#error forced include missing\n#endif\nvoid valid() {}\n");
    write(root_ / "support" / "sample.cpp", "#define INCLUDED 1\n");
    const auto build = root_ / "build";
    database(
        build, "../src/sample.cpp",
        {"clang++", "-std=c++17", "-include", "../support/sample.cpp", "-c", "../src/sample.cpp"});
    cppulse::FileAnalyzer analyzer{root_, std::nullopt, build};
    analyzer.run();
    const auto* source = coverage_for(analyzer, root_ / "src" / "sample.cpp");
    ASSERT_NE(source, nullptr);
    EXPECT_EQ(source->status, "analyzed");
    EXPECT_EQ(source->error_count, 0);
}

}  // namespace
