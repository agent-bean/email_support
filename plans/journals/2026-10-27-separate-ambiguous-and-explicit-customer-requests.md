---
title: Separate ambiguous and explicit customer requests
date: 2026-10-27
summary: Version bilingual Viettel cases and report relevance checks with evidence.
---

# Separate ambiguous and explicit customer requests

## What happened

The profile-sharing Viettel examples lack an explicit request; new bilingual examples explicitly request a briefing. The v3 candidate dataset keeps the previous datasets intact and records the different relevance expectations.

The initial live evaluation returned malformed evidence for the English briefing because the model supplied incorrect offsets for a repeated company name. The prompt now requests an exact quote unique in its field while retaining strict evidence validation.

## Validation

A live v7 run produced 14 valid responses, with 13 relevance matches. All four Viettel cases matched; the English Shopee example remained uncertain against its candidate relevant label. These relevance checks do not certify unsupported workflow or briefing quality. Backend tests, lint, formatting and typecheck passed.

## Next steps

Owner review is required for candidate expectations and semantic quality; missing attachment contents and unsupported checks remain explicit.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
