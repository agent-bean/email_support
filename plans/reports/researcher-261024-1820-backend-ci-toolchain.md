# Issue #2 planning research: backend foundation, local Compose, and CI

Advisory research snapshot. [Controller evidence and decisions](scout-261024-1827-issue-2-foundation.md) supersede the Python baseline, shortened backend paths/namespace and merge-first CI bootstrap suggestion below. The phase files own execution.

**Date:** 2026-10-24 18:20 Asia/Bangkok
**Scope:** executable planning only; `--yagni --hard --tdd`

## Recommendation

Build the smallest real vertical slice: a typed FastAPI liveness endpoint, a React/Vite web app consuming generated OpenAPI-derived TypeScript and Zod contracts, and two-service local Compose. Pin the Python runtime and lock dependencies with uv; use Ruff plus strict mypy and pytest for backend gates. Keep live providers, databases, worker, authentication, secrets, and deployment out of this issue. These limits match the documented API/web and generated-contract boundaries ([architecture](../../docs/02-system-architecture.md), [issue scope as supplied to this research task]).

Prefer Python 3.12 as the initial runtime and constrain the project to a deliberate supported range (proposed `>=3.12,<3.14`), subject to confirming dependency support when lockfile is created. Pin uv in developer/CI setup and commit `uv.lock`; use dependency ranges in `pyproject.toml`, not exact direct pins. FastAPI supports Python 3.10+, but 3.12 is a conservative current baseline with broad ecosystem support. FastAPI/Pydantic major ranges should remain bounded (`fastapi>=0.115,<1`, `pydantic>=2,<3`) and exact resolved versions belong in the lockfile. Add `pytest` and `httpx` as development dependencies for in-process HTTP contract tests. Ruff is formatter/linter; mypy owns strict static typing. Avoid adding a separate formatter or full test framework stack.

uv's project commands can update the lockfile automatically. Developer runs may use `uv run`, which checks manifest/lock consistency and syncs dependencies; clean-clone setup should use `uv sync --locked` to fail on drift rather than silently rewrite the lock. CI should explicitly run `uv lock --check`, then locked install and tool commands. Docker builds that have both manifest and lock available should use `uv sync --locked --no-dev`; `--frozen` deliberately skips manifest/lock consistency validation and should only be used in an intermediate layer where the manifest is absent. The lockfile is portable across supported platforms and should be version controlled. [uv lock/sync](https://docs.astral.sh/uv/concepts/projects/sync/), [uv projects and lockfile](https://docs.astral.sh/uv/concepts/projects/layout/), [uv Docker guidance](https://docs.astral.sh/uv/guides/integration/docker/)

## Minimal implementation shape

- `backend/pyproject.toml`, `backend/uv.lock`, `.python-version`: package metadata, runtime constraints, app and dev dependencies, Ruff/mypy/pytest settings. Pin the uv installer/action separately in CI.
- `backend/src/email_support_api/`: application factory or a single entry point, one `/health` liveness route, and no empty future module folders. The response shape and path should be decided from the issue acceptance text rather than invented to appease tooling. FastAPI natively publishes OpenAPI; test the chosen route status and schema generation through `TestClient`/HTTPX. [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/)
- `backend/tests/`: focused tests first. Assert health status/body and OpenAPI's operation/schema existence; do not test framework guarantees or introduce a DB fixture.
- `web/`: Vite app and generated API/validator artifacts. Keep the generated source committed if it is consumed by app builds; provide one deterministic generator command that exports the running app's OpenAPI schema and regenerates TypeScript/Zod output. CI regenerates into the same files and fails on a diff. Generated output is not hand-edited.
- Root `compose.yaml`: only API and web services, loopback-bound host ports, stable project name/port mapping, health/readiness checks only where the service supports them, and no database/worker/provider containers. Use service DNS inside Compose for API-to-web proxying; browser-facing API base URL must remain host-reachable. No `.env` file or provider credentials required.
- `.github/workflows/ci.yml`: pull request and main push; job-level names stable and useful (e.g. `backend`, `web`, `generated-contracts`). Minimal workflow permissions: `contents: read`; no secrets, write token, `pull_request_target`, privileged cache writes, or self-hosted runner. Do not add deployment behavior.

