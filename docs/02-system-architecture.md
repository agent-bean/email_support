# System architecture

Module navigation is owned by [03](03-codebase-summary.md); engineering constraints by [04](04-code-standards.md).

## Runtime boundaries

The React/TypeScript/Vite web app talks to a FastAPI backend. A separate Python worker runs scheduled synchronization, durable jobs, and LangGraph workflows. Both processes share application services and PostgreSQL; long-running research does not live inside an HTTP request.

LangGraph coordinates explicit stages and review pauses. Specialist LLM roles handle email interpretation, web research, and briefing synthesis. Deterministic code handles database lookup, calendar access, memory persistence, authorization, and delivery. These are separate responsibilities without requiring a separate process or an LLM loop for each one.

| Responsibility | Owner and boundary |
| --- | --- |
| Email interpretation | Email specialist extracts typed intent/contact/company candidates from untrusted message content. |
| Company information | Resolution service and lookup tools retrieve identities and facts; ambiguity remains visible. |
| Web research | Research specialist chooses from a bounded read-only tool allowlist and returns typed evidence references. |
| Calendar context | Read-only Google Calendar integration normalizes meeting context for the workflow. |
| Report generation | Briefing specialist synthesizes a typed report, rendered as Markdown with evidence references. |
| Memory | Knowledge service stores approved material and explicit preferences; retrieval tools select relevant context. |
| Human approval | Authenticated owner UI and approval service record an actual human decision; the LLM has no approval authority. |

An agent defines instructions, context, tools, and a bounded execution policy. A tool is a typed callable exposed to a model. An integration implements a provider protocol. A service enforces application invariants. These concepts must remain distinguishable during review.

Backend dependencies flow from API routes to services, and from the worker through workflows to agents, tools, and services. Tools may call services or integrations; services may call storage and integrations. Provider/storage code must not import HTTP routes or workflow orchestration. Keep construction of resources at composition points instead of creating import cycles.

The web composition layer assembles feature screens. Features consume shared API and UI modules, and shared modules never depend on features. Features do not reach into another feature's internal files. TanStack Query owns server state; the briefing editor owns unsaved local changes. Generate API types, client calls, and runtime validators from backend OpenAPI rather than maintaining a second payload definition by hand.

## Workflow and durable work

Synchronization records normalized input and schedules research through PostgreSQL jobs. A worker claims work using an expiring lease. Unique input/job keys and conditional state changes prevent duplicate processing. A lost lease must prevent a stale worker from committing another worker's result.

The research graph resolves identity, retrieves prior context, performs bounded research when necessary, and produces a versioned briefing. Multiple messages for the same company can share fresh context. Freshness and research budgets are explicit configuration, not hidden prompt instructions.

Persist the briefing before pausing for review. The owner can return much later; an HTTP request is never held open while awaiting a decision. Use PostgreSQL-backed LangGraph checkpoints and stable workflow identifiers. Checkpoints support resume, not authorization.

