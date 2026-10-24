# Code Standards

These standards guide implementation and review. For module ownership and dependency boundaries, see [System Architecture](02-system-architecture.md); use the [Codebase Summary](03-codebase-summary.md) for navigation.

## Types and contracts

- Annotate function parameters and return values, including asynchronous functions and collections. Use strict mypy and Ruff formatting/lint in Python; use TypeScript strict mode, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, and ESLint rules against unsafe `any` and non-null assertions by default.
- Avoid `Any`, bare `list`/`dict`, untyped business payloads, blind casts, and `type: ignore`. Use a narrow exception only at a provider or framework adapter, with validation and an explanation.
- Represent external JSON as `unknown`/`JsonValue` at the boundary and normalize it once into a validated model. Application code should access named fields, not raw payload keys. Use keyed maps when the domain needs them; use `TypedDict` only for fixed framework-shaped contracts, not as a `dict[str, Any]` escape hatch.
- Use Pydantic for runtime-boundary data and LLM/tool arguments and results. Use dataclasses for simple internal immutable values; do not add duplicate model layers without a distinct contract.
- Set `extra="forbid"` on application request, tool, and LLM contracts. Normalize provider envelopes by selecting the needed fields. Require strict scalar validation where coercion could change meaning, while allowing explicit parsing for transport dates, UUIDs, and environment settings; do not enable global strict mode without checking legitimate JSON inputs.
- Distinguish missing values from explicit optional values. Use validated email/URL types, UUIDs, aware UTC datetimes, and bounded integers where applicable. Defaults must express real semantics; do not use empty strings, collections, or `False` to conceal a missing required value. Avoid shared mutable defaults.
- Keep distinct contracts distinct and named by their role, such as `CompanyRow`, `CompanyBriefing`, and `ApproveBriefingRequest` when each is genuinely needed.
- In TypeScript, consume generated API contracts rather than hand-maintaining duplicate enums or schemas. Use discriminated unions for variant payloads and exhaustive handling where variants matter.

## Domain choices and framework boundaries

- Use closed status, action, and tool identifiers where the valid set is finite. Python enums should use `StrEnum`; represent tool identity with a type such as `ToolName.WEB_SEARCH`, and centralize wire conversion. Reject unknown names. An enum does not grant authorization, and arbitrary provider model names or free text should not be enums.
- Give each agent an explicit allowlist of callable tool objects. A model must not choose or grant its own permissions.
- Keep LangGraph's framework update dictionaries at graph nodes. Pydantic state supports attribute reads but does not validate every later node update or output; validate business models and final workflow results explicitly. `create_agent` does not support Pydantic state, so use its native `TypedDict` shape where required. Model partial updates as typed contracts when useful; avoid writing whole stale state from parallel branches. Add explicit deterministic reducers and verify resume/serialization behavior when implementing graph workflows.
- Use functions by default and classes for owned state or resources. Do not require `BaseService`, `GenericRepository`, custom dependency injection, or one-line service wrappers. Direct tool-to-integration calls are acceptable when no business invariant or coordination belongs in a service.

## Reliability and security

- Centralize named domain errors and their HTTP mapping. Do not turn unexpected failures into `None` or success-shaped values.
- Bound transient retries by deadlines and jitter; do not swallow cancellation. Async paths must not perform blocking I/O. Scope database sessions to a unit of work and end transactions before LLM calls or external HTTP requests.
- Bind approval to an immutable report version, action, and recipient set. Any edit invalidates that approval. Reconcile unknown delivery outcomes before retrying; never blindly resend.
- Parameterize SQL and Cypher values. Keep secrets, full email content, and prompt content out of default logs. Use typed trace identifiers and fail early on invalid configuration.

## Naming and organization

- Python modules, functions, and variables use `snake_case`; TypeScript component files and component names use `PascalCase`, hooks use `useX`, and other TypeScript files use kebab-case.
- Keep functions focused on one responsibility. Do not enforce arbitrary line-count limits or create a generic `utils` dumping ground. Comments should explain a decision or constraint, not restate the code.
- Keep API, workflow, tool, business, provider, persistence, and web-feature contracts at their owning boundaries; do not create empty scaffold folders or import another web feature's internals.

## Tests and gates

Test application behavior, business rules, and integration contracts at the smallest layer that can prove the invariant. Prefer meaningful failure and edge cases over exhaustive combinations or tests of framework guarantees and trivial accessors.

- Use unit tests for pure logic and integration tests with the real database for application persistence contracts. Use controlled provider doubles at external boundaries; keep live provider smoke checks separate and opt-in.
- For LLM behavior, citations, and prompt-injection handling, use a human-reviewed corpus of authorized, redacted material. Do not treat an LLM judge as a deterministic security gate.
- Keep development and test data, databases, and credentials separate. Concurrency tests should target a specific application invariant with deterministic synchronization.
- Continuous integration should cover tests, lint, type checks, web build, and generated OpenAPI drift. Mark checks as required only after the corresponding workflow has run and GitHub exposes the checks.

## Review checklist

- Does each behavior and contract have one clear owning boundary?
- Are external and framework-shaped values validated before business use?
- Are optional, missing, and defaulted values semantically distinct?
- Are authorization, approval invalidation, transaction scope, and retry behavior explicit?
- Are provider and database failures handled without hiding cancellation or unknown outcomes?
- Do tests prove the changed invariant at its lowest reliable layer?
- Are generated contracts and static checks kept aligned with source?

## Contributions

Work from an issue branch; open a pull request targeting `main` and link the issue. Use Task, Feature, or Bug issue types, area labels for ownership, and the release milestone. Use sub-issues to group scope and dependency relationships to express ordering. Use the [pull request template](pull_request_template.md) for documentation and code changes.
