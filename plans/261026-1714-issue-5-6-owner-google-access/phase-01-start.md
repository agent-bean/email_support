---
title: "Phase 1: Owner access backend"
status: todo
priority: P1
effort: 14h
---

# Phase 1: Owner access backend

## Context, dependencies and requirements

Depends on verified closure of #3. Build #5 backend only; phase 2 completes its UI and review boundary. No Gmail/Calendar consent or tokens in this phase.

Current composition is only the public health router at [main.py:7](../../apps/backend/src/email_support/main.py#L7). The lazy engine factory at [database.py:11](../../apps/backend/src/email_support/storage/postgres/persistence/database.py#L11) creates no connection until use; caller-owned sessions start at [database.py:16](../../apps/backend/src/email_support/storage/postgres/persistence/database.py#L16). Preserve that trace: import → construct app/routes → public health without auth settings/DB/provider dependencies; authenticated request → validated configuration → request-scoped DB session → service → provider/storage.

- [x] Configured owner can sign in; any other Google subject rejects even with matching email.
- [x] Expired/revoked sessions and unsafe browser requests reject; login initiation itself resists CSRF.
- [x] Fixed callback/return targets, state, browser binding, nonce, S256 PKCE and HTTPS cookies are tested.
- [x] Import, OpenAPI generation and health work with no auth environment and with DB/provider outages.

## Contracts and data flow

Use Authlib async OAuth2/OIDC primitives with explicit DB state; do not add Starlette signed-cookie session middleware. Proposed production constraints are `authlib>=1.9.1,<1.10` and `httpx2>=2.16,<3`, resolved into `uv.lock`; verify the installed API and dependency graph before implementation. Authlib's [HTTP client](https://docs.authlib.org/en/stable/oauth2/client/http/index.html) and [changelog](https://docs.authlib.org/en/stable/upgrades/changelog.html) explain HTTPX2 compatibility. No independent hand-built JWT verification or sync Google client. Use `AsyncOAuth2Client.create_authorization_url` and `fetch_token`, then validate the signed ID token with joserfc decoding and Authlib's `CodeIDToken.validate` OIDC primitive; the current async client exposes no `parse_id_token` or `fetch_access_token` method. Preserve explicit stored state, issuer, audience, nonce, and `azp` checks; avoid helpers that require `request.session` and reject missing ID tokens. Bound JWKS request time/response size and cached key lifetime; test one bounded key refresh for an unknown key ID.

Configuration uses an explicit auth-enabled flag (default false), PostgreSQL URL, configured owner `sub`, Google client ID/secret, fixed login callback URI and exact web origin. Disabled or invalid auth configuration returns typed `503 auth_unavailable` on auth/protected routes; an otherwise configured service with missing/invalid session returns `401`. Validate settings once in composition/lifespan without connecting to DB, and retain a typed unavailable state rather than crashing public health. Close the owned engine/client on shutdown. No shared request/session/CSRF values in app-wide resource objects. No credential defaults or first-login enrollment.

Proposed endpoints (all `/api`): `GET /auth/preauth`, `POST /auth/google/login`, `GET /auth/google/callback`, `GET /auth/session`, `POST /auth/logout`. Public protocol endpoints have explicit OpenAPI inclusion/exclusion; expose typed session, authorization URL and sanitized error contracts for generation. `/auth/session` is a real protected route, returns owner authentication, absolute expiry and a session CSRF token, never the session secret. Login returns a server-generated Google authorization URL; browser navigation is a separate GET. Callback redirects only to the configured application root with an allowlisted result code, never code/state/token values.

Login requests only `openid email`, without offline access; discard all returned Google tokens after ID validation even if previous consent causes broader grants.

1. Same-origin web fetches preauth with no-store caching. Backend issues a fresh random 256-bit HttpOnly browser-binding cookie and a random CSRF challenge returned to JS memory. Store only challenge SHA256 digest and binding-cookie SHA256 digest in a 10-minute OAuth-attempt row with purpose `login_bootstrap`. No CORS permission to read this endpoint from another origin; same-origin policy protects the returned challenge.
2. Login initiation POST requires the exact configured `Origin`, JSON content type and submitted preauth CSRF header. Atomically consume the unexpired bootstrap row matching challenge and binding cookie, then create a new `login` attempt with random state, nonce, S256 verifier, binding digest, 10-minute deadline and fixed return target. A new preauth invalidates the previous browser flow; concurrent-tab rejection is a recoverable restart state, not authorization bypass. Store state as a digest; transient nonce/verifier exist only server-side until consumed/expired.
3. Callback requires matching live state and binding cookie. Atomically claim the attempt (`DELETE ... RETURNING` or equivalent conditional consume) and commit **before** token exchange. Require purpose `login`; reject replay/missing/expired/wrong-binding/provider denial without creating a session. Do not hold a DB transaction during provider HTTP. Browser cannot substitute a redirect or return URL.
4. Exchange using saved verifier and fixed callback URI; validate signature/JWKS, allowed Google issuer, exact audience, `azp` where applicable, expiry, reasonable issued-at and nonce, then compare verified `sub` to configured owner. Email is optional display metadata, never authorization. Bound JWKS/token requests and cancellation; a failed exchange consumes the attempt and requires a fresh flow. Discard login access/ID tokens after validation.
5. Issue a new random 256-bit opaque session ID, store only SHA256 digest with owner `sub`, issued-at, absolute expiry and session CSRF secret. Owner-confirmed absolute TTL is 12h, no sliding/idle timer. This is the application session lifetime; Google access/refresh-token lifetimes are separate phase 3 concerns. In the same commit revoke the presented old session, if any, and issue the new session; do not preserve attacker-chosen IDs. Cookie is `HttpOnly`, production `Secure`, `SameSite=Lax`, `Path=/`, no Domain, Max-Age bounded by expiry. Use a `__Host-` cookie in HTTPS mode; an explicitly local loopback HTTP mode uses a distinct unprefixed cookie and is forbidden for public origins.
6. Every protected request looks up the session digest and checks owner/expiry; unsafe methods additionally require exact Origin and constant-time synchronizer-token comparison. OAuth GET callback instead uses state/browser binding/nonce/PKCE. Logout requires CSRF, deletes the current session and expires its cookie; deletion must conflict with a row lock taken by a protected final-write transaction. Use lock order session then connection when phase 3 extends this protocol, and check expiry inside the locked transaction. No provider HTTP runs while these locks are held; another logout with no session returns 401 and clears it. Expired cookies clear on detection. Logout does not change future Google connection state.

OAuth-attempt table: UUID ID, purpose (`login_bootstrap | login`, extended in phase 3), unique state/challenge digest, browser-binding digest, expiry, nonce/verifier nullable only for bootstrap, fixed return target. Constraints require complete protocol fields for login. Session table: unique digest, nonblank owner subject, created/absolute-expiry times, CSRF secret. Session/attempt storage has short-lived expiry enforcement and opportunistic bounded cleanup on creation; no scheduler. Persistent secrets never enter logs; configure access logging to omit callback query strings and auth headers/cookies, including Compose's uvicorn route, before real login.

## Files and ownership

Paths below are proposed unless described as existing. Create only these real boundaries; no base services, generic repositories or empty directories. Over eight files is justified by the established API → service → integration/storage boundaries, migration ownership and independent tests.

| Action | Files | Responsibility |
|---|---|---|
| Modify | `apps/backend/pyproject.toml`, `apps/backend/uv.lock` | Production Authlib/HTTPX2 dependencies |
| Modify | `apps/backend/src/email_support/main.py` | Explicit resource lifespan, configuration state, router composition |
| Create | `apps/backend/src/email_support/config.py` | Validated explicit settings/local HTTPS policy |
| Create | `apps/backend/src/email_support/api/access.py`, `api/dependencies.py` | Routes; owner/session/CSRF guard (second path under the same source package) |
| Create | `apps/backend/src/email_support/models/access.py` | Public strict contracts and closed errors |
| Create | `apps/backend/src/email_support/services/access.py` | Browser transaction, owner, session and CSRF invariants |
| Create | `apps/backend/src/email_support/integrations/google_oidc.py` | Authlib async protocol/claim boundary |
| Create | `apps/backend/src/email_support/storage/postgres/persistence/access.py`, `tables/access.py` | Conditional attempt/session operations and mappings (second under persistence) |
| Modify | `apps/backend/src/email_support/storage/postgres/persistence/tables/__init__.py` | Register mappings; Alembic imports this metadata |
| Create | `apps/backend/migrations/versions/create_owner_access.py` | Additive migration from existing `da3c8e14f627` |
| Create | `apps/backend/tests/unit/access/test_access.py`, `tests/integration/test_access_contracts.py`, `tests/database/access/test_access_storage.py` | Pure/protocol contract tests and real DB scenarios (all under backend) |
| Modify | `apps/backend/tests/database/migrations/test_migrations.py` | New-head assertions plus old-revision preservation |

Delete: none. Phase 1 owns these files exclusively; phase 2 may subsequently touch composition/contracts/runtime and phase 3 extends access attempts after handoff. Existing engine helpers need no abstraction rewrite.

## Tests Before — RED

- [x] Add tests first, run focused commands below, record exact failure and expected missing behavior; missing proposed modules/routes initially fails collection/404. A collection failure alone is insufficient: after minimum interfaces exist, observe failing behavioral assertions before implementing each invariant.
- [x] Unit/provider-boundary cases: wrong subject despite matching email; valid owner with changed email; bad issuer/aud/azp/exp/iat/nonce/signature; S256 and exact callback; denial/timeouts/cancellation; absence of leaked secrets in captured logs.
- [x] Real PostgreSQL cases: state replay/two simultaneous callback claims yield one exchange; wrong browser cannot consume valid state; bootstrap CSRF one-use; expiry; rotation/logout; session lookup/owner authorization; logout waits for a held session-row final-write lock and wins before any later finalization; unsafe CSRF mismatch; isolated sessions between simultaneous requests.
- [x] Add API/import tests proving no environment/network/DB is needed for import/OpenAPI/health, malformed config fails protected routes closed, DB outage leaves health 200, and OpenAPI advertises cookie auth/CSRF error contracts without secrets.
- [x] Extend migration tests from old head, with existing canonical data and backups; preserve prior assertions and add snapshot comparisons across this new revision.

## Implementation/refactor and Tests After — GREEN

- [x] Implement migration/mappings/storage before service and routes; respect request-owned `AsyncSession` lifetime. Inject doubles only at provider boundary, never mock the DB concurrency invariant.
- [x] Implement Authlib adapter and state/session rules, then typed HTTP errors; all provider calls occur outside DB transactions and have deadlines.
- [x] Re-run focused tests until assertions pass, refactor duplication while preserving behavior, then run full backend/database gates and regenerate contracts. No tests run as part of this planning task.

Existing commands, run from repository root; proposed file targets become executable **only after creation**:

```sh
(cd apps/backend && uv run --locked pytest -q tests/unit/access/test_access.py tests/integration/test_access_contracts.py)
./scripts/check-database.sh local tests/database/access/test_access_storage.py tests/database/migrations/test_migrations.py
make backend-check
make database-check
make generate
```

`make backend-check` at [Makefile:30](../../Makefile#L30) covers lock, unit/integration/contracts, Ruff and strict mypy; local DB coverage is separate. Database fixture [conftest.py:43](../../apps/backend/tests/database/conftest.py#L43) creates a guarded target, migrates and backs up before scenario seeds; use that harness rather than pointing tests at the runtime DB. Update all three current hardcoded head assertions in [test_migrations.py:61](../../apps/backend/tests/database/migrations/test_migrations.py#L61), [120](../../apps/backend/tests/database/migrations/test_migrations.py#L120), [318](../../apps/backend/tests/database/migrations/test_migrations.py#L318); retain restoration and preservation coverage for both existing revisions. Add a preservation test beginning at `da3c8e14f627` with seeded decisions/knowledge rows, not only the original core revision.

## Scenario matrix and success

| Layer | Scenario | Observable success |
|---|---|---|
| Unit/API | OIDC wrong identity/claims or provider denial | Typed rejection; zero new sessions |
| DB concurrency | Same callback submitted twice; separate browsers | One successful consume; mismatched browser cannot claim |
| DB/API | Expiry, logout, fixation, missing/wrong CSRF | No usable stale session; unsafe operation blocked |
| Integration | Auth disabled, missing secrets, DB outage | Public health 200; protected request 503 or 401 as applicable |
| Migration | Old head → new head, backup/restore, metadata drift | Existing canonical rows unchanged; new constraints registered |

Success requires passing RED/GREEN evidence for every invariant and independent credential-free generation. Live Google owner login is phase 2 evidence, not asserted here.

## Risk, security and rollback

| Risk | Likelihood × impact | Mitigation / stop signal |
|---|---|---|
| CSRF/replay or wrong-owner admission | Medium × High | Browser-bound one-use state, preauth CSRF and claim matrix; stop on any bypass |
| Lazy composition becomes health dependency | Medium × High | Import/DB-outage tests; remove eager validation/network coupling |
| Additive schema or dependency incompatibility | Medium × High | Real old-head preservation/restore and locked dependency resolution; stop if Authlib API differs, consult current official docs |
| Callback query logged by server | Medium × High | Explicit no-query access-log configuration and captured-log assertion before live run |

Backwards compatibility: preserve all canonical tables/contracts and public health, add new auth schema only. Before runtime migration use the existing guarded backup/restore lifecycle against its owned verification DB; actual persistent runtime backup procedure must be recorded and tested before applying schema there. Rollback stops authenticated runtime, reverts code to the health-only revision and leaves additive tables intact. Do not automatically downgrade/drop sessions while newer code runs; drop new tables only in a verified disposable test target, or restore a verified backup with owner authorization for consequential data loss.

## Handoff

- [x] Record checks, failures and unresolved verification gaps; hand phase 2 the generated contracts and backend error semantics.
- [x] No Issue/Project acceptance, merge, closure or next-issue action occurs here.

## Execution evidence

- RED: the initial access contract tests failed against the health-only app (missing routes and OpenAPI contracts). The JWKS streaming test failed while the adapter still buffered via `get`; the PostgreSQL attempt constraint test confirmed an incomplete `login` row was accepted. Each failure was fixed and re-run green.
- GREEN: `make backend-check` passed (56 tests, Ruff, formatting and strict mypy); `make backend-database-check` passed (47 tests, including migration preservation/restore and session/attempt concurrency); `make generate` completed for OpenAPI and web contracts; `git diff --check origin/main` passed.
- Live Google sign-in was not run because owner OAuth setup remains a phase 2 prerequisite. Phase 2 has the generated contracts and typed error/session semantics; this phase made no Issue or Project changes.

Unresolved questions: none. Owner Google client and trusted callback setup remain phase 2 live prerequisites. Protocol sources: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect), [OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server), [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

<!-- Updated: Validation Session 2 - owner approved atomic session locking against logout. -->
