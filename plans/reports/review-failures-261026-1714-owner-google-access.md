# Failure-mode and contract review

Scope: the four documents in `plans/261026-1714-issue-5-6-owner-google-access/`. Read-only source verification; no builds, tests, provider calls or GitHub mutations. Flags: `--hard --tdd --yagni`. Accepted same-account, secondary/shared calendars and 12h absolute sessions are preserved. Proposed auth/connection/runtime files do not exist yet; findings below concern the specified implementation contract, not existing application defects.

## Findings

### High — A live-session predicate alone does not serialize callback completion with logout

- Plan: `phase-03-google-connection-and-verification.md:41` requires a final conditional write guarded by live session and promises logout makes late callback results unusable; `phase-01-start.md:36` deletes only the current session on logout.
- Current source boundary: `apps/backend/src/email_support/storage/postgres/persistence/database.py:13` constructs an ordinary async engine without a stronger isolation policy; `:16-20` leaves transaction ownership to callers. Existing helpers such as `apps/backend/src/email_support/storage/postgres/persistence/core.py:60-74` flush within that caller-owned transaction rather than providing cross-operation serialization.
- Failure: callback C executes a connection UPDATE with an `EXISTS(live_session)` predicate. Logout L deletes the separate session row and commits while C is completing. C can still commit its connection write because its statement saw the session before L committed and no conflicting session-row lock was acquired. Rechecking before the UPDATE does not fix this ordering.
- Minimal fix: specify that callback finalization locks the referenced session row in the same short transaction as its generation-conditional connection write; logout deletion must conflict with that lock. Define the serialization point, and add a real PostgreSQL barrier test for final-write versus logout DELETE/commit, rather than only exchange-versus-logout.

### Medium — Empty runtime database has no revision or representative rows to verify before its first migration

- Plan: `phase-02-owner-access-ui-and-verification.md:34` mandates restoring the pre-upgrade archive and checking revision/representative rows before every upgrade; `:97` explicitly requires empty-install success. It does not define an empty/base verification branch.
- Current code evidence: `apps/backend/scripts/test_database.py:745-751` backs up a newly created **empty** target. `apps/backend/tests/database/conftest.py:46-50` migrates that target before yielding it. Existing revision/row restore checks at `apps/backend/tests/database/migrations/test_migrations.py:98-120` therefore run against an already migrated, seeded source and query `alembic_version` unconditionally. They do not prove the first-install runtime sequence.
- Failure: copying the existing revision check into the new pre-upgrade restore verifier raises undefined-table on `alembic_version` for a fresh runtime DB and stops first installation before Alembic can create it. Requiring representative canonical rows likewise cannot succeed there.
- Minimal fix: record the source state before backup as either verified empty/base or a recognized revision. Restore verification must compare against that state: absence of application tables/version is valid only for verified empty/base; existing databases require revision and representative-row comparison. Add an actual disposable-runtime empty-install execution of the new script, using private synthetic settings and no Google HTTP, plus a seeded-upgrade case. Existing command-boundary unit tests and the old DB fixture cannot validate this new lifecycle by themselves.

### Medium — Natural access-token expiry can falsely pass remote-revocation smoke

- Plan: `phase-03-google-connection-and-verification.md:50` permits a cached token with only 60 seconds remaining; `:66-68` polls its pre-disconnect snapshot for up to 120 seconds and accepts remote credential rejection as revocation evidence.
- Current-source boundary: `apps/backend/src/email_support/main.py:5-8` exposes only health and `apps/backend/src/email_support/api/health.py:10-18` has no provider behavior. The planned smoke script is new; existing runtime/health smoke cannot establish its rejection classification. The plan itself explicitly persists the access expiry at phase 3 `:48-50`, so the harness can inspect it without introducing a new token service.
- Failure: smoke starts with a token valid for 65 seconds, disconnect revoke is ineffective/unknown, and Google later rejects the naturally expired token. The current pass rule records remote revocation even though the same rejection would occur without disconnect.
- Minimal fix: require a freshly valid snapshot whose remaining lifetime exceeds the entire disconnect/poll window plus clock skew. Track its expiry in memory; any rejection at/after the safe expiry boundary is inconclusive. Add a controlled-provider smoke-classifier test in which expiry occurs without revocation and must remain pending.

### High — Late provider revoke can invalidate a newer successful consent grant

- Plan: `phase-03-google-connection-and-verification.md:39-42` allows new consent after generation advance; `:58-60` purges then revokes outside the transaction and fences only the eventual metadata write. The same-project revocation scope is acknowledged at `:60`.
- Current-source boundary: `apps/backend/src/email_support/storage/postgres/persistence/database.py:16-20` supplies caller-owned DB transactions; there is no existing durable provider-operation coordinator in `apps/backend/src/email_support/main.py:5-8` to supply the missing ordering. The planned connection state is only three states at phase 3 `:25`, and no persisted revoke-in-flight dispatch gate is specified.
- Failure: disconnect commits purge, revoke request is delayed; explicit reconnect obtains and persists a new grant; delayed revoke reaches Google and removes that project/user grant. Generation CAS prevents a stale local metadata update but cannot undo the remote side effect. Local state can claim connected while its new refresh grant is invalid.
- Minimal fix: add a narrowly scoped durable revoke-in-flight fence that prevents consent initiation/finalization while a prior revoke can still be dispatched or is in flight. Define crash/timeout handling honestly; an ambiguous remote outcome must not be presented as a safely ordered reconnect. Add a barrier test delaying actual revoke dispatch until after a concurrent reconnect attempt. This overlaps the security/assumptions review and needs one controller-owned resolution.

