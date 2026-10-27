---
title: "Phase 2: Access UI and independent Issue 5 verification"
status: done
priority: P1
effort: 10h
---

# Phase 2: Access UI and independent Issue 5 verification

## Dependencies and requirements

Depends on phase 1. Finish only #5 and produce a standalone review/acceptance result before phase 3. Read [interface guidelines](../../docs/05-design-guidelines.md) and generated phase 1 contracts before editing.

- [x] Show useful loading, signed-out/expired-session, signing-in, owner-rejected, auth-unavailable and provider-failed states.
- [x] Owner can initiate login and sign out; auth credentials never enter localStorage/sessionStorage or the rendered DOM.
- [x] Keep public health visible and usable with no auth environment.
- [x] Supply an explicit opt-in authenticated local runtime with separate persistent PostgreSQL and safe migration backups.
- [x] Verify #5 independently with automated evidence; configured-owner Google login remains pending because operator OAuth setup was not available, and is not called accepted.

Existing [App.tsx:5](../../apps/web/src/app/App.tsx#L5) uses a health query only. [health.ts:6](../../apps/web/src/shared/api/health.ts#L6) bounds requests and forwards caller cancellation; preserve these properties for new API wrappers. Default Compose has API/web only at [compose.yaml:1](../../compose.yaml#L1); the test service is separately owned and guarded. Browser discovery currently matches health only at [playwright.config.ts:5](../../apps/web/playwright.config.ts#L5), while Vitest includes only unit files at [vite.config.ts:27](../../apps/web/vite.config.ts#L27).

## UI/data flow

`App` composes the access feature and existing health panel. The feature reads the session through TanStack Query. A 401 clears authenticated cached data and in-memory CSRF, then renders signed-out or expired text from the typed backend reason. A 503 renders actionable setup/service-unavailable text without pretending login succeeded. Use accessible semantic buttons, focus and alerts, no new visual framework.

Login click fetches preauth, then posts its CSRF header with same-origin credentials. Validate generated authorization response and navigate to its backend-controlled URL. Keep preauth/session CSRF in JS memory only. Reload obtains fresh session data; mutations wait for current session bootstrap. A login callback URL result is an allowlisted display hint; the session endpoint establishes authenticated state. Logout sends the session CSRF header; on success clears all owner queries and shows signed-out. On network failure retain an honest unknown/local-refresh state and re-fetch session before asserting logout. Cross-feature shared API wrappers never import access feature internals.

Generated client and Zod validators own shapes. New wrappers explicitly validate responses and propagate deadline/caller abort, using the same origin proxy. Do not hand-maintain response schemas or use an E2E login bypass. Default no-config runtime shows health plus auth-unavailable; it does not imply an owner session exists.

## Authenticated local route (proposed, not available yet)

Add `compose.auth.yaml`, layered over `compose.yaml`, with an `auth` profile PostgreSQL service using the same pinned Postgres image already verified in `compose.test.yaml`, its own database/user/credentials and private network-only port. Store persistent data/backups under ignored `.local-auth/` with owner-only permissions. It must never use `.test-database`, port 55432, the test administrator or CI credentials. API uses this DB only under the explicit overlay, gets auth settings from a private ignored file/operator environment, and waits for PostgreSQL health. Public web/API ports stay deterministic 5173/8000; inspect ownership before start and refuse occupied unrelated ports rather than incrementing.

Add a narrow `scripts/local-auth.sh {up|migrate|down}` route; this is local development support, not production deployment. `up` validates explicit settings presence without printing values, creates protected runtime directories, starts this exact Compose project/profile, calls guarded `migrate`, then starts API/web. `migrate` verifies the exact owned runtime PostgreSQL container/volume/project identity and existing database; refuses test/remote URLs. Determine the current revision and target head with checked command results: already at head is a no-op with no mutation or backup. An empty initial DB is an explicit verified base state without an Alembic row; a failed revision query is an error, never evidence of emptiness. Run container `pg_dump --format=custom` into a mode-0600 archive in `.local-auth/backups/` **before every actual schema mutation**, including initial install, then validate the archive with `pg_restore --list`. On any failure stop migration and retain archive. Do not restore into a temporary database on every normal migration; reuse the existing real-DB restore suite for recovery verification. Run Alembic upgrade in a one-shot API container after backup verification, passing the runtime URL internally as `EMAIL_SUPPORT_ALEMBIC_DATABASE_URL`; never print the URL or secrets. Include migrations and `alembic.ini` in the backend image so that this command is real. Use explicit one-shot `run --rm --no-deps` ordering to avoid API starting before migration. `down` stops only this owned project and preserves data/backups. Do not reuse/relax the test harness guards; its existing backup-before-migration and restoration scenarios remain the automated verification route.

Default `make up`, `make down` and existing CI smoke remain credential-free. Use a different Compose project name for opt-in runtime; both routes bind the same documented ports and therefore cannot run together. Record command/container ownership and stop only resources started by the executor. Production secure-cookie behavior is asserted in tests; local loopback HTTP uses the explicit phase 1 exception, while actual public callback setup requires stable HTTPS. No tunnel, DNS or production setup is provisioned here.

## Files and sequential ownership

| Action | Files | Purpose |
|---|---|---|
| Create | `apps/web/src/features/access/AccessPanel.tsx`, `apps/web/src/features/access/use-access.ts` | Feature rendering and query/mutation state |
| Create | `apps/web/src/shared/api/access.ts` | Generated/validated access calls with deadlines/cancellation |
| Modify | `apps/web/src/app/App.tsx`, `apps/web/tests/unit/App.test.tsx` | Compose access with health; preserve useful health states |
| Create | `apps/web/tests/unit/access.test.tsx`, `apps/web/tests/unit/access-api.test.ts` | UI transitions and boundary errors/cancellation |
| Create | `apps/web/tests/e2e/access-smoke.spec.ts` | Real API/proxy signed-out or unavailable access surface, no bypass |
| Modify | `apps/web/playwright.config.ts` | Explicitly discover health/access smoke files; retain unit/E2E isolation |
| Modify | `apps/backend/openapi.json`, `apps/web/src/shared/api/generated/` | Generated artifacts only through `make generate` |
| Create | `compose.auth.yaml`, `scripts/local-auth.sh` | Opt-in separate local runtime, backup/migrate/stop |
| Modify | `apps/backend/Dockerfile`, `.gitignore` | Include Alembic assets; ignore private runtime storage |
| Create | `apps/backend/tests/unit/test_local_auth_runtime.py` | Command-boundary checks plus real disposable-runtime initial/no-op/upgrade/failure scenarios |
| Modify | `docs/06-deployment-guide.md`, `docs/03-codebase-summary.md` | Smallest owning local-auth setup/commands and actual new module navigation |

Delete: none. Paths are proposed except existing source/config/docs/generated surfaces. Phase 2 acquires shared files only after phase 1 completes; phase 3 acquires them after #5 gate. More than eight files follows necessary UI, generated contracts, runtime ownership and test boundaries; do not add a design system, generalized CLI or deployment pipeline.

## Tests Before — RED

- [x] Add UI tests for initial session loading, 401 missing/expired, 503, owner rejection, retryable provider failure, login navigation and signout; assert retained health panel and keyboard-accessible state text.
- [x] Add API-wrapper tests for strict generated response validation, CSRF header, same-origin credentials, request deadline, caller cancellation and cleanup. Provider doubles stay at API boundary for UI unit tests.
- [x] Add discovery tests/checks showing both smoke files selected by Playwright while Vitest excludes E2E; existing health assertion may need a narrower locator after access adds another status region.
- [x] Test refusal of foreign/test database identity and occupied unrelated ports, private paths, archive validation before Alembic and failure-stop behavior. Exercise empty install, head no-op, old-head upgrade with seeded-data preservation, and injected archive-verification failure on the real disposable PostgreSQL runtime. Keep the existing real-DB restore suite.
- [x] Record behavior-level RED failures before implementing each behavior; do not treat module/404 failures alone as evidence once interfaces exist.

## Implementation/refactor and Tests After — GREEN

- [x] Implement wrappers and access feature, compose App, then add opt-in runtime route and smallest documentation updates.
- [x] Regenerate contracts intentionally and review changed generated files; no generated contract changes were needed.
- [x] Run default browser smoke against actual Compose API/web and inspect authenticated local setup with real DB. Live Google login remains pending; phase 1 login/expiry/logout persistence coverage remains in place.

Existing commands with **future-only test targets** (execute only after files exist):

```sh
npm --prefix apps/web run test -- tests/unit/access.test.tsx tests/unit/access-api.test.ts
(cd apps/backend && uv run --locked pytest -q tests/unit/test_local_auth_runtime.py)
make generate
make check
make database-check
docker compose config --quiet
make up
npm --prefix apps/web run test:smoke -- --list
npm --prefix apps/web run test:smoke
make down
```

Inspect current process/port ownership before `make up`; do not stop an existing user's stack. New commands, **proposed until script creation**, are `./scripts/local-auth.sh up`, `./scripts/local-auth.sh migrate`, `./scripts/local-auth.sh down`. Document required private config names, safe defaults and backup location in the guide before users invoke them. Backend CI already runs real DB via [ci.yml:45](../../.github/workflows/ci.yml#L45); browser job uses default Compose at [ci.yml:91](../../.github/workflows/ci.yml#L91), requiring no Google secrets. No authenticated runtime credential is added to CI.

After reviewed generation is committed and generated paths are clean, run `make check-api-drift` (or CI's clean checkout gate). The script deliberately rejects dirty generated paths before generation; never prescribe it immediately after dirty regeneration as a passing check.

## Scenario matrix and #5 success boundary

| Layer | Scenario | Required result |
|---|---|---|
| Web unit | Signed-out/expired/unavailable/provider failure | Distinct actionable states; health retained |
| Web API | Abort, deadline, malformed data, CSRF | Generated validation rejects; cancellation propagates; no lingering listeners/timers |
| Browser/default runtime | Real proxy and health; no auth environment | 200 health; useful auth-unavailable state; both smoke files discovered |
| Real DB/API | Session rotation, expiry, logout, unsafe calls | Phase 1 invariants still pass |
| Local runtime | Empty install, head no-op, old-head upgrade, failed backup | Real disposable-route evidence; initial/upgrade archives validated before mutation; no-op skips backup/mutation; errors stop promotion |
| Live Google/manual | Owner signs in; different Google identity rejects; signout/reload | Backend identity rule and real secure callback/session path verified without captured secrets |

Live prerequisites: owner provisions verified Google `sub`, OAuth client, exact callback URI and trusted origin. Use only `openid email` for login, no offline access; discard provider tokens even if previous grants appear. Record check times, revision, pass/fail and redacted categories only; do not record account identifiers or credentials. If prerequisites are absent, mark live checks **PENDING** and do not declare #5 owner acceptance/runtime success. Automated tests and a reviewable PR can still be prepared independently.

- [x] Present #5 scope alone for review, list every original criterion and evidence/gap, and retain owner acceptance/merge authority.
- [x] Pause before phase 3 until the owner resolves #5 acceptance/merge and dependency status. No issue or Project state was changed.

## Risks, compatibility, rollback and handoff

| Risk | Likelihood × impact | Mitigation / stop signal |
|---|---|---|
| Misleading UI says logged out after failed request | Medium × High | Re-fetch session; typed unknown/failure state |
| Runtime accidentally uses disposable test DB | Medium × High | Dedicated project/database/private path; script refuses test identity |
| Backup or migration order is wrong | Medium × High | Validate archive before actual upgrade; retain real restore-suite coverage; fail closed and retain archives |
| Browser checks silently undiscovered | High × Medium | Explicit testMatch and `--list`, retain Vitest include boundary |
| Google setup absent | High × Medium | Pending live gate, no fake auth bypass or acceptance claim |

Backwards compatibility: health/default `make up` and CI need no credentials; additive UI only; canonical data stays intact. Rollback reverts feature/runtime-overlay changes, stops owned local processes, keeps runtime DB and verified archives, and leaves phase 1 additive schema. Do not downgrade a persistent database merely to revert UI. Restore a verified backup only with explicit data-loss authorization. Hand phase 3 verified contract conventions and a reviewable/accepted #5 baseline; no Gmail scope is required to complete #5.

Unresolved questions: none. Operational OAuth setup/live verification remain pending prerequisites, not silently removed acceptance criteria.

## Phase 2 execution evidence

- TDD RED: malformed session data initially passed the wrapper test, showing the boundary needed explicit strict parsing; the UI tests also exposed missing access-error handling. GREEN: 27 web unit tests and 65 backend unit/integration/contract tests pass.
- `make check`, `make check-api-drift`, `make generate`, and `git diff --check` passed. Web typecheck, lint, format check and production build passed. `make database-check` passed all 47 PostgreSQL migration/storage/backup/restore checks.
- Playwright lists exactly two smoke files. Both passed against the credential-free default Compose stack, and both passed against the opt-in authenticated Compose stack through its real API proxy. Both stacks were stopped after their checks.
- The disposable authenticated database installed from empty state with a validated mode-0600 archive; rerunning at head made no backup. An old-revision upgrade to `b17e9a4d2c61` preserved a seeded `migration_probe` row. A forced `pg_restore --list` failure on that runtime stopped before Alembic and retained a mode-0600 archive; the revision stayed at `da3c8e14f627`. The test runtime used nonfunctional local OAuth values and made no Google request.
- Real Google owner login and different-identity rejection remain PENDING until operator OAuth setup. No production runtime was exercised.
- `local-auth.sh down` preserved the disposable test data as designed. An execution guard rejected removal of the test-only ignored `.local-auth/` directory, so its synthetic config, stopped database files, and test archives remain in the workspace. No live OAuth credentials or owner data were used.

<!-- Updated: Validation Session 2 - owner approved backup on actual schema mutation; explicit empty/no-op handling and real script verification. -->
