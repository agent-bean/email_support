---
phase: 2
title: "Complete typed storage and canonical invariants"
status: done
priority: P1
effort: 10h
dependencies: [1]
---

# Complete typed storage and canonical invariants

## Goal and ownership

After phase 1, add approvals/actions, approved knowledge/preferences and projection bookkeeping through a second substantive additive migration. Preserve every core record. `docs/02-system-architecture.md:35` requires atomic approval + action, and `:43-53` distinguishes canonical storage from projections and preferences. `docs/04-code-standards.md:27` requires exact approval binding; execution-time validity/rechecks remain later Issue #14/#15 behavior.

Sequential owner takes over these phase-1 files (modify):

- `apps/backend/src/email_support/models/persistence/` (shared, core, decisions and projection contracts with a stable package facade)
- `apps/backend/src/email_support/storage/postgres/persistence/tables/` (base and scope-grouped mappings with a stable package facade)
- `apps/backend/tests/unit/persistence/core/test_core_persistence_contracts.py`
- `apps/backend/tests/unit/persistence/decisions/test_decision_persistence_contracts.py`
- `apps/backend/tests/unit/persistence/projections/test_projection_persistence_contracts.py`
- `apps/backend/tests/database/migrations/test_migrations.py`

Create:

- `apps/backend/migrations/versions/create_approval_knowledge_storage.py`
- `apps/backend/src/email_support/storage/postgres/persistence/decisions.py`: concrete approval/action and knowledge/preferences operations.
- `apps/backend/src/email_support/storage/postgres/persistence/projections.py`: metadata read/write only.
- `apps/backend/tests/database/decisions/test_decision_storage.py`
- `apps/backend/tests/database/knowledge/test_knowledge_storage.py`
- `apps/backend/tests/database/projections/test_projection_metadata.py`

## Concrete schema: second revision

Use initial-revision UUID/time/nullability/FK conventions. No jobs, leases, retries, authentication or delivery status machine.

| Table | Columns and constraints |
| --- | --- |
| approvals | `id`, `briefing_id FK`, `briefing_version_id`, `action_kind CHECK send_email/save_knowledge`, `recipient_emails jsonb NOT NULL`, `selected_knowledge jsonb NOT NULL`, `approved_at`; composite FK `(briefing_id, briefing_version_id)` to versions' unique pair prevents cross-briefing binding. Send requires nonempty recipients and empty knowledge selection; save requires empty recipients and nonempty knowledge selection. `selected_knowledge` is an ordered array of exact nonblank text entries validated by a named Pydantic contract and database checks/trigger. Binding rows reject UPDATE/DELETE/TRUNCATE. No inferred human identity or authentication claim. |
| actions | `id`, `approval_id FK UNIQUE`, `created_at`; binding exists only on approval, never duplicate version/action/recipients. No external attempt/result fields without a current executor. Immutable approval FK prevents reassignment. |
| knowledge | `id`, `company_id FK NULL`, `approval_id FK`, `selection_index integer >= 0`, `briefing_version_id FK`, `sealed boolean NOT NULL DEFAULT false`, `created_at`, `invalidated_at NULL`; unique `(approval_id, selection_index)`. Approval must be save_knowledge for this exact source version, and index must address an entry in its immutable `selected_knowledge` array, checked in PostgreSQL. Text is derived from that approved entry, with no independently writable content column. After construction, provenance is immutable; only one-way eligibility invalidation may change. Multiple selected entries may reference one approval. |
| knowledge_evidence | `(knowledge_id FK, evidence_id FK)` PK; preserve immutable source membership, each evidence must belong to the approved source version, enforced in PostgreSQL. Construct knowledge + citations atomically with the same storage-only seal convention as versions. |
| preferences | `id`, `key text UNIQUE`, `value jsonb`, `updated_at`; explicit single-owner settings only, no implicit extraction and no speculative preference catalogue. Pydantic value is validated JsonValue; missing required value rejected, explicit JSON null allowed and preserved. |
| projection_metadata | `id`, `projection_kind CHECK neo4j/qdrant`, `knowledge_id FK`, `source_version_id FK`, `projected_version_id FK NULL`, `embedding_version text NULL`, `updated_at`; unique `(projection_kind, knowledge_id)`. Composite FK `(knowledge_id, source_version_id)` references a unique `(knowledge.id, knowledge.briefing_version_id)` pair. CHECK projected version is NULL or equals source version; unrelated versions are rejected. Never-projected records have NULL projected/embedding versions; graph embedding is always NULL; recorded vector projection requires a nonblank embedding version. No executor/job/outbox. |

