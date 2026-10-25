---
title: "Issue 3: canonical PostgreSQL persistence"
description: "Add typed canonical storage, integrity constraints, additive migrations, and guarded real-database verification."
status: in-progress
priority: P1
effort: 24h
issue: 3
branch: docs/issue-3-persistence-plan
tags: [backend, database, feature]
blockedBy: []
blocks: []
created: 2026-10-25
---

# Canonical persistence

Issue [#3](https://github.com/agent-bean/email_support/issues/3) is in Review through open [PR #29](https://github.com/agent-bean/email_support/pull/29); owner acceptance is pending. SQLAlchemy + Alembic is selected; the owner accepted the corrected plan on 2026-10-25. Implementation is in progress on `feat/issue-3-canonical-persistence`. Cook flags: `--tdd --yagni`.

## Outcome and boundary

Persist all requested canonical families with typed storage operations, stable IDs, provider-scoped uniqueness, provenance, UTC timestamps, immutable briefing history, exact historical approval bindings, and transaction rollback. Prove empty installation, real cross-revision preservation, reconnect durability, and restore using PostgreSQL.

Use async SQLAlchemy 2 + Psycopg 3, Alembic, and separate Pydantic contracts. Callers own sessions and transactions; helpers flush without committing. No generic repository framework, API/UI, authentication, provider connections, worker/jobs, checkpoints, delivery, or Neo4j/Qdrant execution. Account fields only namespace external IDs.

File inventories and command paths are relative to the repository root; Markdown links resolve relative to their document.

## Phases and dependencies

| Phase | Execution detail | Depends on | Effort |
| --- | --- | --- | --- |
| 1 | [Core schema, safe database harness](phase-01-start.md) | Owner plan acceptance (satisfied) | 10h |
| 2 | [Complete storage and invariants](phase-02-typed-storage-and-invariants.md) | Phase 1 checks | 10h |
| 3 | [CI and maintainer verification](phase-03-local-ci-and-verification.md) | Phase 2 checks | 4h |

One executor owns each phase sequentially. Shared files transfer ownership only after the predecessor finishes. Two real additive revisions separate core inputs/evidence/briefings from approvals/knowledge/projection metadata. Phase checklists and `ak plan status` own execution progress.

## Acceptance evidence

- [ ] Every requested family has concrete contracts, columns, foreign keys and meaningful persistence tests.
- [ ] Duplicate provider keys, orphan references, cross-briefing approvals, replacement knowledge text and ordinary SQL changes/TRUNCATE of immutable history fail; coordinated two-session tests prove locking.
- [ ] Caller rollback removes all partial writes, including approval + action; a new connection reads committed records.
- [ ] Both production Alembic revisions install empty and preserve seeded first-revision records on upgrade.
- [ ] Fresh guarded scenario targets isolate migration/storage/restore paths; backups precede mutations and cleanup. Failed backup stops verified owned processes while retaining recovery data.
- [ ] Projection metadata records only exact canonical source/embedding provenance; invalidated knowledge is excluded immediately.
- [ ] Database checks are mandatory in Backend CI; credential-free health, export and `make check` remain available locally.
- [ ] Existing lint/type/build/contract checks pass with no generated API drift.

## Evidence and review gates

[Accepted direction](../reports/brainstorm-261025-1529-issue-3-canonical-persistence.md), [scout](../reports/scout-261025-1529-issue-3-persistence.md), [storage research](../reports/researcher-261025-1529-issue-3-storage-contracts.md), [database research](../reports/researcher-261025-1529-issue-3-database-verification.md). Research suggestions to defer preservation or use asyncpg are superseded by this plan's two real revisions and Psycopg 3 selection.

Implementation and local verification evidence are recorded in the phase files. At the time of review, PR #29's original head `bf70387877242b81197d694ef5cb5af3c2d2781b` had all four checks passed. Review fixes were committed as `de1dd44f7eabbde6b96ec3f3ba9d61bc4d45daf6`; Backend, Web, API contracts and Smoke passed on that revision in GitHub Actions run [40190386860](https://github.com/agent-bean/email_support/actions/runs/40190386860). Owner acceptance remains pending.

## Red Team Review

Three independent reviewers produced six distinct findings: three High and three Medium. Owner approved all six on 2026-10-25; all are applied across the phases. See the [decisions and verification record](../reports/validation-261025-1529-issue-3-persistence.md). TRUNCATE guards, coordinated concurrency tests, immutable selected-text binding, coherent projection states, fresh targets and recovery-safe cleanup are required implementation outcomes.

## Validation Log

Session 1, 2026-10-25: owner answered “Apply all six (Recommended)” to the recorded review question. Corrections are propagated to schema, operations, tests and lifecycle requirements. Phase checklists and the local plan index provide tracking; no applicable live task-management tool was available. Plan acceptance and implementation permission are separate from correction approval.

### Whole-plan consistency sweep

All four plan files reread against the six approved deltas; superseded serial-only, arbitrary knowledge-content, mismatched projection-version and unconditional cleanup claims removed. Structural/link checks and pending-task parsing are recorded in the validation report. No unresolved design contradiction remains; implementation checks are recorded in the phase files.

## Readiness

Session 2, 2026-10-25: owner accepted the plan (“tôi thấy plan này ổn rồi”) and requested relative paths. File inventories and the cook handoff now use repository-relative paths. Session 3 implemented the accepted scope and completed local checks. At that point hosted CI had not run, no PR existed, and Issue #3 had not been changed. At the time of this state update, PR #29 was open, all four checks passed at its original head, and Issue #3 was in Review. Review fixes were then committed and locally verified; hosted CI passed for `de1dd44` and owner acceptance remains pending.
