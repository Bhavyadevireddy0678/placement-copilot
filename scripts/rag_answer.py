from sentence_transformers import SentenceTransformer
from pgvector.psycopg2 import register_vector
from groq import Groq
import psycopg2
import os
from dotenv import load_dotenv
from db_config import get_database_url

load_dotenv()

# Embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Groq client
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("GROQ_API_KEY is not set")

MODEL_NAME = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
client = Groq(api_key=api_key)

# User question
query = input("Ask: ")

# Convert question to embedding
query_embedding = model.encode(query)

# Connect to PostgreSQL
conn = psycopg2.connect(get_database_url(), connect_timeout=5)

register_vector(conn)

cur = conn.cursor()

# Retrieve top matching chunk
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

print("\nRetrieved Context:")
print(context)

# RAG prompt
prompt = f"""
Answer the question using only the context below.

Context:
{context}

Question:
{query}
"""

response = client.chat.completions.create(
    model=MODEL_NAME,
    messages=[
        {
            "role": "user",
            "content": prompt
        }
    ]
)

print("\nAnswer:")
print(response.choices[0].message.content)

cur.close()
conn.close()