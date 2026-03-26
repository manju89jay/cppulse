#!/bin/bash
# cppulse GitHub Action entrypoint
# Runs the full analysis pipeline and optionally posts PR comments
set -eo pipefail

REPO_PATH="${INPUT_REPO_PATH:-.}"
BASE_REF="${INPUT_BASE_REF:-}"
POST_COMMENT="${INPUT_POST_COMMENT:-true}"
GENERATE_PDF="${INPUT_GENERATE_PDF:-false}"
FAIL_ON_REGRESSION="${INPUT_FAIL_ON_REGRESSION:-false}"

OUTPUT_DIR="/tmp/cppulse-output"
mkdir -p "$OUTPUT_DIR"

echo "::group::cppulse Configuration"
echo "  Repo path:         $REPO_PATH"
echo "  Base ref:          ${BASE_REF:-auto-detect}"
echo "  Post comment:      $POST_COMMENT"
echo "  Generate PDF:      $GENERATE_PDF"
echo "  Fail on regression: $FAIL_ON_REGRESSION"
echo "::endgroup::"

# ── Step 1: Static Analysis ────────────────────────────────────
echo "::group::Running cppulse-analyzer"
cppulse-analyzer --repo "$REPO_PATH" --output "$OUTPUT_DIR" || {
    echo "::warning::analyzer-core failed — continuing with partial results"
}
echo "::endgroup::"

# ── Step 2: Git Mining (skip on shallow clone) ─────────────────
echo "::group::Running git-miner"
GIT_DEPTH=$(git -C "$REPO_PATH" rev-list --count HEAD 2>/dev/null || echo "0")

if [ "$GIT_DEPTH" -gt 10 ]; then
    cd /app/git-miner
    python3 -m src.main --repo "$REPO_PATH" --output "$OUTPUT_DIR" || {
        echo "::warning::git-miner failed — continuing with partial results"
    }
else
    echo "::warning::Shallow clone detected ($GIT_DEPTH commits). Skipping git-miner."
    echo "::warning::Set fetch-depth: 0 in actions/checkout for full git analysis."
    # Create minimal git_metrics.json
    cat > "$OUTPUT_DIR/git_metrics.json" <<GEOF
{
  "version": "1.0.0",
  "metadata": {
    "repo_path": "$REPO_PATH",
    "analyzed_at": "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)",
    "commit_range": "shallow",
    "total_commits": $GIT_DEPTH
  },
  "file_metrics": [],
  "knowledge_silos": []
}
GEOF
fi
echo "::endgroup::"

# ── Step 3: Predictor ──────────────────────────────────────────
echo "::group::Running predictor"
cd /app/predictor
python3 -m src.main --input "$OUTPUT_DIR" --output "$OUTPUT_DIR" || {
    echo "::warning::predictor failed — continuing with partial results"
}
echo "::endgroup::"

# ── Step 4: Extract results ────────────────────────────────────
HEALTH_SCORE="0"
FINDINGS_COUNT="0"

if [ -f "$OUTPUT_DIR/risk_scores.json" ]; then
    HEALTH_SCORE=$(jq -r '.health_score.overall' "$OUTPUT_DIR/risk_scores.json" 2>/dev/null || echo "0")
fi

if [ -f "$OUTPUT_DIR/findings.json" ]; then
    FINDINGS_COUNT=$(jq -r '.summary.total_findings' "$OUTPUT_DIR/findings.json" 2>/dev/null || echo "0")
fi

echo "Health Score: $HEALTH_SCORE/100"
echo "Total Findings: $FINDINGS_COUNT"

# ── Step 5: Diff against base (if in PR context) ──────────────
NEW_FINDINGS="0"
if [ -n "$BASE_REF" ] && [ -f "$OUTPUT_DIR/findings.json" ]; then
    echo "::group::Computing diff against $BASE_REF"

    BASE_OUTPUT="/tmp/cppulse-base"
    mkdir -p "$BASE_OUTPUT"

    # Analyze only changed files at base ref for speed
    CHANGED_FILES=$(git -C "$REPO_PATH" diff --name-only "$BASE_REF"...HEAD -- '*.cpp' '*.h' '*.hpp' 2>/dev/null || echo "")

    if [ -n "$CHANGED_FILES" ]; then
        # Stash current state, checkout base, analyze, restore
        CURRENT_SHA=$(git -C "$REPO_PATH" rev-parse HEAD)
        git -C "$REPO_PATH" checkout "$BASE_REF" --quiet 2>/dev/null || true
        cppulse-analyzer --repo "$REPO_PATH" --output "$BASE_OUTPUT" 2>/dev/null || true
        git -C "$REPO_PATH" checkout "$CURRENT_SHA" --quiet 2>/dev/null || true

        if [ -f "$BASE_OUTPUT/findings.json" ]; then
            NEW_FINDINGS=$(python3 /app/diff_findings.py \
                "$BASE_OUTPUT/findings.json" \
                "$OUTPUT_DIR/findings.json" 2>/dev/null || echo "0")
        fi
    fi
    echo "New findings: $NEW_FINDINGS"
    echo "::endgroup::"
fi

# ── Step 6: Generate PDF (if requested) ────────────────────────
if [ "$GENERATE_PDF" = "true" ]; then
    echo "::group::Generating PDF report"
    cd /app/report-engine
    python3 -c "
from src.pdf_generator import PDFGenerator
from pathlib import Path
gen = PDFGenerator(Path('$OUTPUT_DIR'))
pdf = gen.generate_pdf()
Path('$OUTPUT_DIR/report.pdf').write_bytes(pdf)
print(f'PDF generated: {len(pdf):,} bytes')
" || echo "::warning::PDF generation failed"
    echo "::endgroup::"
fi

# ── Step 7: Post PR comment ───────────────────────────────────
if [ "$POST_COMMENT" = "true" ] && [ -n "$GITHUB_EVENT_PATH" ]; then
    echo "::group::Posting PR comment"
    PR_NUMBER=$(jq -r '.pull_request.number // empty' "$GITHUB_EVENT_PATH" 2>/dev/null || echo "")

    if [ -n "$PR_NUMBER" ] && [ -n "$GITHUB_REPOSITORY" ]; then
        python3 /app/post_comment.py \
            --output-dir "$OUTPUT_DIR" \
            --repo "$GITHUB_REPOSITORY" \
            --pr "$PR_NUMBER" \
            --new-findings "$NEW_FINDINGS" \
            --token "$GITHUB_TOKEN" || echo "::warning::Failed to post PR comment"
    else
        echo "Not a PR context — skipping comment"
    fi
    echo "::endgroup::"
fi

# ── Step 8: Regression check ──────────────────────────────────
if [ "$FAIL_ON_REGRESSION" = "true" ] && [ "$NEW_FINDINGS" -gt 0 ] 2>/dev/null; then
    echo "::error::Health regression: $NEW_FINDINGS new findings introduced"
    exit 1
fi

# ── Set outputs ────────────────────────────────────────────────
echo "health-score=$HEALTH_SCORE" >> "$GITHUB_OUTPUT"
echo "findings-count=$FINDINGS_COUNT" >> "$GITHUB_OUTPUT"
echo "new-findings=$NEW_FINDINGS" >> "$GITHUB_OUTPUT"

# Copy outputs to workspace for artifact upload
if [ -d "$GITHUB_WORKSPACE" ]; then
    cp -r "$OUTPUT_DIR" "$GITHUB_WORKSPACE/cppulse-output" 2>/dev/null || true
fi

echo "cppulse analysis complete."
