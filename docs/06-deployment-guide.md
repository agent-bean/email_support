# Deployment direction

## Target environment

Deploy the web app, FastAPI API, Python worker, PostgreSQL, Neo4j, and Qdrant through Docker Compose on a VPS, with Cloudflare as the public edge. Keep API and web under one public origin where practical.

Databases, metrics, and trace storage remain private to the deployment network. The browser receives no provider credentials. Google OAuth needs a stable verified HTTPS callback; public exposure must follow owner-access and session protection.

Set and measure resource limits, database caches, worker concurrency, research budgets, trace retention, and disk growth against actual workloads.

## Operational prerequisites

- Use explicit configuration validation and separate production/test credentials and data.
- Provide readiness checks for required dependencies and a minimal liveness check independent of external LLM calls.
- Apply versioned PostgreSQL migrations before serving incompatible code. Keep application/checkpoint compatibility in mind when changing persisted workflow state.
- Give the worker graceful shutdown and bounded lease handling; terminating a container must not turn an uncertain email send into an automatic retry.
- Establish encrypted backup storage outside the VPS and perform a PostgreSQL restore exercise. Neo4j/Qdrant projections need rebuild procedures backed by canonical records.
- Supply OpenTelemetry, Prometheus, Tempo, and Grafana with bounded retention and resource use. Verify dashboards and trace correlation under real execution before treating instrumentation as complete.
- Verify rollback with both database compatibility and in-flight jobs/approvals. Reverting a container cannot undo a sent email.