For local execution, document commands only after manifests exist. Intended planned commands are `docker compose config --quiet`, `docker compose up --build`, smoke-check both loopback URLs, and `docker compose down --remove-orphans`. Do not add `-v` because the accepted stack has no persistent services/volumes. Before start, identify an existing port owner (`ss -ltnp` or `lsof -i :<port>`); stop only a process demonstrably started for this project. Choose fixed host ports in the Compose file and do not silently increment when occupied. Publishing without an explicit loopback address binds all interfaces; Docker documents that this can expose the container beyond localhost. [Compose services / published ports](https://docs.docker.com/reference/compose-file/services/), [Compose networking](https://docs.docker.com/compose/how-tos/networking/)

## Test-first evidence matrix

| Concern | Write failing evidence first | Implementation evidence / planned gate |
|---|---|---|
| API health | HTTP test for the exact issue-accepted route/status/body; OpenAPI test finds that operation | `uv run --locked pytest`; health does not call LLM or external services |
| Python contracts | Add a typed function/route and a deliberately invalid fixture only if it represents a meaningful contract | `uv run --locked mypy --strict src tests`; `uv run --locked ruff check .`; `uv run --locked ruff format --check .` |
| Web contract generation | Generate from backend OpenAPI fixture/live app and assert a known operation is represented in generated TS and Zod output | `npm ci`; generator command; assert clean git diff; then web lint/typecheck/test/build scripts as actually declared |
| Compose behavior | Validate parsed Compose and assert only API/web services and loopback-published ports | `docker compose config --quiet`; build/up; HTTP smoke checks; down with orphan cleanup |
| Repository clean clone | Fresh checkout installs without rewriting tracked dependency state | `uv lock --check`; `uv sync --locked`; npm lockfile install via `npm ci`; all CI gates |
| CI/ruleset wiring | Open PR and observe exact job/check names and their success/failure behavior | Select those checks as required only after GitHub exposes them; merge then verify main push reruns the CI workflow |

The order is test-first, but avoid tests for mock status pages, empty scaffolding, or package/framework behavior. Existing code standards explicitly call for tests at the smallest meaningful layer and required checks only after GitHub has exposed them ([code standards](../../docs/04-code-standards.md)).

## CI and branch protection sequence

The checked-in `main` ruleset currently blocks deletion, non-fast-forward updates, and requires linear history plus PRs with squash merge; it has **no required status-check rule** ([main ruleset](../../.github/rulesets/main.json)). The separate `review` ruleset requires one approval and allows a repository-role bypass for PRs ([review ruleset](../../.github/rulesets/review.json)). Keep this admin/review exception distinct: adding required CI checks belongs in `main`; do not widen the review bypass or make it bypass CI.

Bootstrap ordering matters: first add and merge the CI workflow without making its not-yet-seen checks mandatory. Run it on a PR (and ensure a main-branch run if necessary) until GitHub reports the stable check/job names. Then update/apply the main ruleset to require the selected checks, ideally selecting their expected GitHub Actions source where available. If required checks are activated before the workflow emits them, PRs can remain blocked with no runnable matching check. GitHub's docs state that checks need to exist as reported checks/statuses to select and distinguish strict up-to-date requirements from loose ones. After the ruleset change, verify a failing check blocks and passing checks allow normal review policy; post-merge main-push CI is a separate rerun/evidence point, not a substitute for PR required checks. [GitHub required status checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)

Use ordinary `pull_request` for untrusted PR code. Set explicit read-only permissions; GitHub withholds fork secrets and limits fork PR tokens by default, while `pull_request_target` runs with base-repository trust and creates avoidable risk if it checks out and executes PR code. Avoid all secrets for this CI and use GitHub-hosted runners; self-hosted runners can retain state or credentials between untrusted jobs. [Actions workflow permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), [secure use](https://docs.github.com/en/actions/reference/security/secure-use), [`pull_request_target` risks](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target), [compromised runners](https://docs.github.com/en/actions/concepts/security/compromised-runners)

## Current commands versus planned commands

There are currently no `backend/`, `web/`, Compose manifest, package manifests, or workflow files. README states there are no verified application setup commands ([README](../../README.md)); repository guidance also says to resolve commands from actual scripts/manifests rather than invent them ([AGENTS.md](../../AGENTS.md)). Therefore none of the proposed `uv`, npm, Compose, or CI commands are executable in the current checkout. Existing executable evidence is limited to reading the docs/configuration. Do not report the planned gates as run.

## Trade-offs and adoption risk

| Choice | Benefit | Cost / risk | Fit |
|---|---|---|---|
| uv project + checked-in lock | Fast, reproducible local/CI install; one manifest and lock | Newer than pip; tool/action version must be pinned and upgraded deliberately | Best fit for a greenfield Python service and clean-clone lock enforcement |
| FastAPI + Pydantic v2 | Matches architecture and establishes OpenAPI as source of truth | Framework APIs evolve; avoid pinning to tutorial snippets without lock/test | Direct fit to documented stack and code standards |
| Ruff + strict mypy | One fast linter/formatter plus independent static typing gate | Strict typing can require narrow, documented adapter exceptions | Required by documented standards; no need for extra lint layers now |
| Compose API/web only | Reproducible local vertical slice without credentials or data services | Host port collision remains a developer-machine concern; fixed ports require ownership checks | Explicitly bounded issue scope; prevents premature operational stack |
| PR CI with read-only token | Safe validation of untrusted changes and a merge gate | First run/ruleset configuration sequencing needs deliberate bootstrap | Aligns with ruleset split and current no-secret scope |

Main adoption risk is version/tool drift across Python, uv, Node, and the OpenAPI generator. Pin runtime and CI tool/action versions; commit uv/npm lockfiles; have generation run deterministically; upgrade through ordinary reviewed PRs. Avoid broad pre-release version ranges or floating GitHub action tags. Ruff configuration format is documented in `pyproject.toml`; mypy strictness should be enabled from the first owned Python module rather than retrofitted after untyped code accumulates. [Ruff configuration](https://docs.astral.sh/ruff/configuration/)

## Ownership guidance

Keep backend runtime/dependencies/tests under `backend/`; web app, package lock, and API generation script/config under `web/`; local orchestration in the root Compose file; CI workflow in `.github/workflows/`. Keep only the generated contract artifacts needed by web code, and place their generator invocation beside the web toolchain. Add the exact end-user local commands to README only after they succeed from a clean checkout. Do not update deployment docs for production workflows: this issue does not implement shipping or deploy mechanics. If local setup is added, update the smallest relevant README/docs owner and verify its commands.

## Sources

- Repository sources: [README](../../README.md), [documentation index](../../docs/00-index.md), [architecture](../../docs/02-system-architecture.md), [code standards](../../docs/04-code-standards.md), [deployment direction](../../docs/06-deployment-guide.md), [main ruleset](../../.github/rulesets/main.json), [review ruleset](../../.github/rulesets/review.json).
- Official tool documentation linked above: FastAPI tutorial; uv project, lock/sync, and Docker guidance; Ruff configuration; Docker Compose ports/networking; GitHub Actions permissions/security and ruleset status checks.

## Limitations / unresolved questions

- The researcher was supplied the accepted issue scope but not the live issue body or CI status history. Confirm the exact health endpoint contract and generated TypeScript/Zod tool command against issue #2 before implementation.
- This research did not test currently installed versions, create files beyond this report, or validate Docker engine port mapping on the owner's OS. Platform/version choices remain to be confirmed by the implementation lock and Compose validation.
- Exact published check names depend on the future workflow's job names and GitHub's reported check-run presentation; select them from live repository checks after the first run, not from this proposal.
