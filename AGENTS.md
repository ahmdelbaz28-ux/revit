# AGENTS.md — Workspace Skill Configuration

## Active Skills

The following skills are installed and active for this workspace. **Use them before any response.**

### 0. `using-superpowers` (META — always active)

- **Location:** `.agents/skills/using-superpowers/SKILL.md`
- **References:** `.agents/skills/using-superpowers/references/`
- **When:** EVERY conversation. Establishes the rule that skills must be invoked before ANY action.
- **Scope:** Enforces skill-first behavior, prevents rationalization, sets priority order for multi-skill tasks.

### 1. `vercel-react-best-practices`

- **Location:** `.agents/skills/vercel-react-best-practices/`
- **Rules:** `.agents/skills/vercel-react-best-practices/rules/`
- **Full guide:** `.agents/skills/vercel-react-best-practices/AGENTS.md`
- **When:** Any React/Next.js code generation, refactoring, or review.
- **Scope:** 70 rules across 8 categories (waterfalls, bundle, server, client, re-renders, rendering, JS perf, advanced).

### 2. `frontend-design`

- **Location:** `.agents/skills/frontend-design/SKILL.md`
- **When:** Building new UI or reshaping existing UI. Distinctive, intentional visual design.
- **Scope:** Aesthetic direction, typography, palette, layout, copy, motion, restraint.

### 3. `superdesign`

- **Location:** `.agents/skills/superdesign/SKILL.md`
- **References:** `.agents/skills/superdesign/references/`
- **When:** Building or refactoring design systems, creating component libraries, establishing design tokens, implementing consistent UI patterns.
- **Scope:** Design token systems, component architecture, accessibility standards, safety-critical UI patterns, visual design principles.

### 4. `security-audit`

- **Location:** `.agents/skills/security-audit/SKILL.md`
- **References:** `.agents/skills/security-audit/` (RECONNAISSANCE.md, HUNTING.md, ATTACK-CLASSES.md, VALIDATION-AND-REPORTING.md, CLIENT-SIDE.md, AI-AND-LLM.md, WEB-PROTOCOL-AND-AUTH.md, MEMORY-SAFETY-AND-BINARY.md)
- **When:** Security audits, vulnerability reviews, penetration testing code reviews, finding exploitable bugs.
- **Scope:** 6-phase methodology — Recon, Hunt, Validate, Report, Structured Output, Independent Verification. Focuses on exploitable vulnerabilities with real impact, not theoretical concerns.

## Rules

1. **Always invoke a relevant skill before acting.** If a skill applies to the task, use it — no exceptions.
2. **Read the full rule files** from the `rules/` directory when working on specific React patterns.
3. **Plan before code.** For design tasks, brainstorm a token system (color, type, layout, signature) before writing CSS/JSX.
4. **Critique your own work.** After implementing, review against the skill guidelines before presenting.

## Skill Priority (from using-superpowers)

When multiple skills apply, process skills come first — they set the approach, then implementation skills carry it out.

- **Multi-skill tasks:** process skill first → implementation skill next
- **User instructions** (this file) override skills, which override default behavior
- If you think there is even a 1% chance a skill applies, invoke it

## Project Context

- **Stack:** React + Vite (client-only SPA), TypeScript, Tailwind CSS, GSAP
- **Not Next.js** — skip server-side rules (RSC, `next/dynamic`, `next/script`, `after()`, server actions).
- **Most relevant rules:** Bundle size (barrel imports, dynamic imports), re-render optimization, JS perf, rendering perf.
