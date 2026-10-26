---
title: "Phase 3: Google connection and independent Issue 6 verification"
status: in-progress
priority: P1
effort: 20h
---

# Phase 3: Google connection and independent Issue 6 verification

## Dependencies, scope and requirements

Depends on completed phases 1–2 and owner authorization. The owner directed local phase 3 implementation after reviewing phase 2 evidence while #5 remains open with no PR; this does not authorize a push, PR, merge, issue closure, or Project status change. Recheck live #6 criteria before implementation. Reuse authenticated-owner sessions; do not change owner enrollment or login's `openid email` scope set.

## Phase 3 start evidence

The owner reviewed phase 2 evidence and explicitly directed phase 3 to proceed. At start, #5 was OPEN with no PR, and #6 was OPEN/Ready. Work continues on the existing local issue branch; no push, PR, merge, issue closure or Project status change is authorized by this direction. The owner later configured the private key and reported the Google prerequisites ready; live evidence is still required.

- [x] Separate consent requests exact Gmail read/send and Calendar read-only scope set, bound to current session and the same configured Google subject.
- [x] Encrypt refresh/access credentials under a key outside PostgreSQL; never return token fields or log them.
- [x] Refresh/expired/partial/revoked/transient outcomes are typed, actionable and safe across processes.
- [ ] Disconnect first durably blocks work and purges credentials, then attempts revoke; live Google smoke proves read access and provider-side revocation.

## Implementation and local verification evidence

- The consent flow uses exact requested scopes, session/browser/state/nonce/PKCE binding, live-session and generation fences, same-owner ID-token validation, and sanitized callback outcomes. The API exposes only status and safe operation results.
- Fernet encrypts the complete access/refresh bundle with connection/owner context. Database checks cover encrypted storage, refresh leases, stale-result fences, disconnect purge-before-revoke, revoke gating, migrations and restore.
- Provider adapters perform only bounded Gmail metadata and Calendar reads plus refresh/revoke. No send, sync, ingestion or background job was added. The UI is owner-gated and has explicit connection, reconnect, partial-scope, transient and unresolved-revoke states.
- TDD evidence: the redirect URL tests first failed for credentialed Google URLs, nonstandard ports and the wrong path; exact endpoint validation then passed all six API tests. The smoke deadline test first failed because an in-flight probe was not cancelled; bounded cancellation then passed all four harness tests.
- TDD callback repair: a new test first failed because owner login redirected to a relative path on the API origin. Login and connection callbacks now redirect to the configured web origin. Failure diagnostics record only the callback stage and an allowlisted OAuth error code or exception class; tests verify that provider code, state and exception text are absent. Focused callback contracts passed 17 tests.
- Login request contract: generated SDK calls now send an explicit empty JSON object, so FastAPI enforces the planned JSON media type. OpenAPI and generated TypeScript were regenerated; PostgreSQL login tests now send the same empty body.
- TDD migration-startup evidence: a regression test first failed because `up` queried the Alembic head before building the current API image. The script now builds API/web before migration discovery; the focused runtime suite passes 16 tests. The local database moved from phase 2 revision `b17e9a4d2c61` to phase 3 revision `3c0f6a9b21e8` only after the guarded migration flow created and validated a backup.
- `make generate` passed. Latest `make check` passed: 104 backend unit/integration/contract tests, 39 web tests, Ruff, Ruff format, strict mypy (79 files), TypeScript, ESLint, Prettier and production build. The earlier full database suite passed 61 PostgreSQL tests including migration and restore coverage; after the callback contract repair, the focused PostgreSQL access suite passed all 6 tests. A repeat full database run was stopped after making no further reported progress for about 90 seconds. `bash -n scripts/local-auth.sh`, Compose configuration parsing and `git diff --check` passed.
- `npm run test:smoke` passed all three Playwright tests against the current owner-auth runtime, including signed-out feature gating and the web-to-API health path.
- After the owner reported setup ready, a presence-only check confirmed a valid Fernet key in ignored `.local-auth/owner.conf`, the expected separate login and connection callback paths on the configured local origin, and the same callback host and scheme. The key value was never displayed. The local API health and web root return HTTP 200. The owner signed in and completed separate Google consent; the app reported connected with the full required scope set. The live harness successfully read minimal Gmail metadata and received a successful Calendar list response, but found no non-primary calendar. After the owner reported the calendar was ready, a read-only diagnostic and a second harness run reproduced the same result: Gmail metadata read succeeded, but no secondary/shared calendar was returned. One intervening harness attempt reported `revocation_pending`; the persisted row remains connected with encrypted credentials, no revoke marker and no stored error, and a read-only retry passed both API calls. The harness returns `PENDING` before prompting for disconnect, so credentials and the Google grant remain active. The Google warning reported that disconnect may revoke permissions for other clients in the same project; no disconnect or provider-side revoke has been attempted. The owner needs to confirm the secondary calendar is shared with and visible in the exact owner account's Google Calendar list. Cloud Console API toggles, exact registered redirect entries and test-user roster were not independently inspected; successful consent and the Gmail/Calendar API calls are the available live evidence.

