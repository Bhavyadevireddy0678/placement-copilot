# Placement Copilot: Interview Guide

## 90-Second Walkthrough

> Placement Copilot is a hybrid question-answering API. It routes structured questions to a SQL path over placement records and policy/interview questions to a retrieval-augmented generation path over company documents. For SQL, a language model proposes a query, SQLGlot parses it into an AST, and an allowlist restricts statements, tables, columns, functions, and result size; execution also uses a read-only database role and a statement timeout. For document questions, a sentence-transformer embeds the query, pgvector retrieves the nearest chunks using cosine distance and an HNSW index, and a language model answers from that context. Ingestion embeds chunks in batches, stages a replacement corpus, and commits the swap transactionally so a failed run does not erase the searchable corpus. The API uses pooled database connections and separates liveness from dependency readiness. The current version is a hardened demo baseline; before internet-facing use, I would add authentication, rate limiting, migrations, observability, pinned dependencies, and a measured evaluation set.

## Request Paths

1. The browser sends a JSON `POST /ask` request. The API rejects blank or over-2,000-character questions.
2. A small keyword router chooses SQL or RAG. This is intentionally simple but brittle; routing quality needs evaluation and should eventually be explicit or model-assisted with a confidence/fallback path.
3. SQL path: Groq proposes PostgreSQL SQL; the AST validator rejects writes, multiple statements, comments, unknown relations/columns/functions, subqueries, and invalid or excessive limits. The API executes only the normalized validated SQL with a read-only role and a database statement timeout.
4. RAG path: the selected embedding model maps the question to a 384-dimensional vector; PostgreSQL orders chunks by cosine distance and returns at most three. A distance threshold abstains when the nearest match is too far away. The model receives the retrieved text as untrusted reference material and returns an answer plus source names.
5. The response is JSON. The browser uses `textContent` for returned content and displays only validated SQL.

## Ingestion and Consistency

`ingest.py` reads sorted `.txt` files, splits them into 500-character chunks with 50-character overlap, embeds batches, and inserts into a temporary staging table. Once all batches succeed, it truncates and repopulates `chunks` in the same PostgreSQL transaction. PostgreSQL transactional DDL/DML means failure before commit rolls back the replacement. Existing readers continue seeing the old committed corpus until the swap commits. The HNSW index is maintained during the insert, trading some ingestion throughput for immediate indexed availability.

`load_data.py` writes placement rows to a uniquely named staging table and swaps them in a transaction without dropping the initialized table or its grants. The database initialization script provisions a writer account and a separate read-only account. Bootstrap scripts run only for a newly initialized PostgreSQL data directory; they are not a migration system.

## Likely Questions and Strong Answers

### Why hybrid SQL and RAG?

Use SQL for exact aggregation and filtering over structured facts; use retrieval for semantic questions over unstructured documents. Forcing both through one path hurts correctness: embeddings are poor substitutes for exact counts, and SQL cannot naturally answer narrative interview-process questions.

### Why not let the model execute SQL directly?

The model is an untrusted query proposer, not an authorization boundary. Parsing and validating an AST constrains the accepted language, a read-only DB role limits impact if validation misses something, and statement/row limits bound resource use. No single layer is sufficient by itself.

### Does SQLGlot validation prove the query is safe?

No. It proves only that the parsed query conforms to this validator's current allowlist and structural checks. Database privileges, timeouts, row limits, dependency updates, and adversarial tests remain necessary. The validator must evolve when the schema or allowed query surface changes.

### Why use a read-only database role if the AST is validated?

Defense in depth. Parser bugs, dialect differences, or an overlooked function should not give the serving process write privileges. The writer account is reserved for ingestion and data loading.

### What does cosine distance mean here?

`embedding <=> query_embedding` is pgvector's cosine-distance operator; lower values are more similar, with zero meaning identical direction. The `0.7` cutoff is a heuristic, not a probability or calibrated confidence. It must be tuned on labeled in-domain and out-of-domain questions; measure false-answer and abstention rates.

### Why HNSW, and what is the trade-off?

HNSW is an approximate nearest-neighbor index that reduces vector-search work as the corpus grows. It uses extra memory and index-build/write time and can trade recall for latency. Compare exact search and HNSW with representative query vectors; track recall@k and p95/p99 latency. For tiny corpora, a sequential scan can be faster.

### Why 500 characters and 50 characters of overlap?

They are initial heuristics, not universal constants. Overlap preserves facts crossing chunk boundaries; too much overlap increases storage, duplicated context, and retrieval noise. Tune chunk size and overlap against retrieval recall, answer faithfulness, prompt-token budget, and latency. Character-based splitting is not token-aware, which is a known limitation.

### Why batch embeddings?

Batching amortizes Python/model-call overhead and improves accelerator utilization. Batch size is bounded because embedding batches consume memory; benchmark throughput and peak memory on the target hardware instead of maximizing batch size blindly.

### What happens if an ingestion run fails halfway through?

