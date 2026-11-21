/**
 * @file test_config_rule_options98.cpp
 * @brief Native public-loader regressions for per-rule supported options.
 */

#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "config.h"
#include "test_temp_directory.h"

namespace {

enum class ConfigFormat98 { kJson, kYaml };

/** @brief Exercise both public file formats and retain fixtures on failure. */
class NativeRuleOptions98Test : public ::testing::TestWithParam<ConfigFormat98> {
   protected:
    void SetUp() override {
        directory_ = cppulse::test::make_test_directory("cppulse_rule_options98");
    }

    void TearDown() override {
        if (HasFailure()) {
            RecordProperty("retained_fixture_directory", directory_.generic_string());
            return;
        }
        std::error_code error;
        std::filesystem::remove_all(directory_, error);
    }

    std::filesystem::path write_document(const std::string& content) {
        const auto extension = GetParam() == ConfigFormat98::kJson ? ".json" : ".yml";
        const auto path = directory_ / ("case-" + std::to_string(next_case_++) + extension);
        std::ofstream stream(path, std::ios::binary);
        stream << content;
        stream.close();
        if (!stream) {
            throw std::runtime_error("Cannot write native configuration fixture: " +
                                     path.generic_string());
        }
        return path;
    }

    std::string rule_document(
        const std::string& rule,
        const std::vector<std::pair<std::string, std::string>>& properties) const {
        if (GetParam() == ConfigFormat98::kJson) {
            std::string result = "{\"rules\":{\"" + rule + "\":{";
            bool first = true;
            for (const auto& property : properties) {
                if (!first) {
                    result += ',';
                }
                first = false;
                result += "\"" + property.first + "\":" + property.second;
            }
            return result + "}}}";
        }
        std::string result = "rules:\n  " + rule + ":";
        if (properties.empty()) {
            return result + " {}\n";
        }
        result += '\n';
        for (const auto& property : properties) {
            result += "    " + property.first + ": " + property.second + "\n";
        }
        return result;
    }

    cppulse::ProjectConfig load_document(const std::string& content) {
        return cppulse::load_config(write_document(content));
    }

    void expect_rejected(const std::string& content) {
        const auto path = write_document(content);
        SCOPED_TRACE(path.generic_string() + "\n" + content);
        EXPECT_THROW(static_cast<void>(cppulse::load_config(path)), std::runtime_error);
    }

   private:
    std::filesystem::path directory_;
    unsigned next_case_{0};
};

TEST_P(NativeRuleOptions98Test, RejectsThresholdsUnsupportedByTheSelectedRule) {
    for (const auto* rule : {"CPP-MEM-001", "CPP-MOD-001", "MISRA-001"}) {
        for (const auto* option : {"warning_threshold", "error_threshold"}) {
            for (const auto* enabled : {"true", "false"}) {
                // Disabling a rule must not turn an unsupported option into an accepted no-op.
                expect_rejected(rule_document(rule, {{"enabled", enabled}, {option, "9"}}));
            }
        }
    }
}

TEST_P(NativeRuleOptions98Test, PreservesSupportedComplexityThresholdExtremes) {
    const auto maximum = std::to_string(std::numeric_limits<int>::max());
    for (const auto* rule : {"CPP-CX-001", "CPP-CX-002", "CPP-CX-003"}) {
        for (const bool reversed : {false, true}) {
            for (const bool enabled : {false, true}) {
                SCOPED_TRACE(std::string{rule} + (reversed ? " reversed" : " forward") +
                             (enabled ? " enabled" : " disabled"));
                const auto config = load_document(
                    rule_document(rule, {{"enabled", enabled ? "true" : "false"},
                                         {"warning_threshold", reversed ? maximum : "0"},
                                         {"error_threshold", reversed ? "0" : maximum}}));
                ASSERT_EQ(config.rules.size(), 1u);
                const auto& settings = config.rules.at(rule);
                EXPECT_EQ(settings.enabled, enabled);
                ASSERT_TRUE(settings.warning_threshold.has_value());
                ASSERT_TRUE(settings.error_threshold.has_value());
                EXPECT_EQ(*settings.warning_threshold,
                          reversed ? std::numeric_limits<int>::max() : 0);
                EXPECT_EQ(*settings.error_threshold,
                          reversed ? 0 : std::numeric_limits<int>::max());
            }
        }
    }
}

TEST_P(NativeRuleOptions98Test, PreservesDefaultsAndEnabledWithoutInventingThresholds) {
    const auto defaults = load_document(GetParam() == ConfigFormat98::kJson ? "{}" : "");
    EXPECT_EQ(defaults.profile, "default");
    EXPECT_EQ(defaults.max_file_bytes, cppulse::kDefaultMaxFileBytes);
    EXPECT_EQ(defaults.max_token_records, cppulse::kDefaultMaxTokenRecords);
    EXPECT_TRUE(defaults.exclude_paths.empty());
    EXPECT_TRUE(defaults.rules.empty());
    for (const auto* rule :
         {"CPP-CX-001", "CPP-CX-002", "CPP-CX-003", "CPP-MEM-001", "CPP-MOD-001", "MISRA-001"}) {
        SCOPED_TRACE(rule);
        const auto config = load_document(rule_document(rule, {}));
        const auto& settings = config.rules.at(rule);
        EXPECT_TRUE(settings.enabled);
        EXPECT_FALSE(settings.warning_threshold.has_value());
        EXPECT_FALSE(settings.error_threshold.has_value());

        const auto disabled = load_document(rule_document(rule, {{"enabled", "false"}}));
        EXPECT_FALSE(disabled.rules.at(rule).enabled);
        EXPECT_FALSE(disabled.rules.at(rule).warning_threshold.has_value());
        EXPECT_FALSE(disabled.rules.at(rule).error_threshold.has_value());
    }
}

TEST_P(NativeRuleOptions98Test, RejectsInvalidSupportedThresholdTypesAndRanges) {
    const auto above_maximum =
        std::to_string(static_cast<long long>(std::numeric_limits<int>::max()) + 1);
    for (const auto* option : {"warning_threshold", "error_threshold"}) {
        for (const auto& value :
             std::vector<std::string>{"true", "\"9\"", "9.0", "9.5", "-1", above_maximum, "null"}) {
            // Native integral JSON spelling remains strict, including the value 9.0.
            expect_rejected(rule_document("CPP-CX-001", {{option, value}}));
        }
    }
}

TEST_P(NativeRuleOptions98Test, RejectsNonBooleanEnabled) {
    for (const auto* value : {"0", "1", "\"false\"", "null"}) {
        expect_rejected(rule_document("CPP-CX-001", {{"enabled", value}}));
    }
}

TEST_P(NativeRuleOptions98Test, RejectsUnknownRootRuleAndOption) {
    expect_rejected(GetParam() == ConfigFormat98::kJson ? "{\"unsupported_option\":true}"
                                                        : "unsupported_option: true\n");
    expect_rejected(rule_document("CPP-NOT-A-RULE", {{"enabled", "true"}}));
    expect_rejected(rule_document("CPP-CX-001", {{"unsupported_option", "9"}}));
}

INSTANTIATE_TEST_SUITE_P(PublicFormats, NativeRuleOptions98Test,
                         ::testing::Values(ConfigFormat98::kJson, ConfigFormat98::kYaml),
                         [](const ::testing::TestParamInfo<ConfigFormat98>& info) {
                             return info.param == ConfigFormat98::kJson ? "Json" : "Yaml";
                         });

}  // namespace
