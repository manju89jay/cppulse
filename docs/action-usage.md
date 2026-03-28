# Using cppulse in Your CI Pipeline

> Add automated C++ health analysis to any GitHub repository in 2 minutes.

## Quick Setup

Add this workflow file to your repository at `.github/workflows/cppulse.yml`:

```yaml
name: cppulse Health Report

on:
  pull_request:
    paths: ['**/*.cpp', '**/*.h', '**/*.hpp']

permissions:
  contents: read
  pull-requests: write

jobs:
  cppulse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: manju89jay/cppulse/.github/actions/cppulse@main
        with:
          post-comment: 'true'
```

That's it. Every PR that touches C++ files will get a health report comment.

## What You Get

On each PR, cppulse posts a comment with:

- **Health Score** (0-100) broken down by memory safety, modernization, complexity, and MISRA compliance
- **Findings Summary** — errors, warnings, and info-level findings
- **New Findings** — issues introduced by this specific PR (diff against base branch)
- **Top Risk Files** — files with highest bug probability (ML-powered)
- **Roadmap** — prioritized refactoring suggestions with estimated hours

## Configuration

| Input | Default | Description |
|-------|---------|-------------|
| `repo-path` | `.` | Path to the C++ source tree |
| `base-ref` | auto | Base branch for diff (e.g., `origin/main`) |
| `post-comment` | `true` | Post results as a PR comment |
| `generate-pdf` | `false` | Generate PDF report as artifact |
| `fail-on-regression` | `false` | Fail the check if new findings are introduced |
| `github-token` | `${{ github.token }}` | Token for PR comments |

## Outputs

| Output | Description |
|--------|-------------|
| `health-score` | Overall health score (0-100) |
| `findings-count` | Total number of findings |
| `new-findings` | Number of new findings in this PR |

### Using outputs in subsequent steps

```yaml
- uses: manju89jay/cppulse/.github/actions/cppulse@main
  id: cppulse

- run: echo "Health score is ${{ steps.cppulse.outputs.health-score }}"
```

## Advanced: Fail on Regression

To block PRs that introduce new findings:

```yaml
- uses: manju89jay/cppulse/.github/actions/cppulse@main
  with:
    fail-on-regression: 'true'
    base-ref: 'origin/${{ github.base_ref }}'
```

## Advanced: PDF Report as Artifact

```yaml
- uses: manju89jay/cppulse/.github/actions/cppulse@main
  with:
    generate-pdf: 'true'

- uses: actions/upload-artifact@v4
  with:
    name: cppulse-report
    path: cppulse-output/report.pdf
```

## Requirements

- **Full git history**: Set `fetch-depth: 0` in `actions/checkout` for accurate git analysis. With shallow clones, git-miner is skipped and only static analysis runs.
- **Permissions**: The workflow needs `pull-requests: write` to post comments.
- **No API keys**: cppulse runs entirely locally — no external services or accounts needed.

## Detection Rules (22)

cppulse checks for 22 patterns across 4 categories:

| Category | Rules | Examples |
|----------|-------|---------|
| Memory Safety (3) | CPP-MEM-001–003 | Raw `new`, `delete`, C-style arrays |
| Modernization (9) | CPP-MOD-001–009 | C-casts, `typedef`, unscoped `enum`, missing `override` |
| Complexity (3) | CPP-CX-001–003 | Cyclomatic complexity, function length, parameter count |
| MISRA C++ (7) | MISRA-001–007 | `goto`, unions, `malloc`, recursion, uninitialized vars |

## Performance

| Repo Size | Analysis Time |
|-----------|---------------|
| < 10K LOC | < 1 minute |
| 100K LOC | ~2 minutes |
| 640K LOC (POCO) | ~5 minutes |
| 1M+ LOC | ~10 minutes |

For large repos, cppulse automatically analyzes only changed files in PR mode.