The new rows are staged in a transaction and the live corpus is changed only at the end. A failed transaction rolls back, leaving the previous committed chunks visible. The current approach is a full-corpus replacement; incremental content hashes and versioned corpora are a future improvement for larger datasets.

### Why connection pooling, and how do you size it?

Creating a TCP connection and authenticating for every retrieval adds latency and load. SQLAlchemy pools reuse connections and `pool_pre_ping` detects stale ones. Pool limits are per engine and per worker process; the API currently has separate RAG and SQL engines. Budget approximately `workers × (pool_size + max_overflow)` for each engine, plus ingestion, migrations, monitoring, and administrative connections, then keep below PostgreSQL's available connection budget. Pool size is not a throughput knob by itself.

### What is the likely bottleneck?

Measure before guessing. Likely contributors are external LLM latency, CPU/GPU embedding throughput, pool wait time, database query time, and HNSW recall/latency. Add spans/timers around routing, embedding, DB retrieval, and LLM calls; report p50/p95/p99, error rate, pool checkout wait, token counts, and cost. There is no honest claim of “no bottlenecks”; the goal is bounded load, observable saturation, and a scaling plan.

### Why are endpoint functions synchronous?

FastAPI runs normal `def` endpoints in its worker threadpool, so blocking SQL, model, and SDK calls do not block the event loop. They still consume thread slots. If concurrency grows, move network calls to an async SDK and isolate CPU embedding work in a bounded worker pool; do not simply add more threads without measuring memory and model throughput.

### Why can adding Uvicorn workers make performance worse?

Each process loads its own embedding model and owns its own connection pools. More workers multiply RAM/VRAM usage and potential database connections. Choose workers using measured memory and concurrency limits, or move embeddings to a dedicated model service.

### How do you handle prompt injection in documents?

The prompt labels retrieved text as untrusted and instructs the model to ignore embedded instructions, but prompt text is not a security guarantee. Reduce impact with source governance, retrieval filtering, no tools/credentials available to the answer model, output checks, and adversarial evaluation. A RAG model should not be treated as an authorization system.

### Why not return retrieved text to the browser?

The API uses the text internally to ground the answer but returns source names, not entire document excerpts. This reduces unnecessary disclosure and payload size. In a real deployment, source-level access controls and citation spans would be needed.

### What if the SQL and RAG paths disagree?

They represent different data sources and update cycles. Define source-of-truth ownership, freshness SLAs, timestamps/version IDs, and explicit routing rules. Add consistency checks or avoid answering cross-source questions until a reliable join/lineage strategy exists.

### How would you evaluate answer quality?

Build a versioned set of realistic questions with expected SQL results, relevant source chunks, acceptable abstentions, and known unanswerable cases. Measure SQL exact-result accuracy, retrieval Recall@k/MRR, groundedness/faithfulness, citation correctness, abstention precision/recall, latency, and cost. Use human review for a sample; an LLM judge alone is not ground truth.

### What tests are missing?

The repository currently has focused unit tests for the SQL validator. Add API tests with mocked LLM/database dependencies, PostgreSQL integration tests for grants/indexes/transactions, ingestion rollback tests, request validation tests, and an end-to-end evaluation dataset. Run them in CI against the pinned dependency set.

### Is this production-ready today?

Not for public exposure. It has meaningful safeguards, but still lacks authentication, rate limiting, formal migrations, dependency lock/pinning, observability/alerting, backups/restore verification, data-retention controls, and evaluation evidence. State those gaps plainly and describe the rollout plan.

## Traps to Avoid

- Do not describe the distance cutoff as a confidence score.
- Do not claim AST validation alone prevents SQL attacks.
- Do not claim `LIMIT 100` bounds query cost; an aggregate or sort can still scan substantial data. Keep the DB timeout and consider query-plan/resource controls.
- Do not assume one pool setting applies to all workers or both engines.
- Do not assume HNSW always beats exact search or that top-3 is always enough.
- Do not call the keyword router an intent classifier with measured accuracy.
- Do not claim prompt instructions eliminate prompt injection.
- Do not call a bootstrap SQL file a migration framework.
- Do not state that the system has no bottlenecks. Explain how you would find and bound them.

## Before a Real Deployment

- Add authentication/authorization, per-user rate limits, request concurrency limits, and abuse protection.
- Pin and audit direct/transitive dependencies; define a supported Python version and build a reproducible image.
- Add versioned schema migrations and a controlled secret manager; test upgrade and rollback paths.
- Add structured request IDs, redacted logs, traces, metrics, and alerts for latency, errors, database pools, and model-provider limits.
- Add retrieval/answer/SQL evaluation data and CI integration tests, including adversarial SQL and prompt-injection cases.
- Decide PII access, retention, deletion, backup encryption, and restore procedures before using real student records.
- Load test with realistic corpus size and concurrency; tune model placement, batch size, pools, HNSW parameters, worker count, and provider limits from results.
