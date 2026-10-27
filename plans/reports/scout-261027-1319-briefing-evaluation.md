# Joint briefing/evaluation source map

Inspected 2026-10-27, Asia/Bangkok. Current scope: #32, #9, #8, #13; `--tdd --hard --yagni`. Planning only. The owner expanded the initially approved three-issue scope to include all of #8. Four sequential PRs now satisfy the native dependencies without bypass. The earlier decision to stage #13 before #8 is superseded. No GitHub mutation is authorized by this record.

## Confirmed source

- Current checkout is clean apart from this planning session's new artifacts, at `67f9594` on `fix/issue-6-verification`. Locally cached `origin/main` is `903f90e` (the merged verification PR). Do not implement on the inherited verification branch; inspect a current main revision and use issue isolation during execution.
- `apps/backend/pyproject.toml:9` targets Python 3.13. Existing Pydantic, SQLAlchemy async, Psycopg binary and HTTPX2 dependencies are reusable (`:10-20`). No LangGraph or provider SDK is declared. New dependency/version selection is an implementation compatibility check, not established runtime evidence.
- `apps/backend/pyproject.toml:35-39` keeps product tests under `tests/`; `:48-52` and `Makefile:35` explicitly enumerate mypy roots. Adding `evals/` needs both manifest and invoked check roots updated. The wheel currently packages only `src/email_support` (`:32-33`); repository-local eval execution need not become a public API.
- `apps/backend/src/email_support/models/persistence/core.py:168-200` stores exactly one typed source reference per evidence row plus a source excerpt and retrieval time. Publication date/source hash belong in the run/eval provenance contract unless a concrete canonical query needs a schema extension.
- `apps/backend/src/email_support/storage/postgres/persistence/core.py:316-369` creates briefing/version records in a caller-owned transaction. `create_briefing_version` locks a briefing, increments the version, adds evidence links and seals it; calling it again does create another version. It is not idempotent per workflow run. Add run-to-version binding and transaction guards rather than weakening the sealed-version invariant.
- `apps/backend/src/email_support/storage/postgres/persistence/tables/decisions.py:26-62` models completed approvals with `approved_at`, not pending review. A pending review must not insert a fabricated owner approval/action. A minimal run/review record may bind a sealed version and pending status; authenticated decisions remain #14.
- `apps/backend/src/email_support/storage/postgres/persistence/decisions.py:188-221` has `list_eligible_knowledge(session, company_id=None)`. Passing None returns all companies. A missing/ambiguous identity must never call this unfiltered path. For a selected known company, reuse this function with its actual ID and validate all provenance. Empty approved context is valid; dependency errors are not empty results.
- `apps/backend/src/email_support/storage/postgres/persistence/database.py` supplies explicit engines/session factories and caller-owned lifetimes. Keep all provider calls outside SQL transactions.
- `apps/backend/migrations/env.py` imports canonical Base metadata and compares schema/defaults. Existing migration head asserted by `tests/database/migrations/test_migrations.py:65` is `3c0f6a9b21e8`. New run tables need additive Alembic migration and preserving restore/drift assertions. Vendor checkpoint tables should live in a separately tested schema so Alembic does not mistake them for canonical drift.
- `apps/backend/tests/database/conftest.py:42-53` creates isolated targets, migrates, backs up before seeding, and drops via `DatabaseLifecycle`. `scripts/check-database.sh` verifies container/server/port identity and backs up owned targets. Reuse it for database tests; no arbitrary database URL or operational mailbox connection in eval.
- `apps/backend/scripts/test_database.py:601-632` creates verified custom-format pg_dump archives without schema filters. `:816-855` owns migration and drift commands. Checkpointer setup is a separate schema mutation and must also be preceded by a verified backup. Preserve entire-database restore, including canonical + checkpoint schemas.
- Existing provider pattern is explicit async HTTPX2 in `integrations/google_workspace.py`, with bounded requests and redirects disabled. Reuse the HTTP library, not Google-specific clients or auth settings for unrelated providers.
- `Makefile:30-39` owns backend tests/static checks and guarded real-PostgreSQL invocation; `.github/workflows/ci.yml` invokes that target with a job-owned service. Keep default health/CI credential-free. Proposed eval/live/briefing commands are unavailable until implemented and must be labelled as proposed.

## Native dependencies observed through gh

- #32 blocked by #2 and #31, both closed.
- #9 blocked by #2, closed.
- #8 blocked by #9, #3 and #32; #3 is closed. Its criteria require relevant/irrelevant interpretation, safe stable identities, persistent owner corrections through typed operations, and separate identity-quality evaluation.
- #13 blocked by #8 and #32. Both are now inside the accepted scope. Execute #32, #9, #8, then #13. No native-dependency correction is needed.

## Accepted contract and scope challenge

Outcome: a developer runs labelled normalized email/meeting scenarios through relevance interpretation, stable company/contact resolution and persistent owner corrections, real bounded research, a persisted cited Markdown draft and durable review pause, then evaluates identity outcomes, evidence support and usefulness separately.

Constraints: complete all four Issues' criteria; four sequential PRs (#32, #9, #8, #13); Pydantic boundaries; PostgreSQL canonical records/checkpoints; no model authority over approval, sends or knowledge promotion; reviewed golden expectations; opt-in paid provider calls; fixed offline clocks/snapshots; safe synthetic addresses; secrets/private content absent from tracked artifacts.

Non-goals: Gmail/Calendar synchronization, durable scheduler/worker delivery, graph/vector retrieval, review UI/authenticated resume implementation, email sending, knowledge promotion, export/attachment execution, Grafana deployment and production release. Keep those scenarios in the corpus as unsupported where applicable. #8 now owns real interpretation/resolution/correction; normalized inputs still avoid pulling in synchronization #7.

Complexity: more than eight files is justified by distinct dataset/evaluator, provider/tool, identity/correction, graph/persistence and meaningful test boundaries. Four execution phases map to the four PRs; combining identity and graph in one phase would obscure separate Issue acceptance. No platform abstraction, new service deployment, generic plugin system or eval-only assistant. Pydantic schemas do not justify a class-based service hierarchy.

Acceptance: runner/self-check and complete scenario inventory (#32); permission/budget/provider/fetch contracts plus actual gateway/search/embedding smoke (#9); real relevant/irrelevant interpretation, stable identity and durable owner corrections with separate eval outcomes (#8); graph, canonical sealed draft/pending review, same-thread restart/concurrency safety and actual live evaluation on reviewed applicable cases (#13). Full-product acceptance is not inferred.

## Verification performed

Read docs/source/manifests and GitHub Issue/dependency state; inspect CLI help. No application tests, dependency changes, DB/schema mutations, external provider calls, merge, acceptance or GitHub updates were performed.
