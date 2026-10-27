---
title: Use generic auth module names
date: 2026-10-27
summary: Renamed owner_auth modules and web feature paths to auth while preserving the single-owner login behavior and HTTP routes.
---

# Use generic auth module names

## What happened
The owner selected `auth` as the internal module and feature name after reviewing the `owner_auth` naming. Backend API, service, model and persistence modules, web feature/API modules, tests, and the codebase navigation page now use `auth`. OpenAPI and the generated SDK were regenerated.

## Decision
Keep the `auth` module name while retaining the current configured-owner behavior, `owner_sub` policy, owner session/storage semantics, and `/api/auth` paths. No multi-user capability or data model was added.

## Next steps
No follow-up is needed for this naming change. A future multi-user feature still needs explicit per-user identity, session, Google connection, and data-authorization design.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
