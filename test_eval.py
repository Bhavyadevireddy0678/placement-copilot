from eval import answer_is_correct, fact_is_present, run_cache_probe


def test_fact_matching_ignores_markdown_and_punctuation():
    assert fact_is_present("minimum CGPA of 7.0", "Minimum CGPA of **7.0**")
    assert fact_is_present(
        "technical/HR interview",
        "Technical / HR interview",
    )


def test_fact_matching_preserves_word_order():
    assert fact_is_present("cleared before joining", "Backlogs are cleared before joining")
    assert not fact_is_present("cleared before joining", "Joining happens before backlogs are cleared")
    assert fact_is_present("maximum of one active backlog", "Up to one active backlog")
    assert fact_is_present("must not have active backlogs", "No active backlogs allowed")
    assert fact_is_present("minimum CGPA of 6.0", "At least a 6.0 CGPA")


def test_live_rag_answer_matches_formatting_variants_and_citation():
    case = {
        "expected_answer": {
            "kind": "rag_facts",
            "source": "amazon.txt",
            "required_facts": ["minimum CGPA of 7.0", "must not have any active backlogs"],
        }
    }
    response = {
        "answer": "Amazon needs a minimum CGPA of **7.0** and students must not have any active backlogs.",
        "sources": ["amazon.txt"],
    }

    assert answer_is_correct(case, response)


def test_abstention_check_accepts_current_api_response():
    case = {"expected_answer": {"kind": "abstain"}}
    response = {"answer": "I don't have enough information in the company documents to answer that."}

    assert answer_is_correct(case, response)


def test_sql_result_comparison_accepts_column_alias_difference():
    from eval import values_equal

    expected = [{"branch": "CSE", "total": 159}]
    actual = [{"branch": "CSE", "num_placements": 159}]

    assert values_equal(expected, actual)


def test_sql_group_results_ignore_row_order():
    from eval import values_equal

    expected = [{"branch": "CSE", "total": 159}, {"branch": "IT", "total": 148}]
    actual = [
        {"branch": "IT", "placements_count": 148},
        {"branch": "CSE", "placements_count": 159},
    ]

    assert values_equal(expected, actual)


def test_cache_probe_submits_identical_rag_and_sql_requests(monkeypatch):
    import eval as eval_module

    requests = []

    def fake_post(api_url, question, timeout_seconds):
        requests.append((api_url, question, timeout_seconds))
        return {"timings_ms": {"total": 1}, "embedding_cache_hit": len(requests) == 2}

    monkeypatch.setattr(eval_module, "post_question", fake_post)
    probe = run_cache_probe("http://test", 10)

    assert len(requests) == 4
    assert requests[0][1] == requests[1][1]
    assert requests[2][1] == requests[3][1]
    assert probe["rag"]["cache_hits"] == [False, True]
