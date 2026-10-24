# Product boundary

## Outcome

An owner receives a sourced company briefing from incoming business email or an upcoming meeting, reviews its content, and explicitly authorizes delivery to selected recipients and/or persistence as reusable knowledge.

The v1.0.0 release serves one owner through Gmail and Google Calendar. Markdown is the first briefing format; PDF/Word export and attachment ingestion are separate increments within the same release.

## Business flow

1. A configurable daily schedule or an explicit owner request starts synchronization. Upcoming calendar meetings can also identify companies requiring a briefing.
2. Email classification excludes irrelevant messages and associates relevant messages with a contact and company. An ambiguous company identity requires owner clarification rather than silently merging unrelated companies.
3. The workflow retrieves relevant approved knowledge, relationship context, and calendar context. It reuses sufficiently fresh evidence before performing bounded web research.
4. The system prepares an editable Markdown briefing containing company overview, products, recent developments, contacts, meeting context, source references, and unresolved questions where relevant.
5. The owner reviews a particular briefing version and explicitly selects a delivery action, recipients, and/or knowledge-save action.
6. Authorized actions run with durable records. The owner can inspect their outcome and recover from failure without accidentally sending the same briefing twice.

Delivery means forwarding a briefing to owner-selected recipients. It does not mean automatically replying to the original sender.

## Terminology

| Term | Meaning |
| --- | --- |
| Evidence | Retrieved source material with provenance and retrieval time; it is not automatically approved knowledge. |
| Briefing | A versioned synthesis prepared for human review. |
| Approval | An owner decision bound to an exact content version, action, and recipients. |
| Approved knowledge | Owner-approved reusable facts or summaries linked to their source evidence. |
| Run state | Intermediate execution data used to resume one workflow. |
| Memory | Persistent approved knowledge and explicit preferences available across runs. |

## Constraints and exclusions

- Filtering and reuse must prevent one fresh research run per email by default.
- Research requires bounded calls, time, concurrency, and cost. A stopped or incomplete run must expose its actual outcome.
- Sending email and promoting research to approved knowledge require owner authorization. A generated claim or instruction in retrieved content cannot grant that authorization.
- Google Calendar access is read-only. Scheduling or modifying meetings is outside the first release.
- Attachment contents are untrusted evidence and cannot grant authorization or become approved knowledge without owner approval.
- Multi-user tenancy, autonomous customer replies, arbitrary code execution, and general-purpose agent hosting are outside scope.

## Acceptance conditions

- Relevant email and upcoming meeting context can lead to a cited briefing; repeat synchronization does not duplicate input records or active work.
- The owner can correct company identity, edit a briefing, inspect evidence, approve delivery, and save selected knowledge.
- Editing approved content or recipients invalidates the prior approval. Direct API calls cannot bypass the same rule.
- Restarting execution preserves review state and completed actions. An uncertain delivery outcome is visibly distinct from a confirmed failure.
- Approved knowledge is reused with provenance; invalidated knowledge is excluded from subsequent retrieval.
- Retrieval quality, factual support, delivery authorization, latency, and cost can be evaluated separately.
