# Customer examples: explicit and ambiguous requests

This candidate dataset builds on [v2](../customer-examples-v2/README.md), keeping its verified website inputs and the original profile-sharing emails. The existing Viettel EN/VI emails contain no explicit briefing request or business discussion, so their candidate expected relevance is `uncertain`. The new `viettel-briefing-en` and `viettel-briefing-vi` emails explicitly request a briefing for a discussion, so their expected relevance is `relevant`.

Both pairs mention an attachment whose contents were not supplied. No meeting date, attachment content, sender identity or company facts should be inferred. The emails are synthetic; all expectations remain candidates. [Website verification](../customer-examples-v2/website-verification.md) describes the sources for the URL updates.

The interpretation replay checks relevance only. A relevance pass is not a pass for the complete briefing: identity, attachment provenance, research, usefulness and workflow outcomes remain unsupported or require human review. See the rubric and the generated review report for each case's expectations and limitations.
