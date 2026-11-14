/** @file test_native_scope.cpp
 * @brief Native source-scope and compilation-context regression cases.
 */
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <string>

#include "analyzer.h"
#include "file_discovery.h"

namespace {

/** @brief Own a source tree and external sibling for each regression. */
class NativeScopeFixture : public ::testing::Test {
   protected:
    void SetUp() override {
        const auto* info = ::testing::UnitTest::GetInstance()->current_test_info();
        base_ =
            std::filesystem::temp_directory_path() / (std::string{"cppulse_scope_"} + info->name());
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
