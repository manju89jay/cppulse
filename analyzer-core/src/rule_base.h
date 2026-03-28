/**
 * @file rule_base.h
 * @brief CRTP base class for all analysis rules.
 *
 * Every rule derives from RuleBase<Derived> and implements:
 *   - check_impl(CXCursor, const std::string&)
 *   - rule_id_impl()   -> std::string_view
 *   - category_impl()  -> std::string_view
 */

#ifndef CPPULSE_RULE_BASE_H
#define CPPULSE_RULE_BASE_H

#include <clang-c/Index.h>

#include <string>
#include <string_view>
#include <vector>

#include "finding.h"

namespace cppulse {

/**
 * @brief CRTP base that all detection rules inherit from.
 *
 * Provides common finding accumulation and a uniform interface so that
 * rules can be stored in a std::variant and dispatched via std::visit.
 *
 * @tparam Derived  The concrete rule class.
 */
template <typename Derived>
class RuleBase {
   public:
    /**
     * @brief Dispatch a single AST cursor to the concrete rule for checking.
     *
     * @param cursor     The libclang cursor to inspect.
     * @param file_path  Absolute path of the translation unit being analyzed.
     */
    void check(CXCursor cursor, const std::string& file_path) {
        static_cast<Derived*>(this)->check_impl(cursor, file_path);
    }

    /**
     * @brief Return the unique rule identifier (e.g. "CPP-MEM-001").
     */
    [[nodiscard]] std::string_view rule_id() const {
        return static_cast<const Derived*>(this)->rule_id_impl();
    }

    /**
     * @brief Return the rule category (e.g. "memory_safety").
     */
    [[nodiscard]] std::string_view category() const {
        return static_cast<const Derived*>(this)->category_impl();
    }

    /**
     * @brief Return all findings accumulated so far.
     */
    [[nodiscard]] const std::vector<Finding>& findings() const {
        return findings_;
    }

    /**
     * @brief Discard all accumulated findings (called between files).
     */
    void clear_findings() {
        findings_.clear();
    }

   protected:
    /**
     * @brief Append a finding to the accumulator.
     *
     * @param f  The finding to record.
     */
    void add_finding(Finding f) {
        findings_.push_back(std::move(f));
    }

   private:
    std::vector<Finding> findings_;
};

}  // namespace cppulse

#endif  // CPPULSE_RULE_BASE_H