For knowledge, store the approval payload once and enforce the knowledge/version relationship using a composite FK to a unique `(approval.id, approval.briefing_version_id)` plus a trigger checking action kind and selection bounds. Add the unique constraint to approvals in this revision. `create_knowledge` accepts approval ID, selection index and provenance, never replacement text; reads join the immutable approval snapshot to return typed `content`. Selection order is part of the immutable snapshot, so indexing cannot later resolve to different text. This records exact selections without implementing owner authentication or the promotion/replay services of Issue #10/#14.

All referenced versions must be sealed. Keep knowledge approval, selection index and source links immutable; invalidation must not destroy historical evidence. Reuse the version construction seal: deferred checks inspect final row state, citation writes lock/check both relevant parents before mutation, and the only construction update seals otherwise unchanged fields. After sealing, allow only NULL-to-timestamp invalidation. Reject DELETE and TRUNCATE of knowledge; reject TRUNCATE on knowledge citations, approvals and actions with statement-level BEFORE TRUNCATE triggers. Keep action binding append-only. Test leaf and representative CASCADE truncation paths. Ordinary privileged DDL/trigger disabling remains outside the guarantee.

Projection metadata is deliberately scoped to approved knowledge, the minimal requested projection bookkeeping; it does not claim graph relationship execution or synchronization coverage. Its valid interpretation is never projected, projected from this knowledge's exact canonical version, or canonically invalidated (which overrides both). Creating a newer briefing version does not mutate an existing knowledge record's source. Stored embedding version describes the recorded projection; desired embedding-version comparison belongs to a future projection caller. Do not add mutable knowledge revisions or automatic source-change/staleness claims. Derive eligibility from canonical knowledge immediately, even if projection metadata is unchanged. Metadata is recovery information, never approval authority.

<!-- Updated: owner-approved red-team corrections — exact selected text, immutable bindings and valid projection states. -->

## Data flow and operations

Pydantic approval input normalizes recipient sets by lowercasing domain only, preserving local part, removing exact canonical duplicates and sorting deterministically. Send requires at least one recipient and empty selected knowledge; knowledge-save has no recipients and at least one exact selected text entry. Keep text byte-for-byte after nonblank validation; do not silently rewrite approved content. Both arrays are required; SQL/JSON NULL is invalid for these action fields. PostgreSQL triggers/checks also reject malformed selections and noncanonical recipient shapes, including direct SQL duplicates/order mismatch. Distinguish these known action arrays from nullable normalized-input arrays.

`record_approval_and_action(session, input)` validates the sealed version, inserts approval, flushes, inserts action and flushes, returning typed snapshots. Caller owns transaction and commit; an exception after either write must propagate and roll back the entire unit of work. Do not add hidden nested transactions or commits. Returned approval remains exact historical evidence after later content versions; whether an old approval can execute is explicitly outside this issue.

Provide typed reads of approval/action binding; create/read/list eligible knowledge from selected approval entries, invalidate knowledge, set/read explicit preference, and set/read projection metadata. Inputs are concrete named contracts; unknown finite enums fail validation. Reads return detached Pydantic values without lazy loads. Knowledge eligibility excludes invalidated rows immediately, regardless of metadata. An exact snapshot proves storage binding, not that an authenticated human approved it; later services still own that authorization.

## Tests Before (red)

1. Extend pure contract tests for recipient/selected-text semantics, finite action/projection enums, explicit null preference and missing value, naive dates and forbidden fields. Reject replacement content on knowledge creation; typed reads must return the exact selected text, including meaningful whitespace.
2. Add DB failures: missing version, version from another briefing, mutable approval/action binding, invalid send/save recipients/selections, duplicate action per approval, wrong-action knowledge, out-of-range selection, duplicate `(approval_id, selection_index)`, source version mismatch, citations outside approved version, immutable knowledge/citation changes and nonexistent references. Test direct SQL selection-shape/bounds violations, unrelated projected versions, graph embedding misuse and missing vector embedding provenance. Add TRUNCATE/CASCADE rejection with unchanged-history reads after rollback.
3. Add caller rollback test that invokes the approval/action operation and raises before commit; separately exercise a failure after approval insertion and before successful action insertion. A fresh independent session must find neither record. Verify success commits both and reopens with identical snapshot.
4. Add core-history preservation test: upgrade empty DB to actual initial revision, seed every initial family and relationship via SQL valid at that revision, dump, upgrade to head, reopen through typed reads and compare stable IDs, NULLs, instants, content, citation links and provider keys. New-family inserts prove the second revision has real purpose.
5. Keep scenario scheduling serial, with phase-1 fresh-target ownership. Add bounded two-session knowledge-citation/seal races in both lock orders using explicit coordination, not sleeps. Test never-projected versus exact-version projection, then invalidate canonical knowledge and prove eligibility changes immediately without editing metadata. A newer briefing version must leave old approved snapshots unchanged.

