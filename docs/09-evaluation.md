# Briefing evaluation

## Purpose and ownership

Evaluate whether a sales or business-development reader can prepare for a meeting using accurate, relevant and traceable information. Report length, citation count and fluent prose are not substitutes for usefulness or factual support.

The repository-local `apps/backend/evals/` package owns quality evaluation; `apps/backend/tests/` owns deterministic correctness and integration checks. The initial `briefing-v1` corpus is candidate data: no case has owner-reviewed golden expectations and no assistant-quality result is established. Later features add behavior-specific cases and measurements. Final integrated evaluation verifies the complete release rather than introducing evaluation for the first time.

## Dataset contract

Use explicitly labelled synthetic emails, contacts and calendar events grounded in verified public company sources. A fictional request or meeting is not a claim about a real company's intentions. Use non-deliverable example addresses in fixtures; live delivery checks require an explicit mapping to controlled test inboxes.

Each case needs:

- A stable identity, dataset version, synthetic-data label and fixed scenario time/timezone.
- Email, calendar and prior-knowledge inputs, including absent or invalidated context where relevant.
- Source URLs, retrieval time, publication time when available, and versioned permitted excerpts or snapshots sufficient to verify expected facts. Missing publication dates remain unknown.
- Expected company identity, supported facts and their evidence, required meeting context, allowed unknowns and forbidden claims/actions.
- Applicable role/retrieval/workflow checks and human review status.

Generated cases are candidates until the owner reviews their evidence and expected outcomes. `GoldenExpectationReview` binds a reviewed case to its dataset version, case hash, source hashes, reviewer and timestamp. Unreviewed cases cannot establish a golden baseline. Do not use a model's own answer as unquestioned ground truth. Keep a held-out subset once the corpus is large enough; record changes to expectations instead of silently rewriting them to make a run pass.

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

The `briefing-v1` dataset includes 24 synthetic candidate cases: one English and one Vietnamese case for each scenario, including uncertain relevance and an incorrect prior company association. Candidate cases still need owner review before they can establish a golden baseline. Product behavior for unsupported later features remains explicitly unsupported in the case record.

## Measures and decisions

Measure email relevance, company identity, retrieval relevance, factual support, meeting usefulness and task completion separately. Replay compares captured relevance and identity status/company/candidates against case expectations; a wrong identity fails independently of briefing claim quality. For each factual claim, identify supporting evidence or mark it unsupported; a valid URL alone does not establish support. Meeting usefulness includes stated needs, relevant history, meeting details and useful questions while distinguishing suggestions from facts.

Report per-case outcomes and failure categories, alongside latency, tool usage and provider-reported usage/cost. Missing usage is unknown. Record dataset/source versions, application revision, prompt version, model identifier and material run configuration so comparisons can be interpreted.

Authorization, approval invalidation, input isolation and delivery deduplication/reconciliation are deterministic gates. LLM judges may assist qualitative scoring but cannot certify these gates. Human review remains necessary for golden expectations and business usefulness. Establish measured baselines before choosing quality/latency/cost targets; illustrative percentages or timings are not release thresholds.

## Execution boundaries

- Regression uses fixed source snapshots and scenario clocks to compare behavior under controlled inputs. Provider doubles can prove contracts, but do not establish live model quality.
- Live evaluation is opt-in and bounded. It verifies actual gateway, search, embeddings and integrations, and records changed sources rather than treating current web results as identical to historical snapshots.
- The research-provider capability smoke uses the production read-only adapters and writes sanitized evidence to a new private output file. Copy the root `.env.example` to `.env`, fill the provider settings locally, then run from `apps/backend` with `uv run --env-file ../../.env --locked python scripts/smoke_research_providers.py --live --output PATH_TO_PRIVATE_OUTPUT`; missing configuration or provider capabilities are reported as unsupported/incomplete, not as successful live evaluation. The configured variables are listed in `.env.example`. `.env` is ignored by Git; never commit or share its keys.
- Unsupported features and unreviewed cases are reported explicitly, never counted as passes. A partial suite can support an intermediate feature; it cannot satisfy complete release acceptance.
- Every workflow role exposes enough trace evidence to identify its inputs, permitted operations and result without default logging of full mailbox contents or credentials. Basic correlation begins with tools and the first workflow; Grafana dashboards build on it.
- Evaluation storage and delivery targets are isolated from operational data. Fixtures never create production approval authority. Reuse production contracts and execution paths; do not build a separate evaluation-only assistant.

Run the evaluator from `apps/backend`:

```sh
uv run --locked python -m evals self-check
uv run --locked python -m evals validate --dataset evals/datasets/briefing-v1
uv run --locked python -m evals replay --dataset evals/datasets/briefing-v1 --results PATH_TO_CAPTURED_RESULTS --output evals/results/run.json
uv run --locked python -m evals replay --dataset evals/datasets/briefing-v1 --results PATH_TO_CAPTURED_RESULTS --review PATH_TO_HUMAN_REVIEW --output evals/results/reviewed-run.json
uv run --locked python -m evals review --run evals/results/run.json --review PATH_TO_HUMAN_REVIEW
```

The evaluation CLI does not invoke providers. Replay consumes a captured output file; results contain hashes, identifiers and evaluations, not email bodies, source excerpts or claim text. Keep captured outputs and review inputs private. `evals/results/` is ignored by Git. Local email interpretation is available separately with `uv run --env-file ../../.env --locked python scripts/interpret_email.py interpret --input PATH_TO_NORMALIZED_INPUT --output PATH_TO_PRIVATE_OUTPUT`; an owner correction uses `correct-company --request PATH_TO_CORRECTION --output PATH_TO_PRIVATE_OUTPUT`. Both commands write mode-0600 outputs and require `EMAIL_SUPPORT_DATABASE_URL`; interpretation also needs gateway settings listed in `.env.example`. Interpretation output includes the normalized input, validated interpretation, identity snapshot and provider events, so it contains mailbox content and must remain private. Neither command adds an unauthenticated HTTP endpoint or submits the full workflow for live evaluation.
