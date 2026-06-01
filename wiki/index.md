# FireAI Knowledge Wiki — Index

> This wiki follows the LLM Wiki pattern (Karpathy, 2026). It is a persistent, compounding artifact maintained by the AI agent. Every page cross-references related pages. The index is content-oriented; the log is chronological.

## Architecture

- [[architecture/overview|System Architecture Overview]]
- [[architecture/ai-providers|AI Provider Integration Architecture]]
- [[architecture/safety-philosophy|Safety-First Design Philosophy]]

## Standards & Codes

- [[standards/nfpa72|NFPA 72 — National Fire Alarm and Signaling Code]]
- [[standards/nec|NEC — National Electrical Code (Chapter 7-9)]]
- [[standards/bs5839|BS 5839 — Fire Detection and Alarm Systems]]

## Bug Fix History (Critical Lessons)

- [[bug-fixes/V12-critical|V12 — 3 CRITICAL Life-Safety Bugs]]
- [[bug-fixes/V12-round2|V12 Round 2 — Atrium Deletion + Obstruction Bypass]]
- [[bug-fixes/V12-round3|V12 Round 3 — Bridges Layer (4 Bugs)]]
- [[bug-fixes/V13-safety|V13 — Point-Cloud Coverage Illusion + PARTIAL Status]]
- [[bug-fixes/V14-fallacies|V14 — DC Return Path + AABB Rotation + A* Crosses]]
- [[bug-fixes/V18-cause-effect|V18 — Cause & Effect Matrix + Conduit Fill (15 Errors)]]
- [[bug-fixes/V43-deep-audit|V43 — Deep Safety Audit (8 CRITICAL + 9 HIGH)]]

## Design Decisions

- [[decisions/001-coverage-method|Decision 001: Area-Based Coverage vs Point-Counting]]
- [[decisions/002-detector-placement|Decision 002: Greedy Farthest-Point vs K-Means]]
- [[decisions/003-status-terminology|Decision 003: APPROVED/REJECTED/REQUIRES_MANUAL_REVIEW]]
- [[decisions/004-ai-safety|Decision 004: AI is ADVISORY Only — Never Authoritative]]

## Wiki Operations

- **Ingest**: Add new source → read → extract key info → update wiki pages → update index → append to log
- **Query**: Read index → find relevant pages → read them → synthesize answer → optionally file answer as new page
- **Lint**: Check for contradictions, orphan pages, missing cross-references, stale claims, data gaps

## Statistics

- Total pages: 15+
- Bug fixes documented: 60+
- Standards referenced: 3 (NFPA 72, NEC, BS 5839)
- Last updated: 2026-05-30
