---
phase: 1
title: "Core schema and guarded database harness"
status: done
priority: P1
effort: 10h
dependencies: []
---

# Core schema and guarded database harness

## Goal and evidence

Create the first real migration, typed core storage, and safe local PostgreSQL verification. Owner plan acceptance is satisfied; implementation and verification evidence are recorded below. At planning time, `apps/backend/src/email_support/main.py:7-8` composed health only and `apps/backend/pyproject.toml:10-22` lacked persistence dependencies. `docs/03-codebase-summary.md:10,14` documents the ORM and application-contract boundaries. `docs/04-code-standards.md:26,40-42` requires scoped sessions, real PostgreSQL and isolated data.

## File ownership

This executor owns every listed file. No parallel edits.

- Modify `apps/backend/pyproject.toml`: SQLAlchemy 2, Psycopg 3, Alembic, pytest-asyncio, email validation dependency, explicit database-test collection.
- Modify `apps/backend/uv.lock`: resolve compatible versions using uv.
- Modify `Makefile`: database lifecycle/check wrappers; retain database-free checks.
- Modify `.gitignore`: private test-backup directory.
- Create `compose.test.yaml`: isolated test PostgreSQL only.
- Create `scripts/check-database.sh`: one serial guarded runner, local and CI modes.
- Create `apps/backend/scripts/test_database.py`: target identity verification, dump/restore and scenario lifecycle helpers, CLI entry.
- Create `apps/backend/alembic.ini` and `apps/backend/migrations/env.py`: metadata and async Psycopg migration environment, no embedded DSN.
- Create `apps/backend/migrations/script.py.mako` and `apps/backend/migrations/versions/create_canonical_core.py`: reviewed substantive revision.
- Create `apps/backend/src/email_support/storage/__init__.py` and `apps/backend/src/email_support/storage/postgres/__init__.py`: package boundaries.
- Create `apps/backend/src/email_support/storage/postgres/persistence/__init__.py` and `database.py`: package boundary plus explicit engine/session factory and disposal.
- Create `apps/backend/src/email_support/storage/postgres/persistence/tables/base.py` and `core.py`: shared declarative base, typed mappings and named constraints.
- Create `apps/backend/src/email_support/storage/postgres/persistence/core.py`: concrete core write/read functions.
- Create `apps/backend/src/email_support/models/persistence/common.py` and `core.py`: shared validators, validated core inputs/results and finite enums.
- Create `apps/backend/tests/unit/persistence/core/test_core_persistence_contracts.py` and `apps/backend/tests/unit/database/test_database_guard.py`.
- Create `apps/backend/tests/database/conftest.py`, `apps/backend/tests/database/core/test_core_storage.py`, and `apps/backend/tests/database/migrations/test_migrations.py`.

## Concrete schema: initial revision

All primary IDs are application-generated UUIDs. Required text is nonblank; instants use `timestamptz`. Nullable fields below are explicit required-nullable Pydantic inputs, not empty defaults. Foreign keys default RESTRICT; never cascade-delete history. Add only PK/unique indexes and demonstrated FK lookup indexes.

| Table | Columns and database constraints |
| --- | --- |
| provider_accounts | `id`, `provider text`, `external_account_id text`, `created_at`; unique `(provider, external_account_id)`. Namespace only; no credentials or connection state. |
| companies | `id`, `name text`, `domain text NULL`, `created_at`; no name/domain uniqueness or automatic identity merging. |
| contacts | `id`, `company_id FK NULL`, `email text`, `display_name text NULL`, `created_at`; unique email after domain-only lowercase normalization; local part preserved. |
| mail_messages | `id`, `account_id FK`, `external_message_id text`, `external_thread_id text NULL`, `sender_email text`, `recipient_emails jsonb array NULL`, `subject text NULL`, `body_text text NULL`, `received_at`, `company_id FK NULL`, `contact_id FK NULL`, `created_at`; unique `(account_id, external_message_id)`. Gmail message IDs are account-scoped, not label/container-scoped. |
| meetings | `id`, `account_id FK`, `external_calendar_id text`, `external_event_id text`, `title text NULL`, `description text NULL`, `organizer_email text NULL`, `attendee_emails jsonb array NULL`, `time_kind CHECK timed/all_day`, `starts_at NULL`, `ends_at NULL`, `start_date date NULL`, `end_date date NULL`, `company_id FK NULL`, `created_at`; unique `(account_id, external_calendar_id, external_event_id)`; timed kind requires aware start/end instants and NULL dates; all_day requires dates and NULL instants; end must follow start (all-day end exclusive). Calendar container prevents event-ID collisions. |
| evidence | `id`, `kind text CHECK mail/meeting/web`, `mail_message_id FK NULL`, `meeting_id FK NULL`, `source_url text NULL`, `source_text text`, `retrieved_at`, `created_at`; exactly the source column matching kind is nonnull. Immutable source snapshot: ordinary SQL UPDATE/DELETE/TRUNCATE rejected. New retrieval inserts a new evidence ID. |
| briefings | `id`, `company_id FK NULL`, `created_at`; no inferred company and no workflow state scaffolding. |
| briefing_versions | `id`, `briefing_id FK`, `version_number integer > 0`, `markdown text`, `sealed boolean NOT NULL DEFAULT false`, `created_at`; unique `(briefing_id, version_number)` and `(briefing_id, id)`. After construction, ordinary UPDATE/DELETE/TRUNCATE rejected. |
| briefing_version_evidence | `(briefing_version_id FK, evidence_id FK)` composite PK; immutable citation membership, implemented with database enforcement below. |

