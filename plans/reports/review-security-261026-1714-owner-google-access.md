# Security and contract review

Scope: `plan.md` and all three phase files in `plans/261026-1714-issue-5-6-owner-google-access/`. Plan-only review under `--hard --tdd --yagni`; no build, test, implementation or GitHub mutation. Used `ak-code-review` and `ak-scout` with targeted source reads. The proposed authentication/connection modules do not exist yet: current composition contains only health (`apps/backend/src/email_support/main.py:5–8`). Findings describe defects in the proposed contract, not implemented vulnerabilities.

## Findings

### High — An older disconnect can revoke a newly completed connection

- Plan evidence: `phase-03-google-connection-and-verification.md:39–41` allows consent to advance generation and commit a new grant; `:58–60` commits disconnected status before the revoke HTTP call, permits explicit reconnect, and fences only the late revoke **metadata** write. There is no persisted revoke-in-progress exclusion on consent/callback.
- Current codebase evidence: `docs/02-system-architecture.md:59` establishes separate owner authentication and Google consent; `apps/backend/src/email_support/storage/postgres/persistence/tables/core.py:27–47` gives the canonical account one provider/external identity, with no generation-aware remote revocation boundary to reuse. `docs/04-code-standards.md:26` requires external HTTP outside transactions. This therefore needs an explicit new coordination contract, not an assumed existing safeguard.
- Failure: A commits disconnect and pauses before sending revoke. B, using another valid owner session, completes Reconnect and persists a new full grant at generation N+1. A resumes and revokes its old snapshot. Google's revoke endpoint invalidates issued access/refresh tokens for the project, including B's newly committed credentials. A's generation CAS correctly rejects its metadata update, but cannot prevent the remote side effect. The DB/UI can remain `connected` while the fresh grant has been destroyed. This is reproducible without an attacker and can be repeatedly triggered by overlapping owner actions.
- Provider evidence: [Google's revocation contract](https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke), checked 2026-10-26, states revocation invalidates project-issued credentials across registered clients and may take time to take full effect. The plan already recognizes the same-project blast radius at `:60`; local generations do not narrow it.
- Minimal correction: persist a distinct revoke operation/in-progress marker when committing the local purge; consent initiation and callback promotion must refuse while that operation can still issue a remote revoke. Fence dispatch and completion of this remote operation, not only its metadata result. Define recovery for cancellation/crash/unknown rather than clearing the marker merely because an HTTP deadline elapsed; keep explicit owner recovery/manual grant-removal guidance for unknown outcomes. Add a deterministic two-session test: pause old revoke before dispatch, attempt reconnect, and prove no new connection can be promoted and subsequently invalidated by that old request. Do not add a generalized job system.

### Medium — Fresh generation preflight does not provide the promised disconnect cutoff

- Plan evidence: `phase-03-google-connection-and-verification.md:54` ends the guard transaction before HTTP yet guarantees that no subsequent work starts after disconnect's committed block. `:58` commits that block independently. `plan.md:45` also says disconnect blocks future calls.
- Current codebase evidence: `docs/04-code-standards.md:26` explicitly requires ending transactions before external HTTP; `apps/backend/src/email_support/storage/postgres/persistence/database.py:16–20` creates caller-owned sessions without any cross-process admission/dispatch coordinator. `docs/02-system-architecture.md:7` allows API and worker processes to share these services, so an in-memory mutex would not close the gap.
- Failure: A successfully checks connected status/generation, commits and is descheduled before its HTTP request. B commits disconnect/purge. A resumes and sends a Gmail/Calendar request with the token already held in memory. A's post-HTTP CAS can reject writes, but Google has already received the read and returned private data after the stated cutoff. The plan exempts a request already sent, which does not cover A's unsent request. Moving the check nearer HTTP does not eliminate this schedule.
- Minimal correction: define the admission boundary precisely. If successful preflight admits an operation, explicitly classify admitted-but-not-yet-sent work as in flight and test that only new admissions fail after disconnect, with stale results discarded. This changes the plan's stronger cutoff wording and should be adjudicated by the controller against accepted requirements. If an actual send-time cutoff is required, specify cross-process dispatch/disconnect serialization and its crash/timeout behavior; generation CAS alone cannot establish it. Add a deterministic pause between preflight and dispatch to prove the selected contract.

## Claim checks

`Verified` means the source or plan text supports the stated design/current-baseline claim. It does not mean the proposed behavior exists or passed tests. `Unverified` means the implementation/provider setup remains pending, correctly proposed unless otherwise stated. `Failed` identifies the concrete finding above.

### Phase 1 — 10 checks

| # | Claim and plan evidence | Result and codebase evidence |
|---|---|---|
| 1 | Existing health-only composition (`phase-01-start.md:14`) | Verified: `apps/backend/src/email_support/main.py:5–8`. |
| 2 | Engine construction lazy; sessions caller-owned (`:14`) | Verified: `apps/backend/src/email_support/storage/postgres/persistence/database.py:11–20`. |
| 3 | OIDC/production HTTP dependencies proposed (`:23,46`) | Unverified installed compatibility; current `apps/backend/pyproject.toml:10–27` has no Authlib and HTTPX2 only in dev. No dependency availability claim is accepted as implemented. |
| 4 | Auth-disabled/invalid settings fail protected paths closed while preserving health (`:25`) | Unverified new behavior; current `apps/backend/src/email_support/main.py:3–8` has no settings/auth composition. |
| 5 | Browser-bound, digest-stored, atomically consumed state (`:31–33`) | Verified design specificity; implementation pending. Current mappings at `apps/backend/src/email_support/storage/postgres/persistence/tables/__init__.py:3–40` contain no access tables. |
| 6 | OIDC signature/JWKS and owner-sub path (`:34`) | Unverified Authlib API path until implementation; signature, issuer, aud, azp, expiry, iat and nonce are explicitly required. Current dependency baseline: `apps/backend/pyproject.toml:10–18`. |
| 7 | Independent 12h opaque sessions, rotation and unsafe-request CSRF (`:35–36`) | Verified specified contract; implementation pending, no session routes at `apps/backend/src/email_support/main.py:5–8`. |
| 8 | Callback queries/auth secrets omitted from actual server logs (`:38,106`) | Unverified; current `apps/backend/Dockerfile:23` starts default uvicorn. Plan explicitly requires fixing this before real login. |
| 9 | Three current migration-head assertions need updates (`:85`) | Verified: `apps/backend/tests/database/migrations/test_migrations.py:61,120,318`, all `da3c8e14f627`. |
| 10 | Backend check and guarded DB fixture claims (`:85`) | Verified: `Makefile:30–39`; `apps/backend/tests/database/conftest.py:43–53` creates target, migrates, backs up before seed and drops it. |

### Phase 2 — 10 checks

| # | Claim and plan evidence | Result and codebase evidence |
|---|---|---|
| 1 | App currently owns only health query (`phase-02-owner-access-ui-and-verification.md:20`) | Verified: `apps/web/src/app/App.tsx:4–23`. |
| 2 | Existing wrapper bounds deadline and forwards abort (`:20,28`) | Verified: `apps/web/src/shared/api/health.ts:12–27,38–40`. |
| 3 | Health wrapper validates returned generated shape (`:28`) | Verified: `apps/web/src/shared/api/health.ts:1–7,31–35`. |
| 4 | Existing Playwright matches health only (`:20,47`) | Verified: `apps/web/playwright.config.ts:4–5`. |
| 5 | Unit/E2E runner isolation (`:20,60`) | Verified baseline: `apps/web/vite.config.ts:25–28`. Future access discovery remains unverified. |
| 6 | Same-origin proxy route (`:28`) | Verified baseline: `apps/web/vite.config.ts:19–23`; health wrapper uses `window.location.origin` at `apps/web/src/shared/api/health.ts:32`. |
| 7 | Existing default Compose API/web and deterministic ports (`:20,32,36`) | Verified: `compose.yaml:1–6,17–27`; both published ports are loopback-bound. |
| 8 | Separate pinned Postgres, private runtime and script are future work (`:32–34`) | Unverified proposed runtime; current pinned test image/user/port are `compose.test.yaml:3–12`. No proposed local-auth script was treated as available. |
| 9 | Backend image needs Alembic assets (`:34,50`) | Verified gap assigned to implementation: `apps/backend/Dockerfile:16–17` copies metadata and source only. |
| 10 | Drift gate rejects dirty generated files before generation (`:87`) | Verified: `scripts/check-api-drift.sh:7–18`; do not run this gate on intentionally dirty regeneration. |

### Phase 3 — 10 checks

| # | Claim and plan evidence | Result and codebase evidence |
|---|---|---|
| 1 | Canonical provider identity uniqueness can be reused (`phase-03-google-connection-and-verification.md:19,46`) | Verified: `apps/backend/src/email_support/storage/postgres/persistence/tables/core.py:27–47`. Existing uniqueness is `(provider, external_account_id)`; new connection uniqueness remains proposed. |
| 2 | Mail/meeting canonical FKs must survive disconnect (`:19,46`) | Verified: `apps/backend/src/email_support/storage/postgres/persistence/tables/core.py:136–143,209–215` uses restricted deletion. |
| 3 | Existing create/get helpers use caller-owned sessions (`:19`) | Verified: `apps/backend/src/email_support/storage/postgres/persistence/core.py:60–81`. Getter accepts UUID, not provider/sub; do not assume a missing lookup already exists. |
| 4 | Consent callback binds browser/session/owner/generation before and after exchange (`:39–41`) | Verified explicit design; unverified implementation. Current composition is still health-only: `apps/backend/src/email_support/main.py:5–8`. |
| 5 | Full product scopes and secondary/shared-calendar discovery (`:27–35,64`) | Verified explicit plan contract; provider setup/behavior unverified. Existing public API only exposes health: `apps/backend/src/email_support/api/health.py:10–18`. |
| 6 | Entire token bundle encrypted with authenticated context and external key (`:46–48`) | Verified specified design; cryptography/key plumbing unverified. Current production dependencies are `apps/backend/pyproject.toml:10–18`; no encryption service exists. |
| 7 | Refresh lease/generation/credential-version fencing is cross-process DB work (`:50–52`) | Verified specified design; real race proof pending. Current factory is caller-owned at `apps/backend/src/email_support/storage/postgres/persistence/database.py:16–20`, and tables remain proposed. |
| 8 | Fresh guard guarantees no request starts after disconnect commit (`:54`) | Failed: admission/send TOCTOU finding above; current transaction boundary rule is `docs/04-code-standards.md:26`. |
| 9 | Late old revoke cannot harm newer consent (`:59`) | Failed for remote credentials: only metadata is fenced; canonical identity baseline is `apps/backend/src/email_support/storage/postgres/persistence/tables/core.py:27–47`; see Google contract and finding above. |
| 10 | Real read/revocation smoke is not yet implemented evidence (`:66–70,126`) | Verified pending status; no existing provider route at `apps/backend/src/email_support/main.py:5–8`. Harness path is explicitly proposed and was not executed. |

## Verification limits and unresolved questions

- No tests/builds/lint/typechecks run, per delegated plan-only scope. Live OIDC/JWKS, dependencies, OAuth scopes, cookie proxy behavior, key configuration and Google reads/revocation remain implementation or operator verification gates.
- Controller decision needed: whether disconnect's cutoff means admission time or actual outbound dispatch time. The current text promises the latter without a mechanism that proves it.
- Controller must define the minimal revoke-in-progress/unknown recovery contract before approving phase 3 for implementation.

Status: DONE_WITH_CONCERNS
Summary: Two concrete phase-3 concurrency defects require plan adjudication; 30 claims checked against plan and current source. No implementation or GitHub changes made.
Concerns/Blockers: Remote revoke/new-consent ordering and disconnect admission semantics remain unresolved.