No sync, jobs, ingestion, actual send, agent tools, multiple accounts, Redis, KMS service, generalized credential vault or per-feature incremental-consent UI. Requesting `gmail.send` does not implement or authorize sending (#15). Keep existing provider-account identity referenced by mail/meetings: mapping at [core.py:28](../../apps/backend/src/email_support/storage/postgres/persistence/tables/core.py#L28), mail FK at [139](../../apps/backend/src/email_support/storage/postgres/persistence/tables/core.py#L139), meeting FK at [212](../../apps/backend/src/email_support/storage/postgres/persistence/tables/core.py#L212). Existing creation/getters at [persistence/core.py:60](../../apps/backend/src/email_support/storage/postgres/persistence/core.py#L60) and [77](../../apps/backend/src/email_support/storage/postgres/persistence/core.py#L77) take caller-owned sessions; reuse these rather than duplicating canonical account identity.

## Public contracts and state

Proposed endpoints: `GET /api/google/connection` (sanitized status), `POST /api/google/connection/consent` (CSRF-protected authorization URL), `GET /api/google/connection/callback` (protocol validation), `POST /api/google/connection/disconnect` (CSRF-protected local purge/revoke outcome). All except protocol callback use #5 owner/session guard; callback explicitly rechecks it. No endpoint accepts arbitrary provider account IDs or returns credential bundles.

Closed connection status: `connected | reconnect_required | disconnected`. Errors: `partial_scope`, `consent_denied`, `identity_mismatch`, `session_expired`, `invalid_callback`, `refresh_invalid`, `provider_unavailable`, `refresh_busy`, `credentials_unavailable`, `revocation_pending`. Transient errors are operation outcomes, not a fourth persisted status. Revoke outcome: `confirmed | unknown | not_attempted`; unknown includes timeout/crash and never implies the remote grant was removed. Responses contain only status, actual granted scopes/missing scope names, safe error category, revoke outcome/time and whether reconnect is blocked by unresolved revocation; no raw provider body or identity token. Connection GET never refreshes a token just to render UI.

All required scopes are requested together:

- `openid`, `email` to validate the subject.
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/calendar.events.readonly`
- `https://www.googleapis.com/auth/calendar.calendarlist.readonly`

Check granted scopes using exact identifiers; normalize documented equivalent identity scopes only. Missing/unknown grants never count as permission. Any required product scope absent yields `reconnect_required` + `partial_scope` + actual/missing scopes; **block all product provider work** until the complete required set exists. UI offers one explicit Reconnect action only when the durable revoke gate allows it; no per-feature expansion or automatic consent loop. Reject unexpected product scopes rather than asking for broad Gmail/Calendar write grants. Login still discards tokens even if Google returns a previous broader grant.

## Consent data flow and stale-result fences

1. Consent POST validates current owner, CSRF and exact Origin. Ensure one canonical provider-account identity for this owner, and one connection row, then create a 10-minute attempt with purpose `google_consent`, random state/nonce/S256 verifier, browser binding, session digest and connection ID + generation snapshot. Perform attempt creation and generation change in the same transaction; lock the connection row before those changes and reject with `revocation_pending` while a revoke operation is in progress or unresolved/unknown. Starting a new consent increments generation and supersedes prior consent/refresh work; it preserves usable old credentials only until replacement or disconnect. For an initial disconnected row, create it before redirect so disconnect can fence an outstanding callback.
2. Use Authlib from phase 1 with fixed dedicated callback, `access_type=offline`, `include_granted_scopes=true` and an explicit reconnect consent prompt when a refresh grant is needed. A Google account hint is convenience only, never authorization. Same-owner verification remains mandatory even if account chooser changes identity.
3. Callback atomically consumes matching purpose/state/browser/session attempt before exchange; verify live session/owner and generation. Commit before HTTP. Validate ID token signature, issuer/aud/azp/exp/iat/nonce and exact owner `sub`. Do not persist anything from a different identity. After exchange, lock and validate the referenced session row, then lock the connection row in the same short final-write transaction. Check owner and expiry under lock, unchanged generation and no in-progress/unresolved revoke operation before the conditional write. Logout deletion conflicts with this session lock: whichever transaction commits first defines the order. Always lock session before connection; perform no provider HTTP while locks are held. Logout, expiry, newer consent or disconnect makes late callback results unusable; discard them without restoring credentials/status. Concurrent successful callbacks have only one winning generation.
4. Validate actual scopes. A complete grant with refresh token becomes connected. On reauthorization, absent refresh token preserves existing refresh token only when its same-owner grant is still usable at the expected generation; preserve it within the encrypted bundle. Initial grant lacking a refresh token yields reconnect-required and no pretend offline connection. Partial grants preserve only actual scope metadata, purge unusable credentials and require explicit reconnect. Provider denial does not silently erase an existing valid connection; its typed outcome appears separately.

## Persistence, encryption and refresh

Add a unique connection row keyed by immutable `provider_account_id`, storing Google subject, exact granted scopes, encrypted bundle, key version, status, generation (monotonic bigint), credential version, lease owner/expiry, durable revoke operation ID/state (`in_progress | unknown | resolved`, nullable before any operation) and safe revoke/error metadata/timestamps. FK deletion remains restricted; disconnect never deletes canonical accounts/mail/meetings. Reuse canonical `provider='google'` + external `sub` for the new owner connection; never remap existing other-provider rows. Single configured-owner guard prevents multiple active owner connections; unique Google subject prevents duplicate identity rows.

Add production `cryptography` and lock a compatible supported release during implementation. Choose high-level [Fernet](https://cryptography.io/en/latest/fernet/) authenticated encryption for the **entire** bundle (refresh token, cached access token and access expiry), with a valid generated Fernet key supplied outside DB via private runtime configuration. Include immutable connection ID, provider and owner `sub` inside the authenticated plaintext and verify equality after decrypt to reject ciphertext swapping. Persist key version; one active key is sufficient here, and changing it requires explicit reconnect rather than a new rotation service. Wrong/missing key, altered ciphertext or mismatched context fails closed with `credentials_unavailable`, while health and login remain usable. Never serialize this internal contract through public Pydantic responses. This deliberately replaces research's lower-level AES-GCM suggestion with a simpler reviewed authenticated-encryption API; both meet at-rest encryption, but Fernet avoids app-owned nonce management. Encrypted cached access token is necessary for cross-process reuse after refresh; refresh-only persistence would cause follower refresh storms.

Provider read path: owner service checks connection status/full scopes; short DB read/decrypt cached bundle; if access expiry is at least 60 seconds away, use it. Otherwise claim a **30-second** PostgreSQL refresh lease via conditional update on connected status, generation, credential version and absent/expired lease; commit. Refresh HTTP deadline is 10 seconds, outside DB transaction. Lease holder saves a fresh encrypted bundle only if status, generation, credential version, lease owner **and unexpired lease** still match; advance credential version and clear lease. Preserve an omitted refresh token; replace only when provider supplies a new one. Use DB time for leases and timezone-aware expiry.

Followers re-read with bounded jitter and a 12-second overall deadline, then reuse the committed cached token or return typed `refresh_busy`; never launch an overlapping refresh while another valid lease exists. Expired lease permits recovery; stale lease holder cannot commit. Cancellation and transient HTTP errors release the matching lease or let it expire, preserving credentials. `invalid_grant` conditionally advances generation, purges stale bundle and sets reconnect-required; do not loop retries. Never allow an error from an old refresh to purge a newer grant.

Before every product provider operation, a short transaction locks the connection row and validates connected status, full scopes and generation. Its successful commit is the admission point, serialized with disconnect on that row. End the transaction before HTTP and bound each admitted operation. Disconnect rejects every new admission after its committed block; previously admitted work counts as in flight even if network dispatch has not happened. Cancel where possible and check generation after HTTP before returning or persisting results; discard stale results. An admitted call may still finish externally, so this contract does not promise an absolute HTTP-send cutoff. No in-memory lock substitutes for PostgreSQL coordination; future worker can call the same service without creating a worker in this issue.

## Disconnect/revoke flow

1. Validate session/CSRF/Origin. In one transaction lock the connection row; if a revoke is already in progress/unknown, return its existing safe status without advancing its generation or dispatching again. Otherwise take a bounded in-memory token snapshot, increment generation/credential version, mark disconnected, invalidate outstanding consent attempts/leases and purge stored credential ciphertext. If there is a snapshot, persist a unique revoke operation ID with state `in_progress` and outcome `unknown`; if no token and no outstanding operation, record `not_attempted`. Repeated disconnect must preserve an existing in-progress/unknown marker rather than clear it or dispatch another revoke. **Commit this local block, purge and reconnect gate before contacting Google.**
2. Send the snapshot token to the fixed Google revocation endpoint once with a 10-second deadline outside the transaction. Update metadata only if operation ID and generation still match. A documented successful response resolves the marker and records confirmed; ambiguous/non-success/timeout records unknown. Snapshot lives only in request memory and is discarded. Crash/cancellation leaves the committed disabled/purged state and a reconnect gate; expiry of the HTTP deadline never automatically unlocks it. Consent start and final promotion both enforce this gate, so delayed old revocation cannot target a newer grant.
3. UI explains that revocation may remove all scopes/clients under the same Google Cloud project for this user. The explicit disconnect click authorizes the action. Show local disconnected status separately from confirmed/unknown remote revocation; disable Reconnect while the gate is unresolved and show manual Google Account grant-removal guidance. Document a narrow explicit operator recovery procedure: first ensure the old dispatch has finished or its owning process has stopped, verify Google grant cleanup, then clear only the matching unresolved marker in a guarded local transaction. Never replay an old revoke after recovery/new consent. No recovery worker, new public recovery endpoint or automatic retry is added. Logout remains independent and leaves connection credentials unchanged.

## Provider reads and live smoke

Provide narrow Gmail/Calendar REST adapters only for connection verification/read access: Gmail list at most one message ID and fetch minimal metadata headers without body; Calendar `calendarList.list` then `events.list` for an accessible secondary/shared calendar with bounded page/result counts. Required calendar-list scope supports discovery beyond primary. Validate only required provider fields into typed internal values; do not persist or print mailbox/event content. No send adapter/call, synchronization, ingestion/cursor or job is introduced.

Add an opt-in local `scripts/live-google-smoke.py` under the backend project. It is an operator test harness, not a public endpoint or production auth bypass. Browser owner completes normal #5 login and #6 consent; harness reads only that configured owner's connected service state through local runtime resources. It performs the minimal reads above and holds a copy of the tested access token **in memory only**. Before disconnect, refresh if necessary so its remaining lifetime exceeds the 10-second disconnect deadline plus the entire 120-second observation window plus at least 30 seconds of clock margin (strictly more than 160 seconds). Confirm a successful read immediately before disconnect and record only the expiry deadline, never token contents. Operator disconnects through the authenticated browser UI while the harness remains alive; harness checks DB disabled/purged and fresh service calls rejected, then calls the same bounded read directly against Google with its pre-disconnect token until Google rejects credentials, polling at bounded intervals for at most 120 seconds. Reject observations at/after the conservative expiry cutoff as inconclusive; ordinary expiry never proves revocation. Use a separate process/client for this remote check so local authorization failure cannot masquerade as Google revocation. Record only revision/time/result categories, not tokens, message IDs, calendar IDs or content.

A Google revoke 200 plus local block is insufficient for the remote verification criterion. Require observed remote credential rejection within the propagation window, or owner-observed removal of this app/project grant in Google Account connections as separately recorded evidence. If the snapshot has insufficient lifetime, rejection can be explained by natural expiry, propagation is unresolved or API merely returns transient errors, record remote verification **PENDING/unknown**, never passed. Reconnect after a passed test requires a resolved revoke gate and the owner's explicit browser action. No sends under any smoke mode.

Prerequisites remain **PENDING**: real configured-owner session, OAuth project/client and exact HTTPS callbacks, Gmail/Calendar APIs, approved test-user/consent state, runtime encryption key and an accessible secondary/shared calendar. Google External Testing refresh grants may expire after seven days; classify that as reconnect-required, not a local refresh bug. `gmail.readonly` is restricted; `gmail.send` and the selected Calendar scopes are sensitive. Operator must verify the applicable consent/publishing requirements before live use; this plan neither provisions them nor claims production approval. See [scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes), [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth) and [token expiry](https://developers.google.com/identity/protocols/oauth2#expiration).

## Files and sequential ownership

| Action | Files | Purpose |
|---|---|---|
| Modify | `apps/backend/pyproject.toml`, `apps/backend/uv.lock`, `apps/backend/src/email_support/config.py`, `apps/backend/src/email_support/main.py` | Encryption dependency, secret config and composition |
| Modify | `apps/backend/src/email_support/integrations/google_oidc.py`, `apps/backend/src/email_support/storage/postgres/persistence/access.py`, `apps/backend/src/email_support/storage/postgres/persistence/tables/access.py` | Reuse protocol; session/purpose/generation binding for consent |
| Create | `apps/backend/src/email_support/api/google_connection.py`, `apps/backend/src/email_support/models/google_connection.py` | Owner endpoints/public errors and internal typed credential/result contracts |
| Create | `apps/backend/src/email_support/services/google_connection.py` | Scope, encryption, refresh and disconnect invariants |
| Create | `apps/backend/src/email_support/integrations/google_workspace.py` | Bounded async Gmail/Calendar read and revoke HTTP boundary |
| Create | `apps/backend/src/email_support/storage/postgres/persistence/google_connection.py`, `apps/backend/src/email_support/storage/postgres/persistence/tables/google_connection.py` | Conditional generation/lease storage and mappings |
| Modify | `apps/backend/src/email_support/storage/postgres/persistence/tables/__init__.py` | Register metadata |
| Create | `apps/backend/migrations/versions/create_google_connections.py` | Additive successor to phase 1 revision; extend consent-attempt constraints |
| Create | `apps/backend/tests/unit/google_connection/test_connection.py`, `apps/backend/tests/integration/test_google_connection_contracts.py`, `apps/backend/tests/database/google_connection/test_connection_storage.py` | Provider-boundary and real PostgreSQL tests |
| Modify | `apps/backend/tests/database/migrations/test_migrations.py` | Head, old-head preservation and restore coverage for each new revision |
| Create | `apps/web/src/features/google-connection/GoogleConnectionPanel.tsx`, `apps/web/src/features/google-connection/use-google-connection.ts`, `apps/web/src/shared/api/google-connection.ts` | Typed connection UI and generated-client wrapper |
| Modify | `apps/web/src/app/App.tsx`, `apps/backend/openapi.json`, `apps/web/src/shared/api/generated/` | Compose feature and regenerate contracts |
| Create | `apps/web/tests/unit/google-connection.test.tsx`, `apps/web/tests/unit/google-connection-api.test.ts`, `apps/web/tests/e2e/google-connection-smoke.spec.ts` | Actionable states/API guards/default signed-out gating |
| Modify | `apps/web/playwright.config.ts`, `compose.auth.yaml`, `scripts/local-auth.sh` | Explicit smoke discovery and private key configuration validation |
| Create | `apps/backend/scripts/live-google-smoke.py` | Opt-in real-provider verification with ephemeral token snapshot |
| Modify | `docs/06-deployment-guide.md`, `docs/03-codebase-summary.md` | Owning setup, smoke/manual revoke, module and failure/rollback routes |

Delete: none. All changes occur after phase 2 releases shared files. Full-scope boundaries require >8 files, but no class-per-operation or generic token-vault abstraction. Feature modules interact only through shared generated API/contracts.

## Tests Before — RED

- [x] Encode failing behaviors before implementation and verify expected invariants with focused tests. Module/404 failures alone are insufficient once interfaces exist.
- [ ] Provider/API: exact requested scopes, offline separate consent, bad state/purpose/browser/session, expiry/replay, invalid token claims, different subject, denied/partial grant, initial missing refresh token, reauth missing/replacement refresh, sanitized typed errors and no token/log/response leaks.
- [ ] Encryption: SQL row contains ciphertext only, round-trip/context identity validation, wrong key/altered data fails closed, no cached access token plaintext.
- [ ] Real PostgreSQL with deterministic barriers: two processes/independent sessions racing refresh get one HTTP call and shared new token; lease expiry/crash; stale holder completion; invalid_grant versus newer consent; disconnect during refresh; callback versus logout/session expiry/disconnect/new consent with barriers at final session-lock/write; ensure all stale writes fail CAS. Pause after operation admission and before HTTP, commit disconnect, then verify new admissions reject and the admitted operation's stale result is discarded.
- [ ] Disconnect tests inspect DB **before** provider revoke executes: disabled, generation advanced, bundle purged. Test timeout, cancellation and crash boundary leave purged state and unknown remote status; referenced canonical rows survive. Delay revoke while attempting new consent/promotion: both reject until resolution; timeout/crash never auto-unlocks, repeated disconnect preserves the marker, and operator recovery cannot allow an old dispatch/retry to revoke a new grant. Test the smoke expiry false-positive with a controlled clock/provider boundary.
- [ ] UI: connected, disconnected, reconnect-required with exact missing scopes, transient failures, auth expiry, unknown revoke/manual action, same-project warning, logout leaves connection independent. API wrappers validate generated responses and cancellation/CSRF.
- [ ] Migration tests preserve phase 1 sessions and original canonical rows across phase 3, with backup/restore through existing harness and metadata registration. Update the three head assertions identified in phase 1 to the actual phase 3 revision without losing prior-revision fixtures.

## Implementation/refactor and Tests After — GREEN

- [x] Implement schema/storage/encryption, then provider/service concurrency rules and API; reuse Authlib, owner guards and session factories.
- [x] Implement generated/validated web wrapper and connection UI; add smoke discovery explicitly without widening Vitest into E2E.
- [ ] Run focused → broad → browser checks, refactor only while invariants pass; record redacted evidence. No runtime/test execution is claimed in this plan.

Existing commands with **future-only paths** after creation:

```sh
(cd apps/backend && uv run --locked pytest -q tests/unit/google_connection/test_connection.py tests/integration/test_google_connection_contracts.py)
./scripts/check-database.sh local tests/database/google_connection/test_connection_storage.py tests/database/migrations/test_migrations.py
npm --prefix apps/web run test -- tests/unit/google-connection.test.tsx tests/unit/google-connection-api.test.ts
make generate
make check
make database-check
make up
npm --prefix apps/web run test:smoke -- --list
npm --prefix apps/web run test:smoke
make down
```

Use phase 2 ownership checks before starting/stopping runtime. Only after intentional generated changes are reviewed/committed and paths clean run `make check-api-drift`; clean-checkout CI also enforces it. Proposed opt-in command, **not available until implemented and prerequisites supplied**: `(cd apps/backend && uv run --locked python scripts/live-google-smoke.py)`, using private runtime configuration without command-line token arguments. Phase 2 `./scripts/local-auth.sh migrate` validates a retained backup archive before an actual local schema upgrade; head is a no-op and recovery remains covered by real restore tests. Keep live Google outside CI and default tests.

## Scenario matrix and success

| Layer | Scenario | Observable result |
|---|---|---|
| Unit/API | Wrong owner/session/state/claims or incomplete scopes | No enabled connection; exact typed actionable outcome |
| Encryption/contract | DB dump, tampered bundle, API/log capture | Encrypted credentials only; no secret disclosure |
| Real DB | Concurrent refresh, lease crash, logout/disconnect/new-consent races | One refresh holder; session lock serializes finalization/logout; stale results discarded; no consent during unresolved revoke |
| DB/provider | Missing refresh, invalid_grant, transient timeout | Preserve valid prior refresh where permitted; purge invalid grant; bounded retry/busy outcome |
| UI/browser | Auth-gated status and disconnect | No owner feature when signed out; truthful local/remote states |
| Live Google | Owner login/consent, minimal Gmail + secondary/shared Calendar read, disconnect | Real reads pass; local credentials purged; independent remote revocation evidence before token expiry, or explicit pending gap |

- [ ] All original #6 criteria have independent evidence; partial-scope/revoked/expiry/transient UI is actionable.
- [ ] Scope check/log capture confirms no send call, token response or secret log; no jobs or data ingestion was added.
- [ ] Live verification gap remains PENDING until actual Google evidence exists. Owner acceptance/merge/closure are separate from passing tests.

## Risk, compatibility and rollback

| Risk | Likelihood × impact | Mitigation / stop signal |
|---|---|---|
| Late consent/refresh restores disconnected credentials | Medium × High | Generation + live-session + lease CAS, pre-revoke purge and deterministic race tests |
| Ciphertext copied between accounts or key lost | Low × High | Authenticated context validation; external key; fail closed and explicit reconnect |
| Provider ambiguity/partial consent misreported | Medium × High | Required full set, typed outcomes, local/remote disconnect distinction |
| Revoke affects same-project clients or propagates slowly | Medium × High | Warning before action, bounded external verification, unknown/manual removal state |
| Google setup/testing restrictions block smoke | High × Medium | Keep live gate pending; no fake success or scope expansion |

Backwards compatibility: no remapping/deletion of canonical provider accounts or mail/meeting FKs; additive migration follows phase 1 head, login continues independently, default health/Compose remain credential-free. Changing owner `sub` must reject existing sessions/connections, not migrate them silently. Rollback blocks Google provider work, stops owned runtime, reverts connection UI/routes to verified #5 while retaining additive tables and local blocked/purged state. Never restore a pre-disconnect credential bundle or reverse generation merely to roll back code; provider revoke cannot be undone by DB restore. Recovery is explicit owner reconnect. A destructive downgrade/restore needs verified backup and separate owner authorization; no production action is planned.

## Handoff and unresolved questions

- [ ] Report per-criterion checks/live evidence, redacted failure categories and pending prerequisite list; leave #7 and #15 untouched.
- [ ] Offer the #6 result for independent review and owner acceptance; no automatic merge/closure/deploy.

Unresolved product questions: none. OAuth provisioning, external key and real Google smoke are pending operational prerequisites. Authoritative behavior sources: [Google web-server OAuth/revocation](https://developers.google.com/identity/protocols/oauth2/web-server), [best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices), [OAuth policy](https://developers.google.com/identity/protocols/oauth2/policies), [Authlib async client](https://docs.authlib.org/en/stable/oauth2/client/http/index.html), [Fernet](https://cryptography.io/en/latest/fernet/).

<!-- Updated: Validation Session 2 - owner approved revoke/reconnect gate, admission semantics, session locking and expiry-safe smoke. -->