Normalized recipient/attendee arrays contain validated email strings; empty arrays mean a known empty set and NULL means unknown. Typed meetings distinguish timed instants from all-day dates; never fabricate midnight UTC for all-day events. Mail sender is required; missing subject/body stays NULL. URL/email contracts validate at the application boundary; JSON array/type checks and requiredness remain in PostgreSQL.

## Data flow and immutable provenance

Caller validates Pydantic input, opens `async with session.begin()`, invokes concrete functions with that session, and commits on context exit. Helpers add/flush/map rows to Pydantic results; they never commit, rollback, close the caller session or return ORM rows. Engine factory has no import-time connection and does not enter health/export composition.

Provide create/read account, company/contact, mail/meeting, evidence and briefing operations; create-version accepts evidence IDs and inserts content plus references atomically. Existing input-key conflict becomes a named conflict; no check-then-insert guarantee. Appending versions locks the briefing row before reading `max(version_number)+1`. Keep scenario scheduling serial, but use deterministic two-session tests inside a scenario to prove locking and uniqueness; no sleeps or parallel pytest workers.

Database immutability must cover citation additions as well as edits/removal. The only allowed version UPDATE is false-to-true sealing with every other column unchanged. A deferred constraint trigger queries the final row state at commit and rejects an unsealed version; it must not reject a successfully sealed row based on the original INSERT event's false snapshot. Citation INSERT/UPDATE/DELETE locks the parent before checking its current seal; for reassignment, check both old and new parents in stable ID order. Evidence UPDATE/DELETE always fails. Reject TRUNCATE using statement-level BEFORE TRUNCATE triggers on evidence, versions and citation membership, including CASCADE paths. Creation inserts version + links, then seals before returning. Published reads only return sealed versions. This seal is storage construction, not human review. Privileged DDL/trigger disabling is outside the guarantee.

<!-- Updated: owner-approved red-team corrections — immutable history and deterministic concurrency. -->

## Tests Before (red)

1. Add pure contracts tests: unknown fields/enums rejected; naive timestamps rejected; aware non-UTC instants normalized; absent required-nullable fields differ from explicit NULL; UUID/email/URL and positive version validation.
2. Add guard tests rejecting unset/app DSNs, wrong exact database/user/server identity, wrong local container, and failed dump/list verification before any mutation callback can run.
3. Add real DB tests for initial revision, all core family round trips through independent connections, duplicate provider keys with differing accounts/calendars, FK failures, explicit NULL, timed/all-day meeting round trips and invalid mixed forms, UTC equivalence, version numbering, and raw SQL history/citation mutation rejection. Fail first for missing implementation, not a missing DB.
4. In one backed-up scenario per invariant, coordinate two independent sessions with events/barriers or observable lock state and bounded timeouts. Competing identical provider inserts must yield one persisted row and one named conflict; concurrent appends must both commit distinct consecutive versions. Exercise both lock orders of citation construction/sealing; no write may attach to an already sealed parent. Confirm a correctly sealed transaction commits and an unsealed one fails.
5. Try direct TRUNCATE on each immutable leaf and representative parent TRUNCATE CASCADE; rollback the rejected operation and reread unchanged history/links from an independent session. Inject final-backup failure and prove failure exit, stopped owned port and retained recovery data/archives.

## Scenario lifecycle and ownership

The shell runner owns the verified test server/container and a private ignored recovery directory; `test_database.py` owns exact database-name allowlists, backup/restore and create/drop operations; `tests/database/conftest.py` requests a new target per scenario and closes all sessions before release. Local database storage uses a private retained bind directory rather than auto-removing container storage. Provision only an owned test service; capture trusted container/server identity independently of the URL under test.

| Target | Initial state and execution | Reset and recovery owner |
| --- | --- | --- |
| Control | Dedicated test-only administration database on the owned server; dump/list it before each scenario CREATE/DROP DATABASE. | Runner allowlists exact generated scenario names; never accepts an arbitrary admin/app DSN. |
| Empty install | New empty scenario database; backup, then production Alembic upgrade to the latest revision available in the current phase. | Lifecycle helper backs up then drops this target; never reuses a head database as empty. |
| Upgrade preservation | Separate new target; backup, upgrade to core revision; backup before core seed and again before upgrade to head. Activated once the second revision exists. | Migration test owns historical seed; lifecycle helper owns final backed-up disposal. No downgrade/reset of an adopted target. |
| Storage | New target per mutating scenario, migrated to available head with required backups. Independent sessions may commit within the scenario. | Conftest disposes the entire target after backup; it does not DELETE immutable committed fixtures or depend on rollback to erase them. |
| Restore | Separate new target; backup it before restoring a selected validated scenario dump. | Lifecycle helper verifies restored rows/revision/constraints and backs up before disposal. Never restores over another scenario. |

