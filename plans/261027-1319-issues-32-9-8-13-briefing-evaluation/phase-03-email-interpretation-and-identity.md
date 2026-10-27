---
title: "Phase 3: Email interpretation and stable company identity — Issue #8"
status: in_progress
priority: P1
effort: "5–8 engineering days"
dependencies: [1, 2]
---

# Phase 3: Email interpretation and company identity

<!-- Updated: Owner-approved red-team R3 - keep canonical validation and compatible synthetic inputs. -->

## Outcome and ownership

Implement full #8 before #13: interpret relevant email, resolve exact contact identity, preserve ambiguity, persist explicit owner corrections and evaluate identity separately from report quality. Begin after accepted/merged #32 and #9. This supersedes the earlier normalized-input staging that excluded #8. Read [research follow-up](../reports/researcher-261027-1322-workflow-evaluation.md), [architecture](../../docs/02-system-architecture.md), [standards](../../docs/04-code-standards.md) and the current issue body. No Gmail/Calendar synchronization, projections, HTTP/UI endpoint or sending is added.

Verified existing contracts: `ContactRow` has a unique exact-local-part/lowercase-domain email index and nullable company FK (`apps/backend/src/email_support/storage/postgres/persistence/tables/core.py:77–106`). Company names/domains are non-unique (`:53–74`). Existing insertion and UUID lookup live at `apps/backend/src/email_support/storage/postgres/persistence/core.py:91–138`; there is no contact-by-email resolver. Provider mail/meeting rows require real account/source keys (`models/persistence/core.py:71–166`), and evidence allows only mail/meeting/web (`:168–200`; `tables/core.py:243–284`). Never fabricate provider accounts to accommodate local inputs.

## Data flow and fixed design

1. A provider-neutral normalized input discriminates local import, synthetic evaluation and actual provider-backed provenance. It carries a stable origin input UUID/key and immutable content hash, aware received/scenario time, email/meeting details and explicit absence/cancellation states. Production imports never pretend to originate at Google. Genuine provider inputs may reference existing canonical mail/meeting records and verified actual origin keys.
2. Persist local normalized inputs in a small `normalized_inputs` table: UUID, unique origin-kind/origin-key, content hash, validated JSON payload and timestamps. Repeating an origin key with the same hash returns the same record; changed content under that key fails with a conflict rather than silently changing provenance. Evaluation seeds the same contracts only in an isolated labelled evaluation DB.
3. Add a `normalized_input` source kind and nullable source FK to canonical evidence, with the existing exactly-one-source invariant extended. Preserve existing mail/meeting/web variants and defaults for their new nullable field. This gives locally imported needs/meeting evidence honest canonical provenance without fake provider rows. Public web evidence continues to use WEB. Source snapshots are immutable; publication date/hash metadata remain in typed source/run output where no canonical query needs them.
4. The Email Agent calls the phase-2 gateway with no callable research/effect tools. Its validated result contains relevance (`relevant`, `irrelevant`, `uncertain`), company/contact candidates, stated needs and evidence spans/IDs, ambiguity and unknowns. Candidate company/domain claims are untrusted assertions, not verified identity. Bound input length and attempts through the shared executor; capture role/run/prompt metadata.
5. Deterministic Company Info resolves exact normalized sender email through existing unique semantics; get-or-create yields a stable contact with no company for a new sender. Preserve local-part case; normalize domain only. Candidate names/domains can list existing companies but never automatically merge or create mappings. Public/shared domains, similar names and missing sender/company remain ambiguous. An existing explicit contact-company mapping can resolve identity; contradictory input makes ambiguity visible instead of silently overriding the mapping.
6. The owner may explicitly create a company using existing typed canonical operations and call a typed `correct_contact_company` service with contact, selected company or null, and expected identity revision. A local owner command invokes this service; the model cannot. Validate IDs and compare-and-set the revision in a short transaction. Default `contacts.identity_revision` to 1 for migrated rows and existing constructors; map it in every read/write. Increment it only on mapping change; repeat identical correction is idempotent. This existing contact row is the durable override; no alias/merge registry or generic correction event system is needed.
7. Resolution outputs `{contact_id, company_id, identity_revision}` plus provenance/relevance/ambiguity. Future lookups honor the correction. Correction A→B does not rewrite historical message/source records or move old approved knowledge. Query history only when both selected company and the contact's current mapping agree; exclude stale mail associations, wrong-company or invalidated sources. Null company never means query every company's history.
8. Phase 4 consumes this exact normalized input/identity service. Irrelevant mail stops before research; ambiguity/uncertain relevance stops for correction/clarification. A new company becomes eligible through explicit company selection/correction with genuinely empty prior history. Identity revision is rechecked under row lock when a briefing becomes pending review or a stored run is recovered. A correction makes old revision results stale; it cannot grant approval.

