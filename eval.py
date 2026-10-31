"""Offline and optional live evaluation for Placement Copilot."""

import argparse
import json
import math
import os
import re
import sqlite3
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from ask_api import classify_intent


BASE_DIR = Path(__file__).resolve().parent
EVAL_SET_PATH = BASE_DIR / "eval_set.json"
DATA_PATH = BASE_DIR / "synthetic_placements.csv"
DOCUMENTS_DIR = BASE_DIR / "documents"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K = 3
DISTANCE_THRESHOLD = 0.7


def load_eval_set():
    cases = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    expected_groups = {"sql": 12, "rag": 13, "hard": 10}
    actual_groups = {
        group: sum(case["group"] == group for case in cases)
        for group in expected_groups
    }
    if len(cases) != 35 or actual_groups != expected_groups:
        raise ValueError(
            f"Expected 35 cases split {expected_groups}, got {len(cases)} / {actual_groups}"
        )
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Evaluation case IDs must be unique")
    return cases


def normalize_text(value):
    normalized = str(value).lower().replace("’", "'")
    normalized = re.sub(r"\bdon't\b", "do not", normalized)
    normalized = re.sub(r"\bmust not have (?:any )?", "no ", normalized)
    normalized = re.sub(r"\bnot have (?:any )?", "no ", normalized)
    normalized = re.sub(r"\bno (active|historical)\b", r"not \1", normalized)
    normalized = re.sub(
        r"\b(?:maximum of|up to|no more than|not more than|at most)\s+",
        "at most ",
        normalized,
    )
    normalized = re.sub(
        r"\bbefore (?:the )?student joins(?:\s+[a-z]+)?\b",
        "before joining",
        normalized,
    )
    normalized = re.sub(
        r"one final interview focused on hr and company values",
        "one hr values fit round",
        normalized,
    )
    normalized = re.sub(r"\bor higher\b", "and above", normalized)
    normalized = re.sub(r"\busually\b", "generally", normalized)
    normalized = re.sub(
        r"\bat least an? ([0-9]+(?:\.[0-9]+)?) cgpa\b",
        r"minimum cgpa of \1",
        normalized,
    )
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def fact_is_present(fact, answer):
    ignored_words = {"a", "an", "of", "the", "any", "is", "are", "be", "to"}
    expected_tokens = [
        token for token in normalize_text(fact).split() if token not in ignored_words
    ]
    answer_tokens = iter(normalize_text(answer).split())
    return all(
        any(answer_token == expected_token for answer_token in answer_tokens)
        for expected_token in expected_tokens
    )


def json_value(value):
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, np.generic):
        return value.item()
    return value


def values_equal(expected, actual, tolerance=0.0001):
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(expected), float(actual), rel_tol=0, abs_tol=tolerance)
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return False
        unmatched = list(actual)
        for expected_item in expected:
            match_index = next(
                (
                    index
                    for index, actual_item in enumerate(unmatched)
                    if values_equal(expected_item, actual_item, tolerance)
                ),
                None,
            )
            if match_index is None:
                return False
            unmatched.pop(match_index)
        return True
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() == actual.keys():
            return all(
                values_equal(expected[key], actual[key], tolerance) for key in expected
            )
        return values_equal(
            list(expected.values()), list(actual.values()), tolerance
        )
    return expected == actual


