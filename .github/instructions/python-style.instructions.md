---
applyTo: "src/**/*.py,tests/**/*.py"
---

> Verified: 2026-11-23 · Source: [standards](https://github.com/clipvoz/standards) and the official docs of each tool.

# Python style and tooling

- MUST use Python 3.13 (`.python-version`), uv with a committed `uv.lock`, ruff and mypy strict.
  Run `uv run ruff check . && uv run ruff format --check . && uv run mypy` before every commit.
- MUST type every function signature. Use `X | None`, never `Optional[X]`.
  MUST NOT use `Any` without a one-line comment explaining why.
- MUST use timezone-aware UTC datetimes (`utcnow()` from `ragdesk.core.database`).
  Pass `now` into time-dependent logic so tests can control it.
- MUST NOT create `utils`, `helpers` or `common` modules. Put code in the feature that owns it.
- MUST be async end to end. NO blocking I/O (`requests`, `time.sleep`, sync DB drivers) in request or
  worker code. Use `httpx.AsyncClient` with an explicit timeout.
- MUST read configuration only through `ragdesk.core.config.Settings` and document every new variable
  in `.env.example`.
- SHOULD keep functions short and name tests after behaviour.
