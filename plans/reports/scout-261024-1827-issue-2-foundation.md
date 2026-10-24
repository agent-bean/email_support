# Issue #2 evidence and planning decisions

Observed 2026-10-24, Asia/Bangkok. Planning only; flags `--yagni --hard --tdd`.

## Repository evidence

- The selected issue is [#2](https://github.com/agent-bean/email_support/issues/2), OPEN. Its only recorded blocker, #1, is CLOSED (`gh issue view 2` and the native blocked-by endpoint, read this session).
- Local HEAD and remote `main` both resolve to `5f81f43622d36cf574246a4b7d3a57c190a0542b`. The owner requested a new branch; current branch is `docs/issue-2-foundation-plan`.
- `README.md:7` correctly describes a documentation-only repository. No apps, package manifests, application tests, Compose file, or workflows existed at that revision. Planned commands must be implemented and then verified before documenting them as executable.
- `docs/03-codebase-summary.md:9-12` owns the future `apps/backend/src/email_support` module shape. `docs/02-system-architecture.md:25` requires generated types, calls and runtime validators, and TanStack Query for server state.
- `docs/04-code-standards.md:5-20` owns typing and contract rules; `docs/04-code-standards.md:38-43` owns focused tests and the required-check discovery order.
- `.github/rulesets/main.json:12-27` has no required-check rule. The live main ruleset (ID 25777101) also has none. `gh workflow list` returned no workflows, and HEAD check-runs returned `total_count: 0`.
- `.github/rulesets/main.json:5` has no bypass actors. The separate review exception is in `.github/rulesets/review.json:5-10`. Preserve that separation.
- `AGENTS.md:5-7` reserves scope/architecture decisions and final acceptance, issue closure, merge, deployment and release for the owner.

## Scope decisions reused from the conversation

Outcome: an actual API/web slice that needs no provider credentials and proves a generated runtime-validated response. Constraints: existing architecture and strict quality gates. Non-goals: persistence, worker, access, providers, domain screens, production operations. Acceptance: local execution, CI static/test/build checks, contract-drift detection, required-check activation after discovery and post-merge evidence.

The owner selected Hey API + Zod. Reuse this selection; no scope interview is needed. More than eight implementation files is unavoidable for two typed applications, manifests, tests and CI. Keep three sequential phases and avoid generic services or speculative domain contracts.

## Tooling evidence and overrides to research suggestions

Local read-only version checks found uv 0.13.5, Node 24.22.1, npm 12.2.1, Docker Compose 5.6.1 and GNU Make 4.4.1. The default Python is 3.15.1; `uv python list --only-installed` also finds Python 3.13.16. Explicit Python 3.13 selection avoids dependence on the host default. These are observations of this machine, not installation prerequisites copied into product docs.

Read-only registry metadata (`npm view`, no package installation) returned:

| Package | Observed version | Compatibility metadata |
| --- | --- | --- |
| `@hey-api/openapi-ts` | 0.99.0 | Node >=22.18.0; a TypeScript peer range is declared. |
| `vite` | 8.3.5 | Node ^20.19.0 or >=22.12.0. |
| `zod` | 4.6.7 | Zod 4 release. |
| `@tanstack/react-query` | 5.104.5 | React 18 or 19 peers. |
| `typescript` | 7.0.2 | Latest metadata is not proof the other tooling supports this major. |
| `typescript-eslint` | 8.72.0 | TypeScript >=4.8.4 and <6.1.0; ESLint 8.57, 9 or 10 peers. |
| `@hey-api/client-fetch` (standalone) | 0.13.1 | Deprecated: Fetch client is bundled in the generator since 0.73.0. |

Choose Node 24 LTS, Python 3.13, uv and npm. Select compatible exact tool patches and dependency locks during implementation, then prove generation, validation, strict compilation and build together. Do not install latest packages independently. Node 24 LTS is confirmed by the [official release table](https://nodejs.org/en/about/previous-releases).

The two research reports are advisory snapshots, superseded by these decisions where they differ:

1. Use `apps/backend/src/email_support` and `apps/web`, not the platform report's shorter example paths or `email_support_api` namespace.
2. Use `apps/backend/openapi.json`; Hey API input is `../backend/openapi.json` from `apps/web`. There is no `apps/api` directory.
3. Include a minimal TanStack Query owner for the real health request; do not add another server-state abstraction.
4. Use Node 24; the web report's 22.12 floor does not satisfy the observed generator's >=22.18 floor.
5. Run the initial CI workflow on the feature PR, discover its emitted checks, then apply required checks before the owner-authorized merge. Do not merge the new workflow unprotected as a bootstrap step. GitHub documents discovery and expected check sources in [required checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-status-checks-to-pass-before-merging).
6. TypeScript 5.9.3 and ESLint 9.39.5 are available conservative candidates from read-only registry metadata. Latest TypeScript 7 does not satisfy the observed typescript-eslint peer range. Keep the `@hey-api/client-fetch` generator plugin identifier but avoid installing the deprecated standalone client package when the pinned generator emits bundled client files; inspect actual generated imports during implementation.

## Proposed contract and operational details

These are future implementation requirements, not existing behavior:

- `GET /api/health`, operation ID `get_health`, returns HTTP 200 and a Pydantic `HealthResponse` with a closed `HealthStatus.OK` wire value `ok`. No database, auth, external provider or credentials are involved.
- Same-origin browser requests preserve `/api/health`; Vite proxies `/api` to the backend. Host defaults are API `127.0.0.1:8000` and web `127.0.0.1:5173`. The Compose web proxy uses internal service DNS; browser code never uses that DNS.
- Export OpenAPI offline; generate the Fetch SDK, TypeScript and Zod artifacts from the local snapshot; enable SDK response validation explicitly. [Hey API validation](https://heyapi.dev/docs/openapi/typescript/plugins/sdk#validators) confirms it is optional by default.
- Check generated drift through path-limited Git status including untracked additions, not only tracked diffs. Commit both the snapshot and generated outputs.
- Observe a real browser request reaching the API for success. Controlled fetch doubles exercise negative external-boundary cases only; no mocked success substitutes for integration evidence.
- Keep Compose development-only, with two services and loopback host publishing. No background processes have been started during planning.

## Evidence limits

No application dependency installation, code generation, application tests, container startup or hosted CI has run. Compatibility and runtime gates belong to implementation. A plan-format pass or adversarial review cannot establish issue acceptance.
