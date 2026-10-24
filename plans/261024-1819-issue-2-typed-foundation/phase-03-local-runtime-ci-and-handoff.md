---
title: "Phase 3: Local runtime, CI and operational handoff"
status: done
phase: 3
dependencies: [2]
priority: P1
effort: 5h
---

# Phase 3: Local runtime, CI and operational handoff

## Outcome and dependencies

Prove clean-clone local operation, actual browser-to-API behavior, deterministic contract CI and required-check protection. Depends on phases 1 and 2 passing. Rough estimate: 5 hours. Single executor owns these files sequentially; no deployment or merge occurs without explicit owner authorization.

Required-check sequencing follows [code standards, line 43](../../docs/04-code-standards.md), baseline/review separation follows [line 59](../../docs/04-code-standards.md), and owner control follows [AGENTS.md, lines 5–7](../../AGENTS.md). Existing [main ruleset, lines 5–27](../../.github/rulesets/main.json) has empty bypass actors and no required-check rule; [review ruleset, lines 20–34](../../.github/rulesets/review.json) separately owns review. Research's merge-first bootstrap is superseded by the pre-merge sequence below and [controller scout](../reports/scout-261024-1827-issue-2-foundation.md). [Deployment direction, lines 13–17](../../docs/06-deployment-guide.md) remains future production authority.

## Proposed architecture and data flow

Root Compose has only API and web, no persistent services/volumes or secrets. Build backend with pinned Python/uv and locked dependencies; web with pinned Node/npm and `npm ci`. Vite dev server is local-development tooling, not a production deploy. Bind containers internally to `0.0.0.0`; publish host `127.0.0.1:8000` and `127.0.0.1:5173`. Web server reads `API_PROXY_TARGET=http://api:8000`; browser sees only same-origin `/api/health`. Fixed port/strictPort prevents silent increment.

Playwright Chromium visits actual web, observes its actual `/api/health` response and healthy UI. No intercepted or injected success response; this covers serialization, generated validation, Query, browser Fetch and proxy together. Compose startup/readiness is bounded; stop only owned processes and always clean up on success/failure. Check port owners first, never kill unrelated listeners or select a new port.

Playwright explicitly uses `testDir: './tests/e2e'` and `testMatch: 'health-smoke.spec.ts'`; Vitest includes only `tests/unit/**/*.test.{ts,tsx}`. Verify both discovery paths after adding the smoke spec. The drift gate checks scoped dirty artifacts before regeneration, then checks generated changes afterward; `make generate` remains the explicit writer for intentional updates.

<!-- Updated: Validation Session 1 - separate test discovery and protect drift probes from regeneration erasure. -->

CI uses `pull_request` and push to `main`, GitHub-hosted runners, explicit `permissions: contents: read`, pinned action commit SHAs, no secrets/deployment environment, and job timeouts. No path filters skip required jobs. Proposed stable job names: `Backend`, `Web`, `API contracts`, `Smoke`; exact emitted check contexts are discovered later. Backend/Web run phase gates; contracts regenerates offline and rejects drift; Smoke builds two-service Compose and runs actual browser integration with bounded cleanup. Jobs may run concurrently only after shared checkout inputs are committed; they do not mutate shared worktrees.

## File inventory and ownership

