---
inclusion: fileMatch
fileMatchPattern: "tests/**/*.py"
---

> Verified: 2026-11-23 · Source: [standards](https://github.com/clipvoz/standards) and the official docs of each tool.

# Testing

- MUST test visible behaviour (the HTTP contract), not internals. Name tests by behaviour.
- Per feature, cover: happy path, validation error, another tenant's resource (404), and every state
  change with side effects (jobs enqueued, rows created).
- MUST run against real PostgreSQL with pgvector (testcontainers locally, a service container in CI).
  The schema is built by running Alembic migrations, so migrations are tested too.
- External providers (Claude, Gemini, Redis, the network) MUST be replaced by in-memory doubles:
  `FakeEmbedder`, a fake chat model, fakeredis, `respx`.
- MUST test the "run twice" case of every job, and failure paths (provider error, empty retrieval,
  refusal).
- MUST add a regression test for every bug and check that it fails without the fix.
- MUST NOT depend on the wall clock, the network or test order.
- Coverage gate: `fail_under = 85`.
