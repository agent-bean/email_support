# Issue #3 persistence direction

Status: SQLAlchemy + Alembic selected by the owner; implementation plan pending.

Issue: https://github.com/agent-bean/email_support/issues/3

## Outcome and scope

Persist normalized inputs, company/contact identities, evidence, briefings and immutable versions, approvals/actions, approved knowledge/preferences, and projection bookkeeping in PostgreSQL. Records must survive reconnects and failed transactions without losing integrity.

## Constraints

Carry `--yagni` into planning and implementation. Keep fields and storage operations tied to the issue's requirements. Separate Pydantic application contracts from ORM rows where their contracts differ. Enforce stable IDs, foreign keys, provider uniqueness, aware UTC timestamps, explicit missing values, provenance, and immutable briefing versions.

Use SQLAlchemy and Alembic. Review generated migrations explicitly. Back up the target database before any schema or data change, including migration verification. Keep development and test databases separate.

## Non-goals

No CRUD screens, provider connections or synchronization, worker/jobs/scheduling, external delivery, LangGraph checkpoints, or Neo4j/Qdrant projection execution. Do not introduce generic repositories, speculative indexes, or a universal event framework.

## Acceptance evidence

- Migrations apply to an empty real PostgreSQL test database; subsequent upgrades preserve existing records.
- Stable IDs, foreign keys, and uniqueness reject duplicate provider records and invalid approval/version references.
- Typed storage operations prove persistence across connections and transaction rollback without exposing ORM rows as public contracts.
- UTC timestamps, explicit missing values, provenance, and immutable briefing versions are enforced.

## Trade-offs

- SQLAlchemy + Alembic assumes typed mappings help maintain related records. Its first failure risk is hidden transaction behavior or unreviewed migrations. This is the selected direction.
- Direct SQL + versioned migrations assumes queries remain small and explicit. Its first failure risk is repetitive mapping and migration maintenance as related records expand.

Better approaches: none identified beyond the requested PostgreSQL direction, which matches `docs/02-system-architecture.md` and Issue #3.

## Evidence and handoff

The brainstorm inspected Issue #3 and its closed dependency #2, the documentation index, architecture, code standards, codebase navigation, roadmap, Makefile, Compose manifest, backend manifest, and CI workflow. The backend currently provides the health slice; persistence tooling is proposed, not implemented. Issue #3 was moved from Backlog to Ready and that status was verified.

Planning must specify the concrete schema, transaction boundaries, immutability enforcement, and migration-preservation test without expanding into later issues. SQLAlchemy + Alembic selection does not establish plan acceptance or authorize implementation, merge, closure, or release.