## File inventory

Phase 3 owns these files sequentially; phase 4 may consume/extend only the shared contracts/docs listed in its inventory. No deletions.

| Action | Repo-relative path | Responsibility |
|---|---|---|
| Create | `apps/backend/src/email_support/models/email_interpretation.py` | Normalized provenance, interpretation, identity snapshot and correction requests/results. |
| Create | `apps/backend/src/email_support/agents/__init__.py` | Actual role package. |
| Create | `apps/backend/src/email_support/agents/email_interpretation.py` | Bounded typed Email role, instructions and prompt identity. |
| Create | `apps/backend/src/email_support/agents/company_info.py` | Deterministic typed Company Info role over identity service. |
| Create | `apps/backend/src/email_support/services/company_identity.py` | Resolution, explicit correction and eligible context rules. |
| Create | `apps/backend/src/email_support/storage/postgres/persistence/identity.py` | Input idempotency, contact-by-email/get-or-create/CAS and scoped context queries. |
| Create | `apps/backend/src/email_support/storage/postgres/persistence/tables/identity.py` | Normalized-input source table. |
| Create | `apps/backend/migrations/versions/<generated-revision>_normalized_inputs_and_contact_identity.py` | Add source table/FK/check variant and contact revision; generate actual revision after rereading head. |
| Create | `apps/backend/scripts/interpret_email.py` | Local interpret and explicit owner correction commands. |
| Create | `apps/backend/tests/unit/identity/test_interpretation.py` | Agent validation, relevance, candidate/authority boundary. |
| Create | `apps/backend/tests/database/identity/test_company_identity.py` | Idempotent inputs/contacts, corrections/concurrency and context isolation. |
| Modify | `apps/backend/src/email_support/models/persistence/core.py` | Contact revision and backward-compatible normalized evidence variant. |
| Modify | `apps/backend/src/email_support/storage/postgres/persistence/core.py` | Map new evidence source and contact revision at existing insertion/read boundaries. |
| Modify | `apps/backend/src/email_support/storage/postgres/persistence/tables/core.py` | Contact revision, evidence source FK/check. |
| Modify | `apps/backend/src/email_support/storage/postgres/persistence/tables/__init__.py` | Register canonical source mappings with existing Base metadata. |
| Modify | `apps/backend/tests/unit/persistence/core/test_core_persistence_contracts.py` | Preserve original evidence variants; reject conflicting source fields. |
| Modify | `apps/backend/tests/database/migrations/test_migrations.py` | New migration head/preservation/drift/restore assertions. |
| Modify | `apps/backend/evals/models.py` | Separate identity/relevance outcomes from report scores. |
| Modify | `apps/backend/evals/runner.py` | Invoke production interpretation path, no evaluation-only agent. |
| Modify | `apps/backend/evals/datasets/briefing-v1/cases.json` | Reviewed relevance, ambiguity and incorrect-association cases/version. |
| Modify | `docs/02-system-architecture.md` | Durable normalized provenance and correction boundary. |
| Modify | `docs/03-codebase-summary.md` | Implemented identity/interpretation navigation. |
| Modify | `docs/09-evaluation.md` | Actual commands and identity baselines/coverage. |

