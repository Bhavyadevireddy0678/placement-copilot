import pytest

from scripts.ai_query import execute_model_sql
from sql_security import SQLValidationError


class EngineThatMustNotConnect:
    def begin(self):
        raise AssertionError("Database access happened before SQL validation")


def test_auxiliary_sql_executor_validates_before_database_access():
    with pytest.raises(SQLValidationError):
        execute_model_sql("DROP TABLE placements", EngineThatMustNotConnect())
