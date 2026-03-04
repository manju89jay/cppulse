# ADR-005: PDF Report as Primary Deliverable

**Date:** 2026-03-04
**Status:** Accepted
**Deciders:** Manjunath Jayaramaiah

---

## Context
cppulse produces analysis results consumed in two ways: engineers exploring
interactively (dashboard), and managers making decisions in meetings (reports).
The question is whether a web dashboard alone is sufficient, or whether a
portable document format is also needed.

## Decision
Generate a **PDF executive report** alongside the interactive web dashboard.

## Consequences

### Positive
- Portability: PDFs go into slide decks, emails, Confluence pages, and Jira tickets
  without requiring the recipient to run any software
- Management communication: engineering managers need a shareable artifact to
  justify refactoring investment to leadership — a URL requires VPN access and
  a running server
- Offline use: PDFs work in meetings without internet or running containers
- PO credibility: generating a PDF report is a product decision, not just a
  technical one — it demonstrates understanding of the full user workflow

### Negative
- Additional dependency: WeasyPrint + Jinja2 add ~50MB to the report-engine image
- PDF is static — interactive drill-down requires the dashboard

### Neutral
- Both outputs are generated from the same data — no duplication of logic
- Dashboard is for exploration; PDF is for decision-making (complementary, not redundant)

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Web dashboard only | Cannot be attached to an email or dropped into a slide deck. Requires a running server to view. Not suitable for async stakeholder communication. |
| Excel/CSV report | No charts. Harder to share with non-technical managers. |
| Markdown report | Not renderable outside a development environment. |
