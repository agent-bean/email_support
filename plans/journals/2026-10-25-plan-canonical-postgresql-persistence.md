---
title: Plan canonical PostgreSQL persistence
date: 2026-10-25
summary: Owner accepted the corrected Issue 3 TDD plan; ready for cook.
---

# Plan canonical PostgreSQL persistence

## Work

Prepared the Issue #3 plan on docs/issue-3-persistence-plan using --tdd --hard --yagni. Reused the accepted SQLAlchemy + Alembic direction, inspected the current health-only source and commands, and gathered two focused research reports. The draft has three sequential phases and two substantive additive migrations to prove preservation of seeded core records.

## Review

Three independent reviewers produced six distinct findings: TRUNCATE protection, deterministic concurrency coverage, exact approved knowledge text, valid projection states, fresh test target lifecycle, and recovery-safe cleanup when backups fail. The controller recommends all six and requested owner review before application. Details are in plans/reports/validation-261025-1529-issue-3-persistence.md.

## Verification and next gate

AgentKit plan validation passes; its parser sees three phases and 12 pending tasks. Draft links and TDD sections were checked. No application tests, builds, containers, migrations or database writes ran. Apply approved corrections, complete the whole-plan sweep, and obtain plan acceptance before implementation. No commit, push, merge, closure, deployment or release occurred. AgentWiki publish skipped.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.

## Owner follow-up

The owner selected “Apply all six (Recommended)”. All six corrections are now incorporated into the three phase files and plan index. Knowledge text derives from immutable selected approval entries; immutable tables reject TRUNCATE; deterministic two-session tests exercise locks; projection metadata admits only exact canonical source versions; each scenario owns a fresh guarded target; failed cleanup backups stop verified owned processes while preserving local recovery data. CI recovery retention is limited to job lifetime. No application or database mutation ran. The corrected plan awaits owner acceptance and implementation authorization.

## Plan acceptance and handoff

The owner accepted the corrected plan and requested repository-relative paths. File inventories and the cook handoff now use that convention. Document verification and review gates are complete; all three phases and 12 implementation tasks remain pending. Ready for cook when requested; implementation has not begun.
