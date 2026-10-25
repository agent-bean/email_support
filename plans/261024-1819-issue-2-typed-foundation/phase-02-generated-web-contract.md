---
title: "Phase 2: Generated and validated web contract"
status: done
phase: 2
dependencies: [1]
priority: P1
effort: 5h
---

# Phase 2: Generated and validated web contract

## Outcome and dependencies

Consume the real health contract through a generated Fetch SDK and runtime Zod validation in a minimal React/Vite app. Depends on all [phase 1](phase-01-start.md) gates and its committed OpenAPI. Rough estimate: 5 hours. One executor owns this phase after phase 1; no parallel root wrapper edits.

Architecture requires TanStack Query for server state and generated client/types/validators ([architecture, line 25](../../docs/02-system-architecture.md)); strict TypeScript and generated contracts follow [standards, line 7](../../docs/04-code-standards.md) and [generated ownership, line 14](../../docs/04-code-standards.md). Honest accessible state follows [guidelines, line 11](../../docs/05-design-guidelines.md), [failure, line 13](../../docs/05-design-guidelines.md), and [interaction, line 21](../../docs/05-design-guidelines.md). Read [web research](../reports/researcher-261024-1819-web-contract-toolchain.md) with [controller overrides](../reports/scout-261024-1827-issue-2-foundation.md): use Node 24 LTS, existing `apps/` paths and Query; older advisory Node floors are superseded.

## Proposed architecture and data flow

From `apps/web/`, generator input is local `../backend/openapi.json`; output is `src/shared/api/generated/`. Configure Hey API TypeScript, Fetch client plugin, SDK and Zod plugins; explicitly set SDK response validator to Zod. Generating schemas alone is insufficient. No hook generator or Vite generation plugin.

Owner decision, 2026-10-24: retain the generated Hey API SDK. Compile generated sources in a separate TypeScript project with `exactOptionalPropertyTypes: false` and all other strict options enabled. Keep the app project at `exactOptionalPropertyTypes: true` and resolve its generated imports through the emitted JavaScript/declaration package boundary. Emit compiled files under ignored `node_modules/.cache/generated-api`; compile them before app typecheck, lint, tests, build, and dev. This isolates the upstream compatibility issue without changing runtime SDK validation or hand-editing generated files.

Browser requests same-origin `/api/health`. Vite proxy preserves `/api` and forwards to `http://127.0.0.1:8000` for host development. `API_PROXY_TARGET` is a server-only Vite configuration variable; Compose overrides it to `http://api:8000`. Never expose internal DNS as browser base URL, prefix `/api` twice, or strip it. Use fixed web port 5173 with `strictPort: true`, loopback binding by default; no broad CORS.

`src/shared/api/health.ts` accepts the Query caller's `AbortSignal`, composes it with a bounded request deadline (proposed 5 seconds), and passes the composed signal through the generated SDK to Fetch. Preserve caller cancellation semantics and reason; release any manually created timer/listener on every completion path. Return generated validated data and surface HTTP/network/JSON/validation/deadline failures as errors. Use the generated operation's supported throw/result contract, established by implementation tests; never cast unvalidated data. `src/app/App.tsx` uses minimal QueryClient/provider and one health query, passes its signal to the helper, and sets explicit `retry: false` to render textual loading, healthy, or actionable failure state. No cancellation button, product dashboard or placeholder domain actions. No duplicate response interface, enum, schema, parallel state store or broad error framework.

Vitest collects only `tests/unit/**/*.test.{ts,tsx}` in jsdom. Phase 3's Playwright suite owns `tests/e2e/health-smoke.spec.ts` under its explicit test directory/match. Unit checks must run without services or browser installation; root `check` and the Web CI job use the unfiltered unit script.

<!-- Updated: Validation Session 1 - isolate test discovery and test caller cancellation with deadline composition. -->

## File inventory and ownership

All entries are proposed creates except the last two modifies. No deletes. Generated descendants are exclusively generator-owned; discover their exact inventory from the pinned generator before committing, and include that inventory in implementation evidence rather than guessing tool-internal filenames.