| Repository-relative path | Action and responsibility |
| --- | --- |
| `compose.yaml` | Create: two-service loopback local stack. |
| `apps/backend/Dockerfile` | Create: pinned runtime/tool and locked package install. |
| `apps/backend/.dockerignore` | Create: exclude environments, caches and private local files. |
| `apps/web/Dockerfile` | Create: pinned Node/npm, npm ci, deterministic local web runtime. |
| `apps/web/.dockerignore` | Create: exclude node_modules/build/test/private local files. |
| `apps/web/playwright.config.ts` | Create: explicit tests directory/smoke match, bounded Chromium test using configured existing Compose URL. |
| `apps/web/tests/e2e/health-smoke.spec.ts` | Create: browser success against actual API. |
| `apps/web/package.json` | Modify: add non-watch test:smoke script. |
| `apps/web/package-lock.json` | Modify only if smoke dependency lock was not established in phase 2. |
| `scripts/check-api-drift.sh` | Create: real root orchestration of export/generation and drift detection. |
| `.github/workflows/ci.yml` | Create: read-only no-secret PR/main checks. |
| `.github/rulesets/main.json` | Modify after first PR run: add exact discovered required checks; preserve all existing rules and empty bypass actors. |
| `Makefile` | Modify: finalize all wrappers below. |
| `README.md` | Modify: verified setup/commands, local-only status and links. |
| `docs/03-codebase-summary.md` | Modify: identify implemented API/web paths and generated ownership; future boundaries remain explicitly planned. |
| `docs/04-code-standards.md` | Modify: smallest durable regeneration/check and required-check bootstrap guidance, linking actual owners. |

No deletes. Preserve `.github/rulesets/review.json` verbatim; no production workflow or broad docs rewrite. More than eight files reflect actual local runtime, test, CI and handoff requirements.

## Tests Before: red

1. Write real browser smoke first; demonstrate failure when API is unavailable, then implement Compose/proxy startup and prove success. Poll readiness with a finite deadline; no sleeps used as readiness assertions.
2. Write the drift gate before accepting artifacts. In a disposable checkout, test its pre-generation guard with a modified output (both staged and unstaged variants), a deleted tracked output and a new untracked generated file. Each must fail before exporter/generator runs and leave the injected bytes/inventory untouched; restore fixtures after each case. Separately start from a clean Git worktree with a committed stale snapshot/generated artifact or a committed source-contract change without regeneration: the full gate must fail on post-generation status. This proves clean-checkout CI detects stale committed generation, independently of dirty-output rejection. Clean committed current artifacts must pass. These are command-level acceptance experiments, not permanent artificial application behavior.
3. Run unfiltered `npm --prefix apps/web run test` with no services/browser installation; it must collect only src tests even with the smoke spec present. Run `npm --prefix apps/web run test:smoke -- --list`; it must list only the browser smoke. Check rendered Compose configuration has exactly two services, correct loopback publishes and internal proxy URL before starting containers. Confirm CI workflow is read-only and every required job runs on PR and main without filters.

## Implement: green

1. Add pinned Dockerfiles, bounded health/readiness mechanism, Compose and actual browser smoke. Root `up` uses deterministic Compose; `down` runs `docker compose down --remove-orphans`, no volume destruction flag. Track command/PID/port/worktree for any host process started and terminate it when finished.
2. Finalize wrappers: `setup` delegates locked backend install plus npm ci; `check` delegates backend gates plus web lint/format/typecheck/unit tests/build; `generate` exports backend then runs web generation from its own cwd; `check-api-drift` invokes the root script; `dev-api`, `dev-web`, `up`, `down` delegate to their actual tools. README describes individual manifest commands as owners, not duplicate settings.
3. Drift script uses fail-fast handling and repository-root resolution. First reject scoped dirty artifacts using `git status --porcelain --untracked-files=all -- <paths>` for `apps/backend/openapi.json` and `apps/web/src/shared/api/generated/`, including staged/unstaged modifications, deletions and untracked files, without running generation or overwriting the evidence. Then run offline exporter and web generator and reject the same scoped status afterward. Do not require unrelated paths to be clean or mutate the index. Use `make generate` for intentional updates, review and commit artifacts, then run the check. Repeat regeneration twice and compare bytes/inventory; no clean-tree claim while candidate artifacts remain uncommitted. Postflight detects committed stale outputs/source-contract changes; preflight alone is not CI drift proof.
4. Add CI jobs using locked/frozen-equivalent installs (`uv lock --check`, `uv sync --locked`, `npm ci`), pinned tool/action versions and bounded browser/Compose cleanup in an always-run step. Fail on check errors; do not hide failures with success fallbacks. Browser installation is explicit (`npx playwright install --with-deps chromium` after npm ci). No deploy or credential access.
5. From a clean checkout with only documented prerequisites, run every documented command and capture results. Update the three owning docs only after commands succeed; source/manifests own details. Keep production direction unchanged.

