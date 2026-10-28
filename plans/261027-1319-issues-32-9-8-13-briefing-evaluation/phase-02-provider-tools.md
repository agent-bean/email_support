---
title: "Phase 2: Bounded research tools and adapters — Issue #9"
status: done
priority: P1
effort: "5–7 engineering days"
dependencies: [1]
---

# Phase 2: Bounded research tools and provider adapters

<!-- Updated: Owner-approved red-team R1/R3 - public research boundary, fixture domains and source citation. -->

## Outcome, dependencies and ownership

Deliver the full #9 contract, including genuine configured-provider smoke. Begin after #32 review, owner acceptance and authorized merge. This PR owns provider protocols, resource lifetime, tool permissions, safe fetch and tool execution evidence. Consume [provider research](../reports/researcher-261027-1319-provider-tools.md), [architecture](../../docs/02-system-architecture.md) and accepted phase-1 result contracts. Do not add a provider SDK hierarchy, extra HTTP stack, proxy deployment, worker or projection implementation.

The existing async HTTP client is HTTPX2 (`apps/backend/pyproject.toml:19`); explicit client/timeouts/disabled redirects are established by `apps/backend/src/email_support/integrations/google_workspace.py:12,85–89`. Reuse that library and construction pattern, not Google-specific authentication. Gateway/OpenRouter/Tavily settings remain private; absent configuration is an actionable prerequisite failure, never an invented provider result.

## Data flow and minimal design

- Product Pydantic contracts define chat request/result/tool-call envelopes, embedding batches/vectors, search result/source records, safe fetch results, typed execution metadata and closed errors. Provider JSON is normalized once and cannot flow as arbitrary dictionaries into roles.
- Direct async adapters use injected owned HTTPX2 clients: gateway Chat Completions for tool calls and strict output requests, OpenRouter embeddings, Tavily basic search. Keep model identifiers configurable strings. Verify structured-output capability at the actual configured gateway; compatibility syntax alone proves nothing.
- `ToolName` contains only actual callable read-only operations, initially `WEB_SEARCH` and `FETCH_SOURCE`. Embeddings are a typed integration capability exercised by smoke and future retrieval, not a fabricated model tool merely to use every adapter. Tool metadata contains description, argument/result schema and callable; a central executor validates identity, arguments and role allowlist before invoking the implementation. Roles receive explicit allowed callable objects.
- The Web Research role may search/fetch. The Email interpretation role added by #8 receives no external research tools. Synthesis receives provided evidence and no effectful tools. No registry entry or fallback can approve, send mail, persist corrections or promote knowledge. A model's requested tool name/arguments never change permissions.
- The research input is a closed public-only contract: explicitly approved public company identifiers and a small enumerated set of public research topics. Exclude raw email, meeting text, private needs and approved private knowledge from the research model's context. Identity resolution alone does not certify a sender-supplied name/domain/topic as public; absent an approved public identifier, stop research with an explicit prerequisite. WEB_SEARCH arguments select an approved company reference/topic; application code builds the bounded query from those values, never arbitrary model text. FETCH_SOURCE accepts an invocation-scoped source reference resolving to an approved public seed or validated search-result URL; reject arbitrary model-composed URLs, page-instructed destinations and foreign/stale references. Apply the connection-safety policy after this provenance gate. Keep the contract and checks in the existing research models/executor, without a separate policy framework.
- One per-run budget object owns maximum calls, attempts, concurrency, response sizes, deadline and optional monetary ceiling. Charge attempted calls before dispatch and retries to the same budget. Do not double-retry in adapters and executor. A deterministic execution helper supplies per-attempt timeout, total deadline, bounded jitter/backoff and valid Retry-After handling; transient rate-limit/unavailable failures may retry, validation/auth failures may not. Ambiguous post-dispatch timeout is recorded as unknown upstream outcome; do not blindly retry billable inference. Propagate cancellation, close streams, and stop queued calls at exhaustion.
- Record run/role/tool/provider/model identifiers, parent execution ID, duration, outcome/error and provider-reported usage. Aggregate all known attempts separately from final attempt; absent fields remain unknown. Enforce a configured hard monetary cap only when costs can be authoritatively bounded; otherwise reject that cap configuration or stop for unknown cost, and expose call/time/token bounds honestly. Never compute imaginary cost from a guessed price table.

