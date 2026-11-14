from eval import keyword_classify_intent
from intent_router import keyword_intent
from eval import load_eval_set


def test_offline_eval_router_matches_keyword_only_api_router():
    questions = [case["question"] for case in load_eval_set()]
    questions.extend(
        [
            "How many placements were recorded?",
            "What eligibility rules apply?",
            "Tell me about quantum weather.",
            "How many interview rounds are listed?",
        ]
    )

    assert [keyword_classify_intent(question) for question in questions] == [
        keyword_intent(question) or "rag" for question in questions
    ]
