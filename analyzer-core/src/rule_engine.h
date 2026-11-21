/**
 * @file rule_engine.h
 * @brief std::variant container that holds all 22 analysis rules.
 *
 * RuleVariant holds one instance of each concrete rule.  The engine uses
 * std::visit to dispatch check() calls uniformly without virtual dispatch.
 */

#ifndef CPPULSE_RULE_ENGINE_H
#define CPPULSE_RULE_ENGINE_H

#include <clang-c/Index.h>

#include <variant>
#include <vector>

#include "finding.h"
#include "generated_rule_types.h"

namespace cppulse {

/**
 * @brief Visitor that calls check() on whichever rule type is active.
 */
struct CheckVisitor {
    CXCursor cursor;
    const std::string& file_path;

    template <typename Rule>
    void operator()(Rule& rule) const {
        rule.check(cursor, file_path);
    }
};

/**
 * @brief Visitor that extracts the findings from whichever rule is active.
 */
struct FindingsVisitor {
    std::vector<Finding>& out;

    template <typename Rule>
    void operator()(const Rule& rule) const {
        const auto& rf = rule.findings();
        out.insert(out.end(), rf.begin(), rf.end());
    }
};

/**
 * @brief Visitor that clears findings on whichever rule is active.
 */
struct ClearFindingsVisitor {
    template <typename Rule>
    void operator()(Rule& rule) const {
        rule.clear_findings();
    }
};

/**
 * @brief Visitor that returns the rule_id string_view from whichever rule is active.
 */
struct RuleIdVisitor {
    template <typename Rule>
    std::string_view operator()(const Rule& rule) const {
        return rule.rule_id();
    }
};

}  // namespace cppulse

#endif  // CPPULSE_RULE_ENGINE_H