## Safe fetch compatibility gate

Application fetch accepts only HTTPS URLs without credentials, fragments used as destinations, unsafe host syntax or nonstandard ports. Resolve all IPv4/IPv6 answers and reject any non-global or mixed public/private set, including metadata, mapped IPv6, loopback, private/link-local/reserved/multicast addresses. Disable automatic redirects; reject redirects initially, which avoids a second routing surface. Stream with deadline, byte/decompression/text limits and supported MIME checks; no attachment/parser execution.

Use the researched HTTPX2 2.16.0 route: resolve A/AAAA with `dns.asyncresolver.resolve_name` under an explicit lifetime and `search=False`, validate every answer, connect to a literal vetted-IP URL, set the original `Host`, and pass `extensions={"sni_hostname": original_host}` with certificate verification enabled. Force HTTP/1.1, `trust_env=False`, no proxy, a fresh fetch client/no cross-host reuse, and no secondary hostname resolution. Request identity encoding, reject unexpected Content-Encoding and count raw streamed bytes before decoding. Add dnspython as a direct dependency because bounded asynchronous DNS is now application behavior. Before enabling fetching, prove actual TCP target, original Host/SNI/certificate verification, proxy isolation, DNS lifetime and cancellation against the locked stack. A DNS precheck followed by unrestricted hostname lookup is forbidden. If unavailable, fail closed with `fetch_unavailable` and preserve evidence gaps. Do not introduce new proxy infrastructure or use `verify=False`. Missing safe fetch capability remains an explicit acceptance concern when applicable live research requires it; search snippets are labelled snippets, not fetched/verified full pages.

## File inventory

No deletions; standard package `__init__.py` files are owned with their package.

| Action | Repo-relative path | Responsibility |
|---|---|---|
| Create | `apps/backend/src/email_support/models/research.py` | Provider/tool/budget/error/trace contracts, public research input/source references and ToolName. |
| Create | `apps/backend/src/email_support/research_config.py` | Explicit private settings, limits and capability requirements. |
| Create | `apps/backend/src/email_support/integrations/provider_http.py` | Shared bounded JSON transport and sanitized provider error/retry metadata. |
| Create | `apps/backend/src/email_support/integrations/llm_gateway.py` | Typed direct gateway adapter. |
| Create | `apps/backend/src/email_support/integrations/openrouter_embeddings.py` | Typed embedding adapter, dimension/finite-value validation. |
| Create | `apps/backend/src/email_support/integrations/tavily.py` | Typed bounded search adapter. |
| Create | `apps/backend/src/email_support/integrations/web_fetch.py` | URL/DNS/connection/stream policy. |
| Create | `apps/backend/src/email_support/tools/__init__.py` | Real tool package. |
| Create | `apps/backend/src/email_support/tools/research.py` | Search/fetch callable implementations and metadata registry. |
| Create | `apps/backend/src/email_support/tools/execution.py` | Validation, permissions, shared budgets/retries and metadata events. |
| Create | `apps/backend/scripts/smoke_research_providers.py` | Explicit opt-in live capability smoke using production adapters. |
| Create | `apps/backend/tests/unit/research/test_provider_contracts.py` | Closed tool identities, public-only inputs, usage and config validation. |
| Create | `apps/backend/tests/unit/research/test_provider_adapters.py` | Controlled gateway, embeddings and search request/response contracts. |
| Create | `apps/backend/tests/unit/research/test_tool_execution.py` | Permissions, total budgets, retries/cancellation and trace privacy. |
| Create | `apps/backend/tests/unit/research/test_web_fetch.py` | DNS connection, redirects, streaming and destination safety. |
| Create | `apps/backend/tests/unit/research/test_provider_smoke.py` | Missing-config behavior and private sanitized output guarantees. |
| Modify | `apps/backend/pyproject.toml` | Declare direct bounded async DNS dependency. |
| Modify | `apps/backend/uv.lock` | Resolve tested DNS/HTTP dependency set. |
| Modify | `docs/03-codebase-summary.md` | Actual provider/tool navigation. |
| Modify | `docs/09-evaluation.md` | Implemented smoke entry point and capability/quality distinction. |

