import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parent


def test_router_examples_are_20_per_route_and_do_not_overlap_eval_questions():
    examples = json.loads((BASE_DIR / "router_examples.json").read_text(encoding="utf-8"))
    tuning = json.loads((BASE_DIR / "eval_set.json").read_text(encoding="utf-8"))
    heldout = json.loads((BASE_DIR / "eval_heldout.json").read_text(encoding="utf-8"))
    eval_questions = [case["question"] for case in tuning + heldout]
    router_questions = examples["sql"] + examples["rag"]

    assert len(examples["sql"]) == 20
    assert len(examples["rag"]) == 20
    normalized_eval = {question.lower().strip() for question in eval_questions}
    exact_matches = [
        question for question in router_questions
        if question.lower().strip() in normalized_eval
    ]
    assert not exact_matches, f"Exact router/eval overlaps: {exact_matches}"

    model = SentenceTransformer("all-MiniLM-L6-v2")
    vectors = model.encode(
        router_questions + eval_questions,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    router_vectors = np.asarray(vectors[: len(router_questions)], dtype=np.float32)
    eval_vectors = np.asarray(vectors[len(router_questions) :], dtype=np.float32)
    similarities = np.sum(
        router_vectors[:, None, :] * eval_vectors[None, :, :],
        axis=2,
    )
    near_matches = [
        (router_questions[row], eval_questions[column], float(similarities[row, column]))
        for row, column in zip(*np.where(similarities > 0.95))
    ]
    assert not near_matches, f"Near-duplicate router/eval overlaps: {near_matches}"
