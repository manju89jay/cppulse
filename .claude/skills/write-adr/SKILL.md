---
name: write-adr
description: Generate an Architecture Decision Record for an architectural decision
             just made. Invoke immediately after any decision about technology choice,
             component design, or inter-component interface.
allowed-tools: Read, Write, Glob
---

# write-adr Skill

## Steps

1. **Read the template**: `docs/adr/ADR-000-template.md`

2. **Find next ADR number**: list `docs/adr/` and take the next sequential number

3. **Gather the decision context** by asking:
   - What problem were we solving?
   - What did we decide to do?
   - What alternatives did we genuinely consider?
   - What are the downsides of our choice?

4. **Write the ADR** at `docs/adr/ADR-NNN-<kebab-case-title>.md`
   - Context: explain the SITUATION that forced a decision, not just background
   - Decision: one clear sentence stating what was decided
   - Consequences: be honest about both positive AND negative
   - Alternatives: at least 2 real alternatives with honest rejection reasons

5. **Update CLAUDE.md**: append a one-line summary to the "Key Decisions" section:
   `- ADR-NNN: <one-line summary>`

6. **Confirm**: "ADR-NNN written at docs/adr/ADR-NNN-<title>.md. CLAUDE.md updated."

## Quality Check
An ADR is good if: reading the Alternatives section makes you genuinely wonder if
the wrong choice was made — that tension proves the alternatives were real.
