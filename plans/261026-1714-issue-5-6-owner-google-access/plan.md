---
title: "Owner access and Google connection"
description: "Plan owner-only OIDC sessions, then separate Gmail and Calendar consent with encrypted credentials."
status: in-progress
priority: P1
effort: 44h
issue: 5
branch: feat/issue-5-owner-access-backend
tags: [feature, auth, backend, frontend, database]
blockedBy: []
blocks: []
created: 2026-10-26
---

# Owner access and Google connection

Accepted phased implementation, `--tdd --yagni`. Planning began on `main`; implementation is on the issue branch recorded above. Phase 1 is complete. No live Google login or production runtime checks have run.

## Outcome and boundaries

Deliver [#5](https://github.com/agent-bean/email_support/issues/5): configured-owner Google OIDC, PostgreSQL opaque sessions, CSRF, logout and access UI. Then deliver [#6](https://github.com/agent-bean/email_support/issues/6): separate same-owner Gmail read/send and read-only Calendar consent, encrypted tokens, safe refresh/disconnect and connection UI.

[#3](https://github.com/agent-bean/email_support/issues/3) is the closed prerequisite for #5; #6 depends on #5 and remains open. Recheck live dependencies before execution. Preserve credential-free health and default Compose smoke. Logout does not disconnect Google.

Exclude production deployment, real sends (#15), synchronization/jobs (#7), multiuser/accounts, Redis, owner enrollment, a general auth framework and extra infrastructure. OAuth setup/credentials are not provisioned by this plan. Google live verification remains pending until operator setup exists.

## Phases and dependency gates

| # | Phase | Estimate | Depends on | Status |
|---|-------|----------|------------|--------|
| 1 | [Owner access backend](phase-01-start.md) | 14h | #3 verified closed | Done |
| 2 | [Access UI and independent #5 verification](phase-02-owner-access-ui-and-verification.md) | 10h | Phase 1 | Pending |
| 3 | [Google connection and independent #6 verification](phase-03-google-connection-and-verification.md) | 20h | Phase 2; #5 review/acceptance boundary | Pending |

All phases are sequential. Each phase owns its listed changes only while active; shared composition, generated artifacts and metadata pass to the next phase after verification. Pause before phase 3 until #5 is independently reviewable and its acceptance/merge/dependency gates are resolved with the owner.

## Acceptance

- [ ] Only the configured Google `sub` signs in; invalid/replayed protocol inputs reject.
- [ ] Protected APIs reject unauthenticated/expired sessions and unsafe requests without CSRF; logout invalidates the server session; HTTPS cookie protections are verified.
- [ ] Useful signed-out/expired UI works; public liveness needs no credentials, DB or provider.
- [ ] Separate consent validates session, same owner, state/nonce/PKCE and exact required scopes, including secondary/shared Calendar reads.
- [ ] Encrypted token bundles use an external key; tokens never reach web responses or normal logs.
- [ ] Refresh, partial consent, expiry, revocation and transient failure have typed outcomes and actionable UI; concurrent stale results cannot undo disconnect.
- [ ] Disconnect blocks new operation admissions and purges credentials before revocation; previously admitted work may finish externally but its stale results are discarded. Reconnect waits for revoke resolution; real Google read/revoke smoke evidence exists, or acceptance stays pending with its prerequisite recorded.

## Review and validation records

- Red Team Review: [five approved corrections](../reports/validation-261026-1714-owner-google-access.md#validation-session-2), 1 High and 4 Medium; all applied and checked. Ready for phased implementation.
- Validation Log: [decision record](../reports/validation-261026-1714-owner-google-access.md); 12h absolute session and all five corrections confirmed; whole-plan validation passed.
- Runtime/live evidence: pending, not established by plan validation or green automated tests.

## Sources and execution

Follow [architecture](../../docs/02-system-architecture.md), [standards](../../docs/04-code-standards.md), [deployment boundaries](../../docs/06-deployment-guide.md) and [owner acceptance workflow](../../docs/08-github-project-workflow.md). Research: [owner access](../reports/researcher-261026-1714-owner-access.md), [Google connection](../reports/researcher-261026-1714-google-connection.md). Scouting: [current source map](../reports/scout-261026-1714-owner-google-access.md). Phase decisions supersede broader research suggestions.

Use focused RED → implementation/refactor → GREEN records per phase. No scope or accepted architecture change, GitHub mutation, merge, closure, production action or next issue is authorized by this planning artifact. Unresolved product questions: none; operational Google setup and live verification remain explicit prerequisites.

<!-- slug: issue-5-6-owner-google-access -->
