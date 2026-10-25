---
title: "Phase 1: Typed backend and offline contract"
status: done
phase: 1
dependencies: []
priority: P1
effort: 4h
---

# Phase 1: Typed backend and offline contract

## Outcome, context and dependencies

Create a real credential-free API and deterministic offline OpenAPI export. No preceding implementation dependency. Rough estimate: 4 hours, not a deadline. One executor owns all files sequentially; phase 2 waits for this gate.

Baseline `5f81f43622d36cf574246a4b7d3a57c190a0542b` has no application or verified commands ([README, line 7](../../README.md)). Planned paths follow [navigation, line 7](../../docs/03-codebase-summary.md), [composition, line 9](../../docs/03-codebase-summary.md), and [models, line 11](../../docs/03-codebase-summary.md). Strict Python, Pydantic and closed enums follow [standards, line 7](../../docs/04-code-standards.md), [models, line 10](../../docs/04-code-standards.md), and [StrEnum, line 18](../../docs/04-code-standards.md). Read [backend research](../reports/researcher-261024-1820-backend-ci-toolchain.md) with [controller corrections](../reports/scout-261024-1827-issue-2-foundation.md): Python 3.13 and `apps/backend/src/email_support/` supersede advisory alternatives.

## Proposed contracts and data flow

All symbols below are proposed, not existing. `main.py` constructs FastAPI and includes `api/health.py`. `GET /api/health`, explicit operation ID `get_health`, returns HTTP 200 and `{"status":"ok"}` through `HealthResponse`. Its required `status` uses `HealthStatus`, a `StrEnum` with `OK = "ok"`. Both belong in `models/health.py`; this is the only application model and enum. No service wrapper is needed.

Offline `scripts/export-openapi.py` imports the same application, calls its OpenAPI method without server startup, serializes stable sorted JSON with a final newline, and writes `apps/backend/openapi.json`. Resolve destination from the script path. Keep framework-shaped JSON confined to the exporter; application payloads use named validated models. No `Any`, blind casts, broad ignores, credentials, dotenv, DB or network service are needed for import/export/health.

## File inventory and ownership

All entries are proposed creates; no deletes. Later phases extend root wrappers only after sequential ownership handoff.

| Repository-relative path | Responsibility |
| --- | --- |
| `apps/backend/pyproject.toml` | Package metadata, Python 3.13 constraint, dependencies, Ruff/strict mypy/pytest configuration. |
| `apps/backend/uv.lock` | Tested locked dependencies. |
| `apps/backend/.python-version` | Explicit tested Python 3.13 patch; never host default 3.15. |
| `apps/backend/src/email_support/__init__.py` | Package marker. |
| `apps/backend/src/email_support/api/__init__.py` | Route package marker. |
| `apps/backend/src/email_support/models/__init__.py` | Model package marker. |
| `apps/backend/src/email_support/models/health.py` | Single response model and enum. |
| `apps/backend/src/email_support/api/health.py` | Typed liveness route. |
| `apps/backend/src/email_support/main.py` | Application composition. |
| `apps/backend/scripts/export-openapi.py` | Deterministic offline export. |
| `apps/backend/tests/integration/test_health_endpoint.py` | Actual HTTP endpoint test. |
| `apps/backend/tests/unit/test_health_model.py` | Model rejection tests. |
| `apps/backend/tests/contracts/test_openapi.py` | Operation/schema/export stability tests. |
| `apps/backend/openapi.json` | Committed generated source. |
| `.gitignore` | Environment/cache/test/build exclusions; keep contract artifacts tracked. |
| `Makefile` | Initial backend setup/check/generate/dev-api wrappers; phases 2/3 extend. |

More than eight files are necessary for real manifests, locks, import packages, contracts and tests. No dummy future folders/services are authorized.

## Tests Before: red

