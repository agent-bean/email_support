# Web/OpenAPI contract toolchain for issue #2

Advisory research snapshot. [Controller evidence and decisions](scout-261024-1827-issue-2-foundation.md) supersede the example OpenAPI path, Node floor, standalone Fetch package suggestion and omission of TanStack Query below. The phase files own execution.

Research conducted: 2026-10-24. Scope: planning research only for the initial typed web/API foundation. The accepted Hey API + Zod choice is fixed. This report does not implement or install anything; filenames and commands below are proposed, not present in the repository.

## Recommendation

Use the local FastAPI OpenAPI document as the sole contract input and generate a small TypeScript SDK and Zod validators with @hey-api/openapi-ts, its Fetch client and Zod plugin. Enable only SDK response validation. Keep the generated client under apps/web/src/shared/api/generated/; application code should import its generated operation types and schemas rather than declare request/response copies. Keep thin app-owned wrappers only where needed for base URL, credentials, and mapping generated errors into visible UI states.

This aligns with the existing architecture/code standards: React + TypeScript + Vite, backend-owned OpenAPI, generated web contracts, and runtime boundary validation. It supplies a coherent narrow vertical slice without introducing TanStack Query, auth flows, UI framework choices, or domain features ahead of their owning issues.

## Version and compatibility evidence

