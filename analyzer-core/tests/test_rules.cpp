/**
 * @file test_rules.cpp
 * @brief Unit tests for all 22 cppulse analysis rules using fixture files.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <string>
#include <vector>

#include "analyzer.h"
#include "finding.h"

namespace {

/// @brief Resolve the absolute path to a fixture file.
std::filesystem::path fixture_path(const std::string& filename) {
    // Primary: relative to this source file (tests/fixtures/).
    std::filesystem::path from_source =
        std::filesystem::path(__FILE__).parent_path() / "fixtures" / filename;
    if (std::filesystem::exists(from_source)) {
        return from_source;
    }
    // Fallback: relative to CWD when running ctest from build/.
    std::filesystem::path from_cwd = std::filesystem::path("../tests/fixtures") / filename;
    if (std::filesystem::exists(from_cwd)) {
        return from_cwd;
    }
    return from_source;
}

/// @brief Return a directory containing only the specified fixture file.
std::filesystem::path fixture_dir(const std::string& filename) {
    return fixture_path(filename).parent_path();
}

/// @brief Run the analyzer on a single fixture file and return its findings.
std::vector<cppulse::Finding> analyze_fixture(const std::string& filename) {
    // Wrap single-file analysis: create a temporary directory with a symlink,
    // OR just analyze the fixture directory and filter by file name.
    const std::filesystem::path file = fixture_path(filename);
    EXPECT_TRUE(std::filesystem::exists(file)) << "Fixture missing: " << file;

    // Use a FileAnalyzer pointed at the fixtures directory, then filter.
    cppulse::FileAnalyzer analyzer{file.parent_path()};
    analyzer.run();

    std::vector<cppulse::Finding> filtered;
    for (const auto& finding : analyzer.findings()) {
        if (std::filesystem::path{finding.file}.filename().string() == filename) {
            filtered.push_back(finding);
        }
    }
    return filtered;
}

/// @brief Check whether findings contain at least one with the given rule_id.
bool has_rule(const std::vector<cppulse::Finding>& findings, const std::string& rule_id) {
    return std::any_of(findings.begin(), findings.end(),
                       [&rule_id](const cppulse::Finding& f) { return f.rule_id == rule_id; });
}

/// @brief Count findings with the given rule_id.
int count_rule(const std::vector<cppulse::Finding>& findings, const std::string& rule_id) {
    return static_cast<int>(
        std::count_if(findings.begin(), findings.end(),
                      [&rule_id](const cppulse::Finding& f) { return f.rule_id == rule_id; }));
}

}  // namespace

// =============================================================================
// Memory Safety Tests
// =============================================================================

class MemorySafetyTest : public ::testing::Test {
   protected:
    void SetUp() override {
        findings_ = analyze_fixture("memory_safety_sample.cpp");
    }
    std::vector<cppulse::Finding> findings_;
};

TEST_F(MemorySafetyTest, DetectsRawNew) {
    EXPECT_TRUE(has_rule(findings_, "CPP-MEM-001"))
        << "Expected CPP-MEM-001 (raw new) in memory_safety_sample.cpp";
}

TEST_F(MemorySafetyTest, DetectsRawDelete) {
    EXPECT_TRUE(has_rule(findings_, "CPP-MEM-002"))
        << "Expected CPP-MEM-002 (raw delete) in memory_safety_sample.cpp";
}

TEST_F(MemorySafetyTest, DetectsCArrayParam) {
    EXPECT_TRUE(has_rule(findings_, "CPP-MEM-003"))
        << "Expected CPP-MEM-003 (C-array param) in memory_safety_sample.cpp";
}

TEST_F(MemorySafetyTest, FindingsHaveCorrectCategory) {
    for (const auto& f : findings_) {
        EXPECT_EQ(f.category, "memory_safety") << "Wrong category for " << f.rule_id;
    }
}

TEST_F(MemorySafetyTest, FindingsHavePositiveLineNumbers) {
    for (const auto& f : findings_) {
        EXPECT_GT(f.line, 0) << "Non-positive line number for " << f.rule_id;
    }
}

// =============================================================================
// Modernization Tests
// =============================================================================

class ModernizationTest : public ::testing::Test {
   protected:
    void SetUp() override {
        findings_ = analyze_fixture("modernization_sample.cpp");
    }
    std::vector<cppulse::Finding> findings_;
};

TEST_F(ModernizationTest, DetectsCStyleCast) {
    EXPECT_TRUE(has_rule(findings_, "CPP-MOD-001")) << "Expected CPP-MOD-001 (C-style cast)";
}

TEST_F(ModernizationTest, DetectsDeprecatedHeader) {
    EXPECT_TRUE(has_rule(findings_, "CPP-MOD-002"))
        << "Expected CPP-MOD-002 (deprecated C header stdio.h)";
}

TEST_F(ModernizationTest, DetectsMissingOverride) {
    EXPECT_TRUE(has_rule(findings_, "CPP-MOD-003")) << "Expected CPP-MOD-003 (missing override)";
}

TEST_F(ModernizationTest, DetectsUnscopedEnum) {
    EXPECT_TRUE(has_rule(findings_, "CPP-MOD-008")) << "Expected CPP-MOD-008 (unscoped enum)";
}

TEST_F(ModernizationTest, DetectsTypedef) {
    EXPECT_TRUE(has_rule(findings_, "CPP-MOD-009")) << "Expected CPP-MOD-009 (typedef)";
}

TEST_F(ModernizationTest, FindingsHaveCorrectCategory) {
    for (const auto& f : findings_) {
        EXPECT_EQ(f.category, "modernization") << "Wrong category for " << f.rule_id;
    }
}

// =============================================================================
// Complexity Tests
// =============================================================================

class ComplexityTest : public ::testing::Test {
   protected:
    void SetUp() override {
        findings_ = analyze_fixture("complexity_sample.cpp");
    }
    std::vector<cppulse::Finding> findings_;
};

TEST_F(ComplexityTest, DetectsLongFunction) {
    EXPECT_TRUE(has_rule(findings_, "CPP-CX-002"))
        << "Expected CPP-CX-002 (long function) in complexity_sample.cpp";
}

TEST_F(ComplexityTest, DetectsTooManyParams) {
    EXPECT_TRUE(has_rule(findings_, "CPP-CX-003"))
        << "Expected CPP-CX-003 (too many params) in complexity_sample.cpp";
}

TEST_F(ComplexityTest, TooManyParamsErrorSeverityForNineParams) {
    bool found_error = false;
    for (const auto& f : findings_) {
        if (f.rule_id == "CPP-CX-003" && f.severity == "error") {
            found_error = true;
            break;
        }
    }
    EXPECT_TRUE(found_error) << "Expected error-severity CPP-CX-003 for 9-param function";
}

TEST_F(ComplexityTest, FindingsHaveCorrectCategory) {
    for (const auto& f : findings_) {
        EXPECT_EQ(f.category, "complexity") << "Wrong category for " << f.rule_id;
    }
}

// =============================================================================
// MISRA Tests
// =============================================================================

class MisraTest : public ::testing::Test {
   protected:
    void SetUp() override {
        findings_ = analyze_fixture("misra_sample.cpp");
    }
    std::vector<cppulse::Finding> findings_;
};

TEST_F(MisraTest, DetectsGoto) {
    EXPECT_TRUE(has_rule(findings_, "MISRA-001"))
        << "Expected MISRA-001 (goto) in misra_sample.cpp";
}

TEST_F(MisraTest, DetectsUnion) {
    EXPECT_TRUE(has_rule(findings_, "MISRA-003"))
        << "Expected MISRA-003 (union) in misra_sample.cpp";
}

TEST_F(MisraTest, DetectsDynamicAlloc) {
    EXPECT_TRUE(has_rule(findings_, "MISRA-004"))
        << "Expected MISRA-004 (malloc/free) in misra_sample.cpp";
}

TEST_F(MisraTest, DetectsRecursion) {
    EXPECT_TRUE(has_rule(findings_, "MISRA-005"))
        << "Expected MISRA-005 (recursion) in misra_sample.cpp";
}

TEST_F(MisraTest, DetectsMultipleReturns) {
    EXPECT_TRUE(has_rule(findings_, "MISRA-006"))
        << "Expected MISRA-006 (multiple returns) in misra_sample.cpp";
}

TEST_F(MisraTest, FindingsHaveCorrectCategory) {
    for (const auto& f : findings_) {
        EXPECT_EQ(f.category, "misra") << "Wrong category for " << f.rule_id;
    }
}

TEST_F(MisraTest, GotoIsErrorSeverity) {
    for (const auto& f : findings_) {
        if (f.rule_id == "MISRA-001") {
            EXPECT_EQ(f.severity, "error") << "MISRA-001 should be error severity";
        }
    }
}

TEST_F(MisraTest, UnionIsErrorSeverity) {
    for (const auto& f : findings_) {
        if (f.rule_id == "MISRA-003") {
            EXPECT_EQ(f.severity, "error") << "MISRA-003 should be error severity";
        }
    }
}

// =============================================================================
// Clean Code Test — zero findings
// =============================================================================

TEST(CleanCodeTest, ProducesZeroFindings) {
    const auto findings = analyze_fixture("clean_modern.cpp");

    if (!findings.empty()) {
        for (const auto& f : findings) {
            ADD_FAILURE() << "Unexpected finding in clean_modern.cpp:" << " rule=" << f.rule_id
                          << " line=" << f.line << " msg=" << f.message;
        }
    }
    EXPECT_TRUE(findings.empty()) << "clean_modern.cpp should produce zero findings";
}

// =============================================================================
// Output Writer Tests
// =============================================================================

#include <fstream>
#include <nlohmann/json.hpp>

#include "output_writer.h"

TEST(OutputWriterTest, WritesValidJson) {
    std::vector<cppulse::Finding> findings;
    findings.push_back(cppulse::Finding{.rule_id = "CPP-MEM-001",
                                        .category = "memory_safety",
                                        .severity = "warning",
                                        .file = "/tmp/test.cpp",
                                        .line = 10,
                                        .column = 5,
                                        .message = "Test finding",
                                        .suggestion = "Fix it",
                                        .confidence = 1.0});

    const std::filesystem::path out_dir =
        std::filesystem::temp_directory_path() / "cppulse_test_output";
    std::filesystem::remove_all(out_dir);

    const bool ok = cppulse::write_findings_json(findings, "/tmp/test_repo", 1, 20, out_dir);
    ASSERT_TRUE(ok) << "write_findings_json returned false";

    const std::filesystem::path out_file = out_dir / "findings.json";
    ASSERT_TRUE(std::filesystem::exists(out_file)) << "findings.json not created";

    std::ifstream ifs(out_file);
    ASSERT_TRUE(ifs.is_open());

    nlohmann::json root;
    ASSERT_NO_THROW(ifs >> root);

    EXPECT_EQ(root["version"].get<std::string>(), "1.0.0");
    EXPECT_EQ(root["findings"].size(), 1u);
    EXPECT_EQ(root["summary"]["total_findings"].get<int>(), 1);
    EXPECT_EQ(root["summary"]["by_category"]["memory_safety"].get<int>(), 1);
    EXPECT_EQ(root["summary"]["by_severity"]["warning"].get<int>(), 1);

    // Close before remove_all: Windows refuses to delete files that are open.
    ifs.close();
    std::filesystem::remove_all(out_dir);
}

TEST(OutputWriterTest, HandlesEmptyFindings) {
    const std::filesystem::path out_dir =
        std::filesystem::temp_directory_path() / "cppulse_test_empty";
    std::filesystem::remove_all(out_dir);

    const bool ok = cppulse::write_findings_json({}, "/tmp/empty_repo", 0, 0, out_dir);
    ASSERT_TRUE(ok);

    const std::filesystem::path out_file = out_dir / "findings.json";
    ASSERT_TRUE(std::filesystem::exists(out_file));

    std::ifstream ifs(out_file);
    nlohmann::json root;
    ASSERT_NO_THROW(ifs >> root);

    EXPECT_EQ(root["findings"].size(), 0u);
    EXPECT_EQ(root["summary"]["total_findings"].get<int>(), 0);

    // Close before remove_all: Windows refuses to delete files that are open.
    ifs.close();
    std::filesystem::remove_all(out_dir);
}

// =============================================================================
// File Discovery Tests
// =============================================================================

#include "file_discovery.h"

TEST(FileDiscoveryTest, FindsFixtureFiles) {
    const auto fixture_dir_path = std::filesystem::path(__FILE__).parent_path() / "fixtures";
    const auto files = cppulse::discover_cpp_files(fixture_dir_path);
    EXPECT_GE(files.size(), 4u) << "Expected at least 4 fixture files";
}

TEST(FileDiscoveryTest, ReturnsEmptyForNonexistentDir) {
    const auto files = cppulse::discover_cpp_files("/nonexistent/path/xyz");
    EXPECT_TRUE(files.empty());
}

TEST(FileDiscoveryTest, OnlyReturnsCppFiles) {
    const auto fixture_dir_path = std::filesystem::path(__FILE__).parent_path() / "fixtures";
    const auto files = cppulse::discover_cpp_files(fixture_dir_path);
    for (const auto& file : files) {
        const std::string ext = file.extension().string();
        EXPECT_TRUE(ext == ".cpp" || ext == ".h" || ext == ".hpp" || ext == ".cxx" ||
                    ext == ".cc" || ext == ".hxx")
            << "Unexpected extension: " << ext << " for file " << file;
    }
}
