# Implementation roadmap

The [v1.0.0 milestone](https://github.com/agent-bean/email_support/milestone/1) and [release issue](https://github.com/agent-bean/email_support/issues/21) retain the complete briefing workflow. The [Project](https://github.com/orgs/agent-bean/projects/15) owns status and priority; Issues own scope and acceptance, and native dependencies own ordering. This sequence is delivery intent, not a date commitment.

## Delivery sequence

1. Establish evaluation cases and a runner alongside bounded research tools. Validate the actual model gateway and collect basic correlated tool evidence.
2. Produce a source-backed briefing from explicit normalized email/meeting inputs, resolve company ambiguity, persist the draft and pause. Evaluate its usefulness before requiring graph/vector context or full-mailbox synchronization.
3. Connect the owner and Google account; integrate durable work, Gmail/Calendar intake, review, approved knowledge and safe delivery into the same workflow.
4. Add Neo4j relationships and Qdrant semantic retrieval to the running workflow, proving useful reuse and excluding stale or wrong-company context.
5. Complete exports, attachments and dashboards, then run integrated evaluation and verify deployment/recovery. All remain release requirements.

A feature is incomplete until its relevant evaluation cases and failure behavior are exercised. Empty memory is valid for a new company; missing implementations are reported honestly and do not count as release-ready behavior.

## Requirements and issue ownership

| Requirement | Issues | Evidence needed |
| --- | --- | --- |
| Evaluation foundation and reviewed synthetic corpus | [#32](https://github.com/agent-bean/email_support/issues/32) | Runnable validation/scoring; source provenance and human-review status. |
| Tool registry, permissions, provider authentication, execution/retry, structured results and audit | [#9](https://github.com/agent-bean/email_support/issues/9) | Provider compatibility, rejected unauthorized calls and correlated outcomes. |
| Email Agent | [#8](https://github.com/agent-bean/email_support/issues/8), [#7](https://github.com/agent-bean/email_support/issues/7), [#15](https://github.com/agent-bean/email_support/issues/15) | Typed email interpretation, normalized intake and approved delivery with reconciliation. |
| Company Info Agent | [#8](https://github.com/agent-bean/email_support/issues/8), [#11](https://github.com/agent-bean/email_support/issues/11) | Correct identity, persistent correction and useful relationship context. |
| Web Research Agent and Report Generation Agent | [#13](https://github.com/agent-bean/email_support/issues/13), [#19](https://github.com/agent-bean/email_support/issues/19), [#20](https://github.com/agent-bean/email_support/issues/20) | Cited meeting briefing, traceable attachments and faithful exports. |
| Calendar Agent and scheduled preparation | [#4](https://github.com/agent-bean/email_support/issues/4), [#7](https://github.com/agent-bean/email_support/issues/7) | Durable scheduled/manual runs and upcoming/cancelled meeting handling. |
| Memory Agent | [#10](https://github.com/agent-bean/email_support/issues/10), [#11](https://github.com/agent-bean/email_support/issues/11), [#12](https://github.com/agent-bean/email_support/issues/12) | Approved knowledge/preferences persist; graph/vector context improves subsequent runs. |
| Human Approval Agent | [#13](https://github.com/agent-bean/email_support/issues/13), [#14](https://github.com/agent-bean/email_support/issues/14), [#15](https://github.com/agent-bean/email_support/issues/15) | Durable review pause, authenticated exact-version decision and guarded effects. |
| Owner access and Google consent | [#5](https://github.com/agent-bean/email_support/issues/5), [#6](https://github.com/agent-bean/email_support/issues/6) | Owner-only sessions and revocable provider access. |
| AgentOps | [#9](https://github.com/agent-bean/email_support/issues/9), [#13](https://github.com/agent-bean/email_support/issues/13), [#16](https://github.com/agent-bean/email_support/issues/16) | Early tool/run correlation, then usable Grafana metrics and traces. |
| Full workflow, security and quality acceptance | [#17](https://github.com/agent-bean/email_support/issues/17) | All seven roles exercised across applicable cases; supported claims and deterministic action gates. |
| Deployment and recovery | [#18](https://github.com/agent-bean/email_support/issues/18) | Owner journey over HTTPS, controlled release, restore, rebuild and rollback. |

The [architecture](02-system-architecture.md) owns role boundaries; the [evaluation design](09-evaluation.md) owns corpus and measurement rules. Preserve the accepted typed foundation and persistence unless a concrete use case demonstrates a necessary change.
