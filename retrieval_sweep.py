"""Measure vector-only and PostgreSQL full-text RRF retrieval on eval_set.json."""

import json
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, event
from pgvector.psycopg2 import register_vector

from eval import fact_is_present, load_eval_set
from retrieval import retrieve_chunks


BASE_DIR = Path(__file__).resolve().parent
TOP_K_VALUES = (1, 3, 5, 8)
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)


def percentile(values, proportion):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, int((len(ordered) - 1) * proportion + 0.999999))
    return round(ordered[index], 3)


def main():
    load_dotenv(BASE_DIR / ".env")
    database_url = os.getenv("RAG_READONLY_DB_URL") or os.getenv("SQL_READONLY_DB_URL")
    if not database_url:
        raise RuntimeError("Set RAG_READONLY_DB_URL or SQL_READONLY_DB_URL")

    cases = load_eval_set()
    source_cases = [
        case for case in cases
        if case["expected_answer"]["kind"] in ("rag_facts", "mixed_facts")
    ]
    abstain_cases = [
        case for case in cases if case["expected_answer"]["kind"] == "abstain"
    ]
    model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    query_texts = [case["question"] for case in source_cases + abstain_cases]
    vectors = model.encode(query_texts, batch_size=32, show_progress_bar=False)
    embeddings = {
        case["id"]: vector for case, vector in zip(source_cases + abstain_cases, vectors)
    }

    engine = create_engine(
        database_url,
        connect_args={"connect_timeout": 5},
        pool_pre_ping=True,
    )
    event.listen(engine, "connect", lambda connection, record: register_vector(connection))

    sweep_rows = []
    try:
        with engine.connect() as connection:
            for mode in ("vector", "hybrid"):
                for top_k in TOP_K_VALUES:
                    retrieved = {}
                    retrieval_times = []
                    for case in source_cases + abstain_cases:
                        started = time.perf_counter()
                        rows = retrieve_chunks(
                            connection,
                            case["question"],
                            embeddings[case["id"]],
                            top_k=top_k,
                            hybrid=(mode == "hybrid"),
                        )
                        retrieval_times.append((time.perf_counter() - started) * 1000)
                        retrieved[case["id"]] = [
                            {
                                "content": row[0],
                                "source": row[1],
                                "distance": float(row[2]),
                            }
                            for row in rows
                        ]

                    for threshold in THRESHOLDS:
                        source_hits = 0
                        context_fact_hits = 0
                        accepted_hits = 0
                        correct_abstentions = 0
                        for case in source_cases:
                            matches = retrieved[case["id"]]
                            has_source = any(
                                row["source"] == case["expected_answer"]["source"]
                                for row in matches
                            )
                            retrieved_context = "\n".join(
                                row["content"] for row in matches
                            )
                            facts_present = all(
                                fact_is_present(fact, retrieved_context)
                                for fact in case["expected_answer"].get(
                                    "required_facts", []
                                )
                            )
                            source_hits += int(has_source)
                            context_fact_hits += int(facts_present)
                            accepted = bool(matches) and matches[0]["distance"] <= threshold
                            accepted_hits += int(has_source and facts_present and accepted)
                        for case in abstain_cases:
                            matches = retrieved[case["id"]]
                            should_abstain = not matches or matches[0]["distance"] > threshold
                            correct_abstentions += int(should_abstain)

                        combined_total = len(source_cases) + len(abstain_cases)
                        combined_correct = accepted_hits + correct_abstentions
                        sweep_rows.append(
                            {
                                "mode": mode,
                                "top_k": top_k,
                                "threshold": threshold,
                                "source_recall_at_k": round(source_hits / len(source_cases), 4),
                                "context_fact_accuracy": round(
                                    context_fact_hits / len(source_cases), 4
                                ),
                                "accepted_source_recall": round(accepted_hits / len(source_cases), 4),
                                "abstention_accuracy": round(correct_abstentions / len(abstain_cases), 4),
                                "combined_correct": combined_correct,
                                "combined_total": combined_total,
                                "combined_accuracy": round(combined_correct / combined_total, 4),
                                "retrieval_latency_p50_ms": percentile(retrieval_times, 0.50),
                                "retrieval_latency_p95_ms": percentile(retrieval_times, 0.95),
                            }
                        )
    finally:
        engine.dispose()

    best = max(
        sweep_rows,
        key=lambda row: (
            row["combined_accuracy"],
            row["source_recall_at_k"],
            row["context_fact_accuracy"],
            row["abstention_accuracy"],
            -abs(row["threshold"] - 0.7),
            -row["top_k"],
            row["mode"] == "vector",
            -row["retrieval_latency_p50_ms"],
        ),
    )
    default_k3_t07 = [
        row for row in sweep_rows if row["top_k"] == 3 and row["threshold"] == 0.7
    ]
    report = {
        "evaluation_set_cases": len(cases),
        "source_cases": len(source_cases),
        "abstain_cases": len(abstain_cases),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        "metric_definition": "Expected source in top-k; accepted-source recall also requires first returned cosine distance <= threshold; out-of-scope cases count correct when first distance > threshold.",
        "vector_vs_hybrid_at_k3_threshold_0_7": default_k3_t07,
        "sweep": sweep_rows,
        "selected_default": {
            "mode": best["mode"],
            "top_k": best["top_k"],
            "distance_threshold": best["threshold"],
            "combined_accuracy": best["combined_accuracy"],
            "source_recall_at_k": best["source_recall_at_k"],
            "context_fact_accuracy": best["context_fact_accuracy"],
            "abstention_accuracy": best["abstention_accuracy"],
        },
    }
    output_path = BASE_DIR / "eval_results_retrieval_sweep.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("Vector-only vs hybrid at top_k=3, threshold=0.7")
    print("mode | recall@3 | fact coverage | accepted-source-recall | abstention-accuracy | p50/p95 ms")
    for row in default_k3_t07:
        print(
            f"{row['mode']} | {row['source_recall_at_k']} | "
            f"{row['context_fact_accuracy']} | "
            f"{row['accepted_source_recall']} | {row['abstention_accuracy']} | "
            f"{row['retrieval_latency_p50_ms']}/{row['retrieval_latency_p95_ms']}"
        )
    print("Top-k=3 distance-threshold sweep")
    print("mode | threshold | accepted-source-recall | abstention-accuracy | combined-accuracy")
    for row in sweep_rows:
        if row["top_k"] == 3:
            print(
                f"{row['mode']} | {row['threshold']} | "
                f"{row['accepted_source_recall']} | {row['abstention_accuracy']} | "
                f"{row['combined_accuracy']}"
            )
    print("Selected default:", report["selected_default"])
    print("Saved:", output_path.name)


if __name__ == "__main__":
    main()
