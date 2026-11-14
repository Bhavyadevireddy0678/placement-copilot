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
        "SELECT student_name FROM placements;",
        "SELECT student_id FROM placements;",
        "SELECT * FROM placements;",
        "SELECT /* bypass */ company FROM placements;",
        "WITH x AS (SELECT company FROM placements) SELECT company FROM x;",
        "SELECT company FROM placements UNION SELECT company FROM placements;",
        "SELECT company FROM placements -- trailing comment",
        "SeLeCt STUDENT_NAME FROM placements;",
        "SELECT cοmpany FROM placements;",
        "SELECT pg_sleep(10) FROM placements;",
        "SELECT company FROM placements LIMIT 1000000000;",
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


def test_average_package_by_branch_is_allowed():
    validated = validate_generated_sql(
        "SELECT branch, AVG(fte_package) AS average_package "
        "FROM placements GROUP BY branch"
    )

    assert "AVG" in validated.sql.upper()
    assert "BRANCH" in validated.sql.upper()
    assert "LIMIT 100" in validated.sql.upper()


def test_pii_columns_can_only_be_enabled_explicitly():
    with pytest.raises(SQLValidationError):
        validate_generated_sql("SELECT student_name FROM placements")

    validated = validate_generated_sql(
        "SELECT student_name FROM placements", allow_pii=True
    )
    assert "STUDENT_NAME" in validated.sql.upper()
