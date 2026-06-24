from sentence_transformers import SentenceTransformer
import psycopg2
from pgvector.psycopg2 import register_vector

model = SentenceTransformer("all-MiniLM-L6-v2")

query = input("Ask: ")

query_embedding = model.encode(query)

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
    LIMIT 3
    """,
    (query_embedding,)
)

results = cur.fetchall()

for row in results:
    print("\nDocument:")
    print(row[0])
    print("Distance:", row[1])

cur.close()
conn.close()