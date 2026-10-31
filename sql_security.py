from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

MAX_SQL_ROWS = 100
ALLOWED_TABLES = {"placements"}
ALLOWED_COLUMNS = {
    "student_id",
    "student_name",
    "branch",
    "company",
    "stipend",
    "fte_package",
    "month_placed",
}
ALLOWED_FUNCTIONS = {"AVG", "COUNT", "MAX", "MIN", "SUM"}
DANGEROUS_FUNCTIONS = {
    "COPY",
    "CURRENT_SETTING",
    "LO_IMPORT",
    "PG_ADVISORY_LOCK",
    "PG_CANCEL_BACKEND",
    "PG_READ_FILE",
    "PG_SLEEP",
    "PG_TERMINATE_BACKEND",
    "SET_CONFIG",
}


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str


class SQLValidationError(ValueError):
    pass


def validate_generated_sql(query: str) -> ValidatedQuery:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise SQLValidationError("empty SQL")
    if "--" in cleaned_query or "/*" in cleaned_query or "*/" in cleaned_query:
        raise SQLValidationError("SQL comments are not allowed")

    try:
        statements = sqlglot.parse(cleaned_query, read="postgres")
    except ParseError as error:
        raise SQLValidationError("malformed SQL") from error

    if len(statements) != 1:
        raise SQLValidationError("multiple SQL statements are not allowed")

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise SQLValidationError("only SELECT statements are allowed")
    if not statement.expressions:
        raise SQLValidationError("SELECT must include at least one expression")

    if statement.find(exp.Subquery):
        raise SQLValidationError("subqueries are not allowed")

    for table in statement.find_all(exp.Table):
        if table.catalog or table.db or table.name.lower() not in ALLOWED_TABLES:
            raise SQLValidationError("table is not allowlisted")

    for column in statement.find_all(exp.Column):
        if column.table and column.table.lower() not in ALLOWED_TABLES:
            raise SQLValidationError("column table is not allowlisted")
        if column.name != "*" and column.name.lower() not in ALLOWED_COLUMNS:
            raise SQLValidationError("column is not allowlisted")

    for function in statement.find_all(exp.Func):
        function_name = function.sql_name().upper()
        if function_name in DANGEROUS_FUNCTIONS or function_name not in ALLOWED_FUNCTIONS:
            raise SQLValidationError("function is not allowlisted")

    limit = statement.args.get("limit")
    if limit is not None:
        limit_expression = limit.expression
        if not isinstance(limit_expression, exp.Literal) or not limit_expression.is_int:
            raise SQLValidationError("LIMIT must be a positive integer")
        limit_value = int(limit_expression.this)
        if limit_value < 1:
            raise SQLValidationError("LIMIT must be a positive integer")
        if limit_value > MAX_SQL_ROWS:
            raise SQLValidationError("result size exceeds the maximum")
    else:
        statement = statement.limit(MAX_SQL_ROWS)

    return ValidatedQuery(sql=statement.sql(dialect="postgres"))
