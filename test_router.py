from types import SimpleNamespace

import numpy as np
import pytest

from ask_api import route_question
from intent_router import classify_intent


class FakeEmbeddingEncoder:
    def __init__(self, vector):
        self.vector = np.asarray(vector, dtype=np.float32)
        self.questions = []

    def encode_with_status(self, question):
        self.questions.append(question)
        return self.vector, False


class FakeClassifier:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def route_vectors(sql_similarity=0.1, rag_similarity=0.1):
    return {
        "sql": np.asarray([[sql_similarity, (1 - sql_similarity**2) ** 0.5]], dtype=np.float32),
        "rag": np.asarray([[rag_similarity, (1 - rag_similarity**2) ** 0.5]], dtype=np.float32),
    }


def test_keyword_free_paraphrase_routes_by_embedding():
    encoder = FakeEmbeddingEncoder([1.0, 0.0])
    classifier = FakeClassifier("rag")
    vectors = route_vectors(sql_similarity=0.99, rag_similarity=0.2)

    intent, reason = route_question(
        "Give me a headcount for applicants?",
        classifier,
        embedding_encoder=encoder,
        router_example_vectors=vectors,
        margin_threshold=0.05,
    )

    assert (intent, reason) == ("sql", "embedding")
    assert classifier.calls == []


def test_typo_question_can_route_by_embedding():
    encoder = FakeEmbeddingEncoder([1.0, 0.0])
    classifier = FakeClassifier("sql")
    vectors = route_vectors(sql_similarity=0.15, rag_similarity=0.98)

    intent, reason = route_question(
        "Deloite applicants with an old arrear?",
        classifier,
        embedding_encoder=encoder,
        router_example_vectors=vectors,
        margin_threshold=0.05,
    )

    assert (intent, reason) == ("rag", "embedding")
    assert classifier.calls == []


def test_low_margin_uses_llm_fallback_and_strict_label():
    encoder = FakeEmbeddingEncoder([1.0, 0.0])
    classifier = FakeClassifier("sql")
    vectors = route_vectors(sql_similarity=0.81, rag_similarity=0.80)

    intent, reason = route_question(
        "How should I prepare?",
        classifier,
        embedding_encoder=encoder,
        router_example_vectors=vectors,
        margin_threshold=0.05,
    )

    assert (intent, reason) == ("sql", "llm_fallback")
    assert classifier.calls[0]["temperature"] == 0
    assert "exactly one token: sql or rag" in classifier.calls[0]["messages"][0]["content"]


def test_out_of_scope_question_defaults_to_rag_on_llm_failure():
    encoder = FakeEmbeddingEncoder([1.0, 0.0])
    classifier = FakeClassifier(error=TimeoutError("classifier timeout"))
    vectors = route_vectors(sql_similarity=0.81, rag_similarity=0.80)

    intent, reason = route_question(
        "What is the weather on Mars?",
        classifier,
        embedding_encoder=encoder,
        router_example_vectors=vectors,
        margin_threshold=0.05,
    )

    assert (intent, reason) == ("rag", "llm_fallback")


def test_keyword_router_is_disabled_unless_flag_is_enabled():
    encoder = FakeEmbeddingEncoder([1.0, 0.0])
    classifier = FakeClassifier("rag")
    vectors = route_vectors(sql_similarity=0.1, rag_similarity=0.99)

    disabled = route_question(
        "How many placements were recorded?",
        classifier,
        embedding_encoder=encoder,
        router_example_vectors=vectors,
        margin_threshold=0.05,
        keyword_enabled=False,
    )
    enabled = route_question(
        "How many placements were recorded?",
        classifier,
        embedding_encoder=encoder,
        router_example_vectors=vectors,
        margin_threshold=0.05,
        keyword_enabled=True,
    )

    assert disabled == ("rag", "embedding")
    assert enabled == ("sql", "keyword")


def test_classifier_uses_mean_of_top_three_similarities():
    encoder = FakeEmbeddingEncoder([1.0, 0.0])
    vectors = {
        "sql": np.asarray(
            [
                [0.90, 0.43589],
                [0.80, 0.60],
                [0.70, 0.71414],
                [0.10, 0.99499],
            ],
            dtype=np.float32,
        ),
        "rag": np.asarray(
            [
                [0.76, 0.64992],
                [0.75, 0.66144],
                [0.74, 0.67261],
                [0.20, 0.97980],
            ],
            dtype=np.float32,
        ),
    }

    intent, scores, margin, _cache_hit = classify_intent(
        "question",
        encoder,
        vectors,
    )

    assert intent == "sql"
    assert scores["sql"] == pytest.approx((0.9 + 0.8 + 0.7) / 3, abs=1e-4)
    assert scores["rag"] == pytest.approx((0.76 + 0.75 + 0.74) / 3, abs=1e-4)
    assert margin == pytest.approx(scores["sql"] - scores["rag"], abs=1e-6)