HTTPX2 is already a dependency; add direct dnspython and update the lock; otherwise change versions only if the compatibility spike proves a needed compatible patch. No speculative SDK or version pin is prescribed. These provider files stay read-only to phases 3/4 except evidence-driven fixes coordinated into their own reviewed change.

## Tests Before — RED and scenario matrix

Write and run these tests before adapters/executor/fetch implementation. Inject transport/resolver/clock at the external seam rather than globally patching DNS.

| Scenario | Level | Expected observation |
|---|---|---|
| Unknown tool, malformed/extra args, invalid result, denied role | Unit | Reject before callable invocation; safe closed error. |
| Model requests approve/send/promote/correct | Unit | No dispatch identity exists; no database/action capability. |
| Injected email/page requests private canary in query or URL | Unit + transport capture | Research context excludes private mail/meeting/knowledge; only approved public query templates and invocation-scoped source references dispatch. Private canary never reaches search payloads or fetch destinations; arbitrary arguments reject before network. |
| Valid tool, structured output, embeddings/search payload | Contract | Request authentication/shape correct; result validated once. |
| 401/403, 429, unavailable, invalid JSON/schema, missing usage | Contract | Categorized errors; bounded transient retries only; unknown usage retained. |
| Timeout after dispatch, cancellation during call/backoff/body stream | Unit + transport | No swallowed cancellation/blind billable retry; close resources. |
| Nested tool loop or retry exhausts calls/time/concurrency | Unit | A single total budget governs every attempt; no recursive unbounded loop. |
| Secret/full email/prompt/page body in arguments or provider error | Unit capture | Metadata logs omit all such content and raw headers. |
| HTTP/file/data URL, userinfo, nonstandard port, private literals and DNS | Unit | Reject before connection, including IPv6 and mixed answers. |
| DNS changes between check and connect; redirect to metadata | Transport | Connect only to vetted address, preserve TLS hostname; reject redirects. |
| Oversize declared/chunked/compressed body or unsupported MIME | Transport | Abort streaming within limits; no full-body buffering shortcut. |
| Missing gateway schema/tools/usage capability | Live smoke | Unsupported/unknown is explicit; no successful compatibility claim. |

## Implementation steps and refactor

1. Implement the connection-pinning compatibility spike and tests first. Keep fetching disabled until proof exists; record literal-IP Host/SNI extension route/reference and tested HTTPX2 version. Raise the concrete incompatibility for plan review if no supported solution fits scope.
2. Define contracts/config and strict startup validation; construct one owned async client per relevant provider at CLI/workflow composition, close all resources on success/cancel/error. Never allocate an import-time client or hold mutable run budgets globally.
3. Implement direct adapters with fixed configured provider endpoints, safe status mapping and normalized usage. Validate vectors are finite, indices/order and batch dimensions match the actual request; no fake zero vectors.
4. Implement read-only registry/callables and executor, including the public input/query/source-reference gate before dispatch. Centralize wire conversion and safe error categories; keep actual provider protocols in integrations. Test budget accounting through multiple retries and provider tool-call turns, and capture actual outgoing requests for private-data canary assertions.
5. Emit bounded structured trace metadata suitable for later correlated export without implementing Grafana/Tempo deployment. Keep full captured sources only in explicitly protected run storage, not traces.
6. Add smoke which exercises real gateway tool-call argument exchange using the production allowed-tool executor, schema output validation and usage fields, real embeddings and Tavily parsing. Use public harmless content and reserved example.com/net/org synthetic identities accepted by the canonical validator; no send capability or operational-address mapping. Fail/incomplete required capabilities rather than accepting a shaped fake response.
7. Refactor only repeated execution policy, then record sanitized smoke revision/config/model IDs and capabilities with actual unknowns. Do not embed credential or instance-specific endpoint/model details in evergreen public docs.

