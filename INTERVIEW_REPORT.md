# Placement Copilot Interview Hardening Report

Branch: `interview-hardening`

This report separates source changes, live measurements, retrieval-only measurements, and unverified claims. Baseline and latest-full-live figures use one local 35-question run each; provider output is nondeterministic and these small-sample results are not a statistical guarantee.

## 1. Per-Step Summary and Commits

### Step 0: Live Baseline
Commit: `40ca233a` (`0: capture live baseline and phase A evaluation`). Files include `eval_set.json`, `eval.py`, `results/eval_results_baseline.json`, `results/eval_results_baseline_live.json`, `ingest.py`, `scripts/groq_test.py`, `test_eval.py`, and `test_sql_security.py`.

What: Added the 35-case ground-truth set, offline/live evaluator, saved baseline reports, made the secret-dependent Groq smoke script import-safe, and fixed the psycopg2 URL scheme discovered while loading data. Why: This established a factual baseline and made default pytest collection possible before later behavior changes. Tradeoff: Live evaluation consumed provider tokens and was vulnerable to model variance; the first commit also captured the pre-existing uncommitted project files because they had no prior Git commit.

### Step 1: SQL and API Security
Commit: `1d80fce2` (`1: secure SQL execution and ask endpoint`). Files include `api_security.py`, `scripts/ai_query.py`, `ask_api.py`, `sql_security.py`, `static/app.js`, `static/index.html`, `static/styles.css`, and the API/security tests.

What: Added constant-time API-key comparison, a per-process sliding-window IP limiter, PII column denial including `SELECT *`, and routed the auxiliary SQL executor through validation and the read-only URL. Why: The API accepts natural language and SQL is model-generated, while placement rows include identifiers. Tradeoff: The browser needs a shared secret entered by the operator, and the in-memory limiter does not coordinate across workers or replicas.

### Step 2a: Corpus Cleanup and Idempotent Ingestion
Commit: `7c40ac65` (`2a: clean document corpus and measure reingestion`). Files: `documents/amazon.txt`, `results/eval_results_after_corpus_cleanup.json`; idempotent staging/replacement is implemented in `ingest.py` from step 0.

What: Removed the literal `cat documents/amazon.txt` artifact and scanned all 12 company files for junk markers. Why: Ingestion indexes file contents literally, so shell residue would become retrieval context. Tradeoff: Ingestion remains a full-corpus replacement rather than an incremental content-hash pipeline; two runs both produced 22 chunks with identical per-source counts.

### Step 2b: Hybrid Router
Commit: `5f9344f7` (`2b: add measured LLM fallback intent routing`). Files: `ask_api.py`, `eval.py`, `test_router.py`, `results/eval_results_after_router.json`.

What: Kept keyword matches as the fast path, sent unmatched/conflicting cases to a strict `sql`/`rag` classifier with a five-second timeout, added `route_reason`, and defaulted classifier failures to RAG. Why: Keyword-only routing missed paraphrases and typos. Tradeoff: The fallback adds provider latency/token use and remained imperfect: the only verified correct flip among the designated hard SQL cases was `hard_02`; `hard_01` and typo case `hard_03` still routed to RAG, and mixed case `hard_07` chose SQL.

### Step 2c: SQL Prompt and Retry
Commit: `71b56543` (`2c: add few-shot SQL generation and one validator retry`). Files: `sql_generation.py`, `ask_api.py`, `test_sql_generation.py`, `results/eval_results_after_sql_prompt.json`.

What: Added six schema-grounded SQL examples and exactly one validator-feedback retry for rejected SQL. Why: Examples demonstrate the supported query shape and rejection feedback lets the model correct parse/allowlist errors once. Tradeoff: More prompt tokens and an extra possible provider call; SQL accuracy rose from 10/15 in the preceding live run to 12/15 in this run, but this was a small, nondeterministic sample and not proof of causal improvement.

### Step 2d: Hybrid Retrieval Benchmark
Commit: `b5b7cc89` (`2d: benchmark hybrid retrieval and retain vector winner`). Files: `retrieval.py`, `retrieval_sweep.py`, `db/init.sql`, `ingest.py`, `ask_api.py`, `test_retrieval.py`, `results/eval_results_retrieval_sweep.json`, `results/eval_results_after_retrieval.json`.

