# cppulse Full MVP — Task Specification for Claude Code

> **Branch**: `feature/full-mvp`
> **Goal**: Build all 6 components end-to-end so `docker-compose up` produces a working pipeline:
> C++ repo → static analysis → git mining → ML prediction → PDF report + REST API + React dashboard.
> **Constraint**: Every architectural decision must be documented in `docs/DECISIONS.md` with rationale.

---

## Table of Contents

1. [Build Order](#1-build-order)
2. [JSON Schemas (Inter-Component Contracts)](#2-json-schemas)
3. [Component 1: analyzer-core (C++17)](#3-analyzer-core)
4. [Component 2: git-miner (Python)](#4-git-miner)
5. [Component 3: predictor (Python)](#5-predictor)
6. [Component 4: report-engine (Python)](#6-report-engine)
7. [Component 5: dashboard (React/TypeScript)](#7-dashboard)
8. [Component 6: cli (C++17)](#8-cli)
9. [Docker & Integration](#9-docker-integration)
10. [DECISIONS.md Template](#10-decisions-md)
11. [Testing Strategy](#11-testing-strategy)
12. [Definition of Done](#12-definition-of-done)

---

## 1. Build Order

Build components in this exact sequence. Each step must pass tests before proceeding.

```
Phase 1 — Data Contracts (do this FIRST)
  └── Define all JSON schemas in docs/schemas/

Phase 2 — Data Producers (parallel-safe)
  ├── analyzer-core (C++17, libclang) → findings.json
  └── git-miner (Python) → git_metrics.json

Phase 3 — Data Consumer
  └── predictor (Python) → risk_scores.json + roadmap.json

Phase 4 — Presentation Layer (parallel-safe)
  ├── report-engine (Python/FastAPI) → PDF + REST API
  └── dashboard (React/TypeScript) → Web UI

Phase 5 — Orchestration
  └── cli (C++17, CLI11) → ties it all together

Phase 6 — Integration
  └── docker-compose up works end-to-end
```

---

## 2. JSON Schemas

Create these files in `docs/schemas/`. Every component validates input against these schemas on startup.

### 2.1 `findings.json` — Output of analyzer-core

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "cppulse Static Analysis Findings",
  "type": "object",
  "required": ["version", "metadata", "findings", "summary"],
  "properties": {
    "version": { "type": "string", "const": "1.0.0" },
    "metadata": {
      "type": "object",
      "required": ["repo_path", "analyzed_at", "file_count", "total_loc"],
      "properties": {
        "repo_path": { "type": "string" },
        "analyzed_at": { "type": "string", "format": "date-time" },
        "file_count": { "type": "integer", "minimum": 0 },
        "total_loc": { "type": "integer", "minimum": 0 }
      }
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id", "category", "severity", "file", "line", "message"],
        "properties": {
          "rule_id": { "type": "string", "pattern": "^(CPP-MEM|CPP-MOD|CPP-CX|MISRA)-\\d{3}$" },
          "category": { "enum": ["memory_safety", "modernization", "complexity", "misra"] },
          "severity": { "enum": ["error", "warning", "info"] },
          "file": { "type": "string" },
          "line": { "type": "integer", "minimum": 1 },
          "column": { "type": "integer", "minimum": 1 },
          "end_line": { "type": "integer", "minimum": 1 },
          "message": { "type": "string" },
          "suggestion": { "type": "string" },
          "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
        }
      }
    },
    "summary": {
      "type": "object",
      "required": ["total_findings", "by_category", "by_severity"],
      "properties": {
        "total_findings": { "type": "integer" },
        "by_category": {
          "type": "object",
          "properties": {
            "memory_safety": { "type": "integer" },
            "modernization": { "type": "integer" },
            "complexity": { "type": "integer" },
            "misra": { "type": "integer" }
          }
        },
        "by_severity": {
          "type": "object",
          "properties": {
            "error": { "type": "integer" },
            "warning": { "type": "integer" },
            "info": { "type": "integer" }
          }
        }
      }
    }
  }
}
```

### 2.2 `git_metrics.json` — Output of git-miner

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "cppulse Git Metrics",
  "type": "object",
  "required": ["version", "metadata", "file_metrics", "knowledge_silos"],
  "properties": {
    "version": { "type": "string", "const": "1.0.0" },
    "metadata": {
      "type": "object",
      "required": ["repo_path", "analyzed_at", "commit_range", "total_commits"],
      "properties": {
        "repo_path": { "type": "string" },
        "analyzed_at": { "type": "string", "format": "date-time" },
        "commit_range": { "type": "string" },
        "total_commits": { "type": "integer" }
      }
    },
    "file_metrics": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["file", "change_frequency", "unique_contributors", "age_days", "lines_of_code"],
        "properties": {
          "file": { "type": "string" },
          "change_frequency": { "type": "integer", "description": "Number of commits touching this file" },
          "unique_contributors": { "type": "integer" },
          "age_days": { "type": "integer", "description": "Days since file was first created" },
          "last_modified_days": { "type": "integer", "description": "Days since last commit" },
          "lines_of_code": { "type": "integer" },
          "lines_added_total": { "type": "integer" },
          "lines_removed_total": { "type": "integer" },
          "churn_rate": { "type": "number", "description": "(added + removed) / LOC" },
          "bug_fix_commits": { "type": "integer", "description": "Commits with fix/bug/patch in message" },
          "contributor_list": { "type": "array", "items": { "type": "string" } }
        }
      }
    },
    "knowledge_silos": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["file", "sole_contributor", "last_commit_date"],
        "properties": {
          "file": { "type": "string" },
          "sole_contributor": { "type": "string" },
          "last_commit_date": { "type": "string", "format": "date" },
          "risk_note": { "type": "string" }
        }
      },
      "description": "Files where only 1 contributor has committed in the last 12 months"
    }
  }
}
```

### 2.3 `risk_scores.json` — Output of predictor

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "cppulse Risk Scores",
  "type": "object",
  "required": ["version", "metadata", "health_score", "file_risks", "hotspots"],
  "properties": {
    "version": { "type": "string", "const": "1.0.0" },
    "metadata": {
      "type": "object",
      "required": ["generated_at", "model_type", "feature_count"],
      "properties": {
        "generated_at": { "type": "string", "format": "date-time" },
        "model_type": { "type": "string", "const": "xgboost" },
        "feature_count": { "type": "integer" },
        "training_samples": { "type": "integer" },
        "f1_score": { "type": "number" }
      }
    },
    "health_score": {
      "type": "object",
      "required": ["overall", "by_category"],
      "properties": {
        "overall": { "type": "number", "minimum": 0, "maximum": 100 },
        "by_category": {
          "type": "object",
          "properties": {
            "memory_safety": { "type": "number", "minimum": 0, "maximum": 100 },
            "modernization": { "type": "number", "minimum": 0, "maximum": 100 },
            "complexity": { "type": "number", "minimum": 0, "maximum": 100 },
            "misra_compliance": { "type": "number", "minimum": 0, "maximum": 100 }
          }
        }
      }
    },
    "file_risks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["file", "bug_probability", "risk_level", "top_factors"],
        "properties": {
          "file": { "type": "string" },
          "bug_probability": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
          "risk_level": { "enum": ["critical", "high", "medium", "low"] },
          "top_factors": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "feature": { "type": "string" },
                "importance": { "type": "number" },
                "value": { "type": "number" }
              }
            },
            "maxItems": 5
          }
        }
      }
    },
    "hotspots": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["file", "hotspot_score"],
        "properties": {
          "file": { "type": "string" },
          "hotspot_score": { "type": "number", "description": "change_frequency * complexity * debt_density" },
          "change_frequency": { "type": "integer" },
          "complexity_score": { "type": "number" },
          "finding_count": { "type": "integer" }
        }
      },
      "maxItems": 20,
      "description": "Top 20 files by hotspot score"
    }
  }
}
```

### 2.4 `roadmap.json` — Output of predictor

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "cppulse Refactoring Roadmap",
  "type": "object",
  "required": ["version", "items"],
  "properties": {
    "version": { "type": "string", "const": "1.0.0" },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["priority", "file", "action", "category", "estimated_hours", "impact_score"],
        "properties": {
          "priority": { "type": "integer", "minimum": 1 },
          "file": { "type": "string" },
          "action": { "type": "string", "description": "Specific refactoring recommendation" },
          "category": { "enum": ["memory_safety", "modernization", "complexity", "misra", "knowledge_silo"] },
          "estimated_hours": { "type": "number", "minimum": 0.5 },
          "impact_score": { "type": "number", "minimum": 0, "maximum": 100, "description": "ROI: expected health score improvement" },
          "finding_ids": { "type": "array", "items": { "type": "string" }, "description": "Related finding rule_ids" }
        }
      }
    }
  }
}
```

**DECISION**: Document in DECISIONS.md why JSON files in `./output/` directory (not REST calls between containers) — simplicity, debuggability, pipeline can be run step-by-step.

---

## 3. analyzer-core (C++17)

### 3.1 Architecture

```
analyzer-core/src/
├── main.cpp                    # CLI entry point (already exists)
├── analyzer.h / analyzer.cpp   # FileAnalyzer: orchestrates rules over files
├── finding.h                   # Finding struct (maps to findings.json schema)
├── rule_base.h                 # CRTP base class for all rules
├── rules/
│   ├── memory_safety/
│   │   ├── raw_pointer_ownership.h/.cpp    # CPP-MEM-001
│   │   ├── manual_memory_mgmt.h/.cpp       # CPP-MEM-002
│   │   └── unsafe_array_access.h/.cpp      # CPP-MEM-003
│   ├── modernization/
│   │   ├── c_style_cast.h/.cpp             # CPP-MOD-001
│   │   ├── deprecated_headers.h/.cpp       # CPP-MOD-002
│   │   ├── missing_override.h/.cpp         # CPP-MOD-003
│   │   ├── raw_string_literal.h/.cpp       # CPP-MOD-004
│   │   ├── auto_usage.h/.cpp              # CPP-MOD-005
│   │   ├── range_for.h/.cpp               # CPP-MOD-006
│   │   ├── nullptr_usage.h/.cpp           # CPP-MOD-007
│   │   ├── enum_class.h/.cpp              # CPP-MOD-008
│   │   └── using_vs_typedef.h/.cpp        # CPP-MOD-009
│   ├── complexity/
│   │   ├── cyclomatic_complexity.h/.cpp    # CPP-CX-001
│   │   ├── function_length.h/.cpp          # CPP-CX-002
│   │   └── parameter_count.h/.cpp          # CPP-CX-003
│   └── misra/
│       ├── no_goto.h/.cpp                  # MISRA-001 (Rule 6.6.2)
│       ├── no_implicit_conversion.h/.cpp   # MISRA-002 (Rule 7.0.2)
│       ├── no_union.h/.cpp                 # MISRA-003 (Rule 12.3.1)
│       ├── no_dynamic_alloc.h/.cpp         # MISRA-004 (Rule 21.6.1)
│       ├── no_recursion.h/.cpp             # MISRA-005 (Rule 17.2.1)
│       ├── single_exit.h/.cpp              # MISRA-006 (Rule 15.5.1)
│       └── init_all_vars.h/.cpp            # MISRA-007 (Rule 8.1.1)
├── output_writer.h/.cpp        # Serializes findings to JSON (nlohmann/json)
└── file_discovery.h/.cpp       # Recursively finds .cpp/.h files in repo
```

### 3.2 Detection Rules — Grounded Specifications

**DECISION**: Document in DECISIONS.md that rules are grounded in MISRA C++:2023 and AUTOSAR C++14 where applicable. Not all 22 rules map to standards — some are empirical best practices. This is honest and defensible.

#### Memory Safety (3 rules)

| ID | Name | Detects | libclang Check | MISRA/AUTOSAR Ref |
|----|------|---------|----------------|-------------------|
| CPP-MEM-001 | Raw pointer ownership | `new` without matching smart pointer in same scope | Walk `CXCursor_CallExpr` for `operator new`, check parent scope for `unique_ptr`/`shared_ptr` wrapping | AUTOSAR A18-5-2 |
| CPP-MEM-002 | Manual memory management | Explicit `delete`/`delete[]` calls | `CXCursor_CXXDeleteExpr` cursor kind | MISRA Rule 21-6-1 (dynamic memory), AUTOSAR A18-5-1 |
| CPP-MEM-003 | Unsafe array access | C-style arrays in function parameters, raw `[]` on pointer types | `CXCursor_ParmDecl` with array type, pointer arithmetic | AUTOSAR A18-1-1 (use std::array) |

#### Modernization (9 rules)

| ID | Name | Detects | libclang Check |
|----|------|---------|----------------|
| CPP-MOD-001 | C-style cast | `(int)x` instead of `static_cast<int>(x)` | `CXCursor_CStyleCastExpr` |
| CPP-MOD-002 | Deprecated headers | `<stdio.h>` instead of `<cstdio>` | Inclusion directives via `clang_getInclusions`, match against deprecated list |
| CPP-MOD-003 | Missing override | Virtual method override without `override` keyword | `CXCursor_CXXMethod` with `clang_CXXMethod_isVirtual()` but no override attr |
| CPP-MOD-004 | Raw string literal candidate | Strings with many escaped chars | String literal cursors, count backslashes |
| CPP-MOD-005 | auto opportunity | Verbose type declarations where auto is clearer | Iterator declarations, `new` expressions assigned to explicit types |
| CPP-MOD-006 | Range-for opportunity | Index-based for loops over containers | `CXCursor_ForStmt` with index-only body access pattern |
| CPP-MOD-007 | nullptr vs NULL | Use of `NULL` macro or `0` for null pointer | Integer literal `0` assigned to pointer type |
| CPP-MOD-008 | Unscoped enum | `enum` without `class` keyword | `CXCursor_EnumDecl` without `clang_EnumDecl_isScoped()` |
| CPP-MOD-009 | typedef vs using | `typedef` instead of `using` alias | `CXCursor_TypedefDecl` |

#### Complexity (3 rules)

| ID | Name | Detects | Threshold |
|----|------|---------|-----------|
| CPP-CX-001 | Cyclomatic complexity | Functions with too many decision points | > 15 (warning), > 25 (error) |
| CPP-CX-002 | Function length | Overly long functions | > 80 lines (warning), > 150 lines (error) |
| CPP-CX-003 | Parameter count | Functions with too many params | > 5 (warning), > 8 (error) |

#### MISRA C++ Subset (7 rules)

| ID | Name | MISRA C++:2023 Rule | Detects |
|----|------|---------------------|---------|
| MISRA-001 | No goto | Rule 6.6.2 | `CXCursor_GotoStmt` |
| MISRA-002 | No implicit narrowing | Rule 7.0.2 | Implicit conversion losing precision (e.g., double→int) |
| MISRA-003 | No union | Rule 12.3.1 | `CXCursor_UnionDecl` |
| MISRA-004 | No dynamic allocation in safety code | Rule 21.6.1 | `malloc`/`calloc`/`realloc`/`free` calls |
| MISRA-005 | No recursion | Rule 17.2.1 | Function calling itself (direct recursion) |
| MISRA-006 | Single exit point | Rule 15.5.1 | Multiple `return` statements in a function |
| MISRA-007 | Initialize all variables | Rule 8.1.1 | Variable declarations without initializers |

### 3.3 CRTP Rule Engine Design

```cpp
// rule_base.h
#pragma once
#include "finding.h"
#include <clang-c/Index.h>
#include <vector>
#include <string_view>

namespace cppulse {

template <typename Derived>
class RuleBase {
public:
    void check(CXCursor cursor, const std::string& file_path) {
        static_cast<Derived*>(this)->check_impl(cursor, file_path);
    }

    [[nodiscard]] std::string_view rule_id() const {
        return static_cast<const Derived*>(this)->rule_id_impl();
    }

    [[nodiscard]] std::string_view category() const {
        return static_cast<const Derived*>(this)->category_impl();
    }

    [[nodiscard]] const std::vector<Finding>& findings() const { return findings_; }
    void clear_findings() { findings_.clear(); }

protected:
    void add_finding(Finding f) { findings_.push_back(std::move(f)); }

private:
    std::vector<Finding> findings_;
};

} // namespace cppulse
```

**DECISION**: Document why CRTP over virtual dispatch: zero-overhead polymorphism, compile-time rule registration, no vtable indirection in hot path. Tradeoff: rules must be known at compile time (acceptable — rules don't change at runtime).

### 3.4 FileAnalyzer Orchestration

The `FileAnalyzer` class:
1. Takes a repo path, discovers all `.cpp`/`.h`/`.hpp` files
2. For each file: creates a libclang translation unit, walks the AST
3. Applies all 22 rules to each cursor via a `std::variant`-based rule container
4. Aggregates findings across all files
5. Writes `findings.json` via `OutputWriter`

```cpp
// Use std::variant to hold all rule types (CRTP means different types)
using AnyRule = std::variant<
    RawPointerOwnership, ManualMemoryMgmt, UnsafeArrayAccess,
    CStyleCast, DeprecatedHeaders, MissingOverride, /* ... all 22 ... */
>;
```

**DECISION**: Document why `std::variant` over `std::unique_ptr<RuleBase>` virtual: type-safe, cache-friendly, no heap allocation per rule. Tradeoff: closed set of rules (acceptable for v1.0).

### 3.5 Existing Code to Preserve

- Keep `hello_libclang.h/.cpp` — rename to `function_extractor.h/.cpp` and use it as a utility
- Keep `CMakeLists.txt` structure — extend it for new source files
- Keep the test fixture files in `tests/fixtures/`

### 3.6 Test Fixtures Needed

Create `tests/fixtures/` files with known patterns for each rule:

```
tests/fixtures/
├── memory_safety_sample.cpp     # Contains raw new/delete, C arrays
├── modernization_sample.cpp     # C-style casts, deprecated headers, missing override
├── complexity_sample.cpp        # Long functions, deep nesting, many params
├── misra_sample.cpp             # goto, unions, recursion, malloc
├── clean_modern.cpp             # Clean C++17 code — should produce zero findings
└── empty.cpp                    # Already exists — should produce zero findings
```

Each test validates: correct rule_id, correct line number, correct severity.

---

## 4. git-miner (Python)

### 4.1 Structure

```
git-miner/
├── Dockerfile
├── requirements.txt          # Already exists
├── src/
│   ├── __init__.py           # Already exists
│   ├── main.py               # CLI entry point: --repo, --output
│   ├── miner.py              # GitMiner class: extracts metrics from git log
│   ├── silo_detector.py      # Identifies knowledge silos
│   ├── szz_labeler.py        # SZZ algorithm: labels bug-introducing commits
│   └── schema_validator.py   # Validates output against git_metrics.json schema
└── tests/
    ├── __init__.py            # Already exists
    ├── test_miner.py
    ├── test_silo_detector.py
    └── test_szz_labeler.py
```

### 4.2 Key Algorithms

**SZZ Algorithm (Simplified)**:
1. Find bug-fix commits (keyword matching: "fix", "bug", "patch", "issue", "crash", "error")
2. For each bug-fix commit, use `git blame` on the fixed lines to find the commit that introduced them
3. Label those introducing commits as "bug-introducing"
4. Mark files touched by bug-introducing commits

**DECISION**: Document SZZ simplification: using keyword-based fix identification instead of issue tracker linking. Honest tradeoff: higher false positive rate, but works without any external integrations. Cite: Śliwerski, Zimmermann, Zeller (2005) original paper.

**Knowledge Silo Detection**:
1. For each file, count unique contributors in last 12 months
2. If only 1 contributor → knowledge silo
3. Weight by file importance (LOC, change frequency)

### 4.3 Metrics Extracted Per File (10 features)

1. `change_frequency` — commit count touching this file
2. `unique_contributors` — distinct authors
3. `age_days` — days since file creation
4. `last_modified_days` — days since last change
5. `lines_of_code` — current LOC
6. `lines_added_total` — total additions across all commits
7. `lines_removed_total` — total deletions
8. `churn_rate` — (added + removed) / LOC
9. `bug_fix_commits` — commits with bug-fix keywords
10. `contributor_list` — list of contributor names/emails

### 4.4 Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python3", "-m", "src.main"]
```

---

## 5. predictor (Python)

### 5.1 Structure

```
predictor/
├── Dockerfile
├── requirements.txt          # Already exists
├── src/
│   ├── __init__.py           # Already exists
│   ├── main.py               # CLI: --input (dir with findings + git_metrics), --output
│   ├── feature_engineer.py   # Merges findings + git_metrics into feature matrix
│   ├── model.py              # XGBoost training and prediction
│   ├── health_scorer.py      # Computes overall 0-100 health score
│   ├── roadmap_generator.py  # Generates prioritized refactoring roadmap
│   └── schema_validator.py
└── tests/
    ├── __init__.py            # Already exists
    ├── test_feature_engineer.py
    ├── test_model.py
    └── test_health_scorer.py
```

### 5.2 Feature Engineering

Merge `findings.json` and `git_metrics.json` by filename:

| Feature | Source | Description |
|---------|--------|-------------|
| finding_count | findings.json | Total findings for this file |
| memory_findings | findings.json | Count of memory_safety findings |
| modernization_findings | findings.json | Count of modernization findings |
| complexity_findings | findings.json | Count of complexity findings |
| misra_findings | findings.json | Count of MISRA findings |
| max_severity | findings.json | Highest severity (error=3, warning=2, info=1) |
| change_frequency | git_metrics.json | How often the file changes |
| unique_contributors | git_metrics.json | Number of distinct contributors |
| churn_rate | git_metrics.json | Code churn ratio |
| bug_fix_commits | git_metrics.json | Historical bug-fix count |
| age_days | git_metrics.json | File age |
| is_knowledge_silo | git_metrics.json | Boolean: sole contributor? |

### 5.3 Model Pipeline

```python
# Pseudocode for the XGBoost pipeline
class BugPredictor:
    def __init__(self):
        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            objective='binary:logistic',
            eval_metric='logloss',
            random_state=42
        )

    def train(self, features_df, labels):
        """Labels come from SZZ: 1 = file introduced a bug, 0 = clean."""
        X_train, X_test, y_train, y_test = train_test_split(...)
        self.model.fit(X_train, y_train)
        # Log F1, precision, recall

    def predict(self, features_df):
        """Returns bug probability per file."""
        return self.model.predict_proba(features_df)[:, 1]

    def explain(self, features_df):
        """SHAP values for top risk factors per file."""
        import shap
        explainer = shap.TreeExplainer(self.model)
        return explainer.shap_values(features_df)
```

**DECISION**: Document why XGBoost over neural networks: interpretability via SHAP, trains in seconds without GPU, proven on tabular SE data. Cite: Kamei et al. (2013) Just-In-Time defect prediction.

**DECISION**: Document the cold-start problem: repos with < 50 commits won't have enough training data for SZZ labeling. Fallback: use a heuristic scoring model (weighted sum of features) instead of ML prediction. This is honest and defensible.

### 5.4 Health Score Calculation

```
overall_health = 100 - weighted_penalty

where weighted_penalty = sum of:
  - memory_safety_findings * 3.0  (highest weight — safety critical)
  - misra_findings * 2.5
  - complexity_findings * 1.5
  - modernization_findings * 1.0

Clamped to [0, 100].
Category scores are 100 - (category_findings / file_count * scale_factor).
```

**DECISION**: Document the penalty weights and why memory safety is weighted 3x modernization. Grounded in: MISRA C++ severity classifications and real bug-introduction rates from the SZZ data.

### 5.5 Hotspot Calculation

```
hotspot_score = change_frequency * normalized_complexity * debt_density
```

Where `debt_density = finding_count / lines_of_code`. Top 20 files by hotspot score.

---

## 6. report-engine (Python)

### 6.1 Structure

```
report-engine/
├── Dockerfile
├── requirements.txt          # Already exists
├── src/
│   ├── __init__.py           # Already exists
│   ├── api.py                # FastAPI app with REST endpoints
│   ├── pdf_generator.py      # WeasyPrint PDF generation
│   ├── templates/
│   │   ├── report.html       # Jinja2 template for PDF
│   │   └── styles.css        # PDF styling
│   └── schema_validator.py
└── tests/
    ├── __init__.py            # Already exists
    ├── test_api.py            # httpx-based API tests
    └── test_pdf_generator.py
```

### 6.2 REST API Endpoints

```
GET  /health                    → { "status": "ok" }
GET  /api/v1/summary            → health_score + summary stats
GET  /api/v1/findings           → paginated findings list
GET  /api/v1/findings?category= → filtered by category
GET  /api/v1/hotspots           → top 20 hotspot files
GET  /api/v1/risks              → file risk scores with SHAP factors
GET  /api/v1/silos              → knowledge silo alerts
GET  /api/v1/roadmap            → prioritized refactoring items
GET  /api/v1/report/pdf         → download PDF report
```

### 6.3 PDF Report Sections

The PDF report (generated by WeasyPrint from Jinja2 HTML template) contains:

1. **Executive Summary** — Overall health score (big number), date, repo name
2. **Health Score Breakdown** — Bar chart by category (memory, modernization, complexity, MISRA)
3. **Hotspot Map** — Table of top 20 hotspot files
4. **Detection Findings** — Grouped by category, sorted by severity
5. **Knowledge Silo Alerts** — Table of files with single contributor
6. **Bug Prediction** — Top 10 highest-risk files with SHAP explanations
7. **Refactoring Roadmap** — Prioritized table with estimated hours and impact

Use matplotlib for generating chart images embedded in the HTML template.

### 6.4 Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 7. dashboard (React/TypeScript)

### 7.1 Structure

```
dashboard/
├── Dockerfile
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   └── client.ts           # Fetch wrapper for report-engine API
│   ├── components/
│   │   ├── HealthScore.tsx      # Big circular score gauge
│   │   ├── CategoryBreakdown.tsx # Bar chart of category scores
│   │   ├── HotspotTable.tsx     # Sortable table of top 20 hotspots
│   │   ├── FindingsList.tsx     # Filterable findings list
│   │   ├── SiloAlerts.tsx       # Knowledge silo warning cards
│   │   ├── RiskPrediction.tsx   # Bug prediction with SHAP factors
│   │   ├── Roadmap.tsx          # Refactoring roadmap table
│   │   └── Layout.tsx           # App shell with navigation
│   └── types/
│       └── index.ts             # TypeScript types matching JSON schemas
└── public/
```

### 7.2 Tech Stack

- **Vite** for build tooling
- **React 18** with TypeScript
- **Recharts** for charts (bar, pie, treemap)
- **Tailwind CSS** for styling
- **No state management library** — React Query or simple fetch + useState

### 7.3 Key Visualizations

1. **Health Score Gauge** — Circular progress bar, color-coded (green >70, amber 40-70, red <40)
2. **Category Breakdown** — Horizontal bar chart comparing memory/modernization/complexity/misra
3. **Hotspot Treemap** — Recharts Treemap with file size = hotspot score
4. **Finding Timeline** — Optional line chart if multiple analysis runs exist
5. **SHAP Waterfall** — For selected file, show which factors drive bug probability

### 7.4 Dockerfile

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
```

The `nginx.conf` should proxy `/api/*` to `report-engine:8000`.

---

## 8. cli (C++17)

### 8.1 Structure

```
cli/
├── CMakeLists.txt
├── Dockerfile
├── src/
│   ├── main.cpp              # CLI11 entry point
│   └── orchestrator.h/.cpp   # Spawns analyzer-core, git-miner, predictor
└── tests/
    └── test_cli.cpp
```

### 8.2 Commands

```
cppulse analyze --repo /path/to/repo --output ./output
cppulse report  --input ./output --format pdf|json
cppulse watch   --repo /path/to/repo --interval 300  # re-analyze every 5 min
```

The CLI orchestrator calls the other components as subprocesses:
1. Runs `cppulse-analyzer` on the repo → `output/findings.json`
2. Runs `python3 -m git_miner.main` → `output/git_metrics.json`
3. Runs `python3 -m predictor.main` → `output/risk_scores.json` + `output/roadmap.json`
4. Runs `python3 -m report_engine.pdf_generator` → `output/report.pdf`

**DECISION**: Document why CLI is C++ (not Python): consistency with analyzer-core, demonstrates full-stack C++ capability, CLI11 is header-only and trivial to integrate.

---

## 9. Docker & Integration

### 9.1 docker-compose.yml Updates

The existing docker-compose.yml is already structured correctly. Components need:
- Each component's Dockerfile (analyzer-core already has one)
- Shared volume `cppulse_output` for JSON files
- Correct `depends_on` ordering

### 9.2 Integration Test

Create `scripts/integration_test.sh`:

```bash
#!/bin/bash
set -e

echo "=== cppulse Integration Test ==="

# Use the project's own test fixtures as the target repo
export REPO_PATH=./analyzer-core/tests/fixtures

# Run the full pipeline
docker-compose up --build --abort-on-container-exit

# Verify outputs exist
for f in findings.json git_metrics.json risk_scores.json roadmap.json report.pdf; do
    if [ ! -f "./output/$f" ]; then
        echo "FAIL: output/$f not found"
        exit 1
    fi
done

# Verify JSON schemas
python3 -c "
import json, jsonschema
for schema_file, data_file in [
    ('docs/schemas/findings.schema.json', 'output/findings.json'),
    ('docs/schemas/git_metrics.schema.json', 'output/git_metrics.json'),
    ('docs/schemas/risk_scores.schema.json', 'output/risk_scores.json'),
    ('docs/schemas/roadmap.schema.json', 'output/roadmap.json'),
]:
    with open(schema_file) as s, open(data_file) as d:
        jsonschema.validate(json.load(d), json.load(s))
    print(f'PASS: {data_file} validates against {schema_file}')
"

echo "=== All integration tests passed ==="
```

---

## 10. DECISIONS.md Template

Create `docs/DECISIONS.md` with this structure. Fill in each decision as it's made during implementation.

```markdown
# cppulse Architectural Decisions Log

> This document explains the WHY behind every significant design choice.
> Read this before any interview — it's your defense guide.

## How to Read This

Each decision follows: **Context** (what problem), **Decision** (what we chose),
**Why** (the real reason), **Tradeoffs** (what we gave up), **Standard Reference**
(if applicable).

---

## D1: libclang over custom parser / Tree-sitter / Clang plugin
- **Context**: Need to parse C++17 for 22 detection rules
- **Decision**: libclang C API
- **Why**: Full semantic AST (resolves types, follows includes), stable ABI across LLVM versions, same parser as Clang compiler
- **Tradeoffs**: Verbose callback-based API, slightly slower than Clang plugin
- **Reference**: ADR-001

## D2: CRTP rule engine over virtual dispatch
- **Context**: 22 rules need polymorphic dispatch during AST walk
- **Decision**: Curiously Recurring Template Pattern
- **Why**: Zero-overhead — no vtable lookup in the hot loop (AST visitor callback runs per-cursor). Rules are statically known.
- **Tradeoffs**: Cannot add rules at runtime, all rules compiled in. Acceptable for v1.0.
- **Interview angle**: "I chose CRTP because the rule set is closed and known at compile time. If rules needed to be loaded dynamically (plugins), I'd switch to virtual dispatch."

## D3: std::variant rule container over type-erasure
- **Context**: Need to store heterogeneous CRTP rule objects in a single container
- **Decision**: std::variant<Rule1, Rule2, ...>
- **Why**: Cache-friendly (no heap allocation), type-safe, compiler-checked exhaustive visitation
- **Tradeoffs**: Closed set; adding a rule requires modifying the variant typedef
- **Interview angle**: "variant gives me value semantics, cache locality, and exhaustive std::visit. For an open plugin system, I'd use std::unique_ptr<RuleInterface>."

## D4: XGBoost over neural networks / logistic regression
- **Context**: Bug prediction from 12 tabular features
- **Decision**: XGBoost gradient-boosted trees
- **Why**: Best performer on tabular data (Kamei et al. 2013), interpretable via SHAP, trains in seconds on CPU
- **Tradeoffs**: Requires enough labeled training data (SZZ needs 50+ commits)
- **Reference**: ADR-002

## D5: SZZ algorithm — simplified keyword-based approach
- **Context**: Need to label bug-introducing commits for ML training
- **Decision**: Keyword matching ("fix", "bug", "patch") + git blame
- **Why**: Works without issue tracker integration. Original SZZ (Śliwerski et al. 2005) is well-cited.
- **Tradeoffs**: Higher false positive rate than issue-tracker linked SZZ. Honest limitation.
- **Interview angle**: "I chose keyword-based SZZ for zero-dependency operation. In production, I'd integrate with Jira/GitHub Issues for higher precision."

## D6: JSON files over REST for pipeline communication
- **Context**: 6 components need to pass data
- **Decision**: JSON files in shared ./output/ directory
- **Why**: Debuggable (inspect files directly), pipeline can run step-by-step, no network complexity
- **Tradeoffs**: Not real-time, requires shared filesystem. For microservices, I'd use gRPC.
- **Reference**: ADR-004

## D7: Health score weighted penalty system
- **Context**: Need a single 0-100 health score
- **Decision**: Weighted deduction: memory_safety×3, misra×2.5, complexity×1.5, modernization×1
- **Why**: Safety-critical findings weighted highest. Mirrors MISRA severity classification.
- **Tradeoffs**: Weights are calibrated empirically, not formally derived. Documented for transparency.

## D8: 22 rules — standard-grounded where possible
- **Context**: Which rules to implement?
- **Decision**: 3 memory safety, 9 modernization, 3 complexity, 7 MISRA subset
- **Why**: Memory/MISRA rules map to MISRA C++:2023 and AUTOSAR C++14. Modernization rules are empirical best practices from clang-tidy modernize-* checks.
- **Tradeoffs**: Not exhaustive. 22 was chosen for demonstrable breadth, not completeness.
- **Interview angle**: "I picked rules that cover the four main debt categories in safety-critical C++. MISRA rules are directly traceable to the standard. Modernization rules mirror clang-tidy's modernize-* set."

## D9: WeasyPrint for PDF generation
- **Context**: Need professional PDF reports
- **Decision**: WeasyPrint (HTML/CSS → PDF)
- **Why**: Full CSS support, Jinja2 templating, Python-native. No external LaTeX dependency.
- **Tradeoffs**: Large Docker image due to system deps (pango, cairo). Acceptable for server-side generation.

## D10: React + Recharts dashboard
- **Context**: Interactive visualization of analysis results
- **Decision**: React 18 + TypeScript + Recharts + Tailwind
- **Why**: Recharts has treemap (for hotspots), standard React stack, Tailwind for rapid styling
- **Tradeoffs**: Full SPA for what could be a static page. Justified by: interactive filtering, future trend comparison.

## D11: CLI in C++ (not Python)
- **Context**: Orchestrator for the pipeline
- **Decision**: C++17 with CLI11
- **Why**: Demonstrates full-stack C++ capability, consistent with analyzer-core. CLI11 is header-only.
- **Tradeoffs**: Python subprocess calls from C++ are less elegant than a pure-Python orchestrator.
- **Interview angle**: "I used C++ for the CLI to show I can build end-to-end in C++, not just the analysis engine."

## D12: Cold-start fallback for ML predictor
- **Context**: Repos with < 50 commits can't train XGBoost
- **Decision**: Fallback to heuristic weighted scoring (no ML)
- **Why**: Graceful degradation. Users still get useful output.
- **Tradeoffs**: Heuristic is less accurate than ML prediction.
```

---

## 11. Testing Strategy

### Unit Tests Per Component

| Component | Framework | Min Coverage | Key Tests |
|-----------|-----------|-------------|-----------|
| analyzer-core | GoogleTest | 80% | One test per rule with fixture file, edge cases (empty file, template-heavy file) |
| git-miner | pytest | 80% | Mock git repo with known history, silo detection, SZZ labeling |
| predictor | pytest | 75% | Feature engineering merge, model train/predict, health score boundaries |
| report-engine | pytest + httpx | 75% | API endpoints return correct JSON, PDF generation succeeds |
| dashboard | (optional) | — | Manual verification for v1.0 |
| cli | GoogleTest | 60% | Command parsing, subprocess invocation |

### Integration Tests

- `scripts/integration_test.sh` — full docker-compose pipeline
- Verify all JSON outputs validate against schemas
- Verify PDF is generated and non-empty

---

## 12. Definition of Done

The MVP is complete when ALL of these are true:

- [ ] `docker-compose up` with a target C++ repo produces all outputs
- [ ] `output/findings.json` validates against schema, contains findings from 22 rules
- [ ] `output/git_metrics.json` validates, contains file metrics and knowledge silos
- [ ] `output/risk_scores.json` validates, contains health score and file risks
- [ ] `output/roadmap.json` validates, contains prioritized refactoring items
- [ ] `output/report.pdf` exists and contains all 7 report sections
- [ ] REST API on :8000 serves all endpoints with correct data
- [ ] Dashboard on :3000 renders health score, hotspots, findings, silos, risks, roadmap
- [ ] `docs/DECISIONS.md` has all 12 decisions documented
- [ ] All unit tests pass (analyzer-core, git-miner, predictor, report-engine)
- [ ] Integration test script passes
- [ ] README.md quickstart actually works

---

## Appendix: Commit Strategy

Use conventional commits on the `feature/full-mvp` branch:

```
feat(schemas): add JSON schemas for inter-component communication
feat(analyzer-core): implement CRTP rule engine with 22 rules
feat(git-miner): implement git metrics extraction and SZZ labeling
feat(predictor): implement XGBoost pipeline with SHAP explanations
feat(report-engine): implement FastAPI + WeasyPrint PDF generation
feat(dashboard): implement React dashboard with Recharts visualizations
feat(cli): implement CLI orchestrator with CLI11
feat(docker): complete Dockerfiles and integration test
docs(decisions): document all architectural decisions
test(integration): add end-to-end pipeline test
```

Squash-merge to `main` when all checks pass.