1. Evaluate stable FastAPI/Pydantic, uv, Ruff, mypy, pytest and Starlette TestClient dependency compatibility. Pin tested Python 3.13 patch and uv version; lock dependencies. The planning-time Python 3.13.16 candidate is superseded by implementation validation of Python 3.13.17. Install a normal package, not an ad hoc `PYTHONPATH`.
2. Write tests before the route: actual in-process HTTP receives exact status/body; the model rejects missing/unknown status. Keep the HTTP integration test under `tests/integration/` and model validation under `tests/unit/`. Observe a meaningful behavior failure after the runner works.
3. Write the OpenAPI contract test under `tests/contracts/`: exact path/method/operation ID, required response field and closed enum; repeated offline subprocess exports produce identical bytes without server or credentials.

## Implement: green

1. Add only the model/enum/route/app above, with explicit annotations. Enable strict mypy over owned source/scripts/tests and Ruff lint/format.
2. Implement exporter and commit snapshot. No timestamps or host-dependent output.
3. Add backend wrappers; manifest configuration remains authoritative. Bind `dev-api` to `127.0.0.1:8000`. Phase 3 completes root command surface.

## Refactor and Tests After

Remove redundant helpers without weakening HTTP/model/export tests. Re-run every backend gate; record actual red/green evidence and chosen versions. Do not add duplicate model layers or broad framework exceptions.

## Test matrix and proposed verification

Commands are planned and unavailable at baseline. Run from `apps/backend/` after implementation:

```sh
uv lock --check
uv sync --locked
uv run --locked pytest -q tests
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy --strict src scripts tests
uv run --locked python scripts/export-openapi.py
```

| Layer | Test | Pass condition |
| --- | --- | --- |
| Model | Missing/unknown status | Rejected, never defaulted. |
| HTTP integration | Actual app health | Exact response without external dependencies. |
| OpenAPI integration | Actual app schema | Stable operation and required enum response. |
| Offline export | Two exports | Identical bytes; committed snapshot matches app. |
| Static quality | Ruff and strict mypy | Owned source/scripts/tests pass without broad suppression. |

## Risk, security, compatibility and rollback

- Medium likelihood × high impact: dependency/runtime incompatibility. Evaluate early, explicitly pin Python/uv, lock install and pass all gates; escalate proven conflicts instead of changing architecture silently.
- Medium × medium: unstable schema churn. Fix operation ID and sort export; phase 2 proves whole-chain stability.
- Local liveness exposes no owner data, secrets or mutations. Bind loopback; no broad CORS or auth/provider scaffold.
- No existing application consumers or persisted data require migration. Later contract changes must update model, snapshot, generated client and tests together.
- Roll back phase-owned changes before downstream work starts; revert dependent phase 2 changes together if needed. No data migration exists.

## Exit checklist

- [x] Observe meaningful red then green tests.
- [x] Pass locked install, backend tests, lint/format and strict typing.
- [x] Commit stable snapshot; record actual evidence and versions.
- [x] Release ownership to [phase 2](phase-02-generated-web-contract.md).

## Implementation evidence

- Runtime: Python 3.13.17, uv 0.13.5; locked packages include FastAPI 0.162.0, Pydantic 2.14.1, Uvicorn 0.54.0, httpx2 2.16.0, pytest 9.1.1, Ruff 0.17.2, and mypy 1.20.2.
- Test-first red: both test modules failed collection before the application modules existed. The first OpenAPI assertion also exposed that FastAPI represents the status field as a `$ref`; the contract test now verifies that reference and the separate closed enum schema.
- Compatibility adjustment: current Starlette deprecates the older `httpx` test client in favor of `httpx2`; the locked test dependencies use `httpx2` and the suite runs without deprecation warnings.
- Green: `uv lock --check`, locked sync, five focused tests, Ruff lint/format, strict mypy, and two byte-identical offline OpenAPI exports passed. `apps/backend/openapi.json` is generated from the actual app and ends with a newline.
- Delivery: commit `b301203` (`feat: add typed health API foundation`) was authored and committed by `javis-27`; the tech-lead review was performed as `biendo27` before commit.
