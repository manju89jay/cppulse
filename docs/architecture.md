# cppulse System Architecture

## Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLI (C++17 / CLI11)                         │
│              cppulse analyze | report | watch                   │
└──────┬──────────────┬───────────────┬───────────────────────────┘
       │              │               │
       ▼              ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────────────┐
│ analyzer-    │ │  git-miner   │ │         predictor            │
│ core (C++17) │ │   (Python)   │ │         (Python)             │
│              │ │              │ │                              │
│ libclang     │ │ gitpython /  │ │ XGBoost ML pipeline          │
│ 22 rules     │ │ PyDriller    │ │ SZZ labeling                 │
│ CRTP engine  │ │ 10 features  │ │ Bug probability per file     │
│ JSON output  │ │ Silo detect  │ │ Refactoring roadmap          │
└──────┬───────┘ └──────┬───────┘ └──────────┬───────────────────┘
       │                │                    │
       └────────────────┴────────────────────┘
                        │  JSON (findings.json + git_metrics.json)
                        ▼
              ┌──────────────────────┐
              │    report-engine     │
              │      (Python)        │
              │ FastAPI REST API     │
              │ WeasyPrint PDF       │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  dashboard (React/TS)│
              │  Recharts + Tailwind │
              │  Health score        │
              │  Hotspot treemap     │
              │  Silo alerts         │
              │  Bug predictions     │
              │  Refactoring roadmap │
              └──────────────────────┘
```

## Data Flow
1. CLI receives target repo path, validates it is a C++ git repo
2. `analyzer-core` runs libclang static analysis → emits `output/findings.json`
3. `git-miner` runs git log analysis → emits `output/git_metrics.json`
4. `predictor` merges both JSONs, engineers features, trains XGBoost → emits `output/risk_scores.json` + `output/roadmap.json`
5. `report-engine` consumes all outputs → generates `output/report.pdf` + serves REST API on :8000
6. `dashboard` reads from REST API → interactive UI on :3000

## Inter-Component Communication
All components communicate via JSON files written to `./output/` directory (ADR-004).
Schema: each component validates its input against a defined JSON schema before processing.

## Detection Rules (22 total in analyzer-core)
| Category          | Rules | IDs              |
|-------------------|-------|------------------|
| Memory Safety     | 3     | CPP-MOD-001–003  |
| Modernization     | 9     | CPP-MOD-004–012  |
| Complexity        | 3     | CPP-MOD-013–015  |
| MISRA C++ Subset  | 7     | MISRA-001–007    |

## Key Libraries Per Component
| Component     | Language | Key Libraries                          |
|---------------|----------|----------------------------------------|
| analyzer-core | C++17    | libclang, nlohmann/json, spdlog, CLI11 |
| git-miner     | Python   | gitpython, pandas, numpy               |
| predictor     | Python   | xgboost, scikit-learn, pandas          |
| report-engine | Python   | fastapi, uvicorn, jinja2, weasyprint   |
| dashboard     | TS/React | recharts, tailwindcss, vite            |
| cli           | C++17    | CLI11, fmt                             |

## Port Map (local dev)
- report-engine API: `localhost:8000`
- dashboard:         `localhost:3000`
- API docs (Swagger): `localhost:8000/docs`
