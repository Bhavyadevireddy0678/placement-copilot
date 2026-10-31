import os

from dotenv import load_dotenv
from groq import Groq
from sqlalchemy import create_engine, text

from sql_security import validate_generated_sql


def validate_model_sql(query):
    return validate_generated_sql(query)


def execute_model_sql(query, engine):
    validated_query = validate_model_sql(query)
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL statement_timeout = 5000"))
        result = connection.execute(text(validated_query.sql))
        return list(result.keys()), result.fetchall(), validated_query.sql


def main():
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    database_url = os.getenv("SQL_READONLY_DB_URL")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    if not database_url:
        raise RuntimeError("SQL_READONLY_DB_URL is not set")

    question = input("Ask: ").strip()
    prompt = f"""
    You are a PostgreSQL expert. Return only one read-only SELECT query.
    Use only the placements table and these columns:
    placements(student_id, student_name, branch, company, stipend, fte_package, month_placed)

    Question:
    {question}
    """

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "user", "content": prompt}],
    )
    generated_sql = (response.choices[0].message.content or "").strip()
    generated_sql = generated_sql.removeprefix("```sql").removesuffix("```").strip()

    engine = create_engine(
        database_url,
        connect_args={"connect_timeout": 5},
        pool_pre_ping=True,
    )
    try:
        columns, rows, validated_sql = execute_model_sql(generated_sql, engine)
        print("Validated SQL:")
        print(validated_sql)
        print("Rows:")
        for row in rows:
            print(dict(zip(columns, row)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()