Create relevant package markers only where Python import conventions need them. Read the owning files immediately before changing. Migration name/revision is proposed, not an existing file or allocated head.

## Tests Before — RED

| Scenario | Level | Expected observation |
|---|---|---|
| Relevant need vs irrelevant mail vs uncertain interpretation | Unit + replay | Typed needs/evidence and relevance; irrelevant never invokes research. |
| Sender claims famous company; shared/public domain; similar names | Unit + DB | Candidate only; no verified identity or silent mapping/company merge. |
| Same origin/hash and normalized sender repeated/concurrent | Real DB | Same input/contact ID; uniqueness conflicts resolved without duplicate identities. |
| Same origin key with changed content | Real DB | Conflict; original provenance unchanged. |
| New local input vs real provider source | Unit + DB | Honest source kind; no invented provider account/message; all exactly-one-source constraints hold. |
| Correction A→B, B→null, repeated B→B, invalid FK or stale revision | Real DB | Persisted future lookup, idempotent repeat, stale correction rejected; missing company remains unresolved. |
| Historical message points to A after current contact correction B | Real DB | No A context inherited and no historical row moved to B. |
| Correction races interpretation/final identity check | Real DB | Deterministic ordering via row lock/CAS; old snapshot detected. |
| Model injection requests correction/send/approval | Unit | No callable permission or persistence command; validated output only. |
| Missing provider/dependency or malformed output | Contract | Explicit failure distinct from irrelevant/empty context. |
| Identity score vs fluent incorrect briefing | Evaluation | Incorrect resolution reported independently; prose cannot compensate. |

## Implementation steps and refactor

1. Define normalized input/provenance and interpretation/correction schemas before migrations. Reuse exact email normalization semantics; validate provider-backed references against actual canonical rows. Synthetic evaluation addresses use the reserved example.com/net/org domains accepted by the unchanged canonical validator, with no operational-address mapping or delivery capability. Verify all new fields' instantiation sites and update explicit readers/writers/tests, without weakening existing provider contracts.
2. Add input source table/evidence variant/contact revision via one additive Alembic migration on the current head. Preserve rows and sealed versions; use guarded backup and real migration/drift/restore tests. Do not broaden the evidence variant to arbitrary file/URL provenance.
3. Implement race-safe exact-email get-or-create and typed contact correction with expected revision. Query company candidates as suggestions only; new company creation is an explicit local owner operation using the existing canonical contract.
4. Implement bounded Email Agent and deterministic Company Info role over these services, with typed evidence spans validated against normalized input. A claimed need belongs to sender content; it is not independently verified company fact.
5. Add local interpretation/correction command using process-local owner authority and private configuration. No anonymous HTTP endpoint, model-controlled correction tool or CLI approval/delivery capability. Future protected interface will call the same typed service.
6. Implement correct context scoping and expose identity snapshot/stale-check helper for phase 4. Do not copy mail association fields as current identity truth after correction.
7. Extend dataset and runner with relevant/irrelevant/ambiguous/incorrect-prior-association cases. Bind human review to updated hashes and record identity metrics separately. Refactor only shared normalization/query logic protected by passing tests.

## Tests After — GREEN and verification

Proposed narrow paths after files exist, from `apps/backend`:

```sh
uv run --locked pytest -q tests/unit/identity/test_interpretation.py tests/unit/persistence/core/test_core_persistence_contracts.py
```

Root existing guarded runner, with proposed new test path:

```sh
./scripts/check-database.sh local tests/database/identity tests/database/migrations
make backend-check
```

Proposed local commands after implementation, from `apps/backend`:

```sh
uv run --locked python scripts/interpret_email.py interpret --input PATH_TO_NORMALIZED_INPUT --output PATH_TO_PRIVATE_OUTPUT
uv run --locked python scripts/interpret_email.py correct-company --request PATH_TO_OWNER_CORRECTION
```

The correction file contains expected revision and explicit company/null selection; it cannot be sourced from model output. A fresh-process lookup must observe its durable result. Capture live interpretation evidence on owner-reviewed applicable cases via phase-2 adapters; missing configuration keeps that evidence pending. No tests/migrations/provider calls were run during planning.

## Acceptance mapping — Issue #8

- [x] AC1: relevant/irrelevant/uncertain outputs expose validated candidates/needs/evidence/ambiguity; sender claims stay unverified.
- [x] AC2: repeated/concurrent inputs preserve stable IDs; shared domains, similar names and missing identity never silently merge.
- [x] AC3: explicit typed owner corrections persist and control later lookup, including clear; local command works without adding unauthenticated HTTP. Stale revision cannot overwrite a correction.
- [ ] AC4: reviewed cases cover relevance, ambiguity and incorrect old associations; identity outcomes are separate from report quality.

## Implementation evidence and pending owner input

Implemented normalized provenance, strict no-tool Email interpretation, deterministic Company Info resolution, revision-checked owner correction, local-only commands, identity-scoped mail history and separate relevance/identity replay outcomes. Added 24 synthetic English/Vietnamese cases across 12 paired scenarios. The cases are candidates, not owner-reviewed baselines. A live model run against the production Email Interpretation Agent returned schema-valid, input-grounded output for all 24 cases after the prompt began including its JSON schema and unique exact quotes were used to derive model-mistyped offsets. Relevance matched the current candidate expectations in 9/24 cases; the other 15 require review and are not release thresholds. The private input/output/provider-event log is `apps/backend/evals/results/live-interpretation-retry-20261027T094425Z.jsonl` (mode 0600). Identity resolution was not run against an isolated evaluation database. AC4 and phase acceptance remain pending owner review and identity evaluation. Phase 4 must also wait for the separate #8 review, acceptance and merge gate.

Verification passed: `make backend-check` (199 tests, Ruff, formatting, strict mypy); `./scripts/check-database.sh local tests/database/identity tests/database/migrations` (14 passed, including migrations); `python -m evals validate --dataset evals/datasets/briefing-v1` (24 candidate cases, 12 English and 12 Vietnamese); `python -m evals self-check`; local CLI help. Live interpretation completed for all 24 synthetic cases; company identity resolution remains untested against an isolated evaluation database.

## Risks, compatibility and rollback

| Risk | Likelihood × impact | Mitigation |
|---|---|---|
| Wrong-company context from stale associations | High × High | Exact contact mapping, scoped queries, contact revision snapshots and correction tests. |
| Candidate output overwrites owner correction | Medium × High | Separate typed correction service, no model write permission, CAS. |
| Fake provider provenance to satisfy evidence FK | Medium × High | Explicit normalized source variant; unchanged provider input requirements. |
| Concurrent input creates duplicate identity | Medium × High | Existing email uniqueness, origin-key uniqueness, race-safe get-or-create. |
| Migration breaks old evidence/readers | Medium × High | Additive nullable field/defaults, preserved variants, drift and seeded upgrade/restore tests. |

New code accepts existing evidence variants through a null default; old code cannot deserialize the new closed enum value once normalized-input evidence exists. Stop new workflow starts and retain schema/data; use a compatible forward fix. Do not remove normalized evidence referenced by sealed briefings or deploy an incompatible old reader. If recovery needs whole-database restore, obtain explicit owner authorization and use a verified backup/restore route; never perform an automatic destructive downgrade. Identity corrections are durable owner decisions and must not be silently reverted by a code rollback. Phase 4 consumes accepted normalized contracts and current identity snapshots only after this PR's separate review, owner acceptance and authorized merge. Open evidence: migration compatibility and source-contract integration are implementation gates; no remaining scope fork.
