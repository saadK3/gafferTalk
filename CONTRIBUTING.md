# Contributing to GafferTalk

GitHub Issues are the source of truth for planned work, decisions, and defects.
By contributing, you acknowledge that the project is source-available under
the terms in [LICENSE.md](LICENSE.md), rather than under an OSI-approved
open-source license.

## Workflow

1. Start with an issue containing a user-visible outcome and acceptance criteria.
2. Keep a change focused on one issue where practical.
3. Create a short-lived branch from the default branch.
4. Open a pull request that links the issue and explains how the change was tested.
5. Merge only after the acceptance criteria and relevant automated checks pass.

Suggested branch names:

```text
feature/12-load-fpl-team
fix/34-transfer-budget-rounding
docs/8-data-source-notes
```

Commit messages should be concise and imperative, for example:

```text
Add FPL team lookup endpoint
Fix club-limit validation
Document projection assumptions
```

## Issue labels

Use a type and priority where applicable:

- Types: `feature`, `bug`, `data`, `model`, `infrastructure`, `documentation`, `research`
- Priorities: `P0-launch-blocker`, `P1-important`, `P2-later`

Do not mark work as complete merely because code exists. The issue's acceptance
criteria must be demonstrably satisfied.

## Product rules

- Never treat an FPL Team ID as authentication.
- Never ask for or store an FPL password.
- Never let the language model determine whether a transfer is legal.
- Never present unknown user state as observed fact.
- Show material assumptions and data freshness with recommendations.
