# Deployment direction

## Target environment

Deploy the web app, FastAPI API, Python worker, PostgreSQL, Neo4j, and Qdrant through Docker Compose on a VPS, with Cloudflare as the public edge. Keep API and web under one public origin where practical.

Databases, metrics, and trace storage remain private to the deployment network. The browser receives no provider credentials. Google OAuth needs a stable verified HTTPS callback; public exposure must follow owner-access and session protection.

Set and measure resource limits, database caches, worker concurrency, research budgets, trace retention, and disk growth against actual workloads.

## Ship and deploy

Merge reviewed issue branches into `main` after the required checks pass. Merging code does not deploy it.

Deploy production explicitly from a validated `main` revision or release tag. GitHub Actions builds the backend and web images, publishes them to GHCR, and deploys recorded image digests through Docker Compose. The API and worker share the backend image. Do not rebuild source on the VPS or deploy automatically on every merge.

Use a protected production environment for deployment credentials and approval. A deployment must serialize against other deployments, back up PostgreSQL before schema changes, apply compatible migrations, check readiness, and record the deployed revision and image digests. On failure, stop promotion and use the verified rollback procedure; restoring application images alone cannot reverse incompatible data changes.

## Local canonical persistence verification

`make check` and `make check-api-drift` remain database-free. Maintainers can run the PostgreSQL migration, storage, backup, and restore suite with `make database-check`; `make database-up` and `make database-down` manage the reusable local test service. The local service binds to `127.0.0.1:55432` and keeps data and private credentials under the ignored `.test-database/` directory. A successful check removes its run's archives after cleanup verification. A failed run stops only the verified local service and retains local state and recovery files for investigation. Backend CI uses a job-scoped PostgreSQL service that is discarded with the job. These are development checks, not production backup storage, credentials, or a production restore procedure.

## Local authenticated development

Owner sign-in is opt-in and uses a separate Compose project and persistent PostgreSQL data. It does not reuse `.test-database/`, the test administrator, or CI credentials. Create `.local-auth/owner.conf` with mode `0600`, owned by the current user, containing these keys and the operator's Google OAuth values:

```text
EMAIL_SUPPORT_OWNER_SUB
EMAIL_SUPPORT_GOOGLE_CLIENT_ID
EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET
EMAIL_SUPPORT_GOOGLE_CALLBACK_URI
EMAIL_SUPPORT_WEB_ORIGIN
# Optional for login-only runtime; required for Google connection consent.
EMAIL_SUPPORT_GOOGLE_TOKEN_ENCRYPTION_KEY
```

The encryption key is a Fernet key generated with `cryptography.fernet.Fernet.generate_key()`. Keep it in the private local configuration, separate from PostgreSQL. Login and the local owner runtime can run without this optional key; Google connection consent requires it. Keep the key stable while encrypted credentials exist. Losing or changing it makes those credentials unavailable and requires an explicit reconnect.

For loopback development, register both callbacks on the same OAuth client: `http://127.0.0.1:8000/api/auth/google/callback` for owner login and `http://127.0.0.1:8000/api/google/connection/callback` for the separate Workspace grant. Use `http://127.0.0.1:5173` as the web origin. The configured Google subject must be the intended owner. Do not commit the file or copy its values into logs or shell history.

```sh
chmod 600 .local-auth/owner.conf
./scripts/local-auth.sh up
./scripts/local-auth.sh migrate
./scripts/local-auth.sh smoke
./scripts/local-auth.sh down
```

`up` refuses occupied unrelated ports 5173/8000. `migrate` checks the owned database and current Alembic revision, skips backups when already at head, and otherwise saves and validates a custom-format PostgreSQL archive before changing schema. Runtime data and archives remain under ignored `.local-auth/`; `down` stops this Compose project and preserves both. The route is local development support, not production deployment or backup storage. Default `make up`, `make down`, health smoke, and CI remain credential-free.

The opt-in `smoke` requires the encryption key, the owner to be signed in and connected, and an accessible secondary or shared calendar. Register both exact callbacks above, enable the Gmail and Calendar APIs, and satisfy Google's test-user/consent requirements first. The harness reads one Gmail message's metadata and at most one event from a secondary calendar, asks the owner to disconnect through the authenticated UI, checks local purge and blocked access, then checks whether Google rejects the old access token before its conservative expiry cutoff. It prints only result categories and the access-token expiry time. A missing calendar, transient response, timeout, or expiry cutoff leaves remote revocation pending; it never sends mail.

For an external OAuth app in Testing, Google refresh grants expire after seven days when the app requests scopes beyond basic identity; this connection does. Verify current requirements in Google's [OAuth refresh-token documentation](https://developers.google.com/identity/protocols/oauth2#expiration). Google's [Gmail scope guide](https://developers.google.com/workspace/gmail/api/auth/scopes) classifies `gmail.readonly` as restricted and `gmail.send` as sensitive. Check the applicable verification requirements for the selected [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth) before live use. `gmail.send` is requested for a separately authorized future capability; this smoke never sends.

If a revoke is unresolved, first allow any prior revoke request to finish. For this local runtime, `resolve-revoke` stops its owned API, then requires the operator to confirm that the app grant has been removed in Google Account permissions and enter the exact pending operation ID:

```sh
./scripts/local-auth.sh resolve-revoke
./scripts/local-auth.sh up
```

The command clears only that matching `in_progress` or `unknown` marker when the connection is disconnected and its encrypted bundle is already absent. It records the manually verified removal as confirmed; it does not replay a provider revoke or restore credentials. Do not use it until the old API process is stopped and grant removal is visible in the Google Account. If the command reports no matching row, stop and investigate instead of editing the database directly.

## Operational prerequisites

- Use explicit configuration validation and separate production/test credentials and data.
- Provide readiness checks for required dependencies and a minimal liveness check independent of external LLM calls.
- Apply versioned PostgreSQL migrations before serving incompatible code. Keep application/checkpoint compatibility in mind when changing persisted workflow state.
- Give the worker graceful shutdown and bounded lease handling; terminating a container must not turn an uncertain email send into an automatic retry.
- Establish encrypted backup storage outside the VPS and perform a PostgreSQL restore exercise. Neo4j/Qdrant projections need rebuild procedures backed by canonical records.
- Supply OpenTelemetry, Prometheus, Tempo, and Grafana with bounded retention and resource use. Expose Grafana through a protected endpoint separate from the application listener; keep metrics and trace stores private. Verify dashboards and trace correlation under real execution before treating instrumentation as complete.
- Verify rollback with both database compatibility and in-flight jobs/approvals. Reverting a container cannot undo a sent email.