| Area | Recommendation/evidence | Confidence |
|---|---|---|
| Hey API | @hey-api/openapi-ts with @hey-api/client-fetch, @hey-api/sdk, and zod. Hey documents local file input, generated Fetch SDK, Zod schema generation, and SDK response validator configuration. [Input/config](https://heyapi.dev/docs/openapi/typescript/configuration), [Fetch client](https://heyapi.dev/docs/openapi/typescript/clients/fetch), [Zod plugin](https://heyapi.dev/docs/openapi/typescript/plugins/zod), [SDK validation](https://heyapi.dev/docs/openapi/typescript/plugins/sdk) | Docs confirm each feature individually. Exact plugin-version interoperability remains unexecuted. |
| Runtime | Pin Node 22.12+ (or the repo's then-current supported Node 22 patch) via .nvmrc/engines; use npm and commit package-lock.json. Current Vite requires Node 20.19+ or 22.12+; Hey API generator docs say Node 22+. Choosing Node 22.12+ satisfies both documented floors. [Vite](https://vite.dev/guide/), [Hey API](https://heyapi.dev/docs/openapi/typescript/get-started) | Documented compatibility floor; exact backend integration still needs a real smoke test. |
| TypeScript | "strict": true, "noUncheckedIndexedAccess": true, "exactOptionalPropertyTypes": true in web TS config, consistent with repo standards. The last two are separate flags and must be explicitly enabled. [Strict](https://www.typescriptlang.org/tsconfig/strict.html), [TSConfig reference](https://www.typescriptlang.org/tsconfig/) | Compiler options documented; generated artifact compatibility under all flags untested. |
| Browser | Fetch API is browser-native; Vite supports the listed React/TS SPA stack. Set generated client's base URL from a same-origin /api proxy in development/production where deployment permits. [Hey Fetch](https://heyapi.dev/docs/openapi/typescript/clients/fetch), [Vite guide](https://vite.dev/guide/) | Browser platform fit is straightforward; proxy/CORS and actual origin behavior are repository deployment decisions to verify. |

Use exact, mutually compatible versions in the lockfile, not latest in CI. The research did not execute npm installation or determine the current latest package release, so the implementation phase should select and lock versions together, then run generation/typecheck/build once before accepting them. Avoid a Vite generator plugin: a dedicated generate:api command is simpler, deterministic in CI, and avoids running codegen as a side effect of every dev/build invocation.

## Proposed minimal inventory (not yet existing)

- apps/web/package.json: generate:api, typecheck, test, build scripts; dependencies @hey-api/client-fetch, zod; dev dependencies @hey-api/openapi-ts, TypeScript, Vite/React, one unit runner and Playwright only if needed for the browser/API smoke test.
- apps/web/package-lock.json: reproducible npm dependency graph.
- apps/web/.nvmrc and apps/web/package.json engines: Node 22.12+.
- apps/web/openapi-ts.config.ts: input ../../apps/api/openapi.json (or whichever checked-in local spec the backend issue establishes), output src/shared/api/generated, plugins for @hey-api/client-fetch, @hey-api/sdk, zod, with SDK validator response set to zod.
- Generated apps/web/src/shared/api/generated/ files: checked in; never hand-edit.
- apps/web/src/shared/api/client.ts: minimal setup of API base URL and credentials policy; do not add auth assumptions before the auth contract exists.
- One focused API client test and one browser integration test as described below.

If backend OpenAPI is generated only at runtime and not committed, make the generation step depend on a deterministic backend export command and produce the spec in a known ignored/build path. Do not fetch a remote spec in routine local generation or CI; local input reduces network variance and makes the source relationship reviewable.

## Test-first matrix

| First failing test / check | Minimal behavior to establish |
|---|---|
| Generator drift check | Run npm run generate:api, then fail if it changes tracked generated output. Regeneration after an intentional backend spec change updates generated files and the committed OpenAPI snapshot in the same reviewed change. |
| Strict typecheck | A small consumer imports a generated operation and compiles with strict flags; no handwritten payload interface or enum is introduced. |
| Client contract test | With a controlled Fetch response, a valid response returns typed data; malformed JSON shape is rejected by the generated Zod response validator and exposed as an API failure, never rendered as success-shaped data. |
| HTTP failure test | Non-success status / network failure follows the generated SDK result/error contract and the app wrapper maps it to an actionable failure. Do not retry mutations automatically. |
| Real browser-to-API success | Start the actual API and Vite app using repository scripts once created; browser calls a harmless API endpoint through the configured origin/proxy and renders its real response. This verifies CORS/proxy, base URL, serialization, and browser Fetch together. |

Start with the generated-client response test and typecheck; add browser smoke test for actual route once both services exist. Do not add a generic mock service worker or broad end-to-end suite until additional behavior requires it. The malformed-response test must exercise the generated operation/validator path, not call a Zod schema in isolation.

## Error behavior and regeneration discipline

Treat HTTP errors, network errors, JSON decoding errors, and Zod response-validation failures as distinct failure paths at the API boundary. The UI should show a bounded actionable error state and preserve any local unsaved edits; a malformed success payload must not be cast to the generated type. Keep detailed validation metadata in developer/test diagnostics, not mailbox or prompt content in normal logs. Do not retry write operations blindly.

Keep generated output committed so reviewers and builds see exactly what the backend schema produced. The generation script should be the sole writer. In CI, run generation and require a clean diff; when generated output changes, review it together with the OpenAPI diff. Lock generator, client and Zod versions through npm lockfile; upgrades are deliberate lockfile changes followed by regeneration, typecheck, client tests, and browser smoke. Do not use package install ranges to let code generation drift silently.

## Risks and unresolved verification

- Hey API docs confirm Zod v4 and validator wiring, but the docs do not prove the selected versions compile together under this project's strict TS flags; test that first during implementation.
- OpenAPI response validation checks the schema Hey generates from the spec. If FastAPI omits or weakens response schemas, the generated check is correspondingly weak; the backend issue must expose meaningful response models.
- Error payload responses may be represented as a union; ensure OpenAPI declares success and error statuses accurately and the wrapper handles the generated union/error result.
- The exact spec path/export command, initial endpoint, and dev proxy origin depend on issue #2's accepted implementation details; this report intentionally does not invent them.
- No package versions were installed or compatibility tests executed during this research.

## Immediate planned steps

1. Confirm issue #2's backend OpenAPI artifact path and a harmless endpoint contract.
2. Add the proposed minimal web manifest/config, pin compatible versions with npm lock, and generate the SDK/Zod artifacts.
3. Write the response validation and strict typecheck cases first, then implement only the narrow client setup needed to pass them.
4. Add the browser-to-live-API smoke test and generation drift check once the repo's service launch commands exist.

Status: DONE_WITH_CONCERNS
Summary: Official documentation supports a conservative local OpenAPI → Hey API Fetch SDK + Zod response validation foundation, with Node 22.12+ covering current Vite and Hey API requirements. Exact dependency compatibility and the repo-specific OpenAPI path remain to be proven during implementation.
Concerns/Blockers: No package installation or runtime compatibility checks were performed, as requested for planning-only research.
