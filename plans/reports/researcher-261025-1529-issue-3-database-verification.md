# Issue #3 database verification research

Conducted: 2026-10-25 (Asia/Bangkok)

## Recommendation

Use one real PostgreSQL test database per test run, driven locally through an isolated Compose test manifest and in CI through a PostgreSQL service container. Run Alembic against it before persistence tests; never replace database integration tests with SQLite. Preserve the user's backup-before-change rule with a `pg_dump` of the designated target before migrations or test setup writes, stored outside the repository and checked for readability. Keep this separate from the normal app/web Compose stack so API generation and the health-only backend remain credential-free and usable without PostgreSQL.

The project currently has pytest only: no SQLAlchemy, Alembic, PostgreSQL driver, async pytest plugin, or database service is present. These recommendations describe proposed Issue #3 tooling, not existing capability. `make backend-check`, `make up`, and existing CI are the actual current paths; the compose stack only runs API and web. Its current health endpoint is HTTP based and does not need a database URL.

## Local and CI database isolation

- Add a dedicated local test database service/manifest (prefer `compose.test.yaml`, not a production-style volume in the main stack). Pin an explicit PostgreSQL major version to match the supported deployment version. Use a named test-only database/user, a health check using `pg_isready`, loopback-only host exposure if host tests need it, and a separate test-only URL. Compose's `service_healthy` dependency avoids a start-before-ready race. Local tests should not attach to or reuse a developer or production data volume.
- In CI, add a PostgreSQL service container to the backend job, configure a distinct database and test credentials through job-scoped environment/secrets, wait on service health, then run the same backend check command. GitHub documents this service-container pattern for PostgreSQL. Do not expose credentials outside the test job or publish the database port unnecessarily.
- Give the test harness a dedicated `EMAIL_SUPPORT_TEST_DATABASE_URL`; fail closed if it is unset or resolves to a non-test database. Use a per-run database name (or schema) to prevent parallel runs colliding. Do not infer test mode from a generic application `DATABASE_URL`.
- Back up the exact target before any migration/schema change or persistent test setup write. A practical run sequence is: confirm target identity is test-only; take `pg_dump --format=custom` to an ignored temp directory outside the repository; check the archive with `pg_restore --list`; only then migrate and write test data. Never commit or upload this dump. The per-run dump satisfies the pre-change rule for the disposable test target; row-level setup/teardown inside the test transaction does not warrant dumping before each statement. If the policy literally requires a separate dump before every test's data writes, that is a material runtime/cost decision for the owner because it defeats ordinary fast integration-test isolation.
- Prefer a fresh disposable database for each full run, with tests isolated in transactions and rolled back; ensure the migration test itself commits where needed, then drop only the test database after its backup has been retained for that run. Avoid `DROP DATABASE`, `drop_all`, or volume deletion against a configurable/shared URL. A unique run database and strict target guard make parallel test runs safe.

PostgreSQL documents `pg_dump` as a consistent snapshot and custom-format archives as restorable via `pg_restore`; archive listing validates structure, while an actual restore into a separate scratch database is stronger recovery evidence. Keep restore verification as a focused migration/backup check rather than repeating it for every row-level test.

## Async SQLAlchemy and pytest

FastAPI supports async endpoints, and code standards require that async paths avoid blocking I/O. If Issue #3 persistence operations are async, use SQLAlchemy's `AsyncEngine`/`AsyncSession` with an asyncio-capable PostgreSQL driver and one `AsyncSession` per request/task, scoped to a unit of work. Do not share an `AsyncSession` across concurrent tasks. SQLAlchemy explicitly describes sessions as mutable transaction state and recommends one session per concurrent task. Dispose test engines at fixture teardown.

For the smallest async test setup, use `pytest-asyncio` in `auto` mode only while asyncio is the sole async test framework; its docs recommend auto mode for this case. Use strict mode if another async plugin is introduced. Keep fixture scopes simple: session-scoped engine/database bootstrap, function-scoped transaction/session, deterministic rollback/cleanup. Run all async tests through pytest (no custom event-loop layer). Current project pytest configuration is strict about pytest config/markers but does not select async behavior.

