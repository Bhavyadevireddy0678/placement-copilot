from fastapi import FastAPI
from groq import Groq
from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer
from pgvector.psycopg2 import register_vector
import psycopg2
import os

app = FastAPI()

model = SentenceTransformer("all-MiniLM-L6-v2")


# Groq Client
client = Groq(
    api_key=os.environ.get("GROQ_API_KEY")
)

# PostgreSQL Connection
engine = create_engine(
    "postgresql://raguser:ragpass@localhost:5432/placement_rag"
)

def classify_intent(question):
    sql_keywords = [
        "how many",
        "count",
        "average",
        "avg",
        "highest",
        "lowest",
        "maximum",
        "minimum",
        "top recruiter",
        "total",
        "package",
        "salary"
    ]

    question = question.lower()

    for keyword in sql_keywords:
        if keyword in question:
            return "sql"

    return "rag"


@app.get("/")
def home():
    return {"message": "Placement Copilot API Running"}


@app.get("/ask")
def ask(question: str):

    intent = classify_intent(question)

    if intent == "sql":

        prompt = f"""
        You are a PostgreSQL expert.

        Table schema:

        placements(
            student_id,
            student_name,
            branch,
            company,
            stipend,
            fte_package,
            month_placed
        )

        Return ONLY valid PostgreSQL SQL.

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

        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = result.fetchall()

        return {
            "intent": "sql",
            "question": question,
            "generated_sql": sql_query,
            "answer": rows[0][0]
        }

    query_embedding = model.encode(question)

    conn = psycopg2.connect(
        dbname="placement_rag",
        user="raguser",
        password="ragpass",
        host="localhost",
        port="5432"
    )

    register_vector(conn)

    cur = conn.cursor()

    cur.execute(
        """
        SELECT content,
               embedding <=> %s AS distance
        FROM chunks
        ORDER BY distance
        LIMIT 1
        """,
        (query_embedding,)
    )

    result = cur.fetchone()

    context = result[0]

    rag_prompt = f"""
    Answer the question using only the context below.

    Context:
    {context}

    Question:
    {question}
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": rag_prompt
            }
        ]
    )

    answer = response.choices[0].message.content

    cur.close()
    conn.close()

    return {
        "intent": "rag",
        "question": question,
        "retrieved_context": context,
        "answer": answer
    }