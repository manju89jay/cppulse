---
name: review-code
description: Deep code review of recently implemented code. Invoke after every
             3-4 implementation tasks. Delegates to code-reviewer agent.
context: fork
allowed-tools: Read, Grep, Glob, Write
---

# review-code Skill

## When to Use
After every 3–4 implementation tasks, or before any major milestone commit.
Never skip this step — the review catches issues that tests don't.

## Steps

1. **Identify scope**: list all files modified since the last review
   (use `git diff --name-only HEAD~4 HEAD` or similar)

2. **Invoke code-reviewer agent**: pass it the list of modified files and ask for
   a full review covering correctness, C++/Python quality, architecture, and
   portfolio readiness

3. **Triage findings**:
   - Critical: fix before any commit
   - Major: fix before end of week
   - Minor: add to backlog

4. **Write review record**: save to `docs/reviews/review-<YYYY-MM-DD>-<component>.md`

5. **Create follow-up tasks**: for each Critical and Major finding,
   add a task to `docs/specs/<feature>/tasks.md`

6. **Report**: "Review complete. N findings: X critical, Y major, Z minor.
   Top 3 to fix: <list>."