Driver trade-off: `asyncpg` is a common direct async SQLAlchemy dialect and aligns with async request code, but Alembic's CLI is synchronous by default and needs either its documented async environment template or a separate synchronous migration URL/driver. A synchronous Psycopg 3 URL for Alembic plus asyncpg for application I/O adds two drivers; an async Alembic environment can use the same asyncpg URL but adds event-loop bridge configuration. Prefer asyncpg for app storage plus Alembic's official async environment only if the implementation truly needs async DB access; otherwise use synchronous SQLAlchemy/Psycopg for simpler migration/test code. The accepted plan's typed storage API and FastAPI boundary do not alone prove async database access is required; choose this with the concrete API contract rather than adding both drivers speculatively.

## Migration and preservation evidence

1. For the first migration, prove `alembic upgrade head` builds the schema from an empty real PostgreSQL database, then inspect the actual database revision and exercise constraints/storage behavior. Review generated migration operations manually; generated migrations are a draft, not evidence of correctness.
2. Do not claim that an initial migration proves upgrade preservation. With no prior migration or established production schema, there is no prior-version data set to preserve. Do not add a fake or no-op revision just to make a test pass.
3. Once a second schema migration is required by real functionality, add a test that upgrades the test database to the prior real revision, inserts representative valid rows using the prior schema, takes the required pre-change dump, applies `upgrade head`, and asserts those rows and relationships survive and remain readable under the new contract. Test constraints changed by that migration as well. This is meaningful forward-upgrade evidence and is repeatable from actual migration history.
4. For the current first-migration stage, separately prove persistence across independent connections and rollback on an intentionally failed transaction; these prove durability/transaction behavior, not cross-version upgrade preservation. Alembic documents `upgrade head` and can report whether the database is at its migration heads. Do not use `metadata.create_all()` as a replacement for migrations.

## Trade-offs and failure modes

| Choice | Fit | Main cost or risk |
|---|---|---|
| Compose test Postgres locally + GitHub Postgres service in CI (recommended) | Real PostgreSQL semantics with low new infrastructure and same database engine locally/CI | Requires Docker locally; service image/version and credentials must be pinned/scoped; CI runner startup adds time |
| SQLite for most persistence tests | Fast and easy | PostgreSQL types, constraints, transaction semantics, and migration behavior differ; violates the existing code-standard requirement for real-database integration tests |
| Testcontainers-managed Postgres | Per-test disposable container lifecycle; can reduce hand-managed local setup | Adds a Python dependency, Docker API coupling, startup cost, and a second local/CI orchestration convention; unnecessary when Compose and Actions service containers already exist |

Key failures to guard against: tests silently pointing at dev/prod; migration started before PostgreSQL readiness; stale persisted test volume contaminating reruns; concurrent workers sharing a database/schema; generated migration omitting or misordering constraints; async fixture/event-loop mismatch; sessions crossing task boundaries; false upgrade-preservation claims while only one revision exists; and backup archives being created but never validated/restorable. Backup files contain test data and must remain ignored and local/ephemeral.

## Sources

- [SQLAlchemy asyncio extension](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — async engine/session setup and disposal.
- [SQLAlchemy session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html) — session transaction semantics; one `AsyncSession` per task.
- [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html) — applying migrations from a clean schema with `upgrade head`.
- [Alembic cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) — async migration environment and checking current migration heads.
- [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io/en/stable/) — async test and fixture mode selection.
- [GitHub Actions PostgreSQL service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers) — CI test database setup.
- [Docker Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/) — health checks and `service_healthy` readiness.
- [PostgreSQL SQL dump/restore](https://www.postgresql.org/docs/current/backup-dump.htm) — consistent `pg_dump` snapshots and restore approach.

## Next planning actions

1. Specify a dedicated test-only URL, local Compose test service, and CI service container using the same PostgreSQL major version.
2. Make pre-migration/pre-setup `pg_dump` plus archive validation part of the test database lifecycle; keep output ignored and ephemeral.
3. Decide sync versus async database I/O from the typed storage/API contract, then choose only the required driver and pytest async plugin.
4. Set first-release acceptance to empty-database migration plus real storage/constraints/rollback evidence; require row-preservation testing when a later legitimate migration exists.

## Unresolved question

Does the owner intend “backup before any data change even tests” to require a dump before each test case's transactional writes, or is a validated pre-run backup of the disposable test database sufficient? The latter is the practical reading used here.
