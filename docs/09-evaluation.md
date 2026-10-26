# Briefing evaluation

## Purpose and ownership

Evaluate whether a sales or business-development reader can prepare for a meeting using accurate, relevant and traceable information. Report length, citation count and fluent prose are not substitutes for usefulness or factual support.

This is the target design. The dataset, runner and role baselines are not implemented yet. The planned `apps/backend/evals/` owns quality evaluation; `apps/backend/tests/` owns deterministic correctness and integration checks. Each feature adds its cases and measurements as it is built. Final integrated evaluation verifies the complete release rather than introducing evaluation for the first time.

## Dataset contract

Use explicitly labelled synthetic emails, contacts and calendar events grounded in verified public company sources. A fictional request or meeting is not a claim about a real company's intentions. Use non-deliverable example addresses in fixtures; live delivery checks require an explicit mapping to controlled test inboxes.

Each case needs:

- A stable identity, dataset version, synthetic-data label and fixed scenario time/timezone.
- Email, calendar and prior-knowledge inputs, including absent or invalidated context where relevant.
- Source URLs, retrieval time, publication time when available, and versioned permitted excerpts or snapshots sufficient to verify expected facts. Missing publication dates remain unknown.
- Expected company identity, supported facts and their evidence, required meeting context, allowed unknowns and forbidden claims/actions.
- Applicable role/retrieval/workflow checks and human review status.

Generated cases are candidates until the owner reviews their evidence and expected outcomes. Unreviewed cases cannot establish a golden baseline. Do not use a model's own answer as unquestioned ground truth. Keep a held-out subset once the corpus is large enough; record changes to expectations instead of silently rewriting them to make a run pass.

## Initial scenarios

| Scenario | Observable outcome |
| --- | --- |
| New company with an upcoming meeting | Correct identity and source-backed briefing with useful preparation questions; no invented history. |
| Returning company with approved knowledge | Relevant prior facts and relationships are reused with provenance; wrong-company context is excluded. |
| Irrelevant incoming email | No unnecessary research run or delivery. |
| Ambiguous company identity | Ambiguity is surfaced and a correction can persist without merging unrelated companies. |
| Missing or cancelled meeting | No invented attendance or active meeting context. |
| Missing, stale or conflicting sources | Dates, uncertainty and unresolved claims are visible; current facts are not inferred from obsolete evidence. |
| Injection in email, a page or an attachment | Content cannot grant tools, disclose secrets, approve knowledge or send mail. |
| Content or recipients change after approval | The previous decision cannot authorize the changed action. |
| Lost delivery confirmation or restart | Uncertain delivery is reconciled before retry; completed effects are not repeated. |
| Supported attachment and report export | Attachment facts retain provenance; Markdown, PDF and Word represent the same selected version. |

These are scenario requirements, not completed dataset records. Concrete source verification and owner review occur during dataset implementation. Expand cases where one input cannot isolate a failure clearly.

## Measures and decisions

Measure company resolution, retrieval relevance, factual support, meeting usefulness and task completion separately. For each factual claim, identify supporting evidence or mark it unsupported; a valid URL alone does not establish support. Meeting usefulness includes stated needs, relevant history, meeting details and useful questions while distinguishing suggestions from facts.

Report per-case outcomes and failure categories, alongside latency, tool usage and provider-reported usage/cost. Missing usage is unknown. Record dataset/source versions, application revision, prompt version, model identifier and material run configuration so comparisons can be interpreted.

Authorization, approval invalidation, input isolation and delivery deduplication/reconciliation are deterministic gates. LLM judges may assist qualitative scoring but cannot certify these gates. Human review remains necessary for golden expectations and business usefulness. Establish measured baselines before choosing quality/latency/cost targets; illustrative percentages or timings are not release thresholds.

## Execution boundaries

- Regression uses fixed source snapshots and scenario clocks to compare behavior under controlled inputs. Provider doubles can prove contracts, but do not establish live model quality.
- Live evaluation is opt-in and bounded. It verifies actual gateway, search, embeddings and integrations, and records changed sources rather than treating current web results as identical to historical snapshots.
- Unsupported features and unreviewed cases are reported explicitly, never counted as passes. A partial suite can support an intermediate feature; it cannot satisfy complete release acceptance.
- Every workflow role exposes enough trace evidence to identify its inputs, permitted operations and result without default logging of full mailbox contents or credentials. Basic correlation begins with tools and the first workflow; Grafana dashboards build on it.
- Evaluation storage and delivery targets are isolated from operational data. Fixtures never create production approval authority. Reuse production contracts and execution paths; do not build a separate evaluation-only assistant.

Use implementation-owned scripts and manifests for commands once they exist. No evaluation command is available merely because it is described here.