## Implementation and Refactor

1. Implement reviewed additive revision with new tables, constraints and triggers; do not alter historical core content or insert dummy revisions. Keep first-revision seed independent of head ORM mappings.
2. Implement small concrete operations. Trigger failures map only expected constraint/SQLSTATE errors to named storage conflicts; cancellation/unexpected errors propagate, caller rolls back.
3. Canonical knowledge changes and metadata bookkeeping remain caller-owned atomic database work. No network calls or automatic approval from evidence.
4. Refactor normalization/mapping shared by actual operations only; do not introduce generic repositories, custom DI or a universal event stream.

## Tests After and test matrix

| Layer | Evidence |
| --- | --- |
| Unit | Pydantic missing/null, finite identifiers, recipient normalization, exact selected text and explicit values. |
| Real PostgreSQL | All family round trips, SQL constraints/TRUNCATE guards, atomic decisions, selected-entry binding, coordinated sealing races, eligibility and exact canonical projection references. |
| Migration/recovery | Initial-to-head preservation, empty-to-head install, Alembic head/schema comparison, dump restore into guarded scratch target. |
| Existing HTTP/contracts | Health remains DB-free; export remains byte-stable; no new API surface. |

Implemented focused runner: `./scripts/check-database.sh local tests/database/decisions/test_decision_storage.py`; full runner: `make database-check`. Both use phase-1 fresh targets and backups before each scenario/setup phase, migration, seed and cleanup; never upgrade a shared head database backwards to obtain the historical seed state. Restore exercise backs up its separate target before restore, checks restored revision/rows/constraints, then backs up before disposal. On failed cleanup guard/backup, stop only verified owned resources and retain recovery data. Suite scheduling stays serial; two-session tests within a scenario use bounded explicit synchronization, never sleeps or pytest worker parallelism.

Run all database tests plus existing backend unit/health/contracts, strict mypy and Ruff. `alembic check` through the guarded runner checks metadata drift but does not prove trigger definitions; explicit catalog/behavior tests cover them.

## Risks, rollback and success

Execution checklist:

- [x] Write failing binding, knowledge, preference, projection and upgrade-preservation tests.
- [x] Implement the substantive additive migration and typed operations.
- [x] Prove caller-owned rollback, cross-connection durability and guarded restore.
- [x] Pass focused and regression checks and record actual evidence.

Medium likelihood / high impact: weaker raw-SQL bindings or citation history; negative SQL tests and database constraints mitigate. Medium/medium: false preservation proof; first-revision-valid seed plus production upgrades and typed post-upgrade reads expose loss. Low/high: backup restore wrong target; separate exact identity guard and dump-before-restore prevent it.

Second revision is additive; existing core consumers remain compatible. Before reverting, back up and stop adopting new-family writes. Code rollback can retain additive tables. Restore a validated backup into an isolated target for data recovery; never casually downgrade away approvals or knowledge. Success: all requested families persist, both migrations preserve core records, exact snapshots survive later edits, and rollback/restore evidence passes.

## Execution evidence (2026-10-25)

`make database-check` passed all 30 PostgreSQL tests, including the empty install, seeded first-revision upgrade preservation, restore verification, typed reads after reconnect, rollback, action/approval atomicity, knowledge eligibility, and exact projection provenance. Coordinated two-session tests proved duplicate-key conflict behavior, consecutive briefing version allocation, and rejection of late citations after a parent is sealed. Citation construction and sealing of a new, uncommitted parent remain one atomic transaction; the database cannot expose that parent to a competing session before commit. The final `make check` passed 26 backend tests, 14 web tests, Ruff, formatting, strict mypy, TypeScript checks, lint, and build.

Review follow-up: the first-to-head migration test now compares complete serialized rows for every first-revision table before and after upgrade, covering IDs, nulls, timestamps, payloads and relationships. `./scripts/check-database.sh local tests/database/migrations` passed all 3 PostgreSQL migration/recovery tests; Ruff check and format checks passed for the updated test.
