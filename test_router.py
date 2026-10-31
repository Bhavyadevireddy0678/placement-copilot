from types import SimpleNamespace

from ask_api import route_question


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


def test_keyword_fast_path_avoids_classifier_call():
    classifier = FakeClassifier("rag")

    intent, reason = route_question("How many placements were recorded?", classifier)

    assert (intent, reason) == ("sql", "keyword_sql")
    assert classifier.calls == []


def test_unmatched_question_uses_strict_classifier_fallback():
    classifier = FakeClassifier("sql")

    intent, reason = route_question("What was the mean offer for Amazon?", classifier)

    assert (intent, reason) == ("sql", "llm_fallback_unmatched_sql")
    assert classifier.calls[0]["temperature"] == 0
    assert "exactly one token: sql or rag" in classifier.calls[0]["messages"][0]["content"]


def test_conflicting_keywords_use_classifier_fallback():
    classifier = FakeClassifier("rag")

    intent, reason = route_question(
        "How many interview rounds are listed for Amazon?", classifier
    )

    assert (intent, reason) == ("rag", "llm_fallback_conflict_rag")
    assert len(classifier.calls) == 1


def test_invalid_or_failed_classifier_defaults_to_rag():
    invalid_classifier = FakeClassifier("The answer is SQL")
    failed_classifier = FakeClassifier(error=TimeoutError("classifier timeout"))
    question = "What was the typical offer amount?"

    assert route_question(question, invalid_classifier) == (
        "rag",
        "default_rag_invalid_classifier_output",
    )
    assert route_question(question, failed_classifier) == (
        "rag",
        "default_rag_classifier_error",
    )
    assert route_question(question, None) == (
        "rag",
        "default_rag_classifier_unavailable",
    )
