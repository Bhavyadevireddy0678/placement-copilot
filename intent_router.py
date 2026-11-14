import json
from pathlib import Path

import numpy as np

from resilience import resilient_chat_completion

ROUTES = ("sql", "rag")
TOP_K = 3


def load_router_examples(path):
    examples = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(examples) != set(ROUTES):
        raise ValueError("Router examples must contain exactly sql and rag routes")
    if any(len(examples[route]) != 20 for route in ROUTES):
        raise ValueError("Each router route must contain exactly 20 examples")
    return examples


def embed_router_examples(model, examples):
    embedded = {}
    for route in ROUTES:
        vectors = model.encode(
            examples[route],
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        embedded[route] = np.asarray(vectors, dtype=np.float32)
    return embedded


def keyword_intent(question):
    normalized_question = question.lower()
    document_keywords = (
        "cgpa",
        "backlog",
        "eligib",
        "round",
        "process",
        "interview",
    )
    sql_keywords = (
        "how many",
        "count",
        "average",
        "avg",
        "highest",
        "lowest",
        "maximum",
        "minimum",
        "top recruiter",
        "total",
        "package",
        "salary",
    )
    document_match = any(word in normalized_question for word in document_keywords)
    sql_match = any(word in normalized_question for word in sql_keywords)
    if document_match and sql_match:
        return None
    if document_match:
        return "rag"
    if sql_match:
        return "sql"
    return None


def classify_intent(question, embedding_encoder, router_example_vectors):
    query_vector, cache_hit = embedding_encoder.encode_with_status(question)
    query_vector = np.asarray(query_vector, dtype=np.float32)
    norm = float(np.linalg.norm(query_vector))
    if norm == 0:
        return None, {"sql": 0.0, "rag": 0.0}, 0.0, cache_hit
    query_vector = query_vector / norm

    route_scores = {}
    for route in ROUTES:
        similarities = np.sum(router_example_vectors[route] * query_vector, axis=1)
        top_scores = np.sort(similarities)[-min(TOP_K, len(similarities)):]
        route_scores[route] = float(np.mean(top_scores))

    ordered_routes = sorted(ROUTES, key=lambda route: route_scores[route], reverse=True)
    margin = route_scores[ordered_routes[0]] - route_scores[ordered_routes[1]]
    predicted = ordered_routes[0]
    return predicted, route_scores, float(margin), cache_hit


def llm_fallback(
    question,
    classifier_client,
    resilience=None,
    model_name=None,
    return_error=False,
):
    if classifier_client is None:
        return ("rag", True) if return_error else "rag"
    prompt = f"""
    Classify the user's primary question as exactly one token: sql or rag.
    Return no explanation, punctuation, or other text.
    Use sql for exact counts, sums, averages, rankings, or filters over placement records.
    Use rag for company policies, eligibility, interview/process documents, or questions not answered by placement aggregates.
    If the question is mixed or unclear, choose the dominant information source.

    Question:
    {question}
    """
    try:
        response = resilient_chat_completion(
            classifier_client,
            resilience,
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        label = (response.choices[0].message.content or "").strip().lower()
        valid_label = label if label in ROUTES else "rag"
        return (valid_label, label not in ROUTES) if return_error else valid_label
    except Exception:
        return ("rag", True) if return_error else "rag"
