---
name: demo-report
description: Generate a polished demo report by running cppulse on a real open-source
             repo and capturing the output. Manual invocation only — has side effects
             (runs the full pipeline, writes to demo/ folder).
disable-model-invocation: true
context: fork
allowed-tools: Bash, Read, Write
---

# demo-report Skill

## When to Use
Week 4 (POCO), Week 6 (OpenCV, Godot), Week 8 (final demos).
Always run on a freshly cloned target repo, not a cached copy.

## Steps

1. **Clone the target repo** into a temp directory:
   ```bash
   git clone --depth=500 <repo_url> /tmp/<repo_name>
   ```

2. **Run the full pipeline**:
   ```bash
   docker-compose run --rm analyzer-core /tmp/<repo_name>
   docker-compose run --rm git-miner /tmp/<repo_name>
   docker-compose run --rm predictor
   docker-compose run --rm report-engine
   ```

3. **Capture outputs**: copy from `output/` to `demo/<repo_name>/`:
   - `findings.json`
   - `git_metrics.json`
   - `risk_scores.json`
   - `roadmap.json`
   - `report.pdf`

4. **Write executive summary**: `demo/<repo_name>/executive-summary.md`:
   - Key stats: total findings, top 3 rules violated, silo count, top risk file
   - 3 key insights (what would surprise the repo maintainers?)
   - 3 recommended actions (prioritized by ROI from roadmap.json)

5. **Update README**: add a row to the Demo Results table with repo name,
   finding count, top finding type, and link to demo folder.

6. **Confirm**: "Demo generated: demo/<repo_name>/ — N findings, N silos, PDF: <size>KB."
