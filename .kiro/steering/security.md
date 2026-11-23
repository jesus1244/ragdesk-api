---
inclusion: fileMatch
fileMatchPattern: "{src/**/*.py,Dockerfile,docker-compose*.yml,.github/workflows/*.yml}"
---

> Verified: 2026-11-23 · Source: [standards](https://github.com/clipvoz/standards) and the official docs of each tool.

# Security

- NEVER commit secrets. `.env.example` lists every variable with placeholder values. Production MUST
  fail to start with a weak `JWT_SECRET` or a missing provider key.
- MUST derive identity and tenant from the verified token, never from the body, query or path.
- MUST return 404 (not 403) for a resource that belongs to another tenant.
- MUST return the same message for "unknown user" and "wrong password" and keep login timing constant.
- MUST rate-limit login, register, the public chat endpoint and uploads.
- The public chat endpoint is keyed by an unguessable bot public key and an allowed-origins list.
  It MUST NOT expose anything except answering.
- MUST NOT log passwords, tokens, `Authorization` headers, document text or full questions.
  Log ids, sizes and durations.
- MUST escape anything rendered as HTML. The widget MUST use `textContent`, never `innerHTML`.
- MUST disable interactive API docs when `ENVIRONMENT` is staging or production.
- Every outbound HTTP call MUST have a timeout and use HTTPS.