def reference_sql_results(cases):
    frame = pd.read_csv(DATA_PATH)
    connection = sqlite3.connect(":memory:")
    frame.to_sql("placements", connection, index=False)
    results = {}
    failures = []
    timings = []
    try:
        for case in cases:
            query = case.get("reference_sql")
            if not query:
                continue
            started = time.perf_counter()
            cursor = connection.execute(query)
            rows = cursor.fetchall()
            elapsed_ms = (time.perf_counter() - started) * 1000
            timings.append(elapsed_ms)
            columns = [column[0] for column in cursor.description]
            if len(rows) == 1 and len(columns) == 1:
                actual = json_value(rows[0][0])
            else:
                actual = [
                    {column: json_value(value) for column, value in zip(columns, row)}
                    for row in rows
                ]
            expected = case["expected_answer"].get("value")
            if case["expected_answer"]["kind"] == "mixed_facts":
                expected = case["expected_answer"].get("required_sql_value")
            results[case["id"]] = actual
            if expected is not None and not values_equal(expected, actual):
                failures.append(
                    {
                        "case_id": case["id"],
                        "stage": "ground_truth_validation",
                        "expected": expected,
                        "actual": actual,
                    }
                )
    finally:
        connection.close()
    return results, failures, timings, len(frame)


def validate_document_ground_truth(cases):
    validated = 0
    for case in cases:
        answer_spec = case["expected_answer"]
        if answer_spec["kind"] not in ("rag_facts", "mixed_facts"):
            continue
        source_path = DOCUMENTS_DIR / answer_spec["source"]
        if not source_path.is_file():
            raise ValueError(f"Missing expected source file for {case['id']}: {source_path.name}")
        source_text = normalize_text(source_path.read_text(encoding="utf-8"))
        for fact in answer_spec.get("required_facts", []):
            if normalize_text(fact) not in source_text:
                raise ValueError(
                    f"Expected fact for {case['id']} is not present in {source_path.name}: {fact}"
                )
        validated += 1
    return validated


