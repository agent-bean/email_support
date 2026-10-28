---
title: Refresh customer evaluation websites
date: 2026-10-27
summary: Verified six company websites and versioned two updated URLs without changing historical cases.
---

# Refresh customer evaluation websites

## What happened
Verified the six screenshot-derived company URLs against official company pages and a government listing. The original Viettel hostname failed certificate verification, the supplied Bosch URL returned 404, and Vinamilk returned 403 to automated access.

## Decision
Created customer-examples-v2 with official Viettel Solutions and Bosch software-company websites, preserving v1 and its historical hashes. Documented sources and access limits; URLs in synthetic emails remain unverified sender claims.

## Verification
The new bilingual corpus validated, all 12 live interpretations completed, and 10 candidate relevance labels matched. The backend check passed 221 tests, Ruff, formatting and strict mypy. Independent review found no actionable issues.

## Next steps
Owner review of candidate expectations, identity evaluation and the missing Viettel attachment remain pending.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