## Tests After — GREEN and verification

Proposed narrow test paths after creation, from `apps/backend`:

```sh
uv run --locked pytest -q tests/unit/research/test_provider_contracts.py tests/unit/research/test_tool_execution.py tests/unit/research/test_web_fetch.py
```

Proposed opt-in command after implementation, from `apps/backend`:

```sh
uv run --locked python scripts/smoke_research_providers.py --live --output PATH_TO_PRIVATE_OUTPUT
```

Credentials come from validated private environment/configuration, never command arguments or checked-in files. Preserve bounded sanitized evidence including missing capabilities. Then existing root `make backend-check`. Contract doubles prove correctness; the real smoke is a separate mandatory evidence gate. No tests/provider calls were run while drafting.

## Acceptance mapping — Issue #9

- [x] AC1: centralized identities/schema metadata, validated IO and unknown/malformed/denied dispatch tests pass.
- [x] AC2: actual adapters authenticate; timeout/retry/cancel/errors/budgets pass; connection-safe fetch rejects private/redirect/oversize inputs.
- [x] AC3: read-only registry cannot approve/send/promote; captured default logs exclude secrets/full mailbox content. Public input/query/source-reference checks and canary tests prevent private context reaching research searches or fetch destinations.
- [x] AC4: correlated event metadata includes duration/outcome and reported usage, with honest missing values and retry totals.
- [x] AC5: genuine gateway tools/structured output/usage, embeddings and search smoke records capabilities and failures; deterministic contract tests separately pass.

## Execution evidence — 2026-10-27

- `make backend-check` passed: lock check, 187 unit/integration/contract tests, Ruff lint and format checks, and strict mypy over source/scripts/tests/migrations/evals.
- `uv run --locked pytest -q tests/unit/research` passed: 49 tests, including public-context exclusion and shared provider-call budget/trace coverage.
- The 2026-10-27 configured live smoke passed: `cd apps/backend && uv run --env-file ../../.env --locked python scripts/smoke_research_providers.py --live --output evals/results/research-provider-smoke-20261027-configured.json`. Gateway tool call, strict output, gateway usage, embeddings and Tavily search all passed. Report mode is 0600 and the file is ignored by Git; reported provider usage is retained while unknown cost stays null.
- Phase 2 local gate passed with `make backend-check`: lock check, 187 unit/integration/contract tests, Ruff lint and format, and strict mypy. The 49 focused research tests passed. Phase 2 is complete; Phase 3 may proceed.

## Risk, compatibility, rollback and handoff

| Risk | Likelihood × impact | Mitigation |
|---|---|---|
| DNS rebinding bypasses preflight | Medium × High | Connection-pinning proof, preserved TLS verification, fail closed. |
| Gateway accepts syntax but omits required behavior | High × High | Real capability smoke before compatibility/acceptance claim. |
| Retry storm or hidden cost | Medium × High | One per-run attempt budget/deadline, unknown billable outcome handling, explicit cost uncertainty. |
| Prompt injection escalates permission | High × High | Deterministic allowlists, no effectful tools, unsafe outputs rejected. |
| Read-only web calls disclose private context | High × High | Public-only research context, approved query templates, controlled source references and outbound canary tests; SSRF controls alone do not prevent disclosure. |
| Sensitive trace/config leakage | Medium × High | Metadata-only capture tests and protected result storage. |

Additive tool/integration code changes no existing auth/API/database contract. Roll back this PR and disable its opt-in entry point; preserve already incurred usage as historical evidence. Existing owner/Google connections stay independent. No external research call can be undone, so cancel in-flight work and retain actual attempt outcomes. #8 starts only after review/checks and explicit owner acceptance/authorized merge. Open evidence: configured provider capabilities and actual safe HTTPX2 connection API remain empirical gates.