## Required-check operational handoff: before merge

1. Open/update the implementation PR with the new workflow while the baseline lacks a required-check rule. Do not merge to bootstrap.
2. Let that PR workflow run successfully, inspect emitted check-run names and source app with `gh`, then add exact contexts to checked-in `main.json`. Preserve deletion/non-fast-forward/linear-history/PR protections and `bypass_actors: []`; keep review policy separate.
3. Apply the updated main ruleset through authenticated GitHub administration during the authorized implementation scope, after the successful PR run and before any merge. Verify live rule equality to intended baseline. If permissions block this, report blocked operational handoff; do not bypass or mark complete.
4. Push final baseline/docs changes, rerun PR checks on final head, verify GitHub reports expected required contexts and satisfied review/ruleset requirements. Record actual names, run links, head SHA and applied ruleset evidence. A failed/pending required check must block merging; use observed GitHub state rather than deliberately weakening rules.
5. Request explicit owner authorization for merge/final acceptance. After an authorized merge, observe main-push CI separately. Issue closure and acceptance require explicit owner authorization and post-merge evidence; PR checks alone do not establish completion.

## Refactor and Tests After

Remove duplicate wrapper logic while preserving drift/error/cleanup behavior. Repeat clean generation and local/browser checks only after relevant changes. Record exact runtime patches, action SHAs and check names; no research proposal counts as runtime proof.

## Test matrix and proposed verification

All commands are planned, unavailable at baseline. From repository root after implementation:

```sh
make setup
make check
make generate
make generate
# Review and commit intended artifacts before the drift check.
make check-api-drift
npm --prefix apps/web run test
npm --prefix apps/web run test:smoke -- --list
docker compose config --quiet
make up
npm --prefix apps/web run test:smoke
make down
```

Install Chromium beforehand from `apps/web/` with `npx playwright install --with-deps chromium`. Setup pins prerequisites; check does not silently install browsers or start duplicate services.

| Layer | Evidence | Pass condition |
| --- | --- | --- |
| Clean clone | uv locked install, npm ci, full check | No lock rewrite or hidden credentials; all gates pass. |
| Dirty artifact guard | Modified (staged/unstaged), deleted, new untracked outputs | Nonzero before generation; injected bytes/inventory untouched. |
| Committed drift | Clean checkout with committed stale artifact/source contract; two generations | Postflight fails on generated changes; current clean committed output passes reproducibly. |
| Suite discovery | Unfiltered unit run and smoke --list | Only src tests in unit job; only browser smoke in Playwright. |
| Compose integration | Rendered config/build/start/down | Only API/web, stable loopback ports, bounded start and cleanup. |
| Real browser E2E | Chromium -> Vite -> actual API | Healthy UI and actual successful JSON response, no interception. |
| Failure integration | Stop owned API, reload browser | Actionable failure appears within timeout; no success fallback. |
| Hosted CI | PR final-head runs | All four actual emitted check contexts pass with read-only execution. |
| Operations | Baseline/live ruleset inspection | Required checks enforced before owner-authorized merge, no baseline bypass. |
| Post-merge | Main push run, only after authorization | Separate recorded evidence; never assumed from PR results. |

## Risk, security, compatibility and rollback

