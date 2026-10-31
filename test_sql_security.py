import pytest

from sql_security import SQLValidationError, validate_generated_sql


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE placements;",
        "DELETE FROM placements;",
        "UPDATE placements SET company = 'x';",
        "INSERT INTO placements (company) VALUES ('x');",
        "ALTER TABLE placements ADD COLUMN unsafe text;",
        "TRUNCATE placements;",
        "SELECT company FROM placements; DROP TABLE placements;",
        "SELECT * FROM pg_catalog.pg_tables;",
        "SELECT pg_sleep(10);",
        "SELECT unknown_column FROM placements;",
        "SELECT * FROM unknown_table;",
        "SELECT company FROM placements LIMIT 101;",
        "SELECT company FROM placements LIMIT 0;",
        "SELECT /* bypass */ company FROM placements;",
    ],
)
def test_unsafe_queries_are_rejected_before_execution(query):
    with pytest.raises(SQLValidationError):
        validate_generated_sql(query)


def test_valid_select_is_allowed_and_bounded():
    validated = validate_generated_sql(
        "SELECT company, COUNT(*) AS total FROM placements GROUP BY company"
    )

    assert validated.sql.upper().startswith("SELECT")
    assert "LIMIT 100" in validated.sql.upper()


def test_empty_and_malformed_queries_are_rejected():
    for query in ("", "SELECT FROM placements"):
        with pytest.raises(SQLValidationError):
            validate_generated_sql(query)


def test_select_star_is_allowed_for_the_application_table():
    validated = validate_generated_sql("SELECT * FROM placements LIMIT 10")

    assert "LIMIT 10" in validated.sql.upper()