## Source facts checked

These checks validate current facts only; proposed behavior remains unimplemented.

| Phase | Checked fact | Current source evidence |
|---|---|---|
| 1 | App only composes health | `apps/backend/src/email_support/main.py:5-8` |
| 1 | Health has no DB/provider dependency | `apps/backend/src/email_support/api/health.py:16-18` |
| 1 | Engine construction is lazy | `apps/backend/src/email_support/storage/postgres/persistence/database.py:11-13` |
| 1 | Session lifetime belongs to caller | `apps/backend/src/email_support/storage/postgres/persistence/database.py:16-20` |
| 1 | Authlib is not installed as a production dependency yet | `apps/backend/pyproject.toml:10-18` |
| 1 | HTTPX2 currently belongs to dev dependencies | `apps/backend/pyproject.toml:20-27` |
| 1 | OpenAPI export imports app without starting server | `apps/backend/scripts/export-openapi.py:6-13` |
| 1 | Default test discovery excludes database scenarios | `apps/backend/pyproject.toml:32-36` |
| 1 | Existing migration head asserted as da3c8e14f627 | `apps/backend/tests/database/migrations/test_migrations.py:61` |
| 1 | DB fixture migrates before scenario seed | `apps/backend/tests/database/conftest.py:46-51` |
| 2 | App currently has only a health query | `apps/web/src/app/App.tsx:5-9` |
| 2 | Health wrapper forwards caller cancellation | `apps/web/src/shared/api/health.ts:12-19` |
| 2 | Health wrapper cleans deadline/listener | `apps/web/src/shared/api/health.ts:38-41` |
| 2 | Default Compose contains API/web | `compose.yaml:1-27` |
| 2 | Public ports are deterministic loopback | `compose.yaml:5-6,26-27` |
| 2 | Current image omits migration assets | `apps/backend/Dockerfile:16-18` |
| 2 | Current image runs a non-root user | `apps/backend/Dockerfile:12-19` |
| 2 | Browser discovery matches only health | `apps/web/playwright.config.ts:4-5` |
| 2 | Vitest discovery is unit-only | `apps/web/vite.config.ts:25-28` |
| 2 | Existing restore command stops on error in one transaction | `apps/backend/scripts/test_database.py:687-690` |
| 3 | Provider natural key is provider + external account ID | `apps/backend/src/email_support/storage/postgres/persistence/tables/core.py:29-32` |
| 3 | Provider identity columns are non-null text | `apps/backend/src/email_support/storage/postgres/persistence/tables/core.py:46-47` |
| 3 | Creation takes caller session | `apps/backend/src/email_support/storage/postgres/persistence/core.py:60-62` |
| 3 | Creation performs insert/flush, not upsert | `apps/backend/src/email_support/storage/postgres/persistence/core.py:63-68` |
| 3 | Existing getter requires UUID, not owner subject | `apps/backend/src/email_support/storage/postgres/persistence/core.py:77-80` |
| 3 | Duplicate natural key raises PersistenceConflict | `apps/backend/src/email_support/storage/postgres/persistence/core.py:51-57` |
| 3 | Existing backup is a custom-format archive | `apps/backend/scripts/test_database.py:612-614` |
| 3 | Existing archive permissions start at 0600 | `apps/backend/scripts/test_database.py:604` |
| 3 | Existing archive validation rejects symlinks/unowned/public files | `apps/backend/scripts/test_database.py:634-650` |
| 3 | Migration URL is supplied by dedicated environment variable | `apps/backend/migrations/env.py:21-29` |

## Limits and unresolved questions

- Refresh lease duration/deadline/CAS and crash recovery are explicitly planned at phase 3 `:50-52,100`; no additional unproven lease defect is asserted.
- The preflight-to-HTTP dispatch gap is also real at phase 3 `:54`, but is already covered by the other review; it is not duplicated as a separate finding here.
- The proposed runtime script must select/build the migration-capable image, but its absence today is expected and is not itself an implementation defect.
- No plan or implementation files were changed. Controller must adjudicate the findings before plan edits.
- Unresolved: exact serialization semantics for logout versus consent finalization, and reconnect eligibility after ambiguous provider revoke.

Status: DONE_WITH_CONCERNS
Summary: Four actionable plan-contract findings; distinct gaps are session/logout serialization, empty-database restore verification and expiry-induced false-positive revoke smoke. Late remote revoke overlaps another reviewer and should be resolved once.
Concerns/Blockers: Resolve the ordering contracts and encode the empty/base restore branch before implementation.
