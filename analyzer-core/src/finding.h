/**
 * @file finding.h
 * @brief Defines the Finding struct — the fundamental unit of analysis output.
 */

#ifndef CPPULSE_FINDING_H
#define CPPULSE_FINDING_H

#include <string>

namespace cppulse {

/**
 * @brief A single diagnostic finding produced by an analysis rule.
 *
 * Each Finding represents one violation or recommendation at a specific
 * location in a source file.  The rule_id and category fields match the
 * identifiers defined in docs/architecture.md.
 */
struct Finding {
    /** @brief Unique rule identifier, e.g. "CPP-MEM-001". */
    std::string rule_id;

    /** @brief Rule category: "memory_safety", "modernization", "complexity", or "misra". */
    std::string category;

    /** @brief Severity level: "error", "warning", or "info". */
    std::string severity;

    /** @brief Absolute path to the source file containing the violation. */
    std::string file;

    /** @brief 1-based line number of the finding. */
    int line{0};

    /** @brief 1-based column number of the finding (0 = unknown). */
    int column{0};

    /** @brief Last line of the construct that triggered the finding (0 = unknown). */
    int end_line{0};

    /** @brief Human-readable description of the violation. */
    std::string message;

    /** @brief Suggested remediation for the violation. */
    std::string suggestion;

    /** @brief Confidence score in [0.0, 1.0].  1.0 means deterministic detection. */
    double confidence{1.0};
};

}  // namespace cppulse

#endif  // CPPULSE_FINDING_H
