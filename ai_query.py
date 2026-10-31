from sqlalchemy import create_engine, text
from groq import Groq
import os
from db_config import get_database_url

client = Groq(
    api_key=os.environ.get("GROQ_API_KEY")
)

engine = create_engine(
    get_database_url()
)

question = input("Ask: ")

prompt = f"""
You are a PostgreSQL expert.

Table:

placements(
    student_id,
    student_name,
    branch,
    company,
    stipend,
    fte_package,
    month_placed
)

Return ONLY SQL.

Question:
{question}
"""

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {
            "role": "user",
            "content": prompt
        }
    ]
)

sql_query = response.choices[0].message.content.strip()
sql_query = sql_query.replace("```sql", "")
sql_query = sql_query.replace("```", "")
sql_query = sql_query.strip()

print("\nGenerated SQL:")
print(sql_query)

with engine.connect() as conn:
    result = conn.execute(text(sql_query))

    print("\nResult:")
    rows = result.fetchall()

print("\nAnswer:")
print(rows[0][0])