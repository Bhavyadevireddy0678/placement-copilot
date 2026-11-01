from eval import classify_intent as eval_classify_intent
from ask_api import classify_intent as api_classify_intent
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

    assert [eval_classify_intent(question) for question in questions] == [
        api_classify_intent(question) for question in questions
    ]