| Repository-relative path | Responsibility |
| --- | --- |
| `apps/web/package.json` | React/Query/Zod runtime; Vite/@vitejs/plugin-react/TS/ESLint/Prettier/Vitest/@testing-library/react/jsdom/Hey API/Playwright tooling and scripts. |
| `apps/web/package-lock.json` | Tested exact dependency resolution. |
| `apps/web/.nvmrc` | Tested Node 24 LTS patch; matching engines/package-manager version. |
| `apps/web/tsconfig.json` | Strict app TS, noUncheckedIndexedAccess, exactOptionalPropertyTypes; resolve generated imports through emitted declarations. |
| `apps/web/tsconfig.generated.json` | Separate strict generated-SDK compilation with exactOptionalPropertyTypes disabled; emit runtime JS and declarations to ignored cache. |
| `apps/web/eslint.config.js` | Type-aware unsafe-any and non-null restrictions for owned source. |
| `apps/web/.prettierrc.json` | Minimal formatting configuration. |
| `apps/web/.prettierignore` | Generator-owned output and build/test artifacts only. |
| `apps/web/vite.config.ts` | React plugin, generated package runtime alias, deterministic proxy/port, Vitest jsdom with explicit src-only test include. |
| `apps/web/openapi-ts.config.ts` | Local input, generated types/Fetch SDK/Zod and response validator wiring. |
| `apps/web/index.html` | Minimal document and app mount. |
| `apps/web/src/main.tsx` | React entry. |
| `apps/web/src/vite-env.d.ts` | Vite type reference. |
| `apps/web/src/app/App.tsx` | Query provider and health query states. |
| `apps/web/tests/unit/App.test.tsx` | Loading/success/failure rendering via actual SDK boundary. |
| `apps/web/src/shared/api/health.ts` | Minimal generated SDK call with caller/deadline cancellation composition and cleanup. |
| `apps/web/tests/unit/health.test.ts` | Generated operation validation/error, caller cancellation and independent deadline tests. |
| `apps/web/src/shared/api/generated/` | All actual generated files committed, never edited manually; enumerate after initial generation. |
| `Makefile` | Modify sequentially: extend setup/check/generate; add dev-web. |
| `.gitignore` | Modify only for actual web tool outputs. |

File count reflects real tool configuration, entry points, tests and generated artifacts. Do not add routing, design systems, unused features or extra abstraction layers.

## Tests Before: red

1. Evaluate exact package compatibility under Node 24/npm and lock tested versions. The tested toolchain pins Hey API `0.99.0`, Zod `4.6.7`, TanStack Query `5.104.5`, TypeScript `5.9.3`, and ESLint `10.13.0`; `npm ci` succeeds. The `@hey-api/client-fetch` plugin is used without the deprecated standalone package. Generated imports establish the actual runtime dependencies.
2. Generate initial artifacts to make SDK imports available, then write `health.test.ts` first. Controlled Fetch responses must invoke the actual generated operation: valid payload returns typed data; unknown/missing status rejects; non-2xx, invalid JSON, network rejection and timeout become failures. Independently abort a caller signal: assert Fetch receives cancellation and the operation settles promptly with cancellation preserved, before the deadline; also cover an already-aborted signal and cleanup on success/error/abort. A standalone Zod parse test cannot prove wiring.
3. Write UI tests through the same generated call boundary: loading, verified success and failure text; malformed successful HTTP never renders healthy. Controlled Fetch doubles belong only to these boundary tests, never application runtime. Observe red behavior before wrapper/UI implementation.

## Implement: green

1. Enable explicit SDK response validation; compile generated paths with all strict flags except `exactOptionalPropertyTypes` in the separate config selected by the owner. Keep the app config fully strict, including `exactOptionalPropertyTypes`.
2. Implement the thin health call with caller/deadline signal composition and cleanup, one QueryClient and query passing its signal, bounded timeout/retries, and minimal semantic UI. Preserve abort cancellation and settle errors visibly. Do not hardcode success.
3. Configure same-origin proxy, fixed port and explicit Vitest include `tests/unit/**/*.test.{ts,tsx}`. Add manifest scripts: `generate:api`, `compile:generated`, `typecheck`, `lint`, `format:check`, `test` (non-watch), `build`, `dev`; compile generated sources before app checks and runtime bundling. Root wrappers delegate. Phase 3 verifies discovery remains isolated after adding its browser spec under `tests/e2e/`.
4. Generate twice from the same offline input; compare artifact bytes and inventory. Commit OpenAPI and generated output together. No generator side effects in dev/build.

## Refactor and Tests After

Remove redundant wrapper/state while keeping tests on the generated SDK. Owned source cannot weaken strictness or unsafe-any rules. Generated code must pass its separate strict compile with only exact optional checking disabled, then build and run through the emitted package boundary. Avoid linting/formatting generator output into perpetual drift.

## Test matrix and proposed verification

Planned commands, unavailable at baseline; run from `apps/web/` after manifests exist:

```sh
npm ci
npm run generate:api
npm run test
npm run typecheck
npm run lint
npm run format:check
npm run build
npm run generate:api
```

| Layer | Test | Pass condition |
| --- | --- | --- |
| Generated SDK boundary | Valid/missing/unknown status | Only valid response becomes typed success. |
| Generated SDK boundary | HTTP/network/JSON/timeout | Observable failure, bounded completion. |
| Cancellation | Caller abort, already-aborted signal, independent deadline | Actual SDK/Fetch receives abort; prompt cancellation retains semantics/reason; manual timers/listeners are released on all paths. |
| React integration | Loading/success/failure | Textual states, malformed payload cannot look healthy. |
| Suite discovery | Unfiltered unit script | Collects only src unit/integration tests; no Playwright spec, service or browser dependency. |
| Compile/build | Owned and generated TS | App passes all strict flags; generated project passes all other strict flags with exact optional checking disabled; no duplicate payload types. |
| Generation | Repeat export/generation | Identical bytes and file inventory; phase 3 enforces drift. |

Real browser success is deliberately proved in phase 3 against the actual API, without route interception.

## Risk, security, compatibility and rollback

- Medium likelihood × high impact: generator/TS/Zod mismatch or validation silently disabled. Mitigate with an actual generated-operation invalid-payload test, strict generated-project compile under the accepted exact-optional exception, strict app compile, and build.
- Medium × high: double-prefix/proxy DNS mistakes. Keep browser same-origin, preserve path; actual Compose browser smoke in phase 3 proves routing.
- Medium × medium: endless pending/retries or ignored caller cancellation. Compose Query signal with the deadline, disable health query retry, and test abort/deadline independently with cleanup; fake clock where useful.
- No credentials or private data enter web bundles. No auth/provider contracts are introduced.
- No previous web users/state need migration. Preserve new health contract; intentional changes regenerate together.
- Revert phase-owned files and sequential root modifications; retain backend only if its tests remain green. Do not manually repair generated files.

## Exit checklist

- [x] Record red/green SDK and UI tests, exact versions and actual generated inventory.
- [x] Pass strict app TS, separate generated-project strict checks, lint, format, focused and unfiltered unit tests/build, caller/deadline cancellation tests and two stable generations.
- [x] Hand ownership to [phase 3](phase-03-local-runtime-ci-and-handoff.md).

## Implementation evidence

- Runtime and dependencies: Node `24.22.1`, npm `12.2.1`, Hey API `0.99.0`; `make setup` completed with `uv sync --locked` and `npm ci`. `npm audit` reported zero vulnerabilities.
- Test-first and behavior: the missing SDK helper and UI were observed red before implementation. The generated operation is configured with Zod response validation; all 10 SDK boundary tests and 3 UI state tests pass, including malformed data, caller cancellation, deadline cancellation and cleanup.
- Generation: two consecutive `npm run generate:api` runs emitted the same 17 TypeScript files byte-for-byte (the generator reported 5 plugin outputs each run).
- Other web gates: after the owner-approved compiler boundary, `npm run lint`, `npm run format:check`, and `npm run build` pass. A fresh `make setup` completed; `npm ci` reported zero vulnerabilities. The full root `make check` passes backend lock/tests/Ruff/format/strict mypy and all web tests/typecheck/lint/format/build.
- Compatibility disposition: Hey API `0.99.0` generates 12 errors in `src/shared/api/generated/client/` and `src/shared/api/generated/core/` when `exactOptionalPropertyTypes` is enabled; upstream issue [#2236](https://github.com/hey-api/hey-api/issues/2236) remains open with the same runtime serializer error. Per the owner's decision, generated sources compile in a separate strict project with that one option disabled; app sources retain it. The emitted SDK JavaScript and declarations are used through a package alias, and generated source files remain untouched. The full check passes.
- Review: the staged Phase 2 changes were reviewed against phase requirements and the base/web checklist while `biendo27` was the active GitHub account. No blocking or informational findings remained; `git diff --cached --check` passed.
- Commit: `ded277e` (`feat: add generated web health client`), authored and committed as `javis-27`.
