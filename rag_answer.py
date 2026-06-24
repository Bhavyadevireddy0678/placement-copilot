from sentence_transformers import SentenceTransformer
from pgvector.psycopg2 import register_vector
from groq import Groq
import psycopg2
import os

# Embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Groq client
client = Groq(
    api_key=os.environ.get("GROQ_API_KEY")
)
# User question
query = input("Ask: ")

# Convert question to embedding
query_embedding = model.encode(query)

# Connect to PostgreSQL
conn = psycopg2.connect(
    dbname="placement_rag",
    user="raguser",
    password="ragpass",
    host="localhost",
    port="5432"
)

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
    model="llama-3.3-70b-versatile",
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