def load_corpus(model, batch_size):
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = []
    for path in sorted(DOCUMENTS_DIR.glob("*.txt")):
        content = path.read_text(encoding="utf-8").strip()
        for chunk in splitter.split_text(content):
            chunks.append({"source": path.name, "content": chunk})
    if not chunks:
        raise RuntimeError(f"No document chunks found under {DOCUMENTS_DIR}")

    vectors = model.encode(
        [chunk["content"] for chunk in chunks],
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.maximum(norms, 1e-12)
    return chunks, vectors


def retrieve(question, model, chunks, corpus_vectors):
    embedding_started = time.perf_counter()
    query_vector = model.encode(
        question,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    query_vector = np.asarray(query_vector, dtype=np.float32)
    embedding_norm = np.linalg.norm(query_vector)
    if embedding_norm:
        query_vector = query_vector / embedding_norm
    embedding_ms = (time.perf_counter() - embedding_started) * 1000

    retrieval_started = time.perf_counter()
    similarities = np.sum(corpus_vectors * query_vector, axis=1)
    top_indices = np.argsort(-similarities)[:TOP_K]
    matches = []
    for index in top_indices:
        similarity = float(np.clip(similarities[index], -1.0, 1.0))
        match = dict(chunks[int(index)])
        match["distance"] = 1.0 - similarity
        matches.append(match)
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
    return matches, embedding_ms, retrieval_ms


def post_question(api_url, question, timeout_seconds):
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("EVAL_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(
        api_url.rstrip("/") + "/ask",
        data=json.dumps({"question": question}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def answer_is_correct(case, response):
    if not isinstance(response, dict):
        return False
    answer_spec = case["expected_answer"]
    answer = response.get("answer")
    kind = answer_spec["kind"]

    if kind == "sql_result":
        return values_equal(answer_spec["value"], answer)
    if kind == "abstain":
        return any(
            fact_is_present(phrase, answer or "")
            for phrase in ("not enough information", "don't have enough information")
        )
    if kind in ("rag_facts", "mixed_facts"):
        normalized_answer = normalize_text(answer or "")
        required_facts = answer_spec.get("required_facts", [])
        facts_present = all(
            fact_is_present(fact, normalized_answer) for fact in required_facts
        )
        required_source = answer_spec.get("source")
        sources = response.get("sources") or []
        source_present = required_source is None or required_source in sources
        sql_value = answer_spec.get("required_sql_value")
        sql_value_present = sql_value is None or fact_is_present(sql_value, normalized_answer)
        return facts_present and source_present and sql_value_present
    return False


def percentile(values, proportion):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(proportion * len(ordered)) - 1)
    return round(ordered[index], 3)


def latency_summary(samples):
    return {
        "samples": len(samples),
        "p50_ms": percentile(samples, 0.50),
        "p95_ms": percentile(samples, 0.95),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="baseline", help="Output name suffix")
    parser.add_argument(
        "--api-url",
        default=os.getenv("EVAL_API_URL"),
        help="Optional running Placement Copilot base URL, e.g. http://127.0.0.1:8000",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--http-timeout", type=float, default=60)
    args = parser.parse_args()

    cases = load_eval_set()
    document_facts_validated = validate_document_ground_truth(cases)
    sql_results, ground_truth_failures, sql_reference_timings, row_count = reference_sql_results(cases)

    model_started = time.perf_counter()
    model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL))
    model_load_ms = (time.perf_counter() - model_started) * 1000
    if model.get_sentence_embedding_dimension() != 384:
        raise RuntimeError("Evaluation model must produce 384-dimensional embeddings")

    corpus_started = time.perf_counter()
    chunks, corpus_vectors = load_corpus(model, args.batch_size)
    corpus_embedding_ms = (time.perf_counter() - corpus_started) * 1000

    results = []
    failures = list(ground_truth_failures)
    stage_samples = {
        "router": [],
        "embedding": [],
        "vector_retrieval": [],
        "offline_total": [],
        "sql_reference": sql_reference_timings,
        "live_http_total": [],
    }
    router_correct = 0
    router_scored = 0
    context_fact_correct = 0
    context_fact_total = 0
    retrieval_correct = 0
    retrieval_total = 0
    threshold_abstain_correct = 0
    abstain_total = 0
    live_sql_correct = 0
    live_sql_total = 0
    live_rag_correct = 0
    live_rag_total = 0
    live_abstain_correct = 0
    live_abstain_total = 0
    live_retrieval_correct = 0
    live_retrieval_total = 0
    ambiguous_routes = {}

    for case in cases:
        total_started = time.perf_counter()
        router_started = time.perf_counter()
        predicted_intent = classify_intent(case["question"])
        router_ms = (time.perf_counter() - router_started) * 1000
        stage_samples["router"].append(router_ms)

        expected_intent = case["expected_intent"]
        if expected_intent in ("sql", "rag"):
            router_scored += 1
            if predicted_intent == expected_intent:
                router_correct += 1
            else:
                failures.append(
                    {
                        "case_id": case["id"],
                        "stage": "router",
                        "expected": expected_intent,
                        "actual": predicted_intent,
                    }
                )
        else:
            ambiguous_routes[predicted_intent] = ambiguous_routes.get(predicted_intent, 0) + 1

        matches, embedding_ms, retrieval_ms = retrieve(
            case["question"], model, chunks, corpus_vectors
        )
        stage_samples["embedding"].append(embedding_ms)
        stage_samples["vector_retrieval"].append(retrieval_ms)
        offline_total_ms = (time.perf_counter() - total_started) * 1000
        stage_samples["offline_total"].append(offline_total_ms)

        sources = list(dict.fromkeys(match["source"] for match in matches))
        context = "\n".join(match["content"] for match in matches)
        answer_spec = case["expected_answer"]
        kind = answer_spec["kind"]

        if kind in ("rag_facts", "mixed_facts"):
            retrieval_total += 1
            if answer_spec["source"] in sources:
                retrieval_correct += 1
            else:
                failures.append(
                    {
                        "case_id": case["id"],
                        "stage": "recall_at_3",
                        "expected_source": answer_spec["source"],
                        "retrieved_sources": sources,
                    }
                )
            if kind == "rag_facts":
                context_fact_total += 1
                missing_facts = [
                    fact
                    for fact in answer_spec["required_facts"]
                    if not fact_is_present(fact, context)
                ]
                if not missing_facts:
                    context_fact_correct += 1
                else:
                    failures.append(
                        {
                            "case_id": case["id"],
                            "stage": "retrieved_context_facts",
                            "missing_facts": missing_facts,
                        }
                    )

        if kind == "abstain":
            abstain_total += 1
            closest_distance = matches[0]["distance"] if matches else None
            threshold_abstains = (
                closest_distance is None or closest_distance > DISTANCE_THRESHOLD
            )
            if threshold_abstains:
                threshold_abstain_correct += 1
            else:
                failures.append(
                    {
                        "case_id": case["id"],
                        "stage": "abstention_threshold_proxy",
                        "expected": "abstain",
                        "closest_distance": closest_distance,
                    }
                )

        record = {
            "id": case["id"],
            "group": case["group"],
            "question": case["question"],
            "expected_intent": expected_intent,
            "offline_intent": predicted_intent,
            "offline_top3_sources": sources,
            "offline_top3_distances": [round(match["distance"], 6) for match in matches],
            "reference_sql_result": sql_results.get(case["id"]),
            "timings_ms": {
                "router": round(router_ms, 3),
                "embedding": round(embedding_ms, 3),
                "vector_retrieval": round(retrieval_ms, 3),
                "offline_total": round(offline_total_ms, 3),
            },
        }

        if args.api_url:
            request_started = time.perf_counter()
            try:
                live_response = post_question(args.api_url, case["question"], args.http_timeout)
                live_total_ms = (time.perf_counter() - request_started) * 1000
                stage_samples["live_http_total"].append(live_total_ms)
                record["live_response"] = live_response
                record["live_total_ms"] = round(live_total_ms, 3)
                live_intent = live_response.get("intent")
                record["live_intent"] = live_intent
                if expected_intent in ("sql", "rag") and live_intent != expected_intent:
                    failures.append(
                        {
                            "case_id": case["id"],
                            "stage": "live_router",
                            "expected": expected_intent,
                            "actual": live_intent,
                        }
                    )
                if kind == "sql_result":
                    live_sql_total += 1
                    correct = answer_is_correct(case, live_response)
                    live_sql_correct += int(correct)
                    if not correct:
                        failures.append(
                            {
                                "case_id": case["id"],
                                "stage": "sql_answer",
                                "expected": answer_spec["value"],
                                "actual": live_response.get("answer"),
                            }
                        )
                elif kind == "rag_facts":
                    live_rag_total += 1
                    correct = answer_is_correct(case, live_response)
                    live_rag_correct += int(correct)
                    if not correct:
                        failures.append(
                            {
                                "case_id": case["id"],
                                "stage": "rag_answer",
                                "expected_facts": answer_spec["required_facts"],
                                "expected_source": answer_spec["source"],
                                "actual": live_response.get("answer"),
                            }
                        )
                elif kind == "abstain":
                    live_abstain_total += 1
                    correct = answer_is_correct(case, live_response)
                    live_abstain_correct += int(correct)
                    if not correct:
                        failures.append(
                            {
                                "case_id": case["id"],
                                "stage": "live_abstention",
                                "expected": "abstain",
                                "actual": live_response.get("answer"),
                            }
                        )
                elif kind == "mixed_facts" and not answer_is_correct(case, live_response):
                    failures.append(
                        {
                            "case_id": case["id"],
                            "stage": "ambiguous_multi_intent",
                            "expected": answer_spec,
                            "actual": live_response.get("answer"),
                        }
                    )
                if kind in ("rag_facts", "mixed_facts"):
                    live_retrieval_total += 1
                    live_sources = live_response.get("sources") or []
                    if answer_spec["source"] not in live_sources:
                        failures.append(
                            {
                                "case_id": case["id"],
                                "stage": "live_recall_at_3",
                                "expected_source": answer_spec["source"],
                                "actual_sources": live_sources,
                            }
                        )
                    else:
                        live_retrieval_correct += 1
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                record["live_error"] = str(error)
                failures.append(
                    {
                        "case_id": case["id"],
                        "stage": "live_request",
                        "error": str(error),
                    }
                )
        results.append(record)

    sql_reference_correct = sum(
        1 for case in cases
        if case.get("reference_sql") and case["id"] not in {
            failure["case_id"] for failure in ground_truth_failures
        }
    )
    sql_reference_total = sum(bool(case.get("reference_sql")) for case in cases)
    expected_sql_cases = sum(
        case["expected_answer"]["kind"] == "sql_result" for case in cases
    )
    expected_rag_cases = sum(
        case["expected_answer"]["kind"] == "rag_facts" for case in cases
    )
    expected_abstain_cases = sum(
        case["expected_answer"]["kind"] == "abstain" for case in cases
    )
    expected_source_cases = sum(
        case["expected_answer"]["kind"] in ("rag_facts", "mixed_facts")
        for case in cases
    )
    if args.api_url:
        retrieval_correct = live_retrieval_correct
        retrieval_total = expected_source_cases

    metrics = {
        "router_accuracy": {
            "correct": router_correct,
            "total": router_scored,
            "rate": round(router_correct / router_scored, 4) if router_scored else None,
            "ambiguous_route_counts": ambiguous_routes,
            "note": "Ambiguous expected_intent cases are excluded from accuracy.",
        },
        "sql_accuracy": {
            "correct": live_sql_correct if args.api_url else None,
            "total": expected_sql_cases,
            "responses_received": live_sql_total,
            "rate": round(live_sql_correct / expected_sql_cases, 4)
            if args.api_url and expected_sql_cases else None,
            "reference_data_validation": {
                "correct": sql_reference_correct,
                "total": sql_reference_total,
                "rate": round(sql_reference_correct / sql_reference_total, 4)
                if sql_reference_total else None,
            },
            "note": "Live SQL answer accuracy requires --api-url; reference validation checks fixture SQL against the CSV, not generated SQL.",
        },
        "rag_accuracy": {
            "correct": live_rag_correct if args.api_url else None,
            "total": expected_rag_cases,
            "responses_received": live_rag_total,
            "rate": round(live_rag_correct / expected_rag_cases, 4)
            if args.api_url and expected_rag_cases else None,
            "offline_retrieved_context_fact_accuracy": {
                "correct": context_fact_correct,
                "total": context_fact_total,
                "rate": round(context_fact_correct / context_fact_total, 4)
                if context_fact_total else None,
            },
            "note": "Live answer accuracy requires --api-url; offline context-fact coverage is a retrieval proxy, not generated-answer accuracy.",
        },
        "recall_at_3": {
            "correct_sources": retrieval_correct,
            "total_source_cases": retrieval_total,
            "responses_received": live_retrieval_total if args.api_url else retrieval_total,
            "rate": round(retrieval_correct / retrieval_total, 4) if retrieval_total else None,
            "mode": "live_api_sources" if args.api_url else "local_exact_cosine_over_chunked_documents",
        },
        "abstention_correctness": {
            "live_correct": live_abstain_correct if args.api_url else None,
            "live_total": expected_abstain_cases,
            "live_responses_received": live_abstain_total,
            "live_rate": round(live_abstain_correct / expected_abstain_cases, 4)
            if args.api_url and expected_abstain_cases else None,
            "offline_threshold_proxy_correct": threshold_abstain_correct,
            "offline_threshold_proxy_total": abstain_total,
            "offline_threshold_proxy_rate": round(threshold_abstain_correct / abstain_total, 4)
            if abstain_total else None,
        },
    }

    latency = {
        "model_load": {"samples": 1, "p50_ms": round(model_load_ms, 3), "p95_ms": round(model_load_ms, 3)},
        "corpus_embedding_and_prepare": {"samples": 1, "p50_ms": round(corpus_embedding_ms, 3), "p95_ms": round(corpus_embedding_ms, 3)},
        "router": latency_summary(stage_samples["router"]),
        "embedding": latency_summary(stage_samples["embedding"]),
        "vector_retrieval": latency_summary(stage_samples["vector_retrieval"]),
        "offline_total_per_case": latency_summary(stage_samples["offline_total"]),
        "sql_reference_execution": latency_summary(stage_samples["sql_reference"]),
        "live_http_total": latency_summary(stage_samples["live_http_total"]),
        "sql_generation": None,
        "live_sql_execution_internal": None,
        "llm_internal": None,
        "note": "Internal database/LLM stage timings are not exposed by the current API; null means unmeasured, not zero.",
    }

    report = {
        "evaluation_name": args.name,
        "evaluation_mode": "live_api" if args.api_url else "offline",
        "dataset_path": "eval_set.json",
        "case_count": len(cases),
        "source_document_count": len(list(DOCUMENTS_DIR.glob("*.txt"))),
        "document_ground_truth_facts_validated": document_facts_validated,
        "chunk_count": len(chunks),
        "csv_row_count": row_count,
        "embedding_model": os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        "embedding_dimension": int(model.get_sentence_embedding_dimension()),
        "retrieval_top_k": TOP_K,
        "abstention_distance_threshold": DISTANCE_THRESHOLD,
        "measurements": {
            "router": "ask_api.classify_intent",
            "retrieval": "local exact cosine similarity over the same splitter settings; does not execute PostgreSQL/pgvector",
            "sql_reference": "SQLite execution over synthetic_placements.csv; validates stored expected values only",
            "answer_accuracy": "live HTTP endpoint only",
        },
        "metrics": metrics,
        "latency_ms": latency,
        "failures": failures,
        "cases": results,
    }
    output_path = BASE_DIR / f"eval_results_{args.name}.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Evaluation: {args.name} ({report['evaluation_mode']})")
    print(f"Cases: {len(cases)}; documents: {report['source_document_count']}; chunks: {len(chunks)}; CSV rows: {row_count}")
    print("Router accuracy: {correct}/{total} ({rate})".format(**metrics["router_accuracy"]))
    print("SQL generated-answer accuracy: {}/{} ({})".format(
        metrics["sql_accuracy"]["correct"], metrics["sql_accuracy"]["total"], metrics["sql_accuracy"]["rate"]
    ))
    print("SQL reference answers validated: {correct}/{total} ({rate})".format(**metrics["sql_accuracy"]["reference_data_validation"]))
    print("RAG generated-answer accuracy: {}/{} ({})".format(
        metrics["rag_accuracy"]["correct"], metrics["rag_accuracy"]["total"], metrics["rag_accuracy"]["rate"]
    ))
    print("Offline context-fact accuracy: {correct}/{total} ({rate})".format(**metrics["rag_accuracy"]["offline_retrieved_context_fact_accuracy"]))
    print("Recall@3: {correct_sources}/{total_source_cases} ({rate})".format(**metrics["recall_at_3"]))
    print("Abstention threshold proxy: {}/{} ({})".format(
        metrics["abstention_correctness"]["offline_threshold_proxy_correct"],
        metrics["abstention_correctness"]["offline_threshold_proxy_total"],
        metrics["abstention_correctness"]["offline_threshold_proxy_rate"],
    ))
    print("Latency p50/p95 ms:")
    for stage in ("router", "embedding", "vector_retrieval", "offline_total_per_case", "sql_reference_execution", "live_http_total"):
        print(f"  {stage}: {latency[stage]['p50_ms']}/{latency[stage]['p95_ms']}")
    print(f"Failure rows: {len(failures)}")
    if failures:
        print("case_id | stage | detail")
        for failure in failures:
            detail = failure.get("error") or failure.get("missing_facts") or failure.get("expected_source") or failure.get("actual")
            print(f"{failure.get('case_id')} | {failure.get('stage')} | {detail}")
    print(f"Saved: {output_path.name}")


if __name__ == "__main__":
    main()
