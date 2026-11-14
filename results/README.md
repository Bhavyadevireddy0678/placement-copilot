# Evaluation and Load Results

All JSON files here are generated evidence artifacts, not source fixtures. The evaluation set remains at the repository root as `eval_set.json`. Artifacts were produced locally on 2026-10-31 and 2026-11-01; timestamps are available in Git/file metadata. Commit IDs identify the code state used where captured. Live LLM outputs are single-run snapshots and can vary by provider response/quota.

## Phase A and Live Baseline

- `eval_results_baseline.json` (2026-10-31, commit `40ca233a`): offline router, local exact-cosine retrieval, retrieved-context fact coverage, abstention-threshold proxy, and CSV reference-query validation. It does not measure generated answer accuracy.
- `eval_results_baseline_live.json` (2026-10-31, commit `40ca233a`): 35 questions against the live API before security hardening; generated SQL/RAG answer accuracy, live sources, and client HTTP timings.

## Step-by-Step Evaluation

- `eval_results_after_security.json` and `eval_results_after_security_offline.json` (2026-10-31, commit `1d80fce2`): post-auth/PII/rate-limit live and offline runs.
- `eval_results_after_corpus_cleanup.json` (2026-10-31, commit `7c40ac65`): live run after removing the Amazon shell-command artifact and repeating ingestion.
- `eval_results_after_router.json` (2026-10-31, commit `5f9344f7`): live hybrid-router run with route reasons and the keyword-only comparison.
- `eval_results_after_sql_prompt.json` (2026-10-31, commit `71b56543`): live run after few-shot SQL prompts and one validator-feedback retry.
- `eval_results_retrieval_sweep.json` and `eval_results_after_retrieval.json` (2026-10-31, commit `b5b7cc89`): PostgreSQL vector-vs-FTS/RRF sweep and API run with selected vector defaults.
- `eval_results_after_rag_reliability.json` (2026-10-31, commit `4fb239e8`): live API run after RAG errors were converted to safe responses and query timeout was set.
- `eval_results_after_observability.json` (2026-10-31, commit `109fab1c`): live API run with internal per-stage timings and request IDs.
- `eval_results_cache_probe.json` (2026-10-31, commit `691e74d0`): two repeated identical RAG requests and two repeated identical SQL requests, with per-stage cache-hit/timing data.
- `eval_results_after_resilience_offline.json` (2026-10-31, commit `2dc1dac5`): offline evaluation after retry/circuit-breaker implementation; provider failures are simulated in unit tests.
- `eval_results_after_health_offline.json` (2026-10-31, commit `9bb12071`): offline evaluation after dependency-aware health checks.
- `eval_results_after_loadtest_offline.json` (2026-10-31, commit `c5213226`): offline evaluation after load-test tooling was added.
- `eval_results_indexes.json` (2026-10-31, commit `7c11e09c`): exact before/after PostgreSQL EXPLAIN ANALYZE summaries for company/branch filters.
- `eval_results_after_ci_offline.json` (2026-11-01, commit `c021c900`): CI-equivalent offline run after evaluator/API decoupling.
- `eval_results_company_summaries.json` (2026-11-01, commit `ae9a4014`): ground-truth group counts and average packages calculated from the checked-in synthetic CSV for the UI endpoint.
- `eval_results_readme_ci_check.json` (2026-11-01, commit `3f782526`): offline run used while validating the README commands and claims.
- `eval_results_final_offline.json` (2026-11-01, commit `dfb7c4e4`): final pinned-dependency offline run before the last final-report-only commit.
- `eval_results_final_check.json` (2026-11-01, commit `9e07e0f5`): final report commit's offline validation.
- `eval_results_router_offline.json` (2026-11-01, router worktree): keyword-only versus embedding-only accuracy and fallback-rate threshold sweep; no Groq calls.
- `eval_results_router_live.json` (2026-11-01, router worktree): same tuning/held-out sweep with actual Groq fallback calls for low-margin cases.
- `eval_results_router_offline.json` (2026-11-01, current router worktree): keyword-only versus embedding-only accuracy and fallback-rate threshold sweep; no Groq calls.
- `eval_results_router_live.json` (2026-11-01, current router worktree): same tuning/held-out sweep with actual Groq fallback calls for low-margin cases.

## Load Tests

These are retrieval-only `/ask` tests: `RAG_DISTANCE_THRESHOLD=0.0` was used so answers abstained before Groq generation, isolating FastAPI, embedding, retrieval, cache, and database work.

- `loadtest_results_before_cache_disabled.json` (2026-10-31, commit `c5213226`): concurrency 1/10/25 with embedding and SQL caches disabled.
- `loadtest_results_after_cache_enabled.json` (2026-10-31, commit `c5213226`): same test shape with embedding/SQL caches enabled.
- `loadtest_results_before_health_dependency_check.json` (2026-10-31, commit `c5213226`): liveness-only health endpoint concurrency.
- `loadtest_results_after_health_concurrency.json` (2026-10-31, commit `c5213226`): dependency-aware health endpoint concurrency.

No artifact in this directory should be interpreted as a full end-to-end LLM load test unless the artifact explicitly says it was run against the full live `/ask` path.
