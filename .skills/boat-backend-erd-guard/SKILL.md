---
name: boat-backend-erd-guard
description: Use this skill when working on the BOUT backend database schema, migrations, backend models, repositories, API contracts, OCR/AI save flow, files, receipts, warranties, auth, or ingestion features. It protects bounded-context database rules, hard delete policy, application-level cross-BC consistency, and OCR trust boundaries.
---

# BOUT Backend ERD Guard

## Purpose

Protect the BOUT backend architecture while planning and implementing changes.

The ERD is not only a table list. It defines bounded contexts, aggregate ownership, allowed FK boundaries, delete policy, and the OCR/AI trust boundary.

## Mandatory Workflow

Do not write code immediately for ERD, DB, API contract, OCR save flow, file reference, receipt, warranty, auth, or ingestion work.

Follow this order:

1. Read `docs/agent/ERD_SOURCE.md`.
2. Read `docs/agent/INVARIANTS.md`.
3. Research the current codebase.
4. Update `docs/agent/RESEARCH.md`.
5. Update `docs/agent/GAP_REPORT.md` when ERD/code differences matter.
6. Update `docs/agent/PLAN.md`.
7. Wait for explicit approval.
8. Implement only the approved scope.
9. Run tests and checks.
10. Update `docs/agent/TEST_RESULT.md`.

If approval has not been given, do not modify production code.

## Core Invariants

- No cross-BC database foreign keys.
- Same-BC foreign keys are allowed only when the aggregate boundary permits them.
- Use hard delete unless an explicit decision changes the policy.
- Cross-BC consistency belongs in the application layer or events.
- Keep `receipts` and `warranties` as separate aggregates.
- Keep file storage ownership in files BC.
- Receipt APIs may store file IDs as logical references, but must not own object storage internals.
- OCR/AI output is untrusted until user review/correction.
- Raw refresh tokens must never be stored.

## Required Research Output

When researching, include:

- related files
- current request/response flow
- current data flow
- existing validation
- DB constraints
- BC boundary risks
- similar existing logic
- tests to run
- unknowns

## Required Plan Output

When planning, include:

- scope
- out of scope
- Riido/GitHub reference
- files to change
- why each file changes
- API contract
- migration plan
- invariant checks
- test plan
- rollback plan

## Prohibited Actions

Do not:

- add cross-BC DB foreign keys
- add soft delete fields
- merge receipts and warranties
- store raw refresh tokens
- store OCR output as final receipt/warranty data without user confirmation
- modify code before approval
- change unrelated BCs
- add broad refactors to a feature PR

## Stop Conditions

Stop and ask for approval when:

- a change requires a cross-BC FK
- current PRD and ERD conflict
- a migration changes production data shape
- OCR result would be saved as final data without user review
- ownership overlaps with files/storage or notifications