What: Added a stored English `tsvector`, GIN index, optional full-text/vector reciprocal-rank fusion, and PostgreSQL-backed sweep over top-k and thresholds. Why: This provides a measured alternative to vector-only retrieval without silently replacing the baseline. Tradeoff: Hybrid mode has extra index/write/query work; on 22 chunks it matched vector-only at 17/17 source recall, 17/17 fact coverage, and 3/3 abstention accuracy, while measured p50/p95 was 2.015/4.258 ms versus 0.929/2.581 ms for vector-only. The selected default remains vector-only, top-k 3, threshold 0.7; no cross-encoder was added because the sweep showed no factual-recall headroom.

### Step 3a: RAG Failure Containment
Commit: `4fb239e8` (`3a: contain RAG failures and bound retrieval queries`). Files: `ask_api.py`, `test_rag_reliability.py`, `results/eval_results_after_rag_reliability.json`.

What: Wrapped RAG embedding/retrieval/provider work, logged server-side failures, returned a safe degraded-compatible JSON response, and set PostgreSQL statement timeout for retrieval. Why: A DB/provider exception previously escaped the RAG route and could become HTTP 500. Tradeoff: Users receive a generic retry message rather than the underlying cause; the exact cause remains in server logs.

### Step 3b: Request Telemetry
Commit: `109fab1c` (`3b: add request IDs and stage timing telemetry`). Files: `ask_api.py`, `eval.py`, `test_observability.py`, `test_rag_reliability.py`, `results/eval_results_after_observability.json`.

What: Added request IDs, a compact structured JSON HTTP log, and `timings_ms` fields for routing, embedding, retrieval, SQL generation, SQL execution, LLM, and total. Why: The previous live measurements could not attribute latency to internal stages. Tradeoff: Timing and logging add small per-request overhead and response metadata; one full live snapshot measured total p50/p95 820/5,682 ms, with LLM-stage p50/p95 919/7,195 ms.

### Step 3c: Bounded Caches
Commit: `691e74d0` (`3c: cache repeated embeddings and SQL results`). Files: `caches.py`, `ask_api.py`, `eval.py`, `.env.example`, `test_caches.py`, `test_eval.py`, `results/eval_results_cache_probe.json`.

What: Added an exact-question embedding LRU and a bounded TTL cache for validated SQL results, with configurable sizes and hit flags. Why: Repeated questions can avoid embedding and repeated execution of identical validated SQL. Tradeoff: Results can be stale for up to the TTL, cache state is per process, and LLM generation is not cached; the 2-request SQL probe showed execution 14.494 to 0.005 ms but total 444.243 to 619.552 ms because SQL-generation latency varied.

### Step 3d: Provider Resilience
Commit: `2dc1dac5` (`3d: add provider retries and circuit breaker`). Files: `resilience.py`, `ask_api.py`, `sql_generation.py`, `.env.example`, `test_resilience.py`, `results/eval_results_after_resilience_offline.json`.

What: Added transient-only retries with exponential backoff and jitter, a shared circuit breaker with half-open recovery, and explicit degraded responses for SQL/RAG provider exhaustion. Why: Logs during the live work recorded Groq HTTP 429 token-per-minute failures and provider timeouts. Tradeoff: Retrying adds latency and consumes provider quota; the classifier still defaults to RAG on provider failure as required. Provider failure behavior was deterministically tested; post-change full live answer accuracy was not measured due provider TPM limits.

### Step 3e: Health and Sync Handler Semantics
Commit: `9bb12071` (`3e: make health checks dependency aware`). Files: `ask_api.py`, `test_health_async.py`, `results/eval_results_after_health_offline.json`.

What: `/health` now verifies model initialization and connectivity to both DB engines; `/ask` and `/health` are tested as synchronous FastAPI handlers. Why: A process-alive response alone does not establish that the API can serve model/DB work, and blocking operations must not execute directly as async endpoint bodies. Tradeoff: Health probes now perform two DB pings; measured p95 rose from 6.536/4.190/7.364 ms to 26.237/25.298/41.191 ms at 1/10/25 clients.

