# Technology decisions

> Verified: 2026-11-23 · Sources are linked in each section. Versions are the ones locked in `uv.lock` on that date.

RAGDesk answers questions about a customer's own documents (PDF, Markdown, web pages) through an embeddable chat
widget. Each answer cites the passages it used, and questions it could not answer are collected for the owner. This
document records what was chosen, what was rejected, and why.

## Summary

| Concern | Choice | Version |
|---|---|---|
| Language / tooling | Python 3.13, uv, ruff, mypy (strict), pytest | uv 0.13, ruff 0.17, mypy 2.4 |
| Web framework | FastAPI with native Server-Sent Events | 0.165 |
| Database | PostgreSQL 18 + pgvector (HNSW) + built-in full-text search | pgvector 0.8 |
| ORM / migrations | SQLAlchemy 2 (async, asyncpg) + Alembic | 2.1 / 1.20 |
| Embeddings | Google `gemini-embedding-2`, 768 dimensions | google-genai 3.6 |
| Answer generation | Claude (`claude-opus-5-5`) with `search_result` blocks and native citations | anthropic 2.12 |
| Background jobs | ARQ on Redis (persistent queue, deterministic job ids) | arq 0.28 |
| Text extraction | pypdf (PDF), trafilatura (web pages) | 7.1 / 2.3 |
| Auth | JWT access + rotating refresh tokens, Argon2id passwords | pyjwt, pwdlib |

## Vector store: pgvector inside PostgreSQL

**Chosen:** pgvector in the same PostgreSQL database as the rest of the data.

- One database to run, back up and secure. Chunks, sources, bots and conversations live in the same transaction, so
  deleting a source deletes its chunks (`ON DELETE CASCADE`) and nothing is left orphaned in a second system.
- Tenant filtering (`WHERE bot_id = …`) is ordinary SQL. Since pgvector 0.8, *iterative index scans*
  (`hnsw.iterative_scan`) keep scanning the HNSW index until enough rows pass the filter, which fixes the classic
  "filtered ANN returns too few rows" problem.
- HNSW over IVFFlat: no training step, good recall without tuning, works on an empty table.
- **Rejected:** Pinecone / Qdrant / Weaviate. Good products, but a second datastore is not justified at this scale
  (thousands to low millions of chunks per deployment) and complicates tenant deletes.

Source: [pgvector README](https://github.com/pgvector/pgvector) (HNSW, iterative index scans, hybrid search).

## Retrieval: hybrid search with Reciprocal Rank Fusion

**Chosen:** run two queries and fuse them with RRF (`score = Σ 1 / (60 + rank)`):

1. **Semantic:** cosine distance on the embedding (HNSW index), with a maximum-distance cut-off.
2. **Keyword:** PostgreSQL full-text search (`websearch_to_tsquery` + `ts_rank_cd`) on a generated `tsvector`
   column with a GIN index, using the `simple` configuration so it works the same for Spanish and English.

Why: embeddings miss exact tokens (product codes, error numbers, names); keyword search misses paraphrases. RRF needs
no score normalisation between the two, which is why the pgvector README suggests it. A cross-encoder re-ranker would
add quality but also a second model call per question; it is listed as a future improvement.

## Embeddings: `gemini-embedding-2` at 768 dimensions

- Generally available since April 2026, 100+ languages, 8,192-token input.
- Matryoshka output: 768 dimensions keep about the same retrieval quality as 3,072 at a quarter of the storage and
  index size. Truncated outputs of this model are already normalised, so cosine distance can be used directly.
- This model uses **text prefixes instead of `task_type`**: `task: search result | query: …` for questions and
  `title: … | text: …` for documents. Each text goes in its own `Content` object; a plain list of strings would be
  merged into a single embedding.
- The embedder sits behind a small `Embedder` protocol. Tests and offline development use a deterministic
  `FakeEmbedder` (hashed bag of words), so no test calls a paid API.

Source: [Gemini embeddings guide](https://aistudio.google.com/docs/embeddings),
[Gemini Embedding 2 model page](https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2).

## Generation: Claude with `search_result` blocks

**Chosen:** Claude Opus 5.5 (`claude-opus-5-5`) through the official `anthropic` SDK, streaming.

- Retrieved chunks are sent as `search_result` content blocks with `citations: {enabled: true}`. Claude then returns
  `search_result_location` citations that point to the exact chunk (`search_result_index`) it used. Citations come
  from the API, not from parsing `[1]` markers out of free text, so they cannot be invented.
- An answer with **no citations** is treated as *unanswered*: the question shows up in the owner's "unanswered" list.
  This is deterministic and needs no second model call.
- `effort: "low"` keeps chat latency down (this model cannot turn thinking off; effort is the control).
- Server-side refusal fallbacks (`fallbacks: "default"`) are enabled, and `stop_reason == "refusal"` is handled.
- Retrieved text is untrusted: the system prompt says documents are data, never instructions.
- API version `2026-10-21` (SDK 2.x): no `temperature`, and citations are never sent back inside user messages.
  Conversation history is replayed as plain text.

Source: [Search results](https://platform.claude.com/docs/en/build-with-claude/search-results),
Claude API skill reference for model ids, effort and fallbacks.

**Rejected:** LangChain / LlamaIndex. The pipeline is four small steps (extract, chunk, embed, retrieve) plus one API
call; a framework would hide the SQL and the prompt, which are exactly the parts worth reviewing.

## Streaming: FastAPI native SSE

FastAPI ≥ 0.135 ships `fastapi.sse.EventSourceResponse` and `ServerSentEvent`. It works with `POST` (the question is in
the body, not in the URL), sends a keep-alive comment every 15 s, and sets `Cache-Control: no-cache` and
`X-Accel-Buffering: no`. Events: `meta` (conversation and message ids), `delta` (text), `citation`, `done`, `error`.

Source: [FastAPI Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/).

**Rejected:** WebSockets. Chat is one request and one streamed answer; SSE is plain HTTP, passes proxies and CDNs, and
needs no connection state on the server.

## Ingestion as background jobs

Uploading returns `202` with the source in `pending`. An ARQ job (`ingest_source`, job id `ingest:<source_id>`, so
enqueuing twice is a no-op) extracts text, chunks it, embeds it in batches and swaps the chunks in one transaction.
The handler re-reads the source and is safe to run twice. `BackgroundTasks` is not used for this: it would be lost on
restart.

## Chunking

- Markdown and web pages are split by headings; each chunk keeps its heading path (`Guide › Install`) as the title.
- PDFs are split per page; the title is `Page N`, so a citation tells the reader where to look.
- Paragraphs are packed up to ~1,500 characters; longer paragraphs are split on sentence boundaries.

This structure-aware approach beats fixed-size windows on documentation, and the heading travels with the chunk into
both the embedding (`title: …`) and the citation.

## URL ingestion and SSRF

Fetching a user-supplied URL is a server-side request forgery risk. The fetcher resolves the host and rejects private,
loopback, link-local and reserved addresses, does not follow redirects to such addresses, limits the size and the
time, and only accepts `text/html` and `text/plain`.