- Medium likelihood × high impact: wrong or unavailable required contexts block merges. Discover on successful PR, apply before merge, rerun final head; preserve existing protections. Resolve context errors directly; never merge unprotected to bootstrap.
- Medium × medium: port collision/orphan process. Inspect owners, deterministic ports, bounded startup and always cleanup; stop only owned processes.
- Medium × high: regeneration erases dirty probes or CI misses stale committed generation. Enforce scoped preflight/postflight and separately test dirty artifacts and clean committed stale baselines in a disposable checkout.
- CI threat model is untrusted PR code with no secrets. `pull_request_target`, write tokens, self-hosted runners, production credentials and public container publishing are excluded.
- No existing application state or deployment is migrated. Local Compose is explicitly development-only; architecture's later owner access/storage/deployment remains unimplemented.
- Rollback stops owned Compose/processes, reverts phase files and regenerates from retained source if necessary. Snapshot live main ruleset before application; if a bad context blocks progress, restore only this change through authorized administration while retaining baseline/review protection. No production/data rollback is involved.

## Exit checklist

- [x] Pass clean-clone checks, isolated suite discovery, stable generation, dirty-output and committed-stale drift probes, and actual browser smoke.
- [x] Verify no owned orphan processes and report checks actually run plus gaps.
- [x] Verify final-head PR checks and applied baseline required-check protection.
- [x] Hand off concrete PR/evidence for explicit owner merge/acceptance; do not close issue automatically.

## Implementation evidence

- Commit `538036f` (`feat: add local runtime and CI foundation`) was authored and committed as `javis-27` after the `biendo27` techlead checklist review found no local issues.
- `make setup` and `make check` passed in a fresh detached checkout: locked uv/npm installs, five backend tests, thirteen web unit tests, strict type checks, lint, format and build.
- The browser test listed one Playwright smoke while unfiltered Vitest collected thirteen unit tests. The actual browser passed against the two-service Compose stack and against the host `make dev-api`/`make dev-web` pair. Stopping the owned Compose API produced a real proxy 502 and the visible error state, with no healthy fallback.
- `docker compose config --quiet`, rendered topology/loopback/proxy assertions, `make up`, and `make down` passed. Both owned services and host dev servers were stopped afterward.
- Two `make generate` runs produced identical OpenAPI and generated-file hashes; `make check-api-drift` passed. In a detached disposable worktree, unstaged/staged changes, a deletion and a new generated file each failed before generation and retained their evidence. A clean committed stale OpenAPI snapshot failed the post-generation check.
- The first PR run exposed `Backend`, `Web`, `API contracts`, and `Smoke`, all successful from GitHub Actions app `15368`. Commit `c3a0f9a` records those exact strict contexts in the checked-in main baseline.
- Final-head PR run [40097326072](https://github.com/agent-bean/email_support/actions/runs/40097326072) passed all four contexts at `c3a0f9a7e892b881ab60753fb262823b458ef105`. Active repository main ruleset `25777101` was updated and read back with the same contexts and source app, strict up-to-date policy, an empty bypass list, and the original deletion, non-fast-forward, linear-history and pull-request protections intact. The separate review ruleset was left unchanged.
- `biendo27` approved [PR #23](https://github.com/agent-bean/email_support/pull/23) at the final head with no findings. The PR and issue #2 remain open for explicit owner acceptance and merge. No merge or post-merge CI run occurred.
- Session 4 grouped existing tests under `tests/unit/`, `tests/integration/`, `tests/contracts/`, and `tests/e2e/`. The current suites passed before the move; after the move, the first backend collection exposed a missing fixture import, which was fixed. Final `make check`, API drift check, Compose syntax validation, focused backend/web tests and both test-discovery checks passed. Commit `0dd9b3b` is on PR #23 at head `0dd9b3b5facc39abce5383bcbfa9de2012956640`; hosted run [40100660560](https://github.com/agent-bean/email_support/actions/runs/40100660560) passed `Backend`, `Web`, `API contracts`, and `Smoke`. `biendo27` reviewed the new head and approved with no findings. PR #23 remains open; no merge or owner acceptance is claimed.