### Step 3f: Concurrent Load Measurement
Commit: `c5213226` (`3f: add concurrent load and health benchmarks`). Files: `loadtest.py`, `test_loadtest.py`, four `results/loadtest_results_*.json` artifacts, and `results/eval_results_after_loadtest_offline.json`.

What: Added a concurrent HTTP runner reporting throughput, p50/p95, status counts, and degraded responses at 1, 10, and 25 clients. Why: The API’s synchronous model/DB calls and local caches needed measured concurrency behavior. Tradeoff: To avoid Groq TPM throttling, `/ask` load tests used a zero distance threshold so they measured routing/embedding/retrieval and deliberately skipped answer generation; they do not represent full-answer production throughput.

### Step 4a: Placement Indexes
Commit: `7c11e09c` (`4a: index placement company and branch filters`). Files: `db/init.sql`, `ingest.py`, `results/eval_results_indexes.json`.

What: Added B-tree indexes on `placements(company)` and `placements(branch)` to bootstrap and existing-database ingestion paths. Why: These columns are used in common exact filters. Tradeoff: The 600-row table is too small to prove general benefit; Google count switched from seq scan at 0.076 ms to bitmap index/heap scan at 0.042 ms, while branch count remained seq scan at 0.054 ms.

### Step 4b: API Container
Commit: `ffb82e95` (`4b: containerize API and add health checks`). Files: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`.

What: Added a Python API image, Compose API service, healthy-DB dependency, loopback port mapping, and HTTP container healthcheck. Why: It provides a single Compose command for database and API startup without copying `.env`, local venv, docs, or CSV into the API image. Tradeoff: The image includes Sentence-Transformers/PyTorch and downloads the embedding model at startup; the build could not be completed because Docker Desktop’s daemon disconnected mid-build, so image execution is unverified.

### Step 4c: CI
Commit: `c021c900` (`4c: add CI tests and offline evaluation`). Files: `.github/workflows/ci.yml`, `eval.py`, `test_eval_router_parity.py`, `results/eval_results_after_ci_offline.json`.

What: Added GitHub Actions for tests and offline evaluation, and decoupled offline router scoring from DB-dependent API module initialization. Why: CI should validate code and fixtures without Groq credentials or a PostgreSQL service. Tradeoff: The evaluator contains a keyword-router copy; a parity test compares it with `ask_api.classify_intent()` over the full fixture and additional probes.

### Step 4d: Company Summary UI
Commit: `ae9a4014` (`4d: fetch and label sample company summaries`). Files: `ask_api.py`, `static/index.html`, `static/app.js`, `static/styles.css`, `test_company_summaries.py`, `results/eval_results_company_summaries.json`.

What: Replaced static company counts/package values with `/company-summaries`, which aggregates read-only placement data, and labeled the display “Sample placement data.” Why: The old hard-coded values did not match the CSV. Tradeoff: The new endpoint depends on database availability and still displays generated sample records, not verified employer outcomes.

### Step 4e: README and Measured Results
Commit: `3f782526` (`4e: document measured results and actual limitations`). Files: `README.md`, `results/eval_results_readme_ci_check.json`.

What: Updated architecture, run instructions, measurements, and verified current limitations. Why: The previous README claimed authentication, rate limiting, tests, and pinning were missing after those features had been added. Tradeoff: The README explicitly separates full live answers, retrieval-only sweeps, and retrieval-only load tests rather than presenting them as comparable measurements.

### Step 4f: Dependency Pins
Commit: `dfb7c4e4` (`4f: pin direct dependencies and final offline check`). Files: `requirements.txt`, `results/eval_results_final_offline.json`.

What: Pinned all 14 direct runtime/eval/test requirements to exact versions from the configured environment. Why: Reproducible installs make CI and local results less dependent on package releases. Tradeoff: Upgrades now require deliberate pin changes and compatibility checks; transitive dependencies are not locked by a generated lockfile.

## 2. Baseline and Latest Measured Results

“Latest full live snapshot” is the latest full 35-request run with stage timing telemetry, before final caching/resilience changes; it is not a full live evaluation of the final code because the Groq token limit was reached during repeated runs. `final_offline` is the final code’s offline evaluation.

| Metric | Baseline live | Latest full live snapshot | Final offline / load evidence |
|---|---:|---:|---:|
| Router accuracy | 30/33 (90.91%) | 32/33 (96.97%) | Keyword-only: 30/33 (90.91%); live LLM fallback offline metric is not scored |
| SQL answer accuracy | 9/15 (60.00%) | 12/15 (80.00%) | NOT MEASURED on final code; 17/17 fixture reference SQL values match CSV |
| RAG answer accuracy | 12/15 (80.00%) | 13/15 (86.67%) | NOT MEASURED on final code; offline retrieved-context fact coverage 15/15 |
| Source recall@3 | 16/17 (94.12%) live | 15/17 (88.24%) live | 17/17 local exact-cosine; PostgreSQL sweep vector and hybrid both 17/17 |
| Full HTTP p50 / p95 | 761 / 4,879 ms | 823 / 5,686 ms | NOT MEASURED for final code after provider throttling |
| Retrieval-only `/ask` throughput at 1 / 10 / 25 clients, cache off | 5.705 / 144.928 / 156.077 req/s | Same test shape | Cache on: 7.032 / 307.726 / 536.152 req/s |
| Retrieval-only `/ask` p95 at 1 / 10 / 25 clients, cache off → on | 175.047 / 67.892 / 157.156 ms | Same test shape | 142.007 / 31.198 / 44.999 ms |
| Dependency-aware `/health` p95 at 1 / 10 / 25 clients | Liveness-only: 6.536 / 4.190 / 7.364 ms | N/A | DB/model checks: 26.237 / 25.298 / 41.191 ms |

Cache/load tests used a retrieval-only setting that abstained before calling Groq. The 25-client results contain only 25 requests, one per client; they are smoke-scale local measurements, not capacity certification.

## 3. Three Main Bottlenecks

1. **External LLM/provider latency and quota.** In the latest full live timing sample, combined LLM stage p50/p95 was 919/7,195 ms; routing fallback p95 was 2,079 ms, and provider logs reported Groq TPM 429s. Retries/circuit breaker and degraded responses are implemented, but no final full live accuracy run was possible after the provider quota was reached.
2. **Cold/repeated embedding work.** The cache probe measured cold RAG embedding at 193.623 ms and repeated hit at 0.003 ms; across full samples API embedding p50/p95 was 50/102 ms. A bounded LRU was added; the probe’s total RAG time still depended on the uncached LLM call.
3. **Application/thread and retrieval saturation under concurrency remains only partly characterized.** Retrieval-only throughput rose from 156 to 536 req/s at 25 clients when caches were enabled, while cache-off p95 was 157 ms and cache-on p95 was 45 ms. This 22-chunk local test does not identify a production-scale DB bottleneck; no 25-client full Groq answer load test is available, and provider throttling prevented a fair one.

## 4. Skipped, Failed, and Unverified

- **Cross-encoder reranker: SKIPPED.** The measured 17-source/3-abstention retrieval sweep already achieved 100% source/fact coverage for both vector-only and hybrid at the selected settings, so this fixture set showed no measurable headroom to justify its latency/dependency cost.
- **Docker image build/run: UNVERIFIED.** Compose configuration parsed and tests passed, but the Docker daemon disconnected with RPC EOF during dependency installation and later its socket disappeared.
- **Final full live eval after 3d–4f: NOT MEASURED.** Groq returned TPM 429 errors during repeated evaluation runs; final tests and offline evaluation pass, but generated SQL/RAG answer accuracy for the final exact code is unknown.
- **3d live transient retries under a real provider outage: NOT MEASURED.** Retry, jitter, breaker, half-open recovery, and degraded response behavior are covered by deterministic simulated errors.
- **3f full-answer throughput: NOT MEASURED.** The concurrency load test uses retrieval-only abstention to avoid provider limits; it measures the synchronous FastAPI path and local embedding/DB work, not the full model path.
- **PostgreSQL index speedup generalization: NOT ESTABLISHED.** The company query used the index in one plan, but the branch query remained a sequential scan; the table contains only 600 rows and times were sub-millisecond.

## 5. Remaining Limitations

- Shared API key only; no user identity, authorization policy, or row-level data scoping. The optional PII override can permit student identifiers.
- Sliding-window rate limits, embedding/SQL caches, and the circuit breaker are in-memory and per process.
- Keyword/LLM routing can still choose the wrong single branch for mixed or typo-heavy questions; measured fallback routes use a limited 35-case eval set.
- Full live answer accuracy under final provider resilience/caching code is unknown; Groq token limits interrupted subsequent full runs.
- Evaluation covers 22 chunks and 600 synthetic records, not production volume or real student data.
- Bootstrap SQL plus additive ingestion DDL is not a versioned migration system; backup/restore, TLS ingress, centralized alerting, and real-data retention controls are not implemented in the repository.
- Docker image build was not completed in this environment; the API container’s model download/cache behavior remains unverified.

## 6. Explain It to Me: Three Sentences per Step

### 0
I built an evaluation fixture from the existing CSV and company documents, then measured both local components and the live API. I did this first so later changes could be compared against observed behavior rather than intuition. I gave up statistical confidence because 35 questions and one provider run are a small sample, and the initial commit also had to capture previously uncommitted project files.

### 1
I protected `/ask` with a shared API key, per-process rate limiting, PII-aware SQL validation, and a read-only auxiliary SQL path. I did this because generated SQL and placement identifiers create a meaningful data-access risk. I gave up anonymous use and distributed rate-limit consistency; a shared key is not user-level authorization.

### 2a
I removed a shell-command artifact from Amazon’s document and ran ingestion twice while comparing source counts. I did this because ingestion embeds file contents as-is and previously cleared/replaced the corpus. I gave up incremental ingestion efficiency; a complete staged replacement is simpler and keeps a failed replacement from partially publishing.

### 2b
I kept keyword routing for clear matches and added a strict, five-second model fallback for unmatched/conflicting cases. I did this to recover some paraphrases and mixed-language requests without paying LLM latency on every question. I gave up deterministic routing on fallback cases and still saw incorrect hard-case routes.

### 2c
I added six concrete SQL examples and one retry containing SQLGlot’s rejection reason. I did this to show the generator allowed query shapes and let it repair one invalid draft. I gave up extra prompt tokens and potentially another provider call; measured SQL accuracy improved in the run but is not a causal guarantee.

### 2d
I added full-text/vector RRF as an optional path and swept retrieval settings against PostgreSQL. I did this to compare sparse term matching with semantic similarity on the same fixtures. I gave up the hybrid path as default because it tied on measured correctness and was slower in the local small-corpus run; no reranker was added.

### 3a
I caught RAG database and provider failures, logged their details, and returned a safe response while setting a SQL statement timeout. I did this to prevent dependency failures from escaping as uncontrolled request errors. I gave up detailed user-facing diagnostics and instead keep technical context in logs.

### 3b
I attached request IDs and per-stage durations to responses and a structured JSON request log. I did this so p95 latency could be attributed to routing, embedding, retrieval, generation, or execution. I gave up a few response bytes and logging work per request; the measured API stage p95 showed the LLM path dominated.

### 3c
I cached repeated question embeddings and validated SQL results with bounded LRU/TTL stores. I did this to avoid recomputing stable inputs and re-executing identical validated SQL. I gave up immediate freshness for cached SQL until TTL expiry and cross-process cache sharing; model calls remain uncached.

### 3d
I added retry/backoff/jitter and a circuit breaker around transient provider errors. I did this because live runs hit provider rate limits and transient failures. I gave up some response latency during retries and accepted degraded responses when the breaker is open; real-provider post-change accuracy remains unmeasured.

### 3e
I made `/health` check model initialization and both database connections, and verified blocking endpoints remain synchronous `def` handlers. I did this because process liveness alone does not prove dependencies are ready, and sync endpoints are dispatched through FastAPI’s worker pool. I gave up the very low cost of a pure liveness probe; dependency-aware health checks measured slower because they actually query both DBs.

### 3f
I added a concurrent client runner and compared cache-off/cache-on and old/new health endpoints. I did this to record throughput and tail latency rather than guess at scaling behavior. I gave up measuring full LLM throughput under load because provider TPM throttling made the result unstable; the `/ask` load test intentionally measured retrieval-only work.

### 4a
I added company and branch B-tree indexes and captured PostgreSQL plans before and after. I did this to support selective filters as the placement table grows. I gave up claiming a broad speedup: only the company query used the index in this 600-row run, while branch still scanned sequentially.

### 4b
I added an API Dockerfile, Compose service, service-health dependency, and image healthcheck. I did this to make the intended deployment a single Compose invocation with secrets excluded from build context. I gave up verification of the built image because Docker Desktop disconnected during build, so container startup is not claimed as tested.

### 4c
I added GitHub Actions for pytest and offline evaluation and removed the API import from offline eval. I did this so CI does not need Groq credentials or a database for deterministic checks. I gave up a single router implementation by keeping a small offline copy, and added a parity test to detect drift.

### 4d
I replaced hard-coded company card figures with a read-only aggregate endpoint and marked results as sample data. I did this because the prior counts did not match the generated CSV. I gave up static availability when the database is down; the UI now shows a clear unavailable state.

### 4e
I rewrote README architecture, run instructions, measured metrics, and limitations to match code and saved results. I did this so the project’s claims can be defended against actual implementation. I gave up marketing-style claims of production completeness and documented unverified items explicitly.

### 4f
I pinned all direct runtime, evaluation, and test dependencies to exact installed versions. I did this to reduce dependency drift between local runs and CI. I gave up automatic adoption of upstream fixes; upgrades now require a deliberate pin and compatibility run, while transitive dependencies still lack a lockfile.

## 7. Thirty Interview Questions, Easy to Hard

1. What are the two data paths in Placement Copilot, and which questions belong in each?
2. What is the exact request and response shape for `POST /ask`?
3. How does the keyword router decide between SQL and RAG?
4. Why is the SQL branch more appropriate than embeddings for a count or average?
5. What does the `rag_readonly` database role protect against?
6. Which SQL statements, relations, columns, and functions does the validator allow?
7. Why is `SELECT *` blocked when student identifiers are disallowed?
8. How does the SQL validator use SQLGlot’s AST rather than string matching?
9. Why does the SQL path have both a row cap and a statement timeout?
10. How does the validator-feedback retry differ from a provider transient retry?
11. What are the six SQL examples teaching the model, and why are examples not a security boundary?
12. What is cosine distance, and why does a smaller value represent a nearer vector?
13. What do the 500-character chunk size and 50-character overlap trade off?
14. How do you know the expected retrieval facts in the eval set are actually present in source data?
15. What does recall@3 mean in the PostgreSQL sweep, and what does it not measure?
16. How does reciprocal-rank fusion combine vector and full-text results?
17. Why was hybrid retrieval not selected as the default after the sweep?
18. Why was a cross-encoder reranker not added?
19. What is the distinction between answer accuracy, context-fact coverage, and source recall?
20. Why are the 35-case live metrics not statistical proof of an improvement?
21. How does the embedding LRU avoid repeated model work, and what is its cache key?
22. Why does caching validated SQL results have a staleness tradeoff?
23. How are cache capacity and TTL configured, and what happens with multiple workers?
24. Which provider failures are retried, and how are backoff and jitter calculated?
25. What are the closed, open, and half-open states of this circuit breaker?
26. How does the API respond when provider retries are exhausted or the circuit is open?
27. Why are synchronous endpoint functions relevant to event-loop correctness in FastAPI?
28. How did the measured LLM, embedding, and database stage latencies compare?
29. Why did the branch index not appear in the planner’s chosen execution plan?
30. Which production claims remain unverified because Docker and Groq were unavailable or rate-limited, and what evidence would be required to validate them?
