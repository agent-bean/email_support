---
title: Issue 3 canonical persistence implementation
date: 2026-10-25
summary: "Implemented and locally verified canonical PostgreSQL storage, guarded database checks, and Backend CI integration."
---

# Issue 3 canonical persistence implementation

## What happened

Continued the accepted Issue #3 plan on `feat/issue-3-canonical-persistence`. Added typed Pydantic contracts and async SQLAlchemy storage operations for normalized inputs, companies and contacts, source evidence, immutable briefing versions, approval/action bindings, approved knowledge, preferences, and projection metadata. Two additive Alembic revisions define the PostgreSQL schema and database-enforced provenance rules.

Added a guarded PostgreSQL test runner with fresh scenario databases, identity checks, private `pg_dump`/restore verification, safe local cleanup, and a GitHub Actions service-container adapter. Backend CI now requires the database suite; ordinary local `make check` remains database-free. Updated the README and owning codebase/deployment docs.

A TDD regression test caught that the `shutdown-cleanup` CLI dispatch lacked an argparse subcommand. The test failed before the subcommand was registered, then passed after the fix.

## Decision

Keep persistence offline from the health-only API; do not add runtime DB wiring, provider integrations, workers, or projections. Keep the plan in progress until hosted CI and owner acceptance. No push, PR, merge, deployment, or Issue status change was made.

A citation to a newly created uncommitted briefing version is constructed and sealed inside one transaction; a second session cannot cite it before it commits. Coordinated tests cover competing inserts/appends and late citations after a sealed parent is locked.

## Verification

- `make check`: 26 backend tests and 14 web tests passed; Ruff, formatting, strict mypy, TypeScript checks, lint, and production build passed.
- `make database-check`: 30 PostgreSQL tests passed; the owned container/network were removed and port 55432 was free.
- `make check-api-drift`: passed without generated API changes.
- CI adapter: the missing-configuration path failed closed; a disposable PostgreSQL service with its exact container ID passed all 30 database tests.
- Cleanup failure injections retained recovery archives and stopped the verified local service. Earlier failure-injection archives remain in the ignored `.test-database/recovery/` directory; the final successful run removed its own archives.
- `ak plan status`: 3/3 phases done, 12/12 phase tasks checked. Plan remains `in-progress`; GitHub Actions has not run for this branch.

## Next steps

Run the hosted PR checks after a push/PR is separately authorized, then collect owner acceptance. Keep the issue Ready until that acceptance and the project workflow's verify/close steps are authorized.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
