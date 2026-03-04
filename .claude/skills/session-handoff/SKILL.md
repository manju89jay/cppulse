---
name: session-handoff
description: Write a session state summary at the end of every Claude Code session.
             Run this manually before closing any session. Preserves context for
             the next session via auto-memory.
disable-model-invocation: true
context: fork
allowed-tools: Read, Write, Bash
---

# session-handoff Skill

Run this at the END of every session, before closing Claude Code.

## Steps

1. **Capture git state**:
   ```bash
   git diff --name-only HEAD  # uncommitted changes
   git log --oneline -5       # last 5 commits
   ```

2. **Write `.claude/session-state.md`** (overwrites previous):
   ```markdown
   # Session State — <date> <time>

   ## Session Name
   <current /rename value>

   ## What Was Built This Session
   - <bullet list of features/files implemented>

   ## Tests Status
   - analyzer-core: N/N passing
   - <other components>: N/N passing

   ## Uncommitted Changes
   <list from git diff>

   ## Decisions Made (ADRs if applicable)
   - <any architectural decisions, even informal ones>

   ## Next Session: Start Here
   <exact task to pick up next — be specific enough to start without re-reading>

   ## Context Fill at End of Session
   <approximate %>
   ```

3. **Commit if clean**: if all tests pass and no uncommitted breaking changes,
   commit with message: `chore: session handoff <date>`

4. **Confirm**: "Session state written to .claude/session-state.md. Ready to close."
