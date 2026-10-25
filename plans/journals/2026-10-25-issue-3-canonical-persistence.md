---
title: Issue 3 canonical persistence
date: 2026-10-25
summary: "Consolidated the implementation, module organization, verification, and delivery decisions into one Issue 3 journal."
---

# Issue 3 canonical persistence

## What happened

Executed the accepted Issue #3 plan on the feature branch. Added typed Pydantic contracts, async SQLAlchemy persistence operations, and two additive Alembic revisions for canonical inputs, evidence, briefing history, approvals, knowledge, preferences, and projection metadata. Added guarded PostgreSQL checks for fresh installs, upgrades, transactions, concurrency, backup, restore, and cleanup; Backend CI requires the database suite.

After the implementation checkpoint e4f2f5e, grouped model contracts, ORM tables, runtime modules, and tests into the approved core, decisions, and projections scopes. Kept public model/table facades stable and updated migration imports, code navigation, and phase inventories. Corrected the briefing-version fixture so evidence-list validation is exercised. The test-first failure also exposed and fixed the missing shutdown-cleanup CLI subcommand.

Changed all four CI runner labels from ubuntu-26.04 to ubuntu-latest. Kept GitHub Actions pinned to full commit SHAs, consistent with the repository's code standards.

## Decisions

Persistence remains offline from the health-only API. No generic repository layer, provider integration, worker, or vector-store execution was added. CI uses a run-scoped PostgreSQL password. The root plan remains in progress until hosted CI evidence and owner acceptance; Issue #3 remains open.

Applied all six approved review corrections: immutable-history TRUNCATE protection, deterministic two-session locking tests, exact approved-text binding, consistent projection provenance, fresh guarded scenario targets, and recovery-safe cleanup.

## Verification

- make backend-check passed: 26 tests, Ruff, formatting, and strict mypy.
- make database-check passed: 30 PostgreSQL tests; its owned container and network were removed and port 55432 was free.
- make check-api-drift passed without generated API changes.
- The CI adapter failed closed without required configuration and passed all 30 database tests with the job service. Cleanup-failure checks retained recovery archives.
- ak plan validate passed; ak plan status reported 3/3 phases and 12/12 tasks done.
- The updated workflow syntax and diff are checked before commit. Hosted GitHub Actions and owner acceptance remain pending.

## Next steps

Push the feature branch and open a ready PR linked to Issue #3 through GitHub's native Development relationship. Do not merge or close the issue without separate owner authorization.

> Historical work record — not durable authority. Prefer current docs and code for implementation details.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
