---
title: Issue 5 and 6 owner access planning
date: 2026-10-26
summary: Validated TDD/YAGNI plan with five owner-approved red-team corrections; implementation pending.
---

# Issue 5 and 6 owner access planning

## Work

Prepared [the implementation plan](../261026-1714-issue-5-6-owner-google-access/plan.md) for Issue #5 owner-only Google login and Issue #6 separate Gmail/Calendar consent. Three sequential phases retain independent Issue #5 review/acceptance before Issue #6. Research, source scouting and independent red-team reports are linked from the plan.

## Decisions

Retained the same Google identity, secondary/shared Calendar access and a 12-hour absolute application session separate from Google access/refresh tokens. The owner approved all five review corrections: durable revoke/reconnect gating, disconnect at operation admission, expiry-safe revocation smoke, simpler migration backups with explicit empty/no-op branches, and session locking against logout. Applied them to contracts and test scenarios; validation records the exact answers.

## Verification and next step

AgentKit structural validation and all 37 local links/anchors/line bounds passed; parsing found 3 phases and 48 unchecked tasks. No application implementation, application tests, live Google smoke, database mutation or GitHub publication occurred. Execute the plan with TDD when selected; OAuth setup and real-provider acceptance remain pending. No background services were started.

AgentWiki publish skipped.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
