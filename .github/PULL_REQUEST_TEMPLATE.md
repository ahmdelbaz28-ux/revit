## What does this PR do?

<!-- One sentence summary. -->

## Why is this change needed?

<!-- Link to issue, audit report, or describe the problem. -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (existing behavior changes)
- [ ] Safety-critical: modifies regulatory data (NFPA/NEC/IEC/etc.)
- [ ] Security hardening
- [ ] Documentation / governance only
- [ ] Test changes only

## Safety-critical checklist (REQUIRED if you checked "Safety-critical")

- [ ] I have read `agent.md` in full
- [ ] Commit message includes either:
  - `Signed-off-by: <name> PE/FPE <license-number>` trailer, OR
  - Verbatim citation of published standard (e.g., "NFPA 72-2022 §17.7.3.2.3.1")
- [ ] I have verified no other implementation of the same regulatory
      data exists in the repo (Rule 23: single source of truth)
- [ ] Tests cover both the new behavior AND boundary conditions
- [ ] Behavioral diff documented in commit message

## Verification

```
# Paste the output of:
pytest tests/ -q --tb=line | tail -3
ruff check fireai/ qomn_conduit/ parsers/ backend/
bandit -ll -r fireai/ parsers/ backend/
```

## Risks

<!-- What could break? Who needs to know? -->

## Rollback plan

<!-- If this PR causes problems in production, how do we undo it? -->
