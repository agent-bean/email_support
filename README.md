# Email Support

A single-owner assistant for preparing sourced company briefings from business email and meeting context, with explicit human approval for delivery and knowledge reuse.

## Current status

The repository contains technical design documents and GitHub contribution configuration. The backend, web app, provider integrations, and deployment workflows are not implemented yet. There are no verified application setup commands to run.

## Planned capabilities

- Synchronize Gmail and read Google Calendar to identify relevant company and meeting context.
- Produce editable, source-cited Markdown briefings using bounded web research and reusable approved knowledge.
- Require approval of the exact briefing version, action, and recipients before sending email or saving knowledge.
- Retrieve approved knowledge through relationship queries and semantic search.
- Add PDF/Word export and attachment ingestion as separate increments.

The planned stack uses FastAPI, LangGraph, and a Python worker for the backend; React, TypeScript, and Vite for the web app; and PostgreSQL, Neo4j, and Qdrant for storage and retrieval.

## Documentation

Start with the [documentation index](docs/00-index.md) for product scope, architecture, code conventions, deployment direction, and the delivery roadmap.