Approval and an action record are committed together in PostgreSQL. The worker rechecks their exact binding before acting. Nodes that can resume must not repeat external effects merely because their execution restarted. LangGraph documents that interrupted nodes restart on resume; side effects need application-owned idempotency. [Interrupt guidance](https://docs.langchain.com/oss/python/langgraph/interrupts).

Email delivery is not an exactly-once transaction across PostgreSQL and Gmail. Persist an attempt before sending. If the provider may have accepted a message but confirmation was lost, mark the attempt as uncertain and reconcile against Gmail evidence before a retry. A deterministic message identifier is useful reconciliation evidence, not a guarantee that Gmail deduplicates sends.

## Data ownership

| Store | Responsibility | Recovery rule |
| --- | --- | --- |
| PostgreSQL | Owner identity/connections, normalized mail and meetings, company/contact identities, source evidence, versioned briefings, approvals/actions, durable jobs, explicit preferences, approved knowledge, checkpoints. | Canonical data requires backup and restore. |
| Neo4j | Queryable relationship projection between companies, contacts, messages, meetings, and approved knowledge. | Rebuild from canonical records with stable IDs. |
| Qdrant | Semantic retrieval projection of eligible knowledge chunks with provenance, company IDs, source version, and embedding version. | Re-embed/rebuild from canonical records. |

Graph traversal answers relationship questions such as which contacts, meetings, and prior discussions connect to a company. Vector search finds semantically relevant approved knowledge. Neither database is a substitute for authoritative relational records or approval checks.

Projection updates use durable jobs committed with canonical changes. Writes are repeatable; failures remain pending and visible. Before using a retrieved item, confirm its canonical version and eligibility so stale projections cannot reintroduce revoked knowledge. A company with unresolved identity must not inherit another company's context merely through a similar name.

Raw source evidence and approved knowledge have different eligibility. New web evidence may support the current draft; only approved knowledge enters reusable knowledge retrieval. Current evidence, approved material, and owner preferences remain distinguishable in prompts and storage.

Run state/checkpoints are short-term execution memory. Approved knowledge and explicit preferences are long-term memory. There is no additional memory database or automatic preference inference from arbitrary email instructions. Removing canonical knowledge schedules projection removal and prevents its use immediately through eligibility checks. Backup retention and operational-log retention are separate concerns.

## Trust and provider boundaries

- Authenticate the single owner and protect browser state-changing requests. Application sign-in and Google mailbox/calendar consent are separate concerns.
- Keep refresh tokens encrypted at rest with the encryption key outside the database. Keep gateway/API credentials outside source, issue text, model context, and normal logs.
- Treat incoming email, web pages, search results, and saved source text as untrusted data. Message roles and delimiters aid separation but do not guarantee resistance to prompt injection.
- Enforce read-only agent tool allowlists in code. Email sending and knowledge promotion are application actions outside model-controlled tool execution.
- Validate tool arguments, structured model output, retrieved IDs, and permissions before use. Parameterize database queries; do not execute model-generated arbitrary SQL or Cypher.
- Restrict web-fetch destinations, redirects, response sizes, and timeouts to prevent access to private services and metadata endpoints. Minimize mailbox/calendar data sent to external providers.
- Verify the actual gateway's tool calling, structured-output behavior, usage reporting, and timeout/error semantics. OpenAI-compatible request syntax does not prove those capabilities.

## Operations and quality

Propagate trace/run/job identifiers across HTTP, worker, LLM, and tool calls. OpenTelemetry exports traces to Tempo; Prometheus and Grafana expose operational metrics and dashboards. Collect latency, retries, error categories, token/cost usage where reported, queue age, and projection freshness without retaining full mailbox content by default. Missing provider usage is unknown rather than zero.

Quality evaluation is separate from tracing. Use a small human-reviewed corpus covering company resolution, retrieval relevance, source-supported claims, missing evidence, stale knowledge, injection attempts, and unauthorized actions. Evaluate retrieval and briefing quality separately. Deterministic tests enforce approval and delivery rules; an LLM judge cannot certify authorization or factual correctness by itself.

## Important decisions

| Decision | Rationale and material trade-off |
| --- | --- |
| FastAPI + LangGraph with one API and one worker | Durable review/resume and explicit graph execution with fewer hidden handoffs than an autonomous agent team. |
| Conventional backend modules (`agents`, `tools`, `services`, integrations/storage) | Recognizable ownership boundaries without mandatory ports/adapters or a class per operation. |
| PostgreSQL jobs, checkpoints, and canonical records | Transactional input/action scheduling with fewer operating services; polling and leases require careful application logic. |
| Separate Neo4j and Qdrant projections | Graph traversal and semantic retrieval have distinct query responsibilities, with added resource, synchronization, and recovery costs. |
| `models` for typed application contracts | Distinguishes application contracts from ORM classes in PostgreSQL storage; `schema` remains the term for JSON/OpenAPI/database structure. |
| Generated web API contracts | Avoids independently maintained backend/frontend payload definitions; generation and runtime validation need a tested toolchain. |