Generated target names have a fixed test prefix plus run/scenario counters and are stored in the runner's exact ownership allowlist. Verify actual database, role and server identity before backup and mutation, including the control target. A failed guard/backup prohibits schema/data cleanup. Close sessions and stop only previously verified owned processes/containers; retain backing data and last valid archives, return failure and report the private recovery path without credentials. No `down --volumes`, container removal or private-directory deletion on this path. CI retention lasts only for the job-owned environment; no durable CI backup archive is claimed or uploaded. Successful verified cleanup may delete owned disposable data after backups and verification. This exception to deletion must not become an exception to stopping owned processes.

<!-- Updated: owner-approved red-team corrections — fresh targets and failure-safe cleanup. -->

## Implementation and Refactor

1. Add and lock dependencies. Configure pytest async mode and serial database directory; default collection excludes it only through explicit directory selection. Do not silently skip missing DB.
2. Add local Compose test project with deterministic loopback port 55432, isolated private bind storage retained on failure, pinned PostgreSQL 18 patch/digest resolved during implementation, test-only role/database and health check. Preflight port/project ownership; reuse only the matching owned service, otherwise fail. No main Compose changes.
3. Runner exports only `EMAIL_SUPPORT_TEST_DATABASE_URL`; verify exact expected DB and role plus actual server identity from the owned container/CI service before writes. Local verification checks container ID/project labels and server system identifier; CI verifies the service container identity through Docker and server system identifier. A database name substring alone is insufficient. No fallback to app URLs.
4. Before each mutating scenario or setup phase, migration, seed and cleanup: verify identity; `pg_dump --format=custom`; `pg_restore --list`; fail closed on either error. Use a private mode-0700 ignored temporary directory, mode-0600 archives, no DSN/content logging. Backup is before each scenario transaction, not each statement. Final cleanup is backed up too. Dump subprocesses run outside async test I/O.
5. Follow the scenario ownership table rather than globally migrating a shared database before all tests. Apply the actual Alembic initial revision; review DDL, checks, FK order and triggers manually. Never call `metadata.create_all`. Add session factory and small typed functions; refactor only proven repetition.

## Tests After and commands

Existing commands: `make backend-check`, `make check`, `make check-api-drift`; their current backend pytest caller is `Makefile:23`. Implemented phase-1 targets: `make database-up`, `make database-check`, `make database-down`; `database-check` invokes the runner, which runs guarded migration/test scenarios serially. Focused command: `./scripts/check-database.sh local tests/database/core/test_core_storage.py`; test paths are relative to `apps/backend` inside the runner.

Make's ordinary backend check explicitly runs `tests/unit tests/integration tests/contracts`; add `backend-database-check` to run all `tests/database`. In CI, `backend-check` must require and run the DB suite; without its service/config it fails. Outside CI the database suite is selected with the dedicated target; direct `pytest tests/database` without config fails with setup error. Finish pure tests, focused DB tests, Ruff, strict mypy and existing credential-free checks. Include new Python migration modules in strict mypy verification alongside the existing src/scripts/tests paths. Dispose engines and stop only owned services in finally/trap paths, preserving recovery material on failed backup/identity checks.

## Risks, rollback and success

Execution checklist:

- [x] Write failing contract, guard, initial-migration and core-storage tests.
- [x] Implement the guarded local database lifecycle and reviewed initial migration.
- [x] Implement typed core persistence and immutable provenance.
- [x] Pass focused and regression checks; stop owned processes and record actual evidence.

High impact / medium likelihood: wrong target or failed backups; exact identity allowlist plus fail-closed archives and guard negative tests mitigate it. Medium/medium: trigger ordering or async fixture lifetime; raw-SQL tests, simple function-scoped sessions and disposal expose failures. Low/high: dependency drift; lock compatible patches and record actual PostgreSQL image.

No existing storage users/data require migration. Roll back application files before adoption; retain validated dump before any schema reversal, restore to a separately guarded disposable target, never downgrade/delete an adopted database casually. Success: all initial schema/core/guard tests pass, no app startup DB dependency, and owned processes are gone. Later phases depend on these results.

## Execution evidence (2026-10-25)

The final `make database-check` run passed all 30 real-PostgreSQL tests, including empty migration, core storage, immutable history, rollback, independent-connection reads, backup/restore, and guarded cleanup. The final `make check` also passed backend and web suites plus lint, formatting, strict typing, and build checks. The runner stopped and removed its owned service and network; port 55432 was free afterward.
