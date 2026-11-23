---
paths:
  - "src/ragdesk/**/router.py"
  - "src/ragdesk/**/schemas.py"
---

> Verified: 2026-11-23 · Source: [standards](https://github.com/clipvoz/standards) and the official docs of each tool.

# FastAPI routes and schemas

- Modular monolith by feature: `src/ragdesk/<feature>/{models,schemas,router,service}.py`.
  `core/` holds shared infrastructure only. No repository layer, no DI container.
- A feature MUST NOT import another feature's router. It may import its models or service functions.
- MUST declare `response_model` (or a return annotation) and an explicit `status_code` on create
  and delete routes.
- MUST use separate Pydantic v2 schemas for input and output (`SourceCreate`, `SourceRead`).
  Never return ORM objects or ad hoc dicts.
- MUST use `Annotated` dependency aliases (`SessionDep`, `CurrentUser`) instead of repeating `Depends(...)`.
- MUST paginate every list (`limit` max 100, plus `offset`).
- Errors: raise `AppError` subclasses. 401 missing or invalid token, 403 no permission, 404 not found
  **or owned by another tenant**, 409 duplicate, 422 validation, 429 rate limited.
- MUST use `EventSourceResponse` for streaming and yield `ServerSentEvent` objects. Errors inside a
  stream are sent as an `error` event, never as a stack trace.
- MUST keep route functions short: load, check, call a service function, commit, return.
