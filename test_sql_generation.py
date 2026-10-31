from types import SimpleNamespace

import pytest

from sql_generation import (
    SQL_EXAMPLES,
    build_sql_prompt,
    generate_validated_sql,
)
from sql_security import SQLValidationError


class FakeGroqClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        message = SimpleNamespace(content=output)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_prompt_contains_six_schema_grounded_examples_without_pii_projection():
    prompt = build_sql_prompt("average package by branch")

    assert len(SQL_EXAMPLES) == 6
    assert prompt.count("Question:") == 7
    assert "AVG(fte_package)" in prompt
    assert "student_name or student_id" in prompt
    assert "SELECT student_name" not in prompt


def test_generated_sql_retries_once_with_validator_rejection_feedback():
    client = FakeGroqClient(
        [
            "DROP TABLE placements",
            "```sql\nSELECT branch, AVG(fte_package) FROM placements GROUP BY branch\n```",
        ]
    )

    validated = generate_validated_sql(
        client,
        "test-model",
        build_sql_prompt("average package by branch"),
    )

    assert len(client.calls) == 2
    assert "only SELECT statements are allowed" in client.calls[1]["messages"][-1]["content"]
    assert "AVG" in validated.sql.upper()
    assert "LIMIT 100" in validated.sql.upper()


def test_generation_stops_after_one_rejected_retry():
    client = FakeGroqClient(["DELETE FROM placements", "TRUNCATE placements"])

    with pytest.raises(SQLValidationError):
        generate_validated_sql(client, "test-model", "prompt")

    assert len(client.calls) == 2
