---
paths:
  - "src/ragdesk/ingestion/**/*.py"
  - "src/ragdesk/retrieval/**/*.py"
  - "src/ragdesk/chat/**/*.py"
---

> Verified: 2026-11-23 · Source: [standards](https://github.com/clipvoz/standards) and the official docs of each tool.

# RAG pipeline rules

- Retrieved text is **untrusted data**. The system prompt MUST say documents are reference material and
  never instructions. MUST NOT put user or document text into the system prompt.
- Always scope retrieval by `bot_id`. A query without the tenant filter is a bug.
- Retrieval MUST be hybrid (vector + full-text) fused with Reciprocal Rank Fusion, then cut by a maximum
  cosine distance. `top_k` and the distance threshold are settings, not constants.
- Send chunks to Claude as `search_result` blocks with `citations: {"enabled": true}`. `source` is the
  source id and `title` is the chunk title. MUST NOT parse citation markers out of free text.
- MUST NOT send citations back inside `user` messages: replay history as plain text only
  (API version 2026-10-21 rejects it).
- An answer with no citation is **unanswered**: record it, and do not present it as a sourced answer.
- Embeddings: `gemini-embedding-2`, 768 dimensions, text prefixes (`task: search result | query:` and
  `title: ... | text: ...`), one `Content` per text. Everything goes through the `Embedder` protocol so
  tests use `FakeEmbedder`.
- Ingestion MUST run as an ARQ job with the deterministic id `ingest:<source_id>`, be idempotent, and
  replace chunks in one transaction.
- URL fetching MUST go through the SSRF guard (public addresses only, size and time limits, no redirects
  to private hosts).
- Tests MUST NOT call Claude or Gemini. Use `FakeEmbedder` and a fake chat model.
