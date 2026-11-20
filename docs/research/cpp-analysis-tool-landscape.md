# C++ analysis tool landscape

Research snapshot: **2026-11-05**. Status: **Reference for goal selection**.

This inventory covers major C/C++ analysis tools and related platforms relevant to
cppulse. It preserves the high-level comparison used to discuss the project's
direction. cppulse's goal and feature scope remain to be agreed.

The inventory includes specialist tools as well as broader platforms; it does not
list every historical or language-specific analyzer. Tool names link to official
documentation. **OSS** means open source. Free plans, commercial editions, and
language support have different limits. Product capabilities and licensing can
change; revisit the linked sources when making a selection.

The [product discovery and working direction](cppulse-product-discovery.md)
consolidates the subsequent pain-point research, current implementation status,
and proposed maintainer/consumer workflow as of 2026-11-11.

## Source analysis and coding rules

These tools inspect source code for defects, suspicious constructs, and
coding-rule violations.

| Tool | What it does at a high level | Availability |
|---|---|---|
| [clang-tidy](https://clang.llvm.org/extra/clang-tidy/) | Checks C++ correctness, performance, modernization, readability, portability, and coding guidelines. Supports custom checks and selected automatic fixes. | OSS |
| [Clang Static Analyzer](https://clang.llvm.org/docs/ClangStaticAnalyzer.html) | Follows possible execution paths to detect null dereferences, memory leaks, resource misuse, and other defects. | OSS |
| [GCC warnings and `-fanalyzer`](https://gcc.gnu.org/onlinedocs/gcc/Static-Analyzer-Options.html) | Compiler diagnostics plus deeper analysis of memory and resource misuse. Ordinary warnings cover C/C++; `-fanalyzer` is currently documented as suitable for C. | OSS |
| [MSVC C/C++ Code Analysis](https://learn.microsoft.com/en-us/cpp/code-quality/code-analysis-for-c-cpp-overview?view=msvc-170) | Detects buffer errors, uninitialized memory, null dereferences, resource problems, and C++ Core Guidelines violations. | Microsoft toolchain; license terms apply |
| [Cppcheck / Cppcheck Premium](https://www.cppcheck.com/) | Detects undefined behavior and suspicious C/C++ constructs. Premium adds broader safety-standard checks, reporting, and deeper analysis. | OSS core + commercial Premium |
| [PVS-Studio](https://pvs-studio.com/en/pvs-studio/) | Finds correctness, security, and reliability defects using static analysis; provides standards mappings and development-tool integrations. | Commercial; conditional free programs |
| [PC-lint Plus](https://www.vector.com/en/product/pc-lint-plus/) | Checks C/C++ defects, suspicious constructs, and configurable coding standards, including MISRA and AUTOSAR. | Commercial |
| [Infer](https://fbinfer.com/) | Performs analysis across functions to find issues such as null dereferences, memory leaks, and API misuse. Checks vary by language. | OSS |
| [OCLint](https://oclint.org/) | Checks C/C++/Objective-C style, redundant code, overly complex functions, and maintainability problems. Supports custom rules. | OSS |
| [cpplint](https://github.com/cpplint/cpplint) | Checks C/C++ formatting and coding conventions based on Google's C++ style guide. | OSS |
| [Flawfinder](https://github.com/david-a-wheeler/flawfinder) | Finds potentially dangerous C/C++ API usage through lexical pattern matching and ranks findings by risk. | OSS |
| [Sparse](https://sparse.docs.kernel.org/en/latest/) | Checks C types and annotations, including address spaces and locking-related rules. Particularly relevant to kernel code. | OSS; C-focused |

## Security and quality platforms

These platforms add vulnerability analysis, issue management, repository
integration, and policy gates.

| Tool | What it does at a high level | Availability |
|---|---|---|
| [SonarQube Server / Cloud / IDE](https://www.sonarsource.com/products/sonarqube/) | Detects bugs, security issues, code smells, and duplication; imports test coverage; provides quality gates and IDE feedback. | Free and paid offerings; C++ capabilities depend on product/edition |
| [Coverity](https://www.blackduck.com/static-analysis-tools-sast/coverity.html) | Finds defects across functions and files, including memory, resource, and security problems; provides finding review and tracking. | Commercial; free Coverity Scan for qualifying OSS |
| [Klocwork](https://www.perforce.com/products/klocwork) | Analyzes C/C++ security, reliability, and coding standards, with incremental analysis and team issue management. | Commercial |
| [CodeSonar](https://www.adacore.com/codesonar) | Performs deep, whole-program analysis for safety and security defects, with diagnostic paths and finding review. | Commercial |
| [CodeQL](https://codeql.github.com/) | Represents code as a queryable database. Finds vulnerabilities through custom queries and tracking data across functions. | Free OSS/research use under its terms; commercial offerings |
| [Semgrep](https://semgrep.dev/products/semgrep-vs-ce) | Uses configurable patterns and security rules to find dangerous code and API usage. C/C++ analysis capabilities differ between CE and commercial editions. | OSS CE + commercial platform |
| [OpenText Fortify SAST](https://www.opentext.com/products/static-application-security-testing) | Finds source-code security vulnerabilities, tracks unsafe data flows, and supports audit, review, and security workflows. | Commercial |
| [Checkmarx SAST](https://docs.checkmarx.com/en/34965-149060-sast-scanner---supported-languages-and-frameworks.html) | Analyzes C/C++ and other languages for security weaknesses, with configurable queries and centralized finding management. | Commercial |
| [Snyk Code](https://docs.snyk.io/supported-languages/supported-languages-list/c-c%2B%2B) | Finds source-code vulnerabilities, including issues spanning files; integrates with editors, repositories, and development workflows. | Free tier + commercial plans |

## Code health and architecture

This group overlaps most directly with cppulse's code-health, technical-debt,
architecture, and prioritization ambitions.

| Tool | What it does at a high level | Availability |
|---|---|---|
| [CodeScene](https://codescene.com/product) | Combines code-health analysis with Git history: hotspots, change coupling, knowledge ownership, technical-debt prioritization, trends, and review gates. | [Free for OSS; commercial private-repository plans](https://codescene.com/pricing) |
| [CppDepend](https://www.cppdepend.com/) | Provides C/C++ metrics, dependency graphs, architecture rules, custom queries, technical-debt tracking, and quality gates. | Commercial |
| [SciTools Understand / CodeCheck](https://scitools.com/) | Provides code navigation, cross-references, call/dependency graphs, metrics, impact analysis, and configurable coding-standard checks. | Commercial |
| [Axivion Suite](https://www.qt.io/quality-assurance/axivion-suite) | Checks architecture conformance, dependency cycles, code clones, metrics, coding rules, and architecture deterioration. | Commercial |
| [Lattix](https://www.lattix.com/) | Analyzes software dependencies, architectural layers, cycles, coupling, and the impact of changes. | Commercial |
| [Lizard](https://github.com/terryyin/lizard) | Measures function complexity, size, parameter counts, and duplication; supports thresholds for problematic functions. | OSS |
| [Metrix++](https://github.com/metrixplusplus/metrixplusplus) | Collects extensible code metrics, checks limits, and helps identify metric changes between versions. | OSS |
| [PMD Copy/Paste Detector - CPD](https://pmd.github.io/pmd/pmd_userdocs_cpd.html) | Detects duplicated code across supported languages, including C/C++. This is distinct from PMD's language-specific rule analyzers. | OSS |
| [Codacy](https://docs.codacy.com/getting-started/supported-languages-and-tools/) | Aggregates code-quality checks, duplication, complexity, and coverage information into repository dashboards and review gates. | Free OSS and commercial offerings |
| [Qlty](https://qlty.sh/) | Combines linting, complexity, duplication, security checks, coverage, baselines, and pull-request feedback. | Free CLI; hosted plans |

## Safety suites and formal verification

These tools provide coding-standard checks, verification results, and supporting
evidence.

| Tool | What it does at a high level | Availability |
|---|---|---|
| [Perforce QAC](https://www.perforce.com/products/helix-qac) | Checks C/C++ coding standards such as MISRA and AUTOSAR; supports deviations, compliance reporting, and qualification workflows. | Commercial |
| [Parasoft C/C++test](https://www.parasoft.com/products/parasoft-c-ctest/) | Combines static analysis, coding standards, unit testing, coverage, and requirements traceability. Capabilities depend on edition/modules. | Commercial |
| [LDRA tool suite](https://ldra.com/products/ldra-tool-suite/) | Combines coding-rule checks, control/data-flow analysis, testing, structural coverage, and requirements traceability. | Commercial |
| [Polyspace Bug Finder](https://www.mathworks.com/products/polyspace-bug-finder.html) | Finds C/C++ defects, security weaknesses, coding-standard violations, and code metrics. | Commercial |
| [Polyspace Code Prover](https://www.mathworks.com/products/polyspace-code-prover.html) | Uses abstract interpretation to prove the absence of certain runtime errors under specified assumptions and models. | Commercial |
| [Astrée](https://www.absint.com/factsheets/factsheet_astree_c_web.pdf) | Uses abstract interpretation to analyze C/C++ runtime errors and concurrency issues, particularly in embedded software. | Commercial |
| [TrustInSoft Analyzer](https://www.trust-in-soft.com/trustinsoft-analyzer) | Uses formal analysis to check undefined behavior and memory safety under modeled inputs and assumptions. | Commercial |
| [Frama-C](https://www.frama-c.com/) | Provides modular value analysis, contracts, deductive verification, and runtime verification through plugins. | OSS framework; C-focused |
| [CBMC](https://www.cprover.org/cbmc/) | Uses bounded model checking to verify assertions, pointer safety, bounds, and other properties; produces counterexamples. | OSS |
| [ESBMC](https://esbmc.github.io/) | Uses SMT-based model checking to verify program properties and identify counterexamples. Language support and verification bounds matter. | OSS |

## Runtime analysis and testing

Runtime tools execute software or instrument builds. They provide a different
kind of evidence from source-only analysis.

| Tool | What it does at a high level | Availability |
|---|---|---|
| [AddressSanitizer - ASan](https://clang.llvm.org/docs/AddressSanitizer.html) | Detects executed memory errors, including out-of-bounds access and use-after-free. | OSS |
| [ThreadSanitizer - TSan](https://clang.llvm.org/docs/ThreadSanitizer.html) | Detects data races observed during instrumented execution. | OSS |
| [UndefinedBehaviorSanitizer - UBSan](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html) | Detects selected undefined behavior during execution, such as invalid shifts, misalignment, and signed overflow. | OSS |
| [MemorySanitizer - MSan](https://clang.llvm.org/docs/MemorySanitizer.html) | Detects the use of uninitialized memory during execution. | OSS |
| [LeakSanitizer - LSan](https://clang.llvm.org/docs/LeakSanitizer.html) | Detects memory leaks during execution, often alongside ASan. | OSS |
| [Valgrind](https://valgrind.org/info/tools.html) | Provides memory-error detection, leak detection, concurrency checks, heap analysis, and execution/cache profiling through separate tools. | OSS |
| [Dr. Memory](https://drmemory.org/) | Detects invalid and uninitialized memory access, use-after-free, leaks, and selected resource errors through dynamic instrumentation. | OSS |
| [libFuzzer](https://llvm.org/docs/LibFuzzer.html) | Generates and mutates inputs using execution coverage to discover crashes and other failures. | OSS |
| [AFL++](https://aflplus.plus/) | Performs coverage-guided fuzzing with source and binary instrumentation options, input mutation, and corpus management. | OSS |
| [FuzzTest](https://github.com/google/fuzztest) | Combines C++ property-based testing with coverage-guided fuzzing to explore inputs and edge cases. | OSS |
| [OSS-Fuzz](https://google.github.io/oss-fuzz/) | Runs continuous fuzzing for eligible open-source projects and reports crashes and sanitizer failures. | Free for eligible OSS |
| [GoogleTest](https://google.github.io/googletest/reference/testing.html) | Executes C++ unit tests with assertions, fixtures, and parameterized test cases. | OSS |
| [LLVM source-based coverage](https://clang.llvm.org/docs/SourceBasedCodeCoverage.html) | Measures which functions, lines, regions, and branches tests execute. | OSS |
| [gcov / gcovr](https://gcovr.com/) | Collects and reports test-execution coverage, including source and branch coverage. | OSS |
| [VectorCAST/C++](https://www.vector.com/en/product/vectorcast/vectorcast-c/) | Automates embedded unit/integration testing, harnesses, mocks, regression testing, and coverage including MC/DC. | Commercial |
| [Cantata](https://www.qa-systems.com/tools/cantata) | Provides C/C++ unit/integration testing, call control, host/target execution, coverage, and requirements traceability. | Commercial |
| [Testwell CTC++](https://www.testwell.fi/ctcdesc.html) | Measures instrumented C/C++ coverage, including MC/DC, across host and embedded targets. | Commercial |
| [Coco](https://www.qt.io/quality-assurance/coco/feature-coverage-levels) | Measures coverage from functions and statements through conditions, MC/DC, and multiple-condition coverage. | Commercial |

## Libraries and interface compatibility

Libraries introduce additional concerns: public interfaces, binary compatibility,
header dependencies, and API migrations.

| Tool | What it does at a high level | Availability |
|---|---|---|
| [Include What You Use - IWYU](https://include-what-you-use.org/index.html) | Identifies missing and unnecessary includes and suggests more explicit header dependencies. | OSS |
| [ABI Compliance Checker](https://lvc.github.io/abi-compliance-checker/) | Compares library versions for backward source/API and binary/ABI compatibility problems. | OSS |
| [libabigail](https://sourceware.org/libabigail/) | Examines binary interfaces and compares library versions to identify ABI changes. | OSS |
| [Coccinelle](https://coccinelle.gitlabpages.inria.fr/website/) | Uses semantic patterns to detect code patterns and automate large-scale API migrations or bug-fix transformations. | OSS; primarily C-focused |

## Analyzer orchestration and finding management

These platforms coordinate analyzers and manage their results rather than
implementing the underlying checks.

| Tool | What it does at a high level | Availability |
|---|---|---|
| [CodeChecker](https://codechecker.readthedocs.io/en/latest/) | Runs multiple analyzers, captures build information, compares findings, manages suppressions, and provides reports and a finding database. | OSS |
| [MegaLinter](https://megalinter.io/latest/) | Runs configurable collections of linters and analyzers locally or in automation; consolidates reports and selected fixes. | OSS |
| [DefectDojo](https://docs.defectdojo.com/) | Imports security findings from many tools; supports deduplication, review, prioritization, tracking, and reporting. | OSS + commercial Pro |

## Dependencies and licenses

Dependency and license tools inspect the components used by a project. They
complement source-code defect analysis.

| Tool | What it does at a high level | Availability |
|---|---|---|
| [Syft / Grype](https://oss.anchore.com/docs/guides/vulnerability/scan-targets/) | Syft inventories software components and produces SBOMs; Grype matches identified components against known vulnerabilities. | OSS |
| [Trivy](https://trivy.dev/docs/latest/references/terminology/) | Scans supported artifacts for known vulnerabilities, exposed secrets, configuration problems, and license information. | OSS |
| [ScanCode Toolkit](https://scancode-toolkit.readthedocs.io/en/stable/tutorials/configuring-scan-detection.html) | Detects license text, copyright notices, package metadata, and other information embedded in source trees. | OSS |
| [OSS Review Toolkit - ORT](https://oss-review-toolkit.org/ort/docs/intro) | Automates dependency analysis, license/security policies, SBOM generation, attribution documents, and compliance reports. | OSS |
| [Snyk Open Source](https://docs.snyk.io/supported-languages/supported-languages-list/c-c%2B%2B) | Identifies supported C/C++ dependencies and checks known vulnerabilities and licensing issues. | Free tier + commercial plans |
| [Black Duck SCA](https://www.blackduck.com/software-composition-analysis-tools/black-duck-sca.html) | Identifies third-party components, known vulnerabilities, licenses, and supply-chain policy issues. | Commercial |

## Implications for selecting cppulse's goal

Defect detection, maintainability scoring, change-risk prioritization,
compatibility checking, and safety evidence should be evaluated separately.
Feature presence alone does not establish accuracy, scalability, or usability;
those require comparing shortlisted tools on the same representative repositories